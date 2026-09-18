from __future__ import annotations

import datetime
import logging

from peewee import (
    CharField,
    DateTimeField,
    FloatField,
    ForeignKeyField,
    IntegerField,
)

from ankiforge.database.base import BaseModel
from ankiforge.database.models.ai import PersonaModel
from ankiforge.database.models.pipelines import PipelineModel

logger = logging.getLogger(__name__)


class TokenUsageModel(BaseModel):
    """Stocke l'historique de consommation pour calculer les coûts API."""

    provider = CharField()  # ex: "openai", "gemini", "ollama"
    model_id = CharField()  # ex: "gpt-4o", "gemini-2.0-flash"
    prompt_tokens = IntegerField(default=0)
    completion_tokens = IntegerField(default=0)
    total_tokens = IntegerField(default=0)
    estimated_cost_usd = FloatField(default=0.0)
    task_type = CharField(default="1. Reformulation & Génération Wozniak")
    # Vraies clés étrangères (audit "fk-missing-cascade") : la suppression d'un pipeline ou d'un
    # persona conserve l'historique de coûts (SET NULL) au lieu de laisser un id orphelin. Les noms
    # de colonnes restent pipeline_id / persona_id pour la compatibilité des profils legacy.
    pipeline = ForeignKeyField(PipelineModel, null=True, backref="token_usage", on_delete="SET NULL", column_name="pipeline_id")
    persona = ForeignKeyField(PersonaModel, null=True, backref="token_usage", on_delete="SET NULL", column_name="persona_id")
    ab_run_id = CharField(null=True)  # Identifiant de run A/B (comparaison de modèles)
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "token_usage"
        indexes = ((("pipeline", "persona", "ab_run_id"), False),)
