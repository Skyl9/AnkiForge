import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 033 : Ajout de chunk_strategy_version à documentmodel.

    Permet de détecter les documents indexés avec une ancienne stratégie de
    structuration (ex. H3 seul) et de déclencher une re-indexation automatique
    avec la stratégie fine (H1→H6 AST).
    """
    if not fake and database.table_exists("documentmodel"):
        cols = [col.name for col in database.get_columns("documentmodel")]
        if "chunk_strategy_version" not in cols:
            migrator.add_fields("documentmodel", chunk_strategy_version=pw.IntegerField(default=0))


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 033 : Suppression de chunk_strategy_version de documentmodel."""
    if not fake and database.table_exists("documentmodel"):
        cols = [col.name for col in database.get_columns("documentmodel")]
        if "chunk_strategy_version" in cols:
            migrator.remove_fields("documentmodel", "chunk_strategy_version")
