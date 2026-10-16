"""Migration 005 : renommage de la table agents en personas et ajout des champs du moteur de personas."""

import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Renomme les tables et champs du moteur de personas.

    Ajoute également `allowed_tools` sur `personas`, `step_type` sur `pipeline_steps`
    et `faiss_index_path` sur `documentmodel`.
    """
    migrator.rename_table("agents", "personas")

    migrator.rename_field("pipeline_steps", "agent", "persona")

    migrator.add_fields("personas", allowed_tools=pw.TextField(default="[]"))
    migrator.add_fields("pipeline_steps", step_type=pw.CharField(default="LLM_PROMPT", max_length=255))
    migrator.add_fields("documentmodel", faiss_index_path=pw.CharField(null=True, max_length=255))


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Retire les champs du moteur de personas et rétablit les noms de tables d'origine."""
    migrator.remove_fields("documentmodel", "faiss_index_path")
    migrator.remove_fields("pipeline_steps", "step_type")
    migrator.remove_fields("personas", "allowed_tools")
    migrator.rename_field("pipeline_steps", "persona", "agent")
    migrator.rename_table("personas", "agents")
