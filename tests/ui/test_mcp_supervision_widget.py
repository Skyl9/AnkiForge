"""Tests unitaires et UI pour MCPSupervisionWidget (cockpit 2 colonnes sans défilement)."""

from __future__ import annotations

import json

import pytest
from PySide6.QtGui import QGuiApplication

from ankidraft.ui.components.tabs.segmented_tab_bar import SegmentedTabBar
from ankidraft.ui.views.consultant_view.widgets.mcp_supervision_widget import (
    MCPSupervisionWidget,
)

pytestmark = pytest.mark.ui


def test_mcp_supervision_widget_initialization(qtbot) -> None:
    """Vérifie l'initialisation du cockpit de supervision en 2 colonnes."""
    widget = MCPSupervisionWidget(
        initial_status="stopped",
        initial_port=8765,
        initial_token="test_token_supervision",
    )
    qtbot.addWidget(widget)

    assert widget.current_status == "stopped"
    assert widget.port == 8765
    assert widget.token == "test_token_supervision"
    assert widget.url == "http://127.0.0.1:8765/mcp"
    assert widget.sse_url == "http://127.0.0.1:8765/sse"

    # Contrôles de cycle de vie
    assert widget.btn_start.isEnabled()
    assert not widget.btn_stop.isEnabled()
    assert not widget.btn_restart.isEnabled()
    assert widget.btn_rotate_token.isEnabled()

    # Présence des cartes attendues
    assert widget.card_lifecycle.objectName() == "mcp_card_lifecycle"
    assert widget.card_endpoints.objectName() == "mcp_card_endpoints"
    assert widget.card_snippets.objectName() == "mcp_card_snippets"

    # Bandeau contextuel masqué
    assert widget.banner_context_request.isHidden()


def test_mcp_supervision_widget_set_status(qtbot) -> None:
    """Vérifie la mise à jour dynamique de l'état du serveur MCP."""
    widget = MCPSupervisionWidget(initial_status="stopped", initial_port=8765)
    qtbot.addWidget(widget)

    widget.set_status("running", port=9090, token="token_active")

    assert widget.current_status == "running"
    assert widget.port == 9090
    assert widget.token == "token_active"
    assert "9090" in widget.url

    # État actif : Démarrer désactivé, Arrêter et Redémarrer activés
    assert not widget.btn_start.isEnabled()
    assert widget.btn_stop.isEnabled()
    assert widget.btn_restart.isEnabled()
    assert widget.status_badge.text() == "Actif"


def test_mcp_supervision_widget_lifecycle_signals(qtbot) -> None:
    """Vérifie l'émission de tous les signaux de cycle de vie et préférences."""
    widget = MCPSupervisionWidget(initial_status="stopped")
    qtbot.addWidget(widget)

    with qtbot.waitSignal(widget.start_requested, timeout=1000):
        widget.btn_start.click()

    widget.set_status("running")

    with qtbot.waitSignal(widget.stop_requested, timeout=1000):
        widget.btn_stop.click()

    with qtbot.waitSignal(widget.restart_requested, timeout=1000):
        widget.btn_restart.click()

    with qtbot.waitSignal(widget.rotate_token_requested, timeout=1000):
        widget.btn_rotate_token.click()

    with qtbot.waitSignal(widget.open_preferences_requested, timeout=1000):
        widget.btn_open_prefs.click()


def test_mcp_supervision_widget_snippets(qtbot) -> None:
    """Vérifie les configurations client générées et la copie en presse-papiers."""
    widget = MCPSupervisionWidget(
        initial_status="running",
        initial_port=8765,
        initial_token="secret_supervision",
    )
    qtbot.addWidget(widget)

    # Claude
    claude_cfg = widget.get_snippet_config("claude")
    parsed_claude = json.loads(claude_cfg)
    assert parsed_claude["mcpServers"]["ankidraft"]["headers"]["Authorization"] == "Bearer secret_supervision"

    # agy
    agy_cfg = widget.get_snippet_config("agy")
    parsed_agy = json.loads(agy_cfg)
    assert parsed_agy["name"] == "ankidraft"

    # Cursor
    cursor_cfg = widget.get_snippet_config("cursor")
    parsed_cursor = json.loads(cursor_cfg)
    assert "mcpServers" in parsed_cursor

    # cURL
    curl_cfg = widget.get_snippet_config("curl")
    assert "curl" in curl_cfg
    assert "Bearer secret_supervision" in curl_cfg

    # Changement d'onglet client (1 = agy)
    assert isinstance(widget.tab_bar_clients, SegmentedTabBar)
    assert widget.tab_bar_clients.count() == 4
    widget.tab_bar_clients.setCurrentIndex(1)
    assert "ankidraft.json" in widget.lbl_snippet_hint.text()
    assert "ankidraft" in widget.edit_snippet_code.toPlainText()

    # Copie
    widget.copy_current_snippet()
    clipboard = QGuiApplication.clipboard()
    assert clipboard is not None
    assert "ankidraft" in clipboard.text()


