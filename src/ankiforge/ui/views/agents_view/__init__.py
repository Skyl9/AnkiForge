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
    PersonaCreationWizardDialog,
    VariableHelperDialog,
)
from ankiforge.ui.views.agents_view.view import AgentsTab, AgentsView
from ankiforge.ui.views.agents_view.widgets import (
    FolderHeaderWidget,
    PersonaEmptyStateWidget,
    PersonaItemWidget,
    ResponsiveAgentTopActionBar,
    SubTabButton,
    TagPillButton,
    ToolPermissionCard,
)

__all__ = [
    "AgentPromptPreviewDialog",
    "AgentTestDialog",
    "AgentsTab",
    "AgentsView",
    "FolderHeaderWidget",
    "JINJA2_SNIPPETS",
    "MCP_BASE_TOOLS_SPEC",
    "PERSONA_TYPE_SPECS",
    "PersonaCreationWizardDialog",
    "PersonaEmptyStateWidget",
    "PersonaItemWidget",
    "ResponsiveAgentTopActionBar",
    "SubTabButton",
    "TagPillButton",
    "ToolPermissionCard",
    "VariableHelperDialog",
    "apply_pill_style",
]
