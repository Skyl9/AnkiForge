import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your migrations here."""
    # Renommer la table Agent en Personas
    migrator.rename_table("agents", "personas")

    # Mettre à jour la clé étrangère dans pipeline_steps
    migrator.rename_field("pipeline_steps", "agent", "persona")

    # Ajouter les nouveaux champs métier
    migrator.add_fields("personas", allowed_tools=pw.TextField(default="[]"))
    migrator.add_fields("pipeline_steps", step_type=pw.CharField(default="LLM_PROMPT", max_length=255))
    migrator.add_fields("documentmodel", faiss_index_path=pw.CharField(null=True, max_length=255))


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your rollback migrations here."""
    migrator.remove_fields("documentmodel", "faiss_index_path")
    migrator.remove_fields("pipeline_steps", "step_type")
    migrator.remove_fields("personas", "allowed_tools")
    migrator.rename_field("pipeline_steps", "persona", "agent")
    migrator.rename_table("personas", "agents")
