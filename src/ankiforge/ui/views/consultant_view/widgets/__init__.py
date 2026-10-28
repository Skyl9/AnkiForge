"""Widgets spécialisés pour le cockpit du Serveur MCP & Agents (ADR 0043)."""

from ankiforge.ui.views.consultant_view.widgets.inline_diff_card_widget import InlineDiffCardWidget
from ankiforge.ui.views.consultant_view.widgets.mcp_dashboard_widget import MCPServerDashboardWidget
from ankiforge.ui.views.consultant_view.widgets.mcp_garde_fou_widget import MCPGardeFouWidget
from ankiforge.ui.views.consultant_view.widgets.mcp_supervision_widget import MCPSupervisionWidget
from ankiforge.ui.views.consultant_view.widgets.mcp_telemetry_widget import MCPTelemetryWidget
from ankiforge.ui.views.consultant_view.widgets.mcp_tool_catalog_widget import MCPToolCatalogWidget
from ankiforge.ui.views.consultant_view.widgets.mcp_workspace_guide_widget import MCPWorkspaceGuideWidget

__all__ = [
    "InlineDiffCardWidget",
    "MCPGardeFouWidget",
    "MCPServerDashboardWidget",
    "MCPSupervisionWidget",
    "MCPTelemetryWidget",
    "MCPToolCatalogWidget",
    "MCPWorkspaceGuideWidget",
]
