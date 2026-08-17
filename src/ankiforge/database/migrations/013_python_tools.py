import datetime
import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 013 : Création de la table python_tools pour les outils déterministes et scripts personnalisés."""

    @migrator.create_model
    class PythonToolModel(pw.Model):
        id = pw.AutoField()
        name = pw.CharField(max_length=255, unique=True)
        display_name = pw.CharField(max_length=255)
        description = pw.TextField(null=True)
        code = pw.TextField()
        is_builtin = pw.BooleanField(default=False)
        created_at = pw.DateTimeField(default=datetime.datetime.now)

        class Meta:
            table_name = "python_tools"


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 013 : Suppression de la table python_tools."""
    migrator.remove_model("python_tools")