def test_mcp_supervision_widget_token_toggle_and_copy(qtbot) -> None:
    """Vérifie le masquage/démasquage et la copie du jeton Bearer."""
    widget = MCPSupervisionWidget(
        initial_status="running",
        initial_port=8765,
        initial_token="token_reveal_me",
    )
    qtbot.addWidget(widget)

    assert "••••" in widget.edit_token.text()

    # Démasquer
    widget.toggle_token_visibility()
    assert widget.edit_token.text() == "token_reveal_me"

    # Remasquer
    widget.toggle_token_visibility()
    assert "••••" in widget.edit_token.text()

    # Copier
    widget.copy_token()
    clipboard = QGuiApplication.clipboard()
    assert clipboard is not None
    assert clipboard.text() == "token_reveal_me"


def test_mcp_supervision_widget_endpoints_copy(qtbot) -> None:
    """Vérifie la copie des URLs Streamable HTTP et SSE."""
    widget = MCPSupervisionWidget(initial_status="running", initial_port=8765)
    qtbot.addWidget(widget)

    widget.copy_url()
    clipboard = QGuiApplication.clipboard()
    assert clipboard is not None
    assert clipboard.text() == "http://127.0.0.1:8765/mcp"

    widget.copy_sse_url()
    assert clipboard.text() == "http://127.0.0.1:8765/sse"


def test_mcp_supervision_widget_client_tab_bar_segmented(qtbot) -> None:
    """Vérifie que tab_bar_clients est un SegmentedTabBar avec 4 onglets et que le changement d'index rafraîchit la vue snippet."""
    widget = MCPSupervisionWidget(initial_status="running", initial_port=8765, initial_token="tok")
    qtbot.addWidget(widget)

    assert isinstance(widget.tab_bar_clients, SegmentedTabBar)
    assert widget.tab_bar_clients.count() == 4
    assert widget.tab_bar_clients.tabText(0) == widget.tr("Claude")
    assert widget.tab_bar_clients.tabText(1) == widget.tr("Antigravity (agy)")
    assert widget.tab_bar_clients.tabText(2) == widget.tr("Cursor")
    assert widget.tab_bar_clients.tabText(3) == widget.tr("cURL")
    assert widget.tab_bar_clients.get_active_index() == 0

    with qtbot.waitSignal(widget.tab_bar_clients.tab_index_changed, timeout=1000):
        widget.tab_bar_clients.setCurrentIndex(2)

    assert widget.tab_bar_clients.get_active_index() == 2
    assert widget._active_snippet_key == "cursor"
    assert "Cursor" in widget.lbl_snippet_hint.text()
    assert "mcp.json" in widget.lbl_snippet_hint.text()
    assert '"mcpServers"' in widget.edit_snippet_code.toPlainText()

    # accessibleName renseigné sur chaque bouton
    for btn in widget.tab_bar_clients._tabs:
        assert btn.accessibleName()


def test_mcp_supervision_widget_pending_request_banner(qtbot) -> None:
    """Vérifie le comportement du bandeau rétractable de requête contextuelle."""
    widget = MCPSupervisionWidget(initial_status="running")
    qtbot.addWidget(widget)
    widget.show()

    assert widget.banner_context_request.isHidden()

    widget.set_pending_request({"type": "deck", "id": "Vocabulaire"}, "Créer 5 cartes d'anglais.")
    assert not widget.banner_context_request.isHidden()
    assert "Vocabulaire" in widget.lbl_request_context.text()

    widget.btn_copy_request_prompt.click()
    clipboard = QGuiApplication.clipboard()
    assert clipboard is not None
    assert "Créer 5 cartes d'anglais." in clipboard.text()

    widget.btn_dismiss_request.click()
    assert widget.banner_context_request.isHidden()
    assert widget.pending_request is None


def test_mcp_supervision_widget_theme_refresh(qtbot) -> None:
    """Vérifie l'adaptation aux thèmes et l'absence de cascade parasite de bordure."""
    from ankidraft.ui.style_engine import JETBRAINS_DARK, JETBRAINS_LIGHT

    widget = MCPSupervisionWidget(initial_status="running")
    qtbot.addWidget(widget)

    widget.refresh_theme(JETBRAINS_LIGHT)
    assert "mcp_card_lifecycle" in widget.card_lifecycle.styleSheet()
    assert "border: none" in widget.lbl_port_info.styleSheet()

    widget.refresh_theme(JETBRAINS_DARK)
    assert "mcp_card_snippets" in widget.card_snippets.styleSheet()
    assert "border: none" in widget.lbl_snippet_hint.styleSheet()


