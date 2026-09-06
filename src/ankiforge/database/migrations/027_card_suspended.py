import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 027 : Ajout de la colonne is_suspended à cardmodel."""
    if not fake and database.table_exists("cardmodel"):
        cols = [col.name for col in database.get_columns("cardmodel")]
        if "is_suspended" not in cols:
            migrator.add_fields("cardmodel", is_suspended=pw.BooleanField(default=False))


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 027 : Suppression de la colonne is_suspended de cardmodel."""
    if not fake and database.table_exists("cardmodel"):
        cols = [col.name for col in database.get_columns("cardmodel")]
        if "is_suspended" in cols:
            migrator.remove_fields("cardmodel", "is_suspended")
