"""Classe de base des dépôts : transactions atomiques et primitives de requêtage sûres."""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from peewee import Database

from ankiforge.database.base import db as default_db

logger = logging.getLogger(__name__)


class BaseRepository:
    """Classe de base de tous les dépôts d'accès aux données Peewee.

    Encapsule les transactions atomiques et la connaissance de la connexion à la base de données.
    """

    def __init__(self, database: Database | None = None) -> None:
        self._db = database or default_db

    @property
    def db(self) -> Database:
        """Retourne la base de données associée au dépôt."""
        return self._db

    @contextmanager
    def atomic(self) -> Generator[Any, None, None]:
        """Gestionnaire de contexte exécutant plusieurs requêtes de façon atomique dans une transaction."""
        with self._db.atomic():
            yield
