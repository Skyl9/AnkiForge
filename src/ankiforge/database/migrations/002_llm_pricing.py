import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Ajoute les colonnes de tarification au modèle LLMConfig."""
    migrator.add_fields("llm_configs", prompt_pricing=pw.FloatField(default=0.0), completion_pricing=pw.FloatField(default=0.0))


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Annule la migration."""
    migrator.remove_fields("llm_configs", "prompt_pricing", "completion_pricing")
