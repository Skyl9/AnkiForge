import datetime
import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Crée la table ai_cache pour gérer le cache persistant de l'IA."""

    @migrator.create_model
    class AICacheModel(pw.Model):
        id = pw.AutoField()
        prompt_hash = pw.CharField(max_length=255, index=True)
        system_prompt_hash = pw.CharField(max_length=255)
        model_id = pw.CharField(max_length=255)
        temperature = pw.FloatField()
        response_content = pw.TextField()
        created_at = pw.DateTimeField(default=datetime.datetime.now)

        class Meta:
            table_name = "ai_cache"
            indexes = [(("prompt_hash", "system_prompt_hash", "model_id", "temperature"), True)]


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Supprime la table ai_cache."""

    migrator.remove_model("ai_cache")
