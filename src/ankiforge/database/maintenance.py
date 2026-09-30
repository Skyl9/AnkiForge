"""Opérations SQLite de maintenance exécutées hors du thread graphique ou à la fermeture."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

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


def fast_wal_checkpoint_and_optimize(db_path: Path) -> None:
    """Exécute un checkpoint WAL rapide et optimize SQLite (< 100ms) sans VACUUM."""
    if not db_path.exists():
        return
    try:
        with sqlite3.connect(str(db_path), timeout=10) as conn:
            conn.execute("PRAGMA busy_timeout = 10000;")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.execute("PRAGMA optimize;")
            conn.commit()
        logger.info("Checkpoint WAL rapide et optimisation terminés : %s", db_path)
    except Exception as e:
        logger.warning("Remarque checkpoint WAL rapide à la fermeture : %s", e)


def execute_clean_shutdown(
    profile_name: str | None = None,
    clean_orphan_media: bool = False,
) -> dict[str, Any]:
    """
    Exécute la séquence de maintenance à la fermeture propre :
    1. Checkpoint WAL TRUNCATE + optimize SQLite (< 100ms).
    2. Nettoyage conditionnel des médias orphelins (si clean_orphan_media=True).
    3. Libération de tous les verrous de profil.
    """
    from ankiforge.services.profile_lock_service import ProfileLockService
    from ankiforge.services.profile_manager import ProfileManager
    from ankiforge.utils.paths import get_active_profile

    target_profile = profile_name or get_active_profile()
    pm = ProfileManager()
    db_path = pm.get_db_path(target_profile)

    report: dict[str, Any] = {
        "profile": target_profile,
        "wal_checkpoint": False,
        "orphan_media_cleaned": 0,
    }

    if db_path.exists():
        fast_wal_checkpoint_and_optimize(db_path)
        report["wal_checkpoint"] = True

    if clean_orphan_media:
        try:
            from ankiforge.services.cards.media_manager import MediaManager

            media_dir = pm.get_media_dir(target_profile)
            mm = MediaManager(media_dir=media_dir)
            deleted = mm.clean_orphan_media()
            report["orphan_media_cleaned"] = deleted
            logger.info("Nettoyage des médias orphelins à la fermeture : %d fichier(s) purgé(s)", deleted)
        except Exception as e:
            logger.warning("Erreur nettoyage médias orphelins à la fermeture : %s", e)

    ProfileLockService.release_all_locks()
    return report
