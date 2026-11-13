"""Migration 009 : métriques SRS (FSRS) sur cardmodel, type de tâche et indicateur de gratuité LLM."""

import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Ajoute les métriques FSRS et les indicateurs de tâche.

    Ajoute les métriques FSRS à `cardmodel`, le type de tâche à `token_usage` et
    l'indicateur de gratuité à `llm_configs`.
    """
    migrator.add_fields("token_usage", task_type=pw.CharField(default="1. Reformulation & Génération Wozniak"))

    migrator.add_fields(
        "cardmodel",
        ivl=pw.IntegerField(default=0),
        reps=pw.IntegerField(default=0),
        lapses=pw.IntegerField(default=0),
        stability=pw.FloatField(default=0.0),
        difficulty=pw.FloatField(default=0.0),
        retrievability=pw.FloatField(default=0.0),
    )

    migrator.add_fields("llm_configs", is_free=pw.BooleanField(default=False))


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Retire les métriques FSRS, le type de tâche et l'indicateur de gratuité."""
    migrator.remove_fields("cardmodel", "ivl", "reps", "lapses", "stability", "difficulty", "retrievability")
    migrator.remove_fields("token_usage", "task_type")
    migrator.remove_fields("llm_configs", "is_free")