def test_mcp_supervision_widget_ping_and_uptime(qtbot, monkeypatch) -> None:
    """Vérifie le fonctionnement du ping et l'affichage de l'uptime."""
    widget = MCPSupervisionWidget(initial_status="stopped", initial_port=8765)
    qtbot.addWidget(widget)

    # Quand le serveur est arrêté
    assert not widget.btn_ping.isEnabled()
    widget.test_connection_ping()
    assert "arrêté" in widget.lbl_ping_result.text()

    # Quand le serveur passe à running
    widget.set_status("running", port=8765, token="tok_test_ping")
    assert widget.btn_ping.isEnabled()
    assert "Uptime" in widget.lbl_uptime.text()
    assert widget.status_badge.text() == widget.tr("Actif")

    # Tester le ping réussi
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: FakeResponse())

    widget.test_connection_ping()
    qtbot.waitUntil(lambda: "200 OK" in widget.lbl_ping_result.text(), timeout=2000)


def test_mcp_supervision_widget_quick_exports_and_flash(qtbot) -> None:
    """Vérifie la copie de la commande export ENV et de l'URL authentifiée avec feedback bouton."""
    widget = MCPSupervisionWidget(
        initial_status="running",
        initial_port=8765,
        initial_token="super_secret_token_abc123",
    )
    qtbot.addWidget(widget)

    # Export Shell
    widget.copy_env_export()
    clipboard = QGuiApplication.clipboard()
    assert clipboard is not None
    assert "export ANKIFORGE_MCP_TOKEN=super_secret_token_abc123" in clipboard.text()
    assert widget.btn_copy_env_export.text() == widget.tr("Copié !")

    # URL avec jeton
    widget.copy_authenticated_url()
    assert "http://127.0.0.1:8765/mcp?token=super_secret_token_abc123" in clipboard.text()
    assert widget.btn_copy_auth_url.text() == widget.tr("Copié !")


def test_mcp_supervision_widget_kpi_listeners(qtbot) -> None:
    """Vérifie la mise à jour des mini-KPIs d'activité en temps réel."""
    from ankidraft.services.ai.mcp_tracker import get_mcp_activity_tracker

    tracker = get_mcp_activity_tracker()
    widget = MCPSupervisionWidget(initial_status="running", initial_port=8765)
    qtbot.addWidget(widget)

    # Simuler un événement de tracking
    tracker.signals.activity_started.emit({"tool_name": "audit_deck_wozniak"})
    qtbot.waitUntil(lambda: widget.lbl_kpi_last_tool.text() == "audit_deck_wozniak", timeout=2000)

    # Simuler la purge
    tracker.signals.history_cleared.emit()
    qtbot.waitUntil(lambda: widget.lbl_kpi_calls.text() == "0", timeout=2000)
    assert widget.lbl_kpi_last_tool.text() == widget.tr("Aucun appel")


def test_mcp_supervision_widget_open_client_config(qtbot, tmp_path, monkeypatch) -> None:
    """Vérifie l'ouverture ou la création du fichier de configuration client."""
    widget = MCPSupervisionWidget(initial_status="running", initial_port=8765, initial_token="tok_cfg")
    qtbot.addWidget(widget)

    fake_config_file = tmp_path / "claude" / "claude_desktop_config.json"
    monkeypatch.setattr(widget, "_get_client_config_path", lambda client: fake_config_file)

    opened_urls: list[str] = []
    from PySide6.QtGui import QDesktopServices

    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened_urls.append(url.toString()) or True)

    widget.open_client_config()
    assert fake_config_file.exists()
    assert "tok_cfg" in fake_config_file.read_text(encoding="utf-8")
    assert len(opened_urls) == 1


def test_mcp_supervision_widget_button_styles_and_no_pulse_dot(qtbot) -> None:
    """Vérifie l'application des styles chromatiques sur les boutons d'opérations et l'absence du pulse dot."""
    widget = MCPSupervisionWidget(initial_status="stopped", initial_port=8765)
    qtbot.addWidget(widget)

    assert not hasattr(widget, "pulse_dot")
    assert "mcp_btn_start" in widget.btn_start.styleSheet()
    assert "mcp_btn_stop" in widget.btn_stop.styleSheet()
    assert "mcp_btn_restart" in widget.btn_restart.styleSheet()

    # Changement d'état : les icônes sont colorées quand le bouton est actif
    widget.set_status("running")
    assert not widget.btn_start.isEnabled()
    assert widget.btn_stop.isEnabled()
    assert widget.btn_restart.isEnabled()
