"""Package des modèles Peewee d'AnkiForge.

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
    StagedBundleModel,
    StagedPatchModel,
)
from ankiforge.database.models.audit import (
    AuditRecordModel,
    IgnoredDuplicateModel,
    LinterRuleModel,
)
from ankiforge.database.models.cards import (
    DEFAULT_LATEX_POST,
    DEFAULT_LATEX_PRE,
    CardModel,
    DeckModel,
    MediaModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.database.models.flags import (
    FlagDefinitionModel,
    ProfileFlagLabelModel,
)
from ankiforge.database.models.pipelines import (
    PipelineModel,
    PipelineRunModel,
    PipelineStepModel,
    PythonToolModel,
)
from ankiforge.database.models.rag import (
    DocumentChunkModel,
    DocumentModel,
    DocumentPageModel,
    EmbeddingCacheModel,
    FolderModel,
    NoteChunkLinkModel,
)
from ankiforge.database.models.system import SettingModel
from ankiforge.database.models.usage import TokenUsageModel
from ankiforge.database.seeds import (
    seed_default_linter_rules,
    seed_initial_data,
)

__all__ = [
    # Infrastructure
    "db",
    "BaseModel",
    "init_db",
    "generate_guid",
    "DEFAULT_DB_PATH",
    "DB_PATH",
    # Cartes & Decks
    "DeckModel",
    "NoteTypeModel",
    "NoteModel",
    "NoteVersionModel",
    "MediaModel",
    "CardModel",
    "FlagDefinitionModel",
    "ProfileFlagLabelModel",
    "DEFAULT_LATEX_PRE",
    "DEFAULT_LATEX_POST",
    # IA & Personas
    "LLMConfigModel",
    "TokenUsageModel",
    "PersonaFolderModel",
    "PersonaModel",
    "PersonaVersionModel",
    "StagedBundleModel",
    "StagedPatchModel",
    # Pipelines DAG
    "PipelineModel",
    "PipelineRunModel",
    "PipelineStepModel",
    "PythonToolModel",
    # Documents & RAG
    "FolderModel",
    "DocumentModel",
    "DocumentPageModel",
    "DocumentChunkModel",
    "NoteChunkLinkModel",
    "EmbeddingCacheModel",
    # Système & Audit
    "LinterRuleModel",
    "AuditRecordModel",
    "SettingModel",
    "IgnoredDuplicateModel",
    # Seeds
    "seed_initial_data",
    "seed_default_linter_rules",
]
