import datetime
import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Crée la table persona_versions pour tracer l'historique et le versioning des Personas/Agents IA."""

    @migrator.create_model
    class PersonaVersionModel(pw.Model):
        id = pw.AutoField()
        persona_id = pw.IntegerField(index=True)
        version_number = pw.IntegerField(default=1)
        system_prompt = pw.TextField()
        description = pw.TextField(null=True)
        output_format = pw.CharField(max_length=50, default="json")
        persona_type = pw.CharField(max_length=50, default="pipeline")
        allowed_tools = pw.TextField(default="[]")
        llm_config_id = pw.IntegerField(null=True)
        commit_message = pw.CharField(max_length=255, default="Mise à jour du prompt")
        created_at = pw.DateTimeField(default=datetime.datetime.now)
        is_active = pw.BooleanField(default=True)

        class Meta:
            table_name = "persona_versions"


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Supprime la table persona_versions."""
    migrator.remove_model("persona_versions")
