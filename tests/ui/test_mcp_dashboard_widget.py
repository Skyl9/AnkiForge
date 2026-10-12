"""Tests unitaires et UI pour MCPServerDashboardWidget."""

from __future__ import annotations

import json

import pytest
from PySide6.QtGui import QGuiApplication

from ankiforge.ui.views.consultant_view.widgets.mcp_dashboard_widget import (
    MCPServerDashboardWidget,
)

pytestmark = pytest.mark.ui


def test_mcp_dashboard_widget_initialization(qtbot) -> None:
    """Vérifie l'initialisation du tableau de bord MCP et l'état par défaut (arrêté)."""
    widget = MCPServerDashboardWidget(initial_status="stopped", initial_port=8765, initial_token="test_token_123")
    qtbot.addWidget(widget)

    assert widget.current_status == "stopped"
    assert widget.port == 8765
    assert widget.token == "test_token_123"
    assert "8765" in widget.url
    assert widget.url.endswith("/mcp")
    assert widget.sse_url.endswith("/sse")

    # Boutons de cycle de vie : Démarrer actif, Arrêter et Redémarrer inactifs
    assert widget.btn_start.isEnabled()
    assert not widget.btn_stop.isEnabled()
    assert not widget.btn_restart.isEnabled()

    # Le bandeau de requête contextuelle est masqué au départ
    assert not widget.banner_context_request.isVisible()


def test_mcp_dashboard_widget_set_status(qtbot) -> None:
    """Vérifie la mise à jour dynamique de statut, port et token."""
    widget = MCPServerDashboardWidget(initial_status="stopped", initial_port=8765)
    qtbot.addWidget(widget)

    widget.set_status("running", port=9090, token="new_bearer_token")

    assert widget.current_status == "running"
    assert widget.port == 9090
    assert widget.token == "new_bearer_token"
    assert "9090" in widget.url

    # En cours d'exécution : Démarrer inactif, Arrêter et Redémarrer actifs
    assert not widget.btn_start.isEnabled()
    assert widget.btn_stop.isEnabled()
    assert widget.btn_restart.isEnabled()


def test_mcp_dashboard_widget_lifecycle_signals(qtbot) -> None:
    """Vérifie l'émission des signaux de pilotage du démon."""
    widget = MCPServerDashboardWidget(initial_status="stopped")
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


def test_mcp_dashboard_widget_snippets_generation(qtbot) -> None:
    """Vérifie que les 4 snippets de configuration client sont valides et contiennent l'URL et le jeton."""
    widget = MCPServerDashboardWidget(initial_status="running", initial_port=8765, initial_token="secret_abc")
    qtbot.addWidget(widget)

    # 1. Claude
    claude_cfg = widget.get_snippet_config("claude")
    parsed_claude = json.loads(claude_cfg)
    assert "mcpServers" in parsed_claude
    assert parsed_claude["mcpServers"]["ankiforge"]["url"] == "http://127.0.0.1:8765/mcp"
    assert parsed_claude["mcpServers"]["ankiforge"]["headers"]["Authorization"] == "Bearer secret_abc"

    # 2. Antigravity agy
    agy_cfg = widget.get_snippet_config("agy")
    parsed_agy = json.loads(agy_cfg)
    assert parsed_agy["name"] == "ankiforge"
    assert parsed_agy["url"] == "http://127.0.0.1:8765/mcp"

    # 3. Cursor
    cursor_cfg = widget.get_snippet_config("cursor")
    parsed_cursor = json.loads(cursor_cfg)
    assert "mcpServers" in parsed_cursor

    # 4. cURL
    curl_snippet = widget.get_snippet_config("curl")
    assert "curl" in curl_snippet
    assert "http://127.0.0.1:8765/mcp" in curl_snippet
    assert "Bearer secret_abc" in curl_snippet


