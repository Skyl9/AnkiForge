import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 026 : Ajout de la colonne flags à cardmodel."""
    if not fake and database.table_exists("cardmodel"):
        cols = [col.name for col in database.get_columns("cardmodel")]
        if "flags" not in cols:
            migrator.add_fields("cardmodel", flags=pw.IntegerField(default=0))


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 026 : Suppression de la colonne flags de cardmodel."""
    if not fake and database.table_exists("cardmodel"):
        cols = [col.name for col in database.get_columns("cardmodel")]
        if "flags" in cols:
            migrator.remove_fields("cardmodel", "flags")
