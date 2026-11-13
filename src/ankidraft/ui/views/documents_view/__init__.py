"""Package DocumentsView d'AnkiForge (Hub Documentaire & RAG Local).

Re-exporte l'ensemble des dialogues, widgets et la vue principale pour 100% de rétrocompatibilité.
"""

from ankidraft.ui.views.documents_view.dialogs import (
    DocumentDelimitationDialog,
    RAGTestDialog,
)
from ankidraft.ui.views.documents_view.utils import apply_pill_style
from ankidraft.ui.views.documents_view.view import DocumentsTab, DocumentsView
from ankidraft.ui.views.documents_view.widgets import DocumentTreeWidget

__all__ = [
    "DocumentsView",
    "DocumentsTab",
    "DocumentDelimitationDialog",
    "RAGTestDialog",
    "DocumentTreeWidget",
    "apply_pill_style",
]
