import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 012 : Ajout du champ config_data dans pipeline_steps."""
    migrator.add_fields(
        "pipeline_steps",
        config_data=pw.TextField(null=True, default="{}"),
    )


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 012 : Suppression du champ config_data."""
    migrator.remove_fields("pipeline_steps", "config_data")
