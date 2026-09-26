"""
Tests unitaires et d'interface graphique headless (pytest-qt) pour MCPStatusWidget et l'intégration MCP dans la GUI.

Vérifie :
- L'affichage et la transition des états visuels du badge (#MCPStatusBadge)
- La génération et la copie dans le presse-papiers de la configuration JSON client (Claude / agy)
- La copie de l'URL SSE et du jeton Bearer
- Le flash visuel temporisé lors de mutations de données
- L'émission des signaux de pilotage (démarrage, arrêt, redémarrage, préférences)
- L'intégration de la carte MCP dans AIEnginesTab et la persistance QSettings
- La synchronisation réactive de MainWindow lors d'un signal mcp_data_mutated
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

from ankiforge.ui.preferences_dialog import PreferencesDialog, SettingsModal
from ankiforge.ui.widgets.mcp_status_widget import MCPStatusWidget
from ankiforge.ui.widgets.settings_modal.tabs.ai_engines_tab import AIEnginesTab
from ankiforge.utils.environment import get_app_qsettings

pytestmark = pytest.mark.ui


def test_preferences_dialog_compatibility_export() -> None:
    """Vérifie que PreferencesDialog est un alias direct de SettingsModal."""
    assert PreferencesDialog is SettingsModal


def test_mcp_status_widget_initial_state(qtbot: Any) -> None:
    """Vérifie l'état initial par défaut du widget de statut MCP."""
    widget = MCPStatusWidget(initial_status="stopped", initial_port=8765)
    qtbot.addWidget(widget)

    assert widget.current_status == "stopped"
    assert widget.port == 8765
    assert "Inactif" in widget.badge.text()
    assert widget.badge.property("status") == "stopped"
    assert "8765" in widget.badge.toolTip()


def test_mcp_status_widget_state_transitions(qtbot: Any) -> None:
    """Vérifie les transitions entre les états running, error, mutating et stopped."""
    widget = MCPStatusWidget(initial_status="stopped", initial_port=8765)
    qtbot.addWidget(widget)

    # Transition vers running
    widget.set_status("running", port=9000, host="127.0.0.1", token="secret-token-xyz")
    assert widget.current_status == "running"
    assert widget.port == 9000
    assert widget.token == "secret-token-xyz"
    assert "Serveur MCP :9000" in widget.badge.text()
    assert widget.badge.property("status") == "running"
    assert "http://127.0.0.1:9000/sse" in widget.badge.toolTip()

    # Repli de la sidebar (état collapsed: icône seule, texte vide, infobulle préservée)
    widget.set_collapsed(True)
    assert widget.badge.text() == ""
    assert "http://127.0.0.1:9000/sse" in widget.badge.toolTip()
    widget.set_collapsed(False)
    assert "Serveur MCP :9000" in widget.badge.text()

    # Transition vers error
    widget.set_status("error", message="Port déjà utilisé")
    assert widget.current_status == "error"
    assert "Serveur MCP (Erreur)" in widget.badge.text()
    assert widget.badge.property("status") == "error"
    assert "Port déjà utilisé" in widget.badge.toolTip()

    # Transition vers mutating
    widget.set_status("mutating")
    assert widget.current_status == "mutating"
    assert "Serveur MCP (Mutation...)" in widget.badge.text()
    assert widget.badge.property("status") == "mutating"

    # Transition retour à stopped
    widget.set_status("stopped", port=8765)
    assert widget.current_status == "stopped"
    assert "Serveur MCP (Inactif)" in widget.badge.text()
    assert widget.badge.property("status") == "stopped"


def test_mcp_status_widget_client_config(qtbot: Any) -> None:
    """Vérifie la génération du JSON de configuration pour Claude Desktop et Antigravity."""
    widget = MCPStatusWidget(initial_status="running", initial_port=8765)
    qtbot.addWidget(widget)
    widget.token = "test-token-12345"

    config = widget.get_client_config()
    assert "mcpServers" in config
    assert "ankiforge" in config["mcpServers"]
    assert config["mcpServers"]["ankiforge"]["url"] == "http://127.0.0.1:8765/sse"
    assert config["mcpServers"]["ankiforge"]["headers"]["Authorization"] == "Bearer test-token-12345"

    config_json = widget.get_client_config_json()
    parsed = json.loads(config_json)
    assert parsed == config


