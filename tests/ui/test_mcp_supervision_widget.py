"""Tests unitaires et UI pour MCPSupervisionWidget (cockpit 2 colonnes sans défilement)."""

from __future__ import annotations

import json

import pytest
from PySide6.QtGui import QGuiApplication

from ankiforge.ui.views.consultant_view.widgets.mcp_supervision_widget import (
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
    assert parsed_claude["mcpServers"]["ankiforge"]["headers"]["Authorization"] == "Bearer secret_supervision"

    # agy
    agy_cfg = widget.get_snippet_config("agy")
    parsed_agy = json.loads(agy_cfg)
    assert parsed_agy["name"] == "ankiforge"

    # Cursor
    cursor_cfg = widget.get_snippet_config("cursor")
    parsed_cursor = json.loads(cursor_cfg)
    assert "mcpServers" in parsed_cursor

    # cURL
    curl_cfg = widget.get_snippet_config("curl")
    assert "curl" in curl_cfg
    assert "Bearer secret_supervision" in curl_cfg

    # Changement d'onglet client (1 = agy)
    widget.tab_bar_clients.setCurrentIndex(1)
    assert "ankiforge.json" in widget.lbl_snippet_hint.text()
    assert "ankiforge" in widget.edit_snippet_code.toPlainText()

    # Copie
    widget.copy_current_snippet()
    clipboard = QGuiApplication.clipboard()
    assert clipboard is not None
    assert "ankiforge" in clipboard.text()


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
    from ankiforge.ui.style_engine import JETBRAINS_DARK, JETBRAINS_LIGHT

    widget = MCPSupervisionWidget(initial_status="running")
    qtbot.addWidget(widget)

    widget.refresh_theme(JETBRAINS_LIGHT)
    assert "mcp_card_lifecycle" in widget.card_lifecycle.styleSheet()
    assert "border: none" in widget.lbl_port_info.styleSheet()

    widget.refresh_theme(JETBRAINS_DARK)
    assert "mcp_card_snippets" in widget.card_snippets.styleSheet()
    assert "border: none" in widget.lbl_snippet_hint.styleSheet()
