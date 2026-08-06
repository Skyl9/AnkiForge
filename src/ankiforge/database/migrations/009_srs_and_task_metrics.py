import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your migrations here."""
    # Ajouter le champ task_type dans token_usage
    migrator.add_fields("token_usage", task_type=pw.CharField(default="1. Reformulation & Génération Wozniak"))

    # Ajouter les champs FSRS dans cardmodel
    migrator.add_fields(
        "cardmodel",
        ivl=pw.IntegerField(default=0),
        reps=pw.IntegerField(default=0),
        lapses=pw.IntegerField(default=0),
        stability=pw.FloatField(default=0.0),
        difficulty=pw.FloatField(default=0.0),
        retrievability=pw.FloatField(default=0.0),
    )

    # Ajouter le champ is_free dans llm_configs
    migrator.add_fields("llm_configs", is_free=pw.BooleanField(default=False))


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your rollback migrations here."""
    migrator.remove_fields("cardmodel", "ivl", "reps", "lapses", "stability", "difficulty", "retrievability")
    migrator.remove_fields("token_usage", "task_type")
    migrator.remove_fields("llm_configs", "is_free")
