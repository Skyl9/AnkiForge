#!/usr/bin/env python3
"""Porte de vérification canonique unique d'AnkiForge (Verification Gate).

Enchaîne de manière déterministe et ordonnée l'ensemble des contrôles de qualité,
typage, sécurité et tests pré-push du projet :
1. ruff check .                (Linting et règles PEP8 / T20 no print)
2. ruff format --check .       (Formatage uniforme)
3. mypy src/ankiforge          (Typage statique strict 100%)
4. bandit -c pyproject.toml -r src/ (Audit sécurité statique)
5. pytest -m "not slow"        (Tests unitaires et headless rapides < 15s)

Utilisation :
    uv run python script/verify.py             # Exécution standard fail-fast
    uv run python script/verify.py --fix       # Auto-format & fix ruff avant vérification
    uv run python script/verify.py --all-tests # Exécute tous les tests (sans filtre slow)
    uv run python script/verify.py --install-hook # Installe et active le hook git pre-push
    uv run python script/verify.py --step mypy # Exécute uniquement l'étape mypy
    uv run python script/verify.py --skip bandit # Exécute toutes les étapes sauf bandit
    uv run python script/verify.py --dry-run   # Affiche le plan d'exécution sans rien lancer
    uv run python script/verify.py --check-hook # Vérifie que le hook pre-push est actif
"""

from __future__ import annotations

import argparse
import logging
import os
import platform
import shutil
import signal
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("ankiforge.verify")

REPO_ROOT = Path(__file__).resolve().parent.parent
GITHOOKS_DIR = REPO_ROOT / ".githooks"
GITHOOKS_PRE_PUSH = GITHOOKS_DIR / "pre-push"
GIT_DIR = REPO_ROOT / ".git"
GIT_HOOKS_DIR = GIT_DIR / "hooks"

# Délai de grâce (secondes) entre SIGTERM et SIGKILL lors d'un arrêt forcé.
_KILL_GRACE_PERIOD = 2.0

# Table de correspondance des signaux POSIX courants pour le diagnostic.
_SIGNAL_NAMES: dict[int, str] = {
    1: "SIGHUP",
    2: "SIGINT",
    4: "SIGILL",
    6: "SIGABRT",
    8: "SIGFPE",
    9: "SIGKILL",
    11: "SIGSEGV",
    13: "SIGPIPE",
    14: "SIGALRM",
    15: "SIGTERM",
}


@dataclass(frozen=True)
class VerificationStep:
    """Représentation immuable d'une étape de vérification."""

    name: str
    command: list[str]
    description: str = ""
    timeout: float | None = None


@dataclass
class StepResult:
    """Résultat de l'exécution d'une étape de vérification."""

    name: str
    status: str  # "OK", "ÉCHEC", "TIMEOUT", "IGNORÉ", "CRASH"
    duration: float = 0.0
    timeout_limit: float | None = None
    return_code: int | None = None
    signal_name: str | None = None


CANONICAL_STEPS: list[VerificationStep] = [
    VerificationStep(
        name="ruff-check",
        command=["ruff", "check", "."],
        description="Linting et conformité des règles de code (Ruff)",
        timeout=30.0,
    ),
    VerificationStep(
        name="ruff-format",
        command=["ruff", "format", "--check", "."],
        description="Vérification du formatage uniforme du code (Ruff)",
        timeout=30.0,
    ),
    VerificationStep(
        name="mypy",
        command=["mypy", "src/ankiforge"],
        description="Typage statique strict 100% (Mypy)",
        timeout=120.0,
    ),
    VerificationStep(
        name="bandit",
        command=["bandit", "-c", "pyproject.toml", "-r", "src/"],
        description="Audit de sécurité et scan de vulnérabilités (Bandit)",
        timeout=45.0,
    ),
    VerificationStep(
        name="pytest-fast",
        command=["pytest", "-m", "not slow", "--max-worker-restart=0"],
        description="Suite de tests rapides non-slow (< 15s) (Pytest)",
        timeout=120.0,
    ),
]


def is_bypass_requested(args_bypass: bool = False) -> bool:
    """Détermine si un contournement explicite est demandé via argument ou variable d'environnement."""
    if args_bypass:
        return True
    bypass_env_keys = (
        "ANKIFORGE_BYPASS_VERIFY",
        "ANKIFORGE_SKIP_VERIFY",
        "ANKIFORGE_BYPASS_PRE_PUSH",
    )
    for key in bypass_env_keys:
        val = os.environ.get(key, "").strip().lower()
        if val in ("1", "true", "yes"):
            return True
    return False


