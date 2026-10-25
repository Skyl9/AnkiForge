"""Migration 048 : Ajout de la colonne sort_field indexée sur notemodel et backfill canonique."""

from __future__ import annotations

import logging

import peewee as pw
from peewee_migrate import Migrator

from ankiforge.utils.anki_renderer import compute_sort_field, strip_html_for_sort

logger = logging.getLogger(__name__)

__all__ = ["backfill", "compute_sort_field", "migrate", "rollback", "strip_html_for_sort"]


def backfill(database: pw.Database) -> None:
    """Remplit sort_field pour les notes existantes à partir de leur version active."""
    if not database.table_exists("notemodel") or not database.table_exists("noteversionmodel"):
        return

    try:
        cursor = database.execute_sql("""
            SELECT nv.note_id, nv.content
            FROM noteversionmodel nv
            WHERE nv.is_active = 1
        """)
        rows = cursor.fetchall()

        updates: list[tuple[str, int]] = []
        for note_id, content in rows:
            sort_val = compute_sort_field(content)
            updates.append((sort_val, note_id))

        if updates:
            batch_size = 500
            with database.atomic():
                cur = database.cursor()
                for i in range(0, len(updates), batch_size):
                    batch = updates[i : i + batch_size]
                    cur.executemany(
                        "UPDATE notemodel SET sort_field = ? WHERE id = ?",
                        batch,
                    )
            logger.info("Backfill sort_field achevé avec succès pour %s notes.", len(updates))
    except Exception as e:
        logger.warning("Erreur lors du backfill sort_field de la migration 048 : %s", e)


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 048 : Ajout de la colonne sort_field indexée sur notemodel."""
    if fake:
        if "notemodel" in migrator.orm:
            migrator.add_fields("notemodel", sort_field=pw.CharField(max_length=512, default="", index=True))
        return

    if not database.table_exists("notemodel"):
        return

    cols = [col.name for col in database.get_columns("notemodel")]
    if "sort_field" in cols:
        return

    if "notemodel" in migrator.orm:
        migrator.add_fields("notemodel", sort_field=pw.CharField(max_length=512, default="", index=True))
        migrator.run(backfill, database)
    else:
        try:
            database.execute_sql("ALTER TABLE notemodel ADD COLUMN sort_field VARCHAR(512) DEFAULT '' NOT NULL;")
            database.execute_sql("CREATE INDEX IF NOT EXISTS idx_notemodel_sort_field ON notemodel(sort_field);")
            backfill(database)
        except Exception as e:
            logger.warning("Erreur ajout colonne sort_field via SQL direct : %s", e)


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 048 : Suppression de la colonne sort_field sur notemodel."""
    if fake or not database.table_exists("notemodel"):
        return

    cols = [col.name for col in database.get_columns("notemodel")]
    if "sort_field" in cols:
        try:
            database.execute_sql("DROP INDEX IF EXISTS idx_notemodel_sort_field;")
            database.execute_sql("DROP INDEX IF EXISTS notemodel_sort_field;")
        except Exception as e:
            logger.debug("Remarque suppression index sort_field : %s", e)

        try:
            database.execute_sql("ALTER TABLE notemodel DROP COLUMN sort_field;")
        except Exception as e:
            logger.warning("Erreur suppression colonne sort_field : %s", e)
