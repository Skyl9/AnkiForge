"""Migration 050 : Ajout de la colonne `reason` sur staged_patches (motif d'abandon)."""

from __future__ import annotations

import logging

import peewee as pw
from peewee_migrate import Migrator

logger = logging.getLogger(__name__)


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 050 : Ajoute la colonne `reason` (texte) à la table staged_patches."""
    if fake:
        return

    if not database.table_exists("staged_patches"):
        logger.warning("Migration 050 ignorée : table staged_patches absente.")
        return

    cols = [col.name for col in database.get_columns("staged_patches")]
    if "reason" not in cols:
        try:
            migrator.add_fields("staged_patches", reason=pw.TextField(default=""))
        except Exception as e:
            logger.warning("Erreur ajout colonne reason sur staged_patches : %s", e)

    logger.info("Migration 050 : Colonne `reason` ajoutée sur staged_patches.")


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 050 : Supprime la colonne `reason` de la table staged_patches."""
    if fake:
        return

    if database.table_exists("staged_patches"):
        cols = [col.name for col in database.get_columns("staged_patches")]
        if "reason" in cols:
            try:
                database.execute_sql("ALTER TABLE staged_patches DROP COLUMN reason;")
            except Exception as e:
                logger.warning("Erreur suppression colonne reason sur staged_patches : %s", e)

    logger.info("Rollback 050 achevé.")
