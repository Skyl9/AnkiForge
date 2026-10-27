"""Tests d'unification des marges/espacements du cockpit MCP."""

import sys

from PySide6.QtWidgets import QApplication

from ankiforge.ui.views.consultant_view.widgets.mcp_garde_fou_widget import (
    MCPGardeFouWidget,
)
from ankiforge.ui.views.consultant_view.widgets.mcp_supervision_widget import (
    MCPSupervisionWidget,
)
from ankiforge.ui.views.consultant_view.widgets.mcp_telemetry_widget import (
    MCPTelemetryWidget,
)
from ankiforge.ui.views.consultant_view.widgets.mcp_tool_catalog_widget import (
    MCPToolCatalogWidget,
)
from ankiforge.ui.views.consultant_view.widgets.mcp_workspace_guide_widget import (
    MCPWorkspaceGuideWidget,
)


def test_mcp_cockpit_widgets_share_unified_spacing(qtbot):
    """Tous les 5 sous-onglets du cockpit MCP partagent mêmes marges/espacements."""
    if QApplication.instance() is None:
        QApplication(sys.argv)

    widgets = [
        MCPSupervisionWidget(),
        MCPGardeFouWidget(),
        MCPTelemetryWidget(),
        MCPToolCatalogWidget(),
        MCPWorkspaceGuideWidget(),
    ]
    for w in widgets:
        qtbot.addWidget(w)

    refs = []
    for w in widgets:
        layout = w.layout()
        assert layout is not None, f"{w.__class__.__name__} doit avoir un layout racine"
        m = layout.contentsMargins()
        refs.append((m.left(), m.top(), m.right(), m.bottom(), layout.spacing()))

    first = refs[0]
    for ref in refs[1:]:
        assert ref == first, f"Espacements incohérents: {refs}"