def build_full_command(cmd: list[str]) -> list[str]:
    """Construit la commande finale avec le préfixe de runtime adapté (uv run ou sys.executable)."""
    if shutil.which("uv"):
        return ["uv", "run", *cmd]
    return [sys.executable, "-m", *cmd]


def get_step_environment() -> dict[str, str]:
    """Construit l'environnement enrichi et durci pour l'exécution des sous-processus."""
    env = dict(os.environ)
    env.setdefault("PYTHONFAULTHANDLER", "1")
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    env.setdefault("ANKIFORGE_MOCK_WEBENGINE", "1")
    return env


def decode_return_code(returncode: int) -> str:
    """Décode un code de retour en une description humaine, incluant les signaux POSIX."""
    if returncode >= 0:
        return f"code {returncode}"

    # Code négatif sous POSIX = tué par un signal
    sig_num = abs(returncode)
    sig_name = _SIGNAL_NAMES.get(sig_num, f"signal {sig_num}")
    return f"tué par {sig_name} ({sig_num})"


def kill_process_tree(proc: subprocess.Popen[str]) -> None:
    """Termine proprement l'arbre de processus complet via SIGTERM puis SIGKILL.

    Sous POSIX, utilise le group ID du processus pour atteindre tous les descendants.
    Sous Windows, utilise ``taskkill /F /T`` pour la terminaison récursive de l'arbre.
    """
    if platform.system() == "Windows":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        except FileNotFoundError:
            proc.kill()
        return

    # POSIX : terminaison par groupe de processus
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return

    # Étape 1 : SIGTERM (terminaison gracieuse)
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return

    # Étape 2 : Attente de grâce
    try:
        proc.wait(timeout=_KILL_GRACE_PERIOD)
        return  # Processus terminé proprement
    except subprocess.TimeoutExpired:
        pass

    # Étape 3 : SIGKILL (terminaison forcée)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    # Attente finale pour récolter le zombie
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        pass


def run_single_step(
    step: VerificationStep,
    cwd: Path = REPO_ROOT,
    quiet: bool = False,
    timeout_override: float | None = None,
) -> StepResult:
    """Exécute une étape de vérification unitaire avec isolation de processus et timeout."""
    full_cmd = build_full_command(step.command)
    effective_timeout = timeout_override if timeout_override is not None else step.timeout

    if not quiet:
        timeout_info = f" (timeout: {effective_timeout:.0f}s)" if effective_timeout else ""
        print(f"▶ [{step.name}] Exécution : {' '.join(full_cmd)}{timeout_info}")

    env = get_step_environment()
    start_time = time.perf_counter()

    # Lancement avec session de processus séparée pour isolation de l'arbre de processus
    popen_kwargs: dict[str, object] = {
        "cwd": cwd,
        "text": True,
        "env": env,
    }
    if platform.system() != "Windows":
        popen_kwargs["start_new_session"] = True
    else:
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

    proc = subprocess.Popen(full_cmd, **popen_kwargs)  # type: ignore[call-overload]

    try:
        proc.wait(timeout=effective_timeout)
    except subprocess.TimeoutExpired:
        duration = time.perf_counter() - start_time
        print(
            f"⏱️  [{step.name}] TIMEOUT après {duration:.1f}s (limite : {effective_timeout}s) — arrêt de l'arbre de processus...",
            file=sys.stderr,
        )
        kill_process_tree(proc)
        logger.error(
            "Étape %s : timeout après %.1fs (limite : %ss). Cause probable : worker pytest bloqué, boucle d'événements Qt non fermée, ou thread non-démon en attente.",
            step.name,
            duration,
            effective_timeout,
        )
        return StepResult(
            name=step.name,
            status="TIMEOUT",
            duration=duration,
            timeout_limit=effective_timeout,
            return_code=None,
        )
    except KeyboardInterrupt:
        duration = time.perf_counter() - start_time
        print(f"\n⚡ [{step.name}] Interruption utilisateur — arrêt de l'arbre de processus...", file=sys.stderr)
        kill_process_tree(proc)
        raise

    duration = time.perf_counter() - start_time
    returncode = proc.returncode

    # Détection de crash par signal (code négatif sous POSIX)
    if returncode is not None and returncode < 0:
        sig_num = abs(returncode)
        sig_name = _SIGNAL_NAMES.get(sig_num, f"signal {sig_num}")
        print(
            f"💥 [{step.name}] CRASH : processus tué par {sig_name} (code {returncode}, {duration:.2f}s)",
            file=sys.stderr,
        )
        logger.error(
            "Étape %s : crash par %s (code %d, durée : %.2fs)",
            step.name,
            sig_name,
            returncode,
            duration,
        )
        return StepResult(
            name=step.name,
            status="CRASH",
            duration=duration,
            timeout_limit=effective_timeout,
            return_code=returncode,
            signal_name=sig_name,
        )

    if returncode == 0:
        if not quiet:
            print(f"✅ [{step.name}] OK ({duration:.2f}s)\n")
        return StepResult(
            name=step.name,
            status="OK",
            duration=duration,
            timeout_limit=effective_timeout,
            return_code=0,
        )

    print(f"❌ [{step.name}] Échec ({decode_return_code(returncode)}, {duration:.2f}s)\n", file=sys.stderr)
    logger.error(
        "Étape %s échouée avec le %s (durée : %.2fs)",
        step.name,
        decode_return_code(returncode),
        duration,
    )
    return StepResult(
        name=step.name,
        status="ÉCHEC",
        duration=duration,
        timeout_limit=effective_timeout,
        return_code=returncode,
    )