def test_mcp_dashboard_widget_copy_config(qtbot) -> None:
    """Vérifie la copie du snippet courant dans le presse-papiers."""
    widget = MCPServerDashboardWidget(initial_status="running", initial_port=8765, initial_token="secret_xyz")
    qtbot.addWidget(widget)

    widget.copy_current_snippet()
    clipboard = QGuiApplication.clipboard()
    assert clipboard is not None
    text = clipboard.text()
    assert "http://127.0.0.1:8765/mcp" in text
    assert "Bearer secret_xyz" in text


def test_mcp_dashboard_widget_pending_request_banner(qtbot) -> None:
    """Vérifie l'affichage, la copie et la fermeture du bandeau de requête contextuelle."""
    widget = MCPServerDashboardWidget(initial_status="running", initial_port=8765, initial_token="secret_xyz")
    qtbot.addWidget(widget)

    widget.show()
    assert widget.banner_context_request.isHidden()

    context_item = {"type": "note", "id": 42, "model_name": "Basic", "deck": "Default"}
    prompt = "Analyse et propose 2 questions atomiques sur cette note."

    widget.set_pending_request(context_item, prompt)

    assert not widget.banner_context_request.isHidden()
    assert "42" in widget.lbl_request_context.text() or "note" in widget.lbl_request_context.text()

    # Copie du prompt
    widget.btn_copy_request_prompt.click()
    clipboard = QGuiApplication.clipboard()
    assert clipboard is not None
    assert prompt in clipboard.text()

    # Fermeture du bandeau
    widget.btn_dismiss_request.click()
    assert widget.banner_context_request.isHidden()
    assert widget.pending_request is None


def test_mcp_dashboard_widget_no_border_cascade_on_children(qtbot) -> None:
    """Vérifie que les conteneurs QFrame sont scopés par ID et qu'aucun QLabel enfant n'hérite de bordure parasite."""
    from ankiforge.ui.style_engine import JETBRAINS_LIGHT

    widget = MCPServerDashboardWidget(initial_status="running", initial_port=8765, initial_token="secret_xyz")
    qtbot.addWidget(widget)

    # 1. Vérification que les cartes et bandeaux ont des objectName explicites
    assert widget.card_lifecycle.objectName() == "mcp_card_lifecycle"
    assert widget.card_endpoints.objectName() == "mcp_card_endpoints"
    assert widget.card_snippets.objectName() == "mcp_card_snippets"
    assert widget.banner_context_request.objectName() == "mcp_banner_context_request"

    # 2. Vérification que les sélecteurs sont scopés par ID (#...) et neutralisent les QLabel
    for card_name in ("mcp_card_lifecycle", "mcp_card_endpoints", "mcp_card_snippets"):
        card = getattr(widget, card_name.replace("mcp_", ""))
        style = card.styleSheet()
        assert f"#{card_name}" in style
        assert "border: none" in style
        assert "background: transparent" in style

    # 3. Vérification que les labels critiques ont un border: none explicite
    assert "border: none" in widget.lbl_port_info.styleSheet()
    assert "border: none" in widget.lbl_transport_info.styleSheet()
    assert "border: none" in widget.lbl_snippet_hint.styleSheet()

    # 4. Vérification après rafraîchissement de thème
    widget.refresh_theme(JETBRAINS_LIGHT)
    for card_name in ("mcp_card_lifecycle", "mcp_card_endpoints", "mcp_card_snippets", "mcp_card_activity"):
        card = getattr(widget, card_name.replace("mcp_", ""))
        style = card.styleSheet()
        assert f"#{card_name}" in style
        assert "border: none" in style
        assert "background: transparent" in style


