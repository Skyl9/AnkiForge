"""Tests headless PySide6 pour MCPServerView (ADR 0034 §4).

Vérifie l'affichage plein écran à 100%, l'absence de splitter/chat in-app,
la présence du tableau de bord avec ses 5 sous-onglets, et le bon relai des signaux de daemon.
"""

from __future__ import annotations

import pytest

from ankiforge.ui.views.consultant_view import ConsultantView, MCPServerView
from ankiforge.ui.views.consultant_view.widgets.mcp_dashboard_widget import MCPServerDashboardWidget

pytestmark = pytest.mark.ui


def test_mcp_server_view_instantiation_and_fullscreen(qtbot, mock_db):
    """Vérifie que MCPServerView héberge MCPServerDashboardWidget en plein écran sans splitter de chat."""
    view = MCPServerView()
    qtbot.addWidget(view)
    view.show()

    # Vérification de l'alias
    assert ConsultantView is MCPServerView

    # Vérifier que le layout racine est un QVBoxLayout contenant uniquement le tableau de bord (100% largeur)
    assert not hasattr(view, "splitter"), "MCPServerView ne doit pas avoir de splitter racine."
    assert not hasattr(view, "chat_panel"), "MCPServerView ne doit pas avoir de panneau de discussion."
    assert not hasattr(view, "context_panel"), "MCPServerView ne doit pas avoir de panneau de contexte."

    assert view.layout() is not None
    assert view.layout().count() == 1
    assert view.layout().itemAt(0).widget() is view.mcp_dashboard

    # Vérifier la présence du tableau de bord déployé
    assert hasattr(view, "mcp_dashboard")
    assert isinstance(view.mcp_dashboard, MCPServerDashboardWidget)
    assert view.mcp_dashboard.isVisible()

    # Vérifier la présence des 5 sous-onglets via SegmentedTabBar
    assert hasattr(view.mcp_dashboard, "sub_tab_bar")
    assert view.mcp_dashboard.sub_tab_bar.count() == 5


def test_mcp_server_view_signals_relay(qtbot, mock_db):
    """Vérifie que les signaux de commande du serveur MCP sont bien relayés vers MainWindow."""
    view = MCPServerView()
    qtbot.addWidget(view)

    start_calls: list[bool] = []
    stop_calls: list[bool] = []
    restart_calls: list[bool] = []
    rotate_calls: list[bool] = []

    view.mcp_start_requested.connect(lambda: start_calls.append(True))
    view.mcp_stop_requested.connect(lambda: stop_calls.append(True))
    view.mcp_restart_requested.connect(lambda: restart_calls.append(True))
    view.mcp_rotate_token_requested.connect(lambda: rotate_calls.append(True))

    # Émettre depuis le widget interne
    view.mcp_dashboard.start_requested.emit()
    assert len(start_calls) == 1

    view.mcp_dashboard.stop_requested.emit()
    assert len(stop_calls) == 1

    view.mcp_dashboard.restart_requested.emit()
    assert len(restart_calls) == 1

    view.mcp_dashboard.rotate_token_requested.emit()
    assert len(rotate_calls) == 1


def test_mcp_server_view_theme_refresh(qtbot, mock_db):
    """Vérifie que refresh_theme ne lève aucune exception et s'exécute proprement."""
    from ankiforge.ui.style_engine import get_style_engine

    view = MCPServerView()
    qtbot.addWidget(view)

    profile = get_style_engine().current_theme
    view.refresh_theme(profile)
