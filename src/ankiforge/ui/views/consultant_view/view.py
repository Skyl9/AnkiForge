"""Vue principale Serveur MCP & Agents (MCPServerView) — Centrage plein écran sans chat in-app (ADR 0043).

Héberge le cockpit opérationnel MCPServerDashboardWidget déployé sur 100 % de la largeur d'écran,
avec les 5 sous-onglets officiels (Supervision, Garde-Fou, Catalogue, Activité, Guides & Workspaces).
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ankiforge.ui.views.consultant_view.widgets.mcp_dashboard_widget import MCPServerDashboardWidget

logger = logging.getLogger(__name__)


class MCPServerView(QWidget):
    """Cockpit unifié du Serveur MCP & Agents en plein écran (ADR 0043)."""

    request_navigation = Signal(str, object)
    mcp_start_requested = Signal()
    mcp_stop_requested = Signal()
    mcp_restart_requested = Signal()
    mcp_rotate_token_requested = Signal()

    def __init__(
        self,
        ai_manager: Any | None = None,
        profile_name: str = "default",
        parent: QWidget | None = None,
        shortcut_manager: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.profile_name = profile_name
        self._shortcut_manager = shortcut_manager

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.mcp_dashboard = MCPServerDashboardWidget(
            initial_status="stopped",
            parent=self,
        )
        self.mcp_dashboard.start_requested.connect(self.mcp_start_requested.emit)
        self.mcp_dashboard.stop_requested.connect(self.mcp_stop_requested.emit)
        self.mcp_dashboard.restart_requested.connect(self.mcp_restart_requested.emit)
        self.mcp_dashboard.rotate_token_requested.connect(self.mcp_rotate_token_requested.emit)
        self.mcp_dashboard.open_preferences_requested.connect(self._on_open_preferences_requested)

        layout.addWidget(self.mcp_dashboard)

    def _on_open_preferences_requested(self) -> None:
        self.request_navigation.emit("settings", {"tab": "ai_engines"})

    def refresh_theme(self, profile: Any) -> None:
        """Applique les jetons de thème au tableau de bord MCP."""
        if hasattr(self, "mcp_dashboard") and hasattr(self.mcp_dashboard, "refresh_theme"):
            self.mcp_dashboard.refresh_theme(profile)

    def refresh_data(self) -> None:
        """Rafraîchit passivement les sous-composants du serveur MCP."""
        if hasattr(self, "mcp_dashboard") and hasattr(self.mcp_dashboard, "refresh_data"):
            self.mcp_dashboard.refresh_data()
        elif hasattr(self, "mcp_dashboard") and hasattr(self.mcp_dashboard, "garde_fou_widget"):
            self.mcp_dashboard.garde_fou_widget.reload_pending_patches()

    def apply_mcp_mutation(self, mutation: dict[str, Any]) -> None:
        """Applique une mise à jour granulaire sans recharger toute la vue (ADR 0043)."""
        self.refresh_data()


# Alias de rétrocompatibilité ascendante (ADR 0043)
ConsultantView = MCPServerView
