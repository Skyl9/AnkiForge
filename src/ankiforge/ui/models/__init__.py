"""
Package des modèles de données Qt virtualisés (Model/View Architecture) pour AnkiForge.
Fournit des implémentations de QAbstractTableModel et QAbstractListModel avec pagination
intelligente (canFetchMore/fetchMore), requêtes Peewee optimisées (batch prefetch),
et des délégués de rendu vectoriel QStyledItemDelegate pour 60 FPS constants.
"""

from .chunk_list_model import ChunkItemData, VirtualChunkListModel
from .delegates import (
    BADGE_BG_COLOR_ROLE,
    BADGE_TEXT_COLOR_ROLE,
    FLAG_ROLE,
    IS_INVALID_CARD_ROLE,
    NOTE_ID_ROLE,
    RAW_CONTENT_ROLE,
    TAGS_LIST_ROLE,
    BadgeItemDelegate,
    CheckboxItemDelegate,
    FlagItemDelegate,
    ProgressBarItemDelegate,
    SimilarityBadgeDelegate,
    SrsMasteryDelegate,
    TagItemDelegate,
    TextSnippetDelegate,
)
from .note_table_model import NoteRowData, NoteVirtualTableModel, strip_html
from .paginated_model import BasePaginatedPeeweeModel

__all__ = [
    "BasePaginatedPeeweeModel",
    "NoteVirtualTableModel",
    "NoteRowData",
    "strip_html",
    "VirtualChunkListModel",
    "ChunkItemData",
    "BadgeItemDelegate",
    "TagItemDelegate",
    "CheckboxItemDelegate",
    "FlagItemDelegate",
    "ProgressBarItemDelegate",
    "TextSnippetDelegate",
    "SimilarityBadgeDelegate",
    "SrsMasteryDelegate",
    "NOTE_ID_ROLE",
    "TAGS_LIST_ROLE",
    "BADGE_BG_COLOR_ROLE",
    "BADGE_TEXT_COLOR_ROLE",
    "IS_INVALID_CARD_ROLE",
    "RAW_CONTENT_ROLE",
    "FLAG_ROLE",
]
