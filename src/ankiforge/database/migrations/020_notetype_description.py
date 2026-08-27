import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 020 : Ajout du champ description (directives IA) dans notetypemodel."""
    if not fake and (database.table_exists("notetypemodel") or "notetypemodel" in migrator.orm):
        cols = [c.name for c in database.get_columns("notetypemodel")]
        if "description" not in cols:
            try:
                migrator.add_fields(
                    "notetypemodel",
                    description=pw.TextField(null=True, default=""),
                )
            except Exception:
                try:
                    database.execute_sql("ALTER TABLE notetypemodel ADD COLUMN description TEXT DEFAULT '';")
                except Exception:
                    pass  # nosec B110


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 020 : Suppression du champ description."""
    if not fake and (database.table_exists("notetypemodel") or "notetypemodel" in migrator.orm):
        try:
            migrator.remove_fields("notetypemodel", "description")
        except Exception:
            pass  # nosec B110
