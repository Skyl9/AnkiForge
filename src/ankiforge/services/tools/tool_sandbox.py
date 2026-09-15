"""Exécution confinée des scripts Python personnalisés des outils DAG (sandbox défensive).

Les scripts d'outils sont du code Python arbitraire exécuté sur la machine de l'utilisateur.
Un sandboxing Python pur ne peut jamais garantir une isolation totale (le langage est
Turing-complet et permet la réflexion sur les classes), aussi cette couche applique-t-elle
les meilleures pratiques défensives applicables à une application desktop locale :

1. Restriction des ``__builtins__`` : retrait de ``__import__``, ``open``, ``eval``,
   ``exec``, ``compile``, ``globals``, ``locals``, ``input``, ... (pas d'import, pas d'I/O
   fichier direct, pas d'évaluation dynamique).
2. Timeout d'exécution strict pour empêcher les boucles infinies ou scripts trop lourds.
3. Exécution dans un thread ``daemon`` pour ne jamais bloquer la sortie du processus.

Menace modélisée : un script d'outil défectueux ou malveillant (par ex. fourni par un
tiers) ne doit pas pouvoir bloquer l'application ou accéder accidentellement au
système de fichiers. L'exécution reste volontaire et est réalisée sous l'identité de
l'utilisateur lui-même — la restriction anti-escalade complète (sous-processus réduit,
OS sandbox) est hors périmètre d'une application desktop.
"""

from __future__ import annotations

import builtins
import datetime
import json
import logging
import queue
import re
import threading
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TOOL_TIMEOUT_SECONDS = 10.0

_NAME = "<custom_tool>"

# Sous-ensemble sûr des builtins Python pour l'exécution des outils :
# pas d'import, pas d'I/O, pas d'accès à l'interpréteur ou au scope global.
_SAFE_BUILTINS: dict[str, Any] = {
    name: getattr(builtins, name)
    for name in (
        "abs",
        "all",
        "any",
        "ascii",
        "bin",
        "bool",
        "bytearray",
        "bytes",
        "callable",
        "chr",
        "complex",
        "dict",
        "divmod",
        "enumerate",
        "filter",
        "float",
        "format",
        "frozenset",
        "getattr",
        "hasattr",
        "hash",
        "hex",
        "id",
        "int",
        "isinstance",
        "issubclass",
        "iter",
        "len",
        "list",
        "map",
        "max",
        "min",
        "next",
        "oct",
        "ord",
        "pow",
        "range",
        "repr",
        "reversed",
        "round",
        "set",
        "setattr",
        "slice",
        "sorted",
        "str",
        "sum",
        "tuple",
        "type",
        "vars",
        "zip",
    )
    if name
    not in (
        # Interdits : accès à l'interpréteur, aux imports, à l'I/O et au scope.
        "__import__",
        "open",
        "eval",
        "exec",
        "compile",
        "globals",
        "locals",
        "input",
        "exit",
        "quit",
        "breakpoint",
        "memoryview",
    )
}


def _extract_run_fn(global_scope: dict[str, Any], local_scope: dict[str, Any]) -> Any:
    """Retourne la fonction 'run' définie par le script (local d'abord, puis global)."""
    run_fn = local_scope.get("run") or global_scope.get("run")
    if not callable(run_fn):
        raise ValueError("Le script de l'outil doit définir une fonction 'def run(state):'.")
    return run_fn


def _exec_and_run(
    code: str,
    state: Any,
    global_scope: dict[str, Any],
    local_scope: dict[str, Any],
    result_queue: queue.SimpleQueue[tuple[str, Any]],
) -> None:
    """Exécute le script puis la fonction 'run(state)' dans le thread sandbox."""
    try:
        # exec volontaire du code d'un outil utilisateur dans une sandbox restreinte
        # (builtins réduits + timeout) — voir docstring du module.
        exec(code, global_scope, local_scope)  # nosec B102
        run_fn = _extract_run_fn(global_scope, local_scope)
        result_queue.put(("ok", run_fn(state)))
    except BaseException as exc:
        result_queue.put(("error", exc))


def run_python_tool(
    code: str,
    state: Any,
    args: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TOOL_TIMEOUT_SECONDS,
    *,
    log_name: str = "custom_tool",
) -> Any:
    """Exécute un script d'outil Python dans un environnement restreint avec timeout.

    Args:
        code: Source Python du script (doit définir ``def run(state):``).
        state: État pipeline injecté sous le nom ``state``.
        args: Arguments optionnels injectés sous le nom ``args``.
        timeout: Délai maximal d'exécution en secondes (<= 0 : illimité).
        log_name: Nom du logger injecté sous le nom ``logger``.

    Returns:
        La valeur renvoyée par ``run(state)``.

    Raises:
        TimeoutError: si le script dépasse le délai imparti.
        ValueError: si le script ne définit pas de fonction ``run``.
        L'exception propagée par le script lui-même sinon.
    """
    compile(code, _NAME, "exec")

    safe_builtins: dict[str, Any] = dict(_SAFE_BUILTINS)
    local_scope: dict[str, Any] = {}
    global_scope: dict[str, Any] = {
        "__builtins__": safe_builtins,
        "state": state,
        "args": args or {},
        "json": json,
        "re": re,
        "datetime": datetime,
        "logging": logging,
        "logger": logging.getLogger(log_name),
    }

    result_queue: queue.SimpleQueue[tuple[str, Any]] = queue.SimpleQueue()
    worker = threading.Thread(
        target=_exec_and_run,
        args=(code, state, global_scope, local_scope, result_queue),
        name=f"tool-sandbox-{log_name}",
        daemon=True,
    )
    worker.start()

    if timeout and timeout > 0:
        worker.join(timeout=timeout)
        if worker.is_alive():
            raise TimeoutError(f"Le script de l'outil a dépassé le délai maximal de {timeout:g}s et a été interrompu.")
    else:
        worker.join()

    kind, payload = result_queue.get()
    if kind == "error":
        raise payload
    return payload
