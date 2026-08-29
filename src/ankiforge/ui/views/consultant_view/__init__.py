"""
Package ConsultantView d'AnkiForge (AI Consultant Studio).
Re-exporte l'ensemble des composants, widgets et la vue principale pour 100% de rétrocompatibilité.
"""

from ankiforge.ui.views.consultant_view.constants import (
    apply_pill_style,
    render_markdown_message,
)
from ankiforge.ui.views.consultant_view.view import (
    ConsultantTab,
    ConsultantView,
)
from ankiforge.ui.views.consultant_view.widgets import (
    ChatMessageWidget,
    ThoughtStepWidget,
    ToolCallWidget,
)

__all__ = [
    "ConsultantView",
    "ConsultantTab",
    "ThoughtStepWidget",
    "ToolCallWidget",
    "ChatMessageWidget",
    "apply_pill_style",
    "render_markdown_message",
]