def test_mcp_dashboard_activity_empty_state_and_live_updates(qtbot) -> None:
    """Vérifie l'état vide par défaut puis les mises à jour réactives de l'historique d'activité."""
    from ankiforge.services.ai.mcp_tracker import get_mcp_activity_tracker, reset_mcp_activity_tracker

    reset_mcp_activity_tracker()
    tracker = get_mcp_activity_tracker()

    widget = MCPServerDashboardWidget(initial_status="running", initial_port=8765)
    qtbot.addWidget(widget)
    widget.show()

    # 1. État vide
    assert widget.table_activity.isHidden()
    assert not widget.lbl_empty_activity.isHidden()
    assert "0 appel" in widget.badge_activity_count.text()
    assert not widget.btn_clear_activity.isEnabled()

    # 2. Démarrage d'un appel
    cid = tracker.start_tracking("audit_deck_wozniak", {"deck_name": "Grammaire"})
    qtbot.wait(100)

    assert not widget.table_activity.isHidden()
    assert widget.lbl_empty_activity.isHidden()
    assert widget.table_activity.rowCount() == 1
    assert "1 appel" in widget.badge_activity_count.text()
    assert widget.btn_clear_activity.isEnabled()

    # Vérifie le contenu de la première ligne
    assert widget.table_activity.item(0, 1).text() == "audit_deck_wozniak"
    assert "Grammaire" in widget.table_activity.item(0, 4).text()
    assert widget.table_activity.item(0, 3).text() == "—"

    # 3. Fin avec succès
    tracker.record_success(cid, "Audit terminé sans anomalie", duration_ms=42.5)
    qtbot.wait(50)

    assert widget.table_activity.rowCount() == 1
    assert "42.5 ms" in widget.table_activity.item(0, 3).text()

    # 4. Deuxième appel avec erreur
    cid2 = tracker.start_tracking("find_duplicate_cards", {"threshold": 0.9})
    qtbot.wait(50)
    assert widget.table_activity.rowCount() == 2
    assert "2 appels" in widget.badge_activity_count.text()

    tracker.record_error(cid2, "Erreur connexion DB", duration_ms=15.0)
    qtbot.wait(50)
    assert "15.0 ms" in widget.table_activity.item(0, 3).text()

    # 5. Vidage de l'historique
    widget.btn_clear_activity.click()
    qtbot.wait(50)

    assert widget.table_activity.rowCount() == 0
    assert widget.table_activity.isHidden()
    assert not widget.lbl_empty_activity.isHidden()
    assert "0 appel" in widget.badge_activity_count.text()
    assert not widget.btn_clear_activity.isEnabled()


def test_mcp_activity_detail_dialog(qtbot) -> None:
    """Vérifie l'affichage et les contrôles du dialogue d'inspection détaillée."""
    from datetime import datetime

    from ankiforge.services.ai.mcp_tracker import MCPActivityRecord
    from ankiforge.ui.views.consultant_view.widgets.mcp_dashboard_widget import (
        MCPActivityDetailDialog,
    )

    record = MCPActivityRecord(
        call_id="call1234",
        tool_name="propose_card_refactor",
        started_at=datetime(2026, 10, 12, 14, 30, 0),
        ended_at=datetime(2026, 10, 12, 14, 30, 1),
        duration_ms=150.2,
        status="success",
        args_summary="note_id=42, explanation='Correction typo'",
        args_full={"note_id": 42, "explanation": "Correction typo"},
        result_summary="Patch généré avec succès",
        result_full='{"status": "applied", "note_id": 42}',
    )

    dialog = MCPActivityDetailDialog(record)
    qtbot.addWidget(dialog)

    assert "propose_card_refactor" in dialog.windowTitle()
    assert "note_id" in dialog.edit_args.toPlainText()
    assert "Correction typo" in dialog.edit_args.toPlainText()
    assert "Patch généré" in dialog.edit_result.toPlainText() or "applied" in dialog.edit_result.toPlainText()

    # Test bouton copier en JSON
    dialog.btn_copy_json.click()
    clipboard = QGuiApplication.clipboard()
    assert clipboard is not None
    copied_text = clipboard.text()
    assert "propose_card_refactor" in copied_text
    assert "call1234" in copied_text
