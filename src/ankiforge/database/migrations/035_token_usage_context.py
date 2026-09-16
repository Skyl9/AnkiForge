import logging

import peewee as pw
from peewee_migrate import Migrator

logger = logging.getLogger(__name__)


def _existing_columns(database: pw.Database, table: str) -> set[str]:
    """Retourne l'ensemble des colonnes existantes d'une table SQLite."""
    try:
        rows = database.execute_sql(f"PRAGMA table_info({table});").fetchall()
        return {str(row[1]) for row in rows}
    except Exception as e:
        logger.debug("Impossible de lire les colonnes de %s : %s", table, e)
        return set()


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 035 : rattachement de la consommation de tokens au pipeline/persona/run A-B."""
    if fake:
        return
    columns = _existing_columns(database, "token_usage")
    try:
        if "pipeline_id" not in columns:
            migrator.add_fields("token_usage", pipeline_id=pw.IntegerField(null=True))
        if "persona_id" not in columns:
            migrator.add_fields("token_usage", persona_id=pw.IntegerField(null=True))
        if "ab_run_id" not in columns:
            migrator.add_fields("token_usage", ab_run_id=pw.CharField(null=True))
        database.execute_sql("CREATE INDEX IF NOT EXISTS idx_token_usage_context ON token_usage (pipeline_id, persona_id, ab_run_id);")
    except Exception as e:
        logger.warning("Remarque sur la migration 035 (contexte token_usage) : %s", e)


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 035 : retrait des colonnes de contexte et de l'index associé."""
    if fake:
        return
    try:
        database.execute_sql("DROP INDEX IF EXISTS idx_token_usage_context;")
        columns = _existing_columns(database, "token_usage")
        present = [name for name in ("ab_run_id", "persona_id", "pipeline_id") if name in columns]
        if present:
            migrator.remove_fields("token_usage", *present)
    except Exception as e:
        logger.warning("Remarque sur le rollback 035 (contexte token_usage) : %s", e)
