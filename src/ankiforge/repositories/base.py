"""
Base Repository class providing database transactions and safe querying primitives.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from peewee import Database

from ankiforge.database.base import db as default_db

logger = logging.getLogger(__name__)


class BaseRepository:
    """
    Base class for all Peewee data access repositories.
    Encapsulates atomic transactions and database connection awareness.
    """

    def __init__(self, database: Database | None = None) -> None:
        self._db = database or default_db

    @property
    def db(self) -> Database:
        return self._db

    @contextmanager
    def atomic(self) -> Generator[Any, None, None]:
        """Context manager to execute multiple queries atomically in a transaction."""
        with self._db.atomic():
            yield
