# ruff: noqa: E501
from __future__ import annotations

import datetime
import logging
from typing import Any

from peewee import (
    SQL,
    BooleanField,
    CharField,
    DateTimeField,
    FloatField,
    ForeignKeyField,
    IntegerField,
    TextField,
)

from ankiforge.database.base import BaseModel

logger = logging.getLogger(__name__)


class PromptModel(BaseModel):
    """Stocke les templates Jinja2 personnalisés"""

    name = CharField(unique=True)
    content = TextField()
    description = TextField(null=True)
    is_active = BooleanField(default=True)


class LLMConfigModel(BaseModel):
    """Stocke les configurations physiques des modèles d'IA (Le 'Moteur')."""

    display_name = CharField(unique=True)
    provider = CharField()
    model_id = CharField()
    context_limit = IntegerField(default=128000)
    max_tokens = IntegerField(default=16384)
    sort_order = IntegerField(default=100)
    temperature = FloatField(default=0.7)
    api_key = CharField(null=True)
    prompt_pricing = FloatField(default=0.0)
    completion_pricing = FloatField(default=0.0)
    is_free = BooleanField(default=False)
    supports_vision = BooleanField(default=False)
    supports_thinking = BooleanField(default=False)
    supports_json = BooleanField(default=True)
    speed_rating = CharField(default="fast")
    quality_tier = CharField(default="balanced")
    recommended_tasks = CharField(default="[]")
    description = TextField(default="")

    class Meta:
        table_name = "llm_configs"

    @property
    def recommended_tasks_list(self) -> list[str]:
        """Retourne la liste des tâches recommandées sous forme de liste Python."""
        try:
            import json

            return list(json.loads(self.recommended_tasks or "[]"))
        except Exception:
            return []

    @property
    def formatted_context_window(self) -> str:
        """Retourne la taille de contexte lisible (ex: '128k', '1M', '2M')."""
        ctx = int(self.context_limit or 128000)
        if ctx >= 1_000_000:
            val = ctx / 1_000_000
            return f"{val:.1f}M" if val % 1 else f"{int(val)}M"
        if ctx >= 1_000:
            return f"{ctx // 1_000}k"
        return str(ctx)

    @property
    def formatted_pricing(self) -> str:
        """Retourne l'étiquette de prix formatée."""
        if self.is_free or self.provider == "ollama":
            return "100% Gratuit"
        if self.prompt_pricing == 0.0 and self.completion_pricing == 0.0:
            return "Tier Gratuit"
        return f"${self.prompt_pricing:.2f} / ${self.completion_pricing:.2f} (1M)"

    def to_model_spec(self) -> Any:
        """Convertit l'enregistrement SQLite en ModelSpec du catalogue."""
        from ankiforge.services.ai.model_catalog import ModelSpec

        return ModelSpec(
            provider=str(self.provider),
            model_id=str(self.model_id),
            display_name=str(self.display_name or self.model_id),
            context_window=int(self.context_limit or 128000),
            max_tokens=int(self.max_tokens or 16384),
            supports_vision=bool(self.supports_vision),
            supports_thinking=bool(self.supports_thinking),
            supports_json=bool(self.supports_json),
            speed_rating=str(self.speed_rating or "fast"),
            quality_tier=str(self.quality_tier or "balanced"),
            is_free=bool(self.is_free or self.provider == "ollama"),
            prompt_pricing=float(self.prompt_pricing or 0.0),
            completion_pricing=float(self.completion_pricing or 0.0),
            recommended_tasks=self.recommended_tasks_list,
            description=str(self.description or ""),
        )


class TokenUsageModel(BaseModel):
    """Stocke l'historique de consommation pour calculer les coûts API."""

    provider = CharField()  # ex: "openai", "gemini", "ollama"
    model_id = CharField()  # ex: "gpt-4o", "gemini-2.0-flash"
    prompt_tokens = IntegerField(default=0)
    completion_tokens = IntegerField(default=0)
    total_tokens = IntegerField(default=0)
    estimated_cost_usd = FloatField(default=0.0)
    task_type = CharField(default="1. Reformulation & Génération Wozniak")
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "token_usage"


class PersonaFolderModel(BaseModel):
    """Dossier et sous-dossier de classification pour organiser les Personas et Agents IA."""

    name = CharField()
    parent = ForeignKeyField("self", backref="subfolders", null=True, on_delete="CASCADE")
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "persona_folders"

    def get_full_path(self) -> str:
        """Retourne le chemin complet du dossier (ex: 'Création / Mathématiques / Algèbre')."""
        parts = [str(self.name)]
        curr = self.parent
        visited = {self.id}
        while curr is not None and curr.id not in visited:
            parts.append(str(curr.name))
            visited.add(curr.id)
            curr = curr.parent
        return " / ".join(reversed(parts))


class PersonaModel(BaseModel):
    """Définit un agent IA unique (ex: Créateur, Linteur, Contrôleur) augmenté de capacités."""

    name = CharField(unique=True)
    description = TextField(null=True)
    system_prompt = TextField()  # Stockera le contenu du prompt Jinja2
    output_format = CharField(default="json")
    persona_type = CharField(default="pipeline")  # 'pipeline', 'mcp', 'universal'
    folder = ForeignKeyField(PersonaFolderModel, backref="personas", null=True, on_delete="SET NULL")
    allowed_tools = TextField(default="[]")  # JSON: ["query_peewee", "rag_retrieval"]
    llm_config = ForeignKeyField(LLMConfigModel, null=True, on_delete="SET NULL")
    created_at = DateTimeField(constraints=[SQL("DEFAULT CURRENT_TIMESTAMP")])

    class Meta:
        table_name = "personas"


class PersonaVersionModel(BaseModel):
    """Historique des versions et snapshots de configuration pour chaque Persona/Agent IA."""

    persona = ForeignKeyField(PersonaModel, backref="versions", on_delete="CASCADE")
    version_number = IntegerField(default=1)
    system_prompt = TextField()
    description = TextField(null=True)
    output_format = CharField(default="json")
    persona_type = CharField(default="pipeline")
    allowed_tools = TextField(default="[]")
    llm_config = ForeignKeyField(LLMConfigModel, null=True, on_delete="SET NULL")
    commit_message = CharField(default="Mise à jour du prompt")
    created_at = DateTimeField(default=datetime.datetime.now)
    is_active = BooleanField(default=True)

    class Meta:
        table_name = "persona_versions"


class ConsultantSessionModel(BaseModel):
    """Session de discussion persistée avec le Consultant IA."""

    title = CharField(default="Nouvelle Session")
    persona = ForeignKeyField(PersonaModel, backref="consultant_sessions", null=True, on_delete="SET NULL")
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "consultant_sessions"


class ConsultantMessageModel(BaseModel):
    """Message individuel d'une session de chat avec le Consultant IA."""

    session = ForeignKeyField(ConsultantSessionModel, backref="messages", on_delete="CASCADE")
    role = CharField()  # "user", "assistant", "system"
    content = TextField()
    thoughts = TextField(null=True)
    tool_calls_json = TextField(null=True)
    staged_diffs_json = TextField(null=True)
    tokens_used = IntegerField(default=0)
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "consultant_messages"
