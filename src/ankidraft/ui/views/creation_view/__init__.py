"""Package CreationView d'AnkiForge (Studio de Création).

Re-exporte l'ensemble des composants, dialogues, assistants et la vue principale pour 100% rétrocompatibilité.
"""

from ankidraft.ui.views.creation_view.dialogs import CardEditDialog
from ankidraft.ui.views.creation_view.utils import parse_page_ranges
from ankidraft.ui.views.creation_view.view import CreationTab, CreationView
from ankidraft.ui.views.creation_view.widgets import (
    CreationHubWidget,
    DocumentEditorWidget,
    FlashcardPreview,
    VisionCard,
)

__all__ = [
    "CreationView",
    "CreationTab",
    "parse_page_ranges",
    "VisionCard",
    "CreationHubWidget",
    "CardEditDialog",
    "FlashcardPreview",
    "DocumentEditorWidget",
]
