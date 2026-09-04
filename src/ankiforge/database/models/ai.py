# ruff: noqa: E501
import datetime
import logging

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
    context_limit = IntegerField(default=8192)
    temperature = FloatField(default=0.7)
    api_key = CharField(null=True)
    prompt_pricing = FloatField(default=0.0)
    completion_pricing = FloatField(default=0.0)
    is_free = BooleanField(default=False)

    class Meta:
        table_name = "llm_configs"


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
