import datetime
import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 015 : Création de la table persona_folders et ajout de folder_id dans personas."""

    @migrator.create_model
    class PersonaFolderModel(pw.Model):
        id = pw.AutoField()
        name = pw.CharField(unique=True)
        created_at = pw.DateTimeField(default=datetime.datetime.now)

        class Meta:
            table_name = "persona_folders"

    migrator.add_fields(
        "personas",
        folder=pw.ForeignKeyField(PersonaFolderModel, backref="personas", null=True, on_delete="SET NULL"),
    )


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 015 : Suppression de folder_id et de persona_folders."""
    migrator.remove_fields("personas", "folder_id")
    migrator.remove_model("persona_folders")
