import logging

import peewee as pw
from peewee_migrate import Migrator

logger = logging.getLogger(__name__)


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 034 : Index sur documentmodel.source_url pour le dédoublonnage des imports web."""
    if fake:
        return
    try:
        database.execute_sql("CREATE INDEX IF NOT EXISTS idx_documentmodel_source_url ON documentmodel (source_url);")
    except Exception as e:
        logger.debug("Remarque sur la création de l'index source_url : %s", e)


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 034 : Suppression de l'index documentmodel.source_url."""
    if fake:
        return
    try:
        database.execute_sql("DROP INDEX IF EXISTS idx_documentmodel_source_url;")
    except Exception as e:
        logger.debug("Remarque sur la suppression de l'index source_url : %s", e)
