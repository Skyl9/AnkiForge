import datetime

import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Crée la table settings pour mémoriser les paramètres et préférences utilisateur en BDD."""

    @migrator.create_model
    class SettingModel(pw.Model):
        id = pw.AutoField()
        key = pw.CharField(max_length=255, unique=True, index=True)
        value = pw.TextField()
        category = pw.CharField(max_length=100, default="general", index=True)
        updated_at = pw.DateTimeField(default=datetime.datetime.now)

        class Meta:
            table_name = "settings"


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Supprime la table settings."""
    migrator.remove_model("settings")