def test_mcp_status_widget_clipboard_copies(qtbot: Any) -> None:
    """Vérifie les copies dans le presse-papiers pour la config JSON, l'URL SSE et le token."""
    widget = MCPStatusWidget(initial_status="running", initial_port=8765)
    qtbot.addWidget(widget)
    widget.token = "bearer-token-abc"

    clipboard = QGuiApplication.clipboard()
    assert clipboard is not None

    # Copie configuration JSON
    widget.copy_client_config()
    assert "http://127.0.0.1:8765/sse" in clipboard.text()
    assert "bearer-token-abc" in clipboard.text()

    # Copie URL SSE
    widget.copy_sse_url()
    assert clipboard.text() == "http://127.0.0.1:8765/sse"

    # Copie Token
    widget.copy_token()
    assert clipboard.text() == "bearer-token-abc"


def test_mcp_status_widget_mutation_flash(qtbot: Any) -> None:
    """Vérifie que flash_mutation passe temporairement en 'mutating' puis restaure l'état précédent."""
    widget = MCPStatusWidget(initial_status="running", initial_port=8765)
    qtbot.addWidget(widget)

    assert widget.current_status == "running"

    widget.flash_mutation(duration_ms=60)
    assert widget.current_status == "mutating"
    assert widget.badge.property("status") == "mutating"

    # Attente de l'expiration du timer
    qtbot.wait(100)

    assert widget.current_status == "running"
    assert widget.badge.property("status") == "running"


def test_mcp_status_widget_signals(qtbot: Any) -> None:
    """Vérifie l'émission des signaux de pilotage du widget."""
    widget = MCPStatusWidget(initial_status="stopped", initial_port=8765)
    qtbot.addWidget(widget)

    with qtbot.waitSignal(widget.start_requested, timeout=1000):
        widget.start_requested.emit()

    with qtbot.waitSignal(widget.stop_requested, timeout=1000):
        widget.stop_requested.emit()

    with qtbot.waitSignal(widget.restart_requested, timeout=1000):
        widget.restart_requested.emit()

    with qtbot.waitSignal(widget.open_preferences_requested, timeout=1000):
        widget.open_preferences_requested.emit()


def test_ai_engines_tab_mcp_persistence(qtbot: Any) -> None:
    """Vérifie la présence des contrôles MCP dans AIEnginesTab et leur persistance dans QSettings."""
    q_settings = get_app_qsettings()
    q_settings.setValue("mcp/enabled", True)
    q_settings.setValue("mcp/port", 8765)

    tab = AIEnginesTab()
    qtbot.addWidget(tab)

    assert hasattr(tab, "chk_mcp_enabled")
    assert hasattr(tab, "spin_mcp_port")
    assert tab.chk_mcp_enabled.isChecked() is True
    assert tab.spin_mcp_port.value() == 8765

    # Modification des valeurs
    tab.chk_mcp_enabled.setChecked(False)
    tab.spin_mcp_port.setValue(9123)

    assert tab.has_pending_changes() is True

    # Sauvegarde
    tab.save_tab()

    assert q_settings.value("mcp/enabled", type=bool) is False
    assert q_settings.value("mcp/port", type=int) == 9123

    # Rétablissement pour les tests suivants
    q_settings.setValue("mcp/enabled", True)
    q_settings.setValue("mcp/port", 8765)


def test_main_window_mcp_integration(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la présence du widget MCP dans la barre d'état et la réactivité au signal mcp_data_mutated."""
    from ankiforge.ui.main_window import MainWindow

    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None, profile_name="test_mcp_profile")
        qtbot.addWidget(window)

        assert hasattr(window, "mcp_status_widget")
        assert window.mcp_status_widget is not None
        assert hasattr(window, "mcp_data_mutated")

        # Mock d'une vue avec refresh_data
        mock_view = QWidget()
        mock_view.refresh_data = MagicMock()  # type: ignore[attr-defined]
        window._view_widgets["mock_view"] = mock_view

        # Émission du signal via _on_mcp_data_mutated
        mutation_payload = {"action": "apply_patch", "note_ids": [101, 102]}

        with qtbot.waitSignal(window.mcp_data_mutated, timeout=1000) as blocker:
            window._on_mcp_data_mutated(mutation_payload)

        assert blocker.args[0] == mutation_payload
        mock_view.refresh_data.assert_called_once()
        assert window.mcp_status_widget.current_status == "mutating"

        # Vérification arrêt propre sur closeEvent
        window.close()
