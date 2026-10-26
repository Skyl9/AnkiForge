"""Familles de widgets exposées dans la galerie du mode développeur.

Chaque module de ce paquet porte une famille (`dialogs`, `components`, `widgets`,
`views`, ...) et expose une fonction ``register()`` idempotente qui enregistre ses
entrées dans le registre déclaratif. L'ajout d'une famille se limite donc à déposer
un module ici : le chargement est découvert automatiquement.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import re

logger = logging.getLogger(__name__)

_MODULE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def family_names() -> list[str]:
    """Noms des modules de familles disponibles, triés pour un rendu déterministe."""
    names = [info.name for info in pkgutil.iter_modules(__path__) if _MODULE_NAME_PATTERN.match(info.name)]
    return sorted(names)


def load_families() -> list[str]:
    """Importe chaque famille et exécute son ``register()``.

    Le chargement est tolérant aux pannes : une famille qui échoue est journalisée
    puis ignorée, afin qu'une régression isolée ne rende jamais la galerie inouvrable.
    """
    loaded: list[str] = []
    for name in family_names():
        try:
            module = importlib.import_module(f"{__name__}.{name}")
        except Exception:
            logger.exception("Échec du chargement de la famille de galerie « %s »", name)
            continue

        register = getattr(module, "register", None)
        if not callable(register):
            logger.warning("La famille de galerie « %s » n'expose pas de fonction register()", name)
            continue

        try:
            register()
        except Exception:
            logger.exception("Échec de l'enregistrement de la famille de galerie « %s »", name)
            continue

        loaded.append(name)
    return loaded