def apply_auto_fix(cwd: Path = REPO_ROOT, quiet: bool = False) -> int:
    """Applique les corrections automatiques Ruff lint et format."""
    if not quiet:
        print("🛠️  Application automatique des corrections Ruff (lint --fix + format)...")

    cmd_lint_fix = build_full_command(["ruff", "check", "--fix", "."])
    res_lint = subprocess.run(cmd_lint_fix, cwd=cwd, check=False)
    if res_lint.returncode != 0:
        return res_lint.returncode

    cmd_format = build_full_command(["ruff", "format", "."])
    res_fmt = subprocess.run(cmd_format, cwd=cwd, check=False)
    return res_fmt.returncode


def install_git_pre_push_hook(quiet: bool = False) -> int:
    """Installe et active le hook pre-push versionné dans le dépôt git."""
    if not GIT_DIR.exists():
        print("⚠️  Aucun répertoire .git trouvé à la racine. Hook non installé.", file=sys.stderr)
        return 1

    GITHOOKS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Rendre .githooks/pre-push exécutable
    if GITHOOKS_PRE_PUSH.is_file():
        mode = os.stat(GITHOOKS_PRE_PUSH).st_mode
        os.chmod(GITHOOKS_PRE_PUSH, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # 2. Configurer core.hooksPath = .githooks
    proc = subprocess.run(
        ["git", "config", "core.hooksPath", ".githooks"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(f"❌ Impossible de définir core.hooksPath : {proc.stderr}", file=sys.stderr)
        return proc.returncode

    # 3. Synchroniser également .git/hooks/pre-push par précaution
    if GIT_HOOKS_DIR.is_dir():
        local_pre_push = GIT_HOOKS_DIR / "pre-push"
        wrapper_content = '#!/usr/bin/env bash\nHOOK_DIR="$(cd "$(dirname "$0")/../../.githooks" && pwd)"\nif [ -x "$HOOK_DIR/pre-push" ]; then\n    exec "$HOOK_DIR/pre-push" "$@"\nfi\nexit 0\n'
        local_pre_push.write_text(wrapper_content, encoding="utf-8")
        mode = os.stat(local_pre_push).st_mode
        os.chmod(local_pre_push, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    if not quiet:
        print("✅ Hook pre-push versionné configuré avec succès :")
        print("   - .githooks/pre-push actif via git config core.hooksPath .githooks")
        print("   - .git/hooks/pre-push synchronisé en délégation")

    return 0


def check_git_hook_status(quiet: bool = False) -> int:
    """Vérifie que le hook pre-push est correctement installé et actif."""
    issues: list[str] = []

    # 1. Vérifier que .githooks/pre-push existe
    if not GITHOOKS_PRE_PUSH.is_file():
        issues.append("Fichier .githooks/pre-push introuvable")
    elif sys.platform != "win32":
        mode = os.stat(GITHOOKS_PRE_PUSH).st_mode
        if not (mode & stat.S_IXUSR):
            issues.append(".githooks/pre-push n'est pas exécutable")

    # 2. Vérifier core.hooksPath
    if GIT_DIR.exists():
        proc = subprocess.run(
            ["git", "config", "--get", "core.hooksPath"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        hooks_path = proc.stdout.strip()
        if hooks_path != ".githooks":
            issues.append(f"core.hooksPath = '{hooks_path}' (attendu : '.githooks')")
    else:
        issues.append("Aucun répertoire .git trouvé")

    if issues:
        if not quiet:
            print("❌ Hook pre-push non conforme :")
            for issue in issues:
                print(f"   - {issue}")
            print("💡 Correction : uv run python script/verify.py --install-hook")
        return 1

    if not quiet:
        print("✅ Hook pre-push correctement installé et actif.")
    return 0


def filter_steps(
    steps: list[VerificationStep],
    only: list[str] | None = None,
    skip: list[str] | None = None,
) -> list[VerificationStep]:
    """Filtre les étapes selon les listes d'inclusion et d'exclusion."""
    filtered = steps

    if only:
        known_names = {s.name for s in steps}
        for name in only:
            if name not in known_names:
                print(f"⚠️  Étape inconnue ignorée : '{name}' (disponibles : {', '.join(sorted(known_names))})", file=sys.stderr)
        filtered = [s for s in filtered if s.name in only]

    if skip:
        filtered = [s for s in filtered if s.name not in skip]

    return filtered


def print_summary_table(results: list[StepResult], total_duration: float) -> None:
    """Affiche un tableau récapitulatif formaté des résultats d'exécution."""
    # Calcul des largeurs de colonnes
    name_width = max(len(r.name) for r in results) if results else 10
    name_width = max(name_width, 8)  # minimum "Étape"

    status_symbols = {
        "OK": "✅ OK",
        "ÉCHEC": "❌ ÉCHEC",
        "TIMEOUT": "⏱️  TIMEOUT",
        "CRASH": "💥 CRASH",
        "IGNORÉ": "⏭️  IGNORÉ",
    }

    print("\n" + "=" * 65)
    print("📊 Récapitulatif des vérifications")
    print("=" * 65)
    print(f"  {'Étape':<{name_width}}  {'Statut':<14}  {'Durée':>8}  {'Limite':>8}  {'Code':>8}")
    print(f"  {'─' * name_width}  {'─' * 14}  {'─' * 8}  {'─' * 8}  {'─' * 8}")

    for r in results:
        status_display = status_symbols.get(r.status, r.status)
        duration_display = f"{r.duration:.2f}s" if r.duration > 0 else "—"
        timeout_display = f"{r.timeout_limit:.0f}s" if r.timeout_limit else "—"

        if r.signal_name:
            code_display = r.signal_name
        elif r.return_code is not None:
            code_display = str(r.return_code)
        else:
            code_display = "—"

        print(f"  {r.name:<{name_width}}  {status_display:<14}  {duration_display:>8}  {timeout_display:>8}  {code_display:>8}")

    print(f"  {'─' * name_width}  {'─' * 14}  {'─' * 8}  {'─' * 8}  {'─' * 8}")
    passed = sum(1 for r in results if r.status == "OK")
    total = len(results)
    print(f"  Total : {passed}/{total} réussi(s) en {total_duration:.2f}s")
    print("=" * 65)


def print_dry_run(steps: list[VerificationStep]) -> None:
    """Affiche le plan d'exécution sans rien lancer."""
    print("=" * 65)
    print("🔍 Mode simulation (dry-run) — aucune commande ne sera exécutée")
    print(f"📋 {len(steps)} étape(s) prévue(s)")
    print("=" * 65)

    for idx, step in enumerate(steps, start=1):
        full_cmd = build_full_command(step.command)
        timeout_info = f"{step.timeout:.0f}s" if step.timeout else "aucun"
        print(f"\n  [{idx}/{len(steps)}] {step.name}")
        print(f"    Description : {step.description}")
        print(f"    Commande    : {' '.join(full_cmd)}")
        print(f"    Timeout     : {timeout_info}")

    print("\n" + "=" * 65)


def run_verification(
    steps: list[VerificationStep] | None = None,
    fail_fast: bool = True,
    bypass: bool = False,
    quiet: bool = False,
    all_tests: bool = False,
    fix: bool = False,
    only: list[str] | None = None,
    skip: list[str] | None = None,
    timeout_override: float | None = None,
    pytest_timeout: float | None = None,
    dry_run: bool = False,
) -> int:
    """Exécute l'ensemble de la chaîne de vérification canonique."""
    if is_bypass_requested(args_bypass=bypass):
        msg = "⚠️  [WARNING] Porte de vérification canonique contournée explicitement. Aucun contrôle n'a été exécuté !"
        print(msg, file=sys.stderr)
        logger.warning("Porte de vérification AnkiForge contournée explicitement (bypass).")
        return 0

    if fix:
        fix_code = apply_auto_fix(quiet=quiet)
        if fix_code != 0 and fail_fast:
            return fix_code

    active_steps = list(steps if steps is not None else CANONICAL_STEPS)

    if all_tests:
        active_steps = [
            (
                VerificationStep(
                    name="pytest-all",
                    command=["pytest", "--max-worker-restart=0"],
                    description="Suite complète de tests (Pytest)",
                    timeout=step.timeout if step.timeout else 360.0,
                )
                if step.name == "pytest-fast"
                else step
            )
            for step in active_steps
        ]

    # Appliquer le filtrage par étape
    active_steps = filter_steps(active_steps, only=only, skip=skip)

    if not active_steps:
        print("⚠️  Aucune étape à exécuter après filtrage.", file=sys.stderr)
        return 0

    # Mode simulation
    if dry_run:
        print_dry_run(active_steps)
        return 0

    total_start = time.perf_counter()
    if not quiet:
        print("=" * 65)
        print("🛡️  Porte de Vérification Canonique AnkiForge (Pre-Push Gate)")
        print(f"📋 {len(active_steps)} contrôle(s) programmé(s) | Mode fail-fast : {fail_fast}")
        print("=" * 65)

    results: list[StepResult] = []

    for idx, step in enumerate(active_steps, start=1):
        if not quiet:
            print(f"[{idx}/{len(active_steps)}] {step.description} ({step.name})")

        # Déterminer le timeout effectif pour cette étape
        step_timeout = timeout_override
        if step_timeout is None and pytest_timeout is not None and step.name.startswith("pytest"):
            step_timeout = pytest_timeout

        result = run_single_step(step, quiet=quiet, timeout_override=step_timeout)
        results.append(result)

        if result.status != "OK" and fail_fast:
            total_duration = time.perf_counter() - total_start
            if not quiet:
                print("=" * 65)
                print(f"❌ Arrêt immédiat (fail-fast) sur l'étape '{result.name}' ({result.status}).")
                print("💡 Pour auto-corriger le formatage : uv run python script/verify.py --fix")
                print_summary_table(results, total_duration)
            return result.return_code if result.return_code is not None else 1

    total_duration = time.perf_counter() - total_start

    failed_results = [r for r in results if r.status != "OK"]
    if failed_results:
        if not quiet:
            print_summary_table(results, total_duration)
        return failed_results[0].return_code if failed_results[0].return_code is not None else 1

    if not quiet:
        print_summary_table(results, total_duration)

    return 0


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée CLI pour la commande canonique de vérification."""
    parser = argparse.ArgumentParser(
        description="Porte de vérification canonique unique et pre-push gate pour AnkiForge.",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Applique automatiquement le linting fix et formatage Ruff avant de vérifier.",
    )
    parser.add_argument(
        "--all-tests",
        "--full",
        dest="all_tests",
        action="store_true",
        help="Exécute l'intégralité des tests pytest (sans exclure le marqueur slow).",
    )
    parser.add_argument(
        "--no-fail-fast",
        "--keep-going",
        dest="no_fail_fast",
        action="store_true",
        help="Continue d'exécuter les étapes restantes même en cas d'échec intermédiaire.",
    )
    parser.add_argument(
        "--bypass",
        "--skip",
        dest="bypass",
        action="store_true",
        help="Contourne explicitement la vérification (journalise un warning).",
    )
    parser.add_argument(
        "--install-hook",
        action="store_true",
        help="Installe et active le hook pre-push versionné dans git.",
    )
    parser.add_argument(
        "--check-hook",
        action="store_true",
        help="Vérifie que le hook pre-push est correctement installé et actif.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Supprime les affichages d'étape non essentiels.",
    )
    parser.add_argument(
        "--step",
        "--only",
        dest="only_steps",
        action="append",
        metavar="NOM",
        help="Exécute uniquement la ou les étapes spécifiées (répétable).",
    )
    parser.add_argument(
        "--skip-step",
        "--exclude",
        dest="skip_steps",
        action="append",
        metavar="NOM",
        help="Exclut la ou les étapes spécifiées de l'exécution (répétable).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SEC",
        help="Surcharge le timeout (en secondes) pour toutes les étapes.",
    )
    parser.add_argument(
        "--pytest-timeout",
        type=float,
        default=None,
        metavar="SEC",
        help="Surcharge le timeout (en secondes) pour les étapes pytest uniquement.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche le plan d'exécution sans lancer aucune commande.",
    )

    args = parser.parse_args(argv)

    if args.install_hook:
        return install_git_pre_push_hook(quiet=args.quiet)

    if args.check_hook:
        return check_git_hook_status(quiet=args.quiet)

    return run_verification(
        fail_fast=not args.no_fail_fast,
        bypass=args.bypass,
        quiet=args.quiet,
        all_tests=args.all_tests,
        fix=args.fix,
        only=args.only_steps,
        skip=args.skip_steps,
        timeout_override=args.timeout,
        pytest_timeout=args.pytest_timeout,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
