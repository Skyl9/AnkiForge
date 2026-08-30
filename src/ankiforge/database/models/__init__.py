# ruff: noqa: E501
"""
Package des modèles Peewee d'AnkiForge.
Re-exporte l'ensemble des schémas de données, de la connexion et des fonctions d'initialisation
pour assurer une parfaite rétrocompatibilité.
"""

from ankiforge.database.base import (
    DB_PATH,
    DEFAULT_DB_PATH,
    BaseModel,
    db,
    generate_guid,
    init_db,
)
from ankiforge.database.models.ai import (
    LLMConfigModel,
    PersonaFolderModel,
    PersonaModel,
    PersonaVersionModel,
    PromptModel,
    TokenUsageModel,
)
from ankiforge.database.models.audit import (
    AuditRecordModel,
    IgnoredDuplicateModel,
    LinterRuleModel,
)
from ankiforge.database.models.cards import (
    CardModel,
    DeckModel,
    MediaModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionMediaModel,
    NoteVersionModel,
)
from ankiforge.database.models.pipelines import (
    PipelineModel,
    PipelineStepModel,
    PythonToolModel,
)
from ankiforge.database.models.rag import (
    DocumentChunkModel,
    DocumentModel,
    EmbeddingCacheModel,
    FolderModel,
    NoteChunkLinkModel,
)
from ankiforge.database.models.system import (
    AICacheModel,
    JobModel,
    SettingModel,
)
from ankiforge.database.seeds import (
    seed_default_linter_rules,
    seed_initial_data,
)

ALL_MODELS = [
    DeckModel,
    NoteTypeModel,
    NoteModel,
    NoteVersionModel,
    MediaModel,
    NoteVersionMediaModel,
    CardModel,
    PromptModel,
    LLMConfigModel,
    TokenUsageModel,
    PersonaFolderModel,
    PersonaModel,
    PersonaVersionModel,
    PipelineModel,
    PipelineStepModel,
    PythonToolModel,
    FolderModel,
    DocumentModel,
    DocumentChunkModel,
    NoteChunkLinkModel,
    EmbeddingCacheModel,
    JobModel,
    LinterRuleModel,
    AuditRecordModel,
    SettingModel,
    IgnoredDuplicateModel,
    AICacheModel,
]

__all__ = [
    # Infrastructure
    "db",
    "BaseModel",
    "init_db",
    "generate_guid",
    "DEFAULT_DB_PATH",
    "DB_PATH",
    "ALL_MODELS",
    # Cartes & Decks
    "DeckModel",
    "NoteTypeModel",
    "NoteModel",
    "NoteVersionModel",
    "MediaModel",
    "NoteVersionMediaModel",
    "CardModel",
    # IA & Personas
    "PromptModel",
    "LLMConfigModel",
    "TokenUsageModel",
    "PersonaFolderModel",
    "PersonaModel",
    "PersonaVersionModel",
    # Pipelines DAG
    "PipelineModel",
    "PipelineStepModel",
    "PythonToolModel",
    # Documents & RAG
    "FolderModel",
    "DocumentModel",
    "DocumentChunkModel",
    "NoteChunkLinkModel",
    "EmbeddingCacheModel",
    # Système, Cache & Audit
    "JobModel",
    "LinterRuleModel",
    "AuditRecordModel",
    "SettingModel",
    "IgnoredDuplicateModel",
    "AICacheModel",
    # Seeds
    "seed_initial_data",
    "seed_default_linter_rules",
]
