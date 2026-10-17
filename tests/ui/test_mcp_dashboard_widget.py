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
    for card_name in ("mcp_card_lifecycle", "mcp_card_endpoints", "mcp_card_snippets"):
        card = getattr(widget, card_name.replace("mcp_", ""))
        style = card.styleSheet()
        assert f"#{card_name}" in style
        assert "border: none" in style
        assert "background: transparent" in style


def test_mcp_dashboard_segmented_tab_bar_integration(qtbot) -> None:
    """Vérifie l'intégration du composant officiel SegmentedTabBar en mode subtab."""
    from ankiforge.ui.components.tabs.segmented_tab_bar import SegmentedTabBar

    widget = MCPServerDashboardWidget(initial_status="running", initial_port=8765)
    qtbot.addWidget(widget)

    # 1. Le sous-onglet est bien une instance de SegmentedTabBar
    assert isinstance(widget.sub_tab_bar, SegmentedTabBar)
    assert widget.sub_tab_bar.variant == "subtab"
    assert widget.sub_tab_bar.count() == 4

    # 2. Les sous-onglets sont bien instanciés dans le QStackedWidget
    assert hasattr(widget, "supervision_widget")
    assert hasattr(widget, "telemetry_widget")
    assert widget.stacked_widget.widget(0) is widget.supervision_widget
    assert widget.stacked_widget.widget(1) is widget.garde_fou_widget
    assert widget.stacked_widget.widget(2) is widget.catalog_widget
    assert widget.stacked_widget.widget(3) is widget.telemetry_widget


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


def test_mcp_dashboard_sub_tabs_navigation(qtbot) -> None:
    """Vérifie la navigation et la synchronisation des 4 sous-onglets du tableau de bord."""
    widget = MCPServerDashboardWidget(initial_status="running", initial_port=8765)
    qtbot.addWidget(widget)

    assert hasattr(widget, "sub_tab_bar")
    assert hasattr(widget, "stacked_widget")
    assert hasattr(widget, "garde_fou_widget")
    assert hasattr(widget, "telemetry_widget")
    assert widget.sub_tab_bar.count() == 4

    # Onglet initial : 0 (Supervision)
    assert widget.sub_tab_bar.currentIndex() == 0
    assert widget.stacked_widget.currentIndex() == 0
    assert "Supervision" in widget.sub_tab_bar.tabText(0)
    assert "Garde-Fou" in widget.sub_tab_bar.tabText(1)
    assert "Catalogue" in widget.sub_tab_bar.tabText(2)
    assert "Activité" in widget.sub_tab_bar.tabText(3)

    # Bascule vers Télémétrie (3)
    widget.sub_tab_bar.setCurrentIndex(3)
    assert widget.stacked_widget.currentIndex() == 3

    # Bascule vers Garde-Fou (1)
    widget.sub_tab_bar.setCurrentIndex(1)
    assert widget.stacked_widget.currentIndex() == 1

    # Bascule vers Catalogue (2)
    widget.sub_tab_bar.setCurrentIndex(2)
    assert widget.stacked_widget.currentIndex() == 2

    # Retour vers Supervision (0)
    widget.sub_tab_bar.setCurrentIndex(0)
    assert widget.stacked_widget.currentIndex() == 0


def test_mcp_dashboard_telemetry_badge_dynamic_update(qtbot) -> None:
    """Vérifie l'actualisation dynamique du badge et du libellé Activité (N) sur le sous-onglet."""
    from ankiforge.services.ai.mcp_tracker import get_mcp_activity_tracker

    tracker = get_mcp_activity_tracker()
    tracker.clear_history()

    widget = MCPServerDashboardWidget(initial_status="running", initial_port=8765)
    qtbot.addWidget(widget)

    # État initial : Activité sans badge ou count 0
    assert "Activité" in widget.sub_tab_bar.tabText(3)
    assert "(0)" not in widget.sub_tab_bar.tabText(3)

    # Démarrage d'un appel
    _ = tracker.start_tracking("propose_card_refactor", {"note_id": 12})
    qtbot.wait(40)

    assert "(1)" in widget.sub_tab_bar.tabText(3)
    assert widget.sub_tab_bar.tab_badge("telemetrie") == "1"

    # Deuxième appel
    _ = tracker.start_tracking("list_decks", {})
    qtbot.wait(40)
    assert "(2)" in widget.sub_tab_bar.tabText(3)
    assert widget.sub_tab_bar.tab_badge("telemetrie") == "2"

    # Vidage de l'historique
    tracker.clear_history()
    qtbot.wait(40)
    assert "(2)" not in widget.sub_tab_bar.tabText(3)
    assert widget.sub_tab_bar.tab_badge("telemetrie") == ""


