"""Opérations SQLite de maintenance exécutées hors du thread graphique."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def optimize_database(db_path: Path) -> None:
    """Exécute les opérations de maintenance sur une connexion SQLite dédiée."""
    with sqlite3.connect(str(db_path), timeout=30) as connection:
        connection.execute("PRAGMA busy_timeout = 30000;")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        connection.execute("PRAGMA optimize;")
        connection.execute("VACUUM;")
        connection.commit()
    logger.info("Maintenance SQLite terminée : %s", db_path)
