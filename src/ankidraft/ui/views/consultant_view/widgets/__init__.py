"""Widgets spécialisés pour le cockpit du Serveur MCP & Agents (ADR 0043)."""

from ankidraft.ui.views.consultant_view.widgets.inline_diff_card_widget import InlineDiffCardWidget
from ankidraft.ui.views.consultant_view.widgets.mcp_dashboard_widget import MCPServerDashboardWidget
from ankidraft.ui.views.consultant_view.widgets.mcp_garde_fou_widget import MCPGardeFouWidget
from ankidraft.ui.views.consultant_view.widgets.mcp_supervision_widget import MCPSupervisionWidget
from ankidraft.ui.views.consultant_view.widgets.mcp_telemetry_widget import MCPTelemetryWidget
from ankidraft.ui.views.consultant_view.widgets.mcp_tool_catalog_widget import MCPToolCatalogWidget
from ankidraft.ui.views.consultant_view.widgets.mcp_workspace_guide_widget import MCPWorkspaceGuideWidget

__all__ = [
    "InlineDiffCardWidget",
    "MCPGardeFouWidget",
    "MCPServerDashboardWidget",
    "MCPSupervisionWidget",
    "MCPTelemetryWidget",
    "MCPToolCatalogWidget",
    "MCPWorkspaceGuideWidget",
]
