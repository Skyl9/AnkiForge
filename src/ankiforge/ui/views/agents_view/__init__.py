"""
Package AgentsView d'AnkiForge (Atelier d'Agents IA & Personas).
Re-exporte l'ensemble des composants, dialogues, constantes et la vue principale pour 100% de rétrocompatibilité.
"""

from ankiforge.ui.views.agents_view.constants import (
    JINJA2_SNIPPETS,
    MCP_BASE_TOOLS_SPEC,
    PERSONA_TYPE_SPECS,
    apply_pill_style,
)
from ankiforge.ui.views.agents_view.dialogs import (
    AgentPromptPreviewDialog,
    AgentTestDialog,
)
from ankiforge.ui.views.agents_view.view import AgentsTab, AgentsView
from ankiforge.ui.views.agents_view.widgets import (
    FolderHeaderWidget,
    PersonaItemWidget,
    ResponsiveAgentTopActionBar,
    SubTabButton,
    TagPillButton,
    ToolPermissionCard,
)

__all__ = [
    "AgentsView",
    "AgentsTab",
    "AgentPromptPreviewDialog",
    "AgentTestDialog",
    "FolderHeaderWidget",
    "PersonaItemWidget",
    "ResponsiveAgentTopActionBar",
    "SubTabButton",
    "TagPillButton",
    "ToolPermissionCard",
    "apply_pill_style",
    "PERSONA_TYPE_SPECS",
    "MCP_BASE_TOOLS_SPEC",
    "JINJA2_SNIPPETS",
]