def test_mcp_dashboard_patch_staged_notification_and_badge(qtbot, monkeypatch) -> None:
    """Vérifie l'actualisation dynamique du badge et l'affichage d'un toast discret sans redirection forcée."""
    from ankiforge.database.models import StagedPatchModel
    from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

    StagedPatchModel.delete().execute()

    widget = MCPServerDashboardWidget(initial_status="running", initial_port=8765)
    qtbot.addWidget(widget)

    # S'assurer qu'on démarre sur l'onglet Supervision
    widget.sub_tab_bar.setCurrentIndex(0)
    assert widget.sub_tab_bar.currentIndex() == 0
    assert widget.stacked_widget.currentIndex() == 0

    # Création d'un patch staged en BDD
    patch = StagedPatchRegistry.create_patch(
        patch_type="card",
        target_id=101,
        diff_payload={"title": "Refactorisation de la note #101", "original": {"Front": "Q1"}, "modified": {"Front": "Q1 modifiée"}},
    )
    patch_id = patch.patch_id

    # Simulation d'arrivée de patch
    widget.on_patch_staged({"patch_id": patch_id, "note_id": 101, "title": "Refactorisation de la note #101"})
    qtbot.wait(50)

    # 1. Pas de bascule forcée
    assert widget.sub_tab_bar.currentIndex() == 0
    assert widget.stacked_widget.currentIndex() == 0

    # 2. Le texte de l'onglet 1 contient le compte (1)
    assert "(1)" in widget.sub_tab_bar.tabText(1)

    # Nettoyage
    StagedPatchModel.delete().execute()


def test_mcp_dashboard_event_bus_relay(qtbot) -> None:
    """Vérifie que MCPPatchStagedEvent sur l'EventBus met à jour le dashboard de manière thread-safe."""
    from PySide6.QtWidgets import QApplication

    from ankiforge.database.models import StagedPatchModel
    from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry
    from ankiforge.utils.event_bus import MCPPatchStagedEvent, event_bus

    StagedPatchModel.delete().execute()

    widget = MCPServerDashboardWidget(initial_status="running", initial_port=8765)
    qtbot.addWidget(widget)

    patch = StagedPatchRegistry.create_patch(
        patch_type="card",
        target_id=202,
        diff_payload={"title": "Scission de la note #202", "original": {"Front": "Q2"}, "modified": {"Front": "Q2 modifiée"}},
    )
    patch_id = patch.patch_id

    # Émission via l'EventBus
    event_bus.publish(
        MCPPatchStagedEvent(
            patch_id=patch_id,
            patch_type="card",
            target_id=202,
            title="Scission de la note #202",
        )
    )

    # Laisser le temps à Qt de dépiler le signal inter-thread
    qtbot.waitUntil(lambda: "(1)" in widget.sub_tab_bar.tabText(1), timeout=1500)
    QApplication.processEvents()

    assert "(1)" in widget.sub_tab_bar.tabText(1)

    # Nettoyage
    StagedPatchModel.delete().execute()


def test_mcp_dashboard_auto_selection_on_empty_queue(qtbot) -> None:
    """Vérifie que si la file était vide et l'utilisateur sur l'onglet Garde-Fou, le premier patch est sélectionné."""
    from ankiforge.database.models import StagedPatchModel
    from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

    StagedPatchModel.delete().execute()

    widget = MCPServerDashboardWidget(initial_status="running", initial_port=8765)
    qtbot.addWidget(widget)

    # L'utilisateur se place sur l'onglet Garde-Fou
    widget.sub_tab_bar.setCurrentIndex(1)
    assert widget.stacked_widget.currentIndex() == 1
    assert widget.garde_fou_widget.patch_list.count() == 0

    # Création d'un patch
    patch = StagedPatchRegistry.create_patch(
        patch_type="card",
        target_id=303,
        diff_payload={"title": "Atomisation note #303", "original": {"Front": "Q3"}, "modified": {"Front": "Q3 atomique"}},
    )
    patch_id = patch.patch_id

    widget.on_patch_staged({"patch_id": patch_id, "note_id": 303, "title": "Atomisation note #303"})
    qtbot.wait(50)

    # Vérification que le patch a été automatiquement sélectionné
    assert widget.garde_fou_widget.patch_list.count() == 1
    assert widget.garde_fou_widget.current_patch_id == patch_id
    assert widget.garde_fou_widget.detail_stack.currentIndex() == 1

    # Nettoyage
    StagedPatchModel.delete().execute()
