"""Module développeur : mode dev et données factices pour la galerie de widgets."""

from __future__ import annotations

import os

from ankiforge.dev.fake_data import make_fake_collection
from ankiforge.dev.fake_services import (
    FakeDeckRepository,
    FakeDocumentRepository,
    FakeLLMProvider,
    FakeNoteRepository,
)
from ankiforge.utils.environment import AppEnvironment, get_current_environment


def is_dev_mode() -> bool:
    """Indique si l'application tourne en mode développeur.

    Le mode développeur est activé via ``--dev`` ou ``ANKIFORGE_ENV=development``.
    """
    try:
        return get_current_environment() == AppEnvironment.DEVELOPMENT
    except Exception:
        env_var = os.environ.get("ANKIFORGE_ENV", "").strip().lower()
        return env_var in ("dev", "development")


__all__ = [
    "is_dev_mode",
    "make_fake_collection",
    "FakeLLMProvider",
    "FakeDeckRepository",
    "FakeDocumentRepository",
    "FakeNoteRepository",
]
