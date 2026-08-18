import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 014 : Ajout du champ persona_type dans personas."""
    migrator.add_fields(
        "personas",
        persona_type=pw.CharField(default="pipeline"),
    )


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 014 : Suppression du champ persona_type."""
    migrator.remove_fields("personas", "persona_type")
