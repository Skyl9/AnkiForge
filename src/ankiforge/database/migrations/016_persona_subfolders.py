import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 016 : Ajout du champ parent_id dans persona_folders pour supporter les sous-dossiers."""
    migrator.add_fields(
        "persona_folders",
        parent=pw.ForeignKeyField("self", backref="subfolders", null=True, on_delete="CASCADE"),
    )


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 016 : Suppression du champ parent_id."""
    migrator.remove_fields("persona_folders", "parent_id")
