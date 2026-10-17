"""Tests unitaires et UI pour MCPTelemetryWidget."""

from __future__ import annotations

import json

import pytest
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QTableWidget

from ankiforge.services.ai.mcp_tracker import MCPActivityTracker
from ankiforge.ui.views.consultant_view.widgets.mcp_telemetry_widget import (
    MCPTelemetryWidget,
)

pytestmark = pytest.mark.ui


@pytest.fixture
def custom_tracker() -> MCPActivityTracker:
    """Fixture fournissant un tracker de télémétrie isolé pour les tests."""
    return MCPActivityTracker(max_history=50)


def test_mcp_telemetry_widget_initialization(qtbot, custom_tracker: MCPActivityTracker) -> None:
    """Vérifie l'initialisation du widget de télémétrie et son état initial vide."""
    widget = MCPTelemetryWidget(tracker=custom_tracker)
    qtbot.addWidget(widget)

    # 1. Vérification des éléments de KPI
    assert hasattr(widget, "lbl_kpi_total_val")
    assert hasattr(widget, "lbl_kpi_rate_val")
    assert hasattr(widget, "lbl_kpi_duration_val")
    assert hasattr(widget, "btn_clear_history")

    assert widget.lbl_kpi_total_val.text() == "0"
    assert "100" in widget.lbl_kpi_rate_val.text() or "—" in widget.lbl_kpi_rate_val.text()
    assert "0" in widget.lbl_kpi_duration_val.text() or "—" in widget.lbl_kpi_duration_val.text()

    # 2. Barre de filtres
    assert hasattr(widget, "edit_search")
    assert hasattr(widget, "chip_all")
    assert hasattr(widget, "chip_success")
    assert hasattr(widget, "chip_error")
    assert widget.chip_all.isChecked()

    # 3. Table des activités
    assert isinstance(widget.table, QTableWidget)
    assert widget.table.rowCount() == 0
    assert widget.table.columnCount() == 5

    # 4. Volet d'inspection latéral (état vide par défaut)
    assert hasattr(widget, "inspector_stack")
    assert widget.inspector_stack.currentIndex() == 0  # 0 = placeholder état vide


def test_mcp_telemetry_widget_activity_lifecycle(qtbot, custom_tracker: MCPActivityTracker) -> None:
    """Vérifie la mise à jour temps réel lors du démarrage puis de la réussite d'un appel."""
    widget = MCPTelemetryWidget(tracker=custom_tracker)
    qtbot.addWidget(widget)

    # Démarrage d'un appel
    call_id = custom_tracker.start_tracking(
        "propose_card_refactor",
        {"note_id": 42, "instruction": "Découper la carte"},
    )
    qtbot.wait(30)

    # La table contient 1 ligne en cours
    assert widget.table.rowCount() == 1
    assert widget.lbl_kpi_total_val.text() == "1"

    # Réussite de l'appel
    custom_tracker.record_success(
        call_id=call_id,
        result={"status": "staged", "patch_id": "patch_abc"},
        duration_ms=145.5,
    )
    qtbot.wait(30)

    # La ligne est mise à jour
    assert widget.table.rowCount() == 1
    assert widget.lbl_kpi_total_val.text() == "1"
    assert "100%" in widget.lbl_kpi_rate_val.text()
    assert "145" in widget.lbl_kpi_duration_val.text() or "146" in widget.lbl_kpi_duration_val.text()


def test_mcp_telemetry_widget_activity_error(qtbot, custom_tracker: MCPActivityTracker) -> None:
    """Vérifie le traitement d'une erreur d'appel et la répercussion sur le taux d'erreur."""
    widget = MCPTelemetryWidget(tracker=custom_tracker)
    qtbot.addWidget(widget)

    call_id = custom_tracker.start_tracking("create_note", {"deck": "Introuvable"})
    custom_tracker.record_error(call_id, "DeckNotFound: Introuvable", duration_ms=25.0)
    qtbot.wait(30)

    assert widget.table.rowCount() == 1
    assert widget.lbl_kpi_total_val.text() == "1"
    assert "0%" in widget.lbl_kpi_rate_val.text()
    assert "1 erreur" in widget.lbl_kpi_rate_sub.text().lower() or "erreur" in widget.lbl_kpi_rate_val.text().lower()


def test_mcp_telemetry_widget_selection_updates_inspector(qtbot, custom_tracker: MCPActivityTracker) -> None:
    """Vérifie que la sélection d'une ligne met à jour l'inspecteur latéral sans modale bloquante."""
    widget = MCPTelemetryWidget(tracker=custom_tracker)
    qtbot.addWidget(widget)

    call_id = custom_tracker.start_tracking(
        "propose_card_refactor",
        {"note_id": 99, "action": "split"},
    )
    custom_tracker.record_success(
        call_id,
        {"success": True, "created_notes": [100, 101]},
        duration_ms=88.0,
    )
    qtbot.wait(30)

    # Au départ, aucun élément sélectionné -> page 0
    assert widget.inspector_stack.currentIndex() == 0

    # Sélection de la ligne 0
    widget.table.selectRow(0)
    qtbot.wait(30)

    # L'inspecteur bascule sur la page 1 (détail)
    assert widget.inspector_stack.currentIndex() == 1
    assert "propose_card_refactor" in widget.lbl_inspect_tool.text()
    assert "note_id" in widget.edit_inspect_args.toPlainText()
    assert "99" in widget.edit_inspect_args.toPlainText()
    assert "created_notes" in widget.edit_inspect_result.toPlainText()


def test_mcp_telemetry_widget_copy_json(qtbot, custom_tracker: MCPActivityTracker) -> None:
    """Vérifie la copie du payload JSON complet dans le presse-papiers."""
    widget = MCPTelemetryWidget(tracker=custom_tracker)
    qtbot.addWidget(widget)

    call_id = custom_tracker.start_tracking("audit_deck_wozniak", {"deck_name": "Médecine"})
    custom_tracker.record_success(call_id, "Audit terminé sans anomalie", duration_ms=310.2)
    qtbot.wait(30)

    widget.table.selectRow(0)
    qtbot.wait(20)

    widget.btn_copy_json.click()
    clipboard = QGuiApplication.clipboard()
    assert clipboard is not None
    copied_text = clipboard.text()
    assert "audit_deck_wozniak" in copied_text
    assert "Médecine" in copied_text

    # Vérification que c'est un JSON valide
    parsed = json.loads(copied_text)
    assert parsed["tool_name"] == "audit_deck_wozniak"
    assert parsed["duration_ms"] == 310.2


def test_mcp_telemetry_widget_filtering(qtbot, custom_tracker: MCPActivityTracker) -> None:
    """Vérifie le filtrage textuel par nom d'outil et par statut (Tous, Succès, Erreurs)."""
    widget = MCPTelemetryWidget(tracker=custom_tracker)
    qtbot.addWidget(widget)

    # Insertion de 3 appels variés
    id1 = custom_tracker.start_tracking("propose_card_refactor", {"id": 1})
    custom_tracker.record_success(id1, "OK", 50.0)

    id2 = custom_tracker.start_tracking("create_note", {"id": 2})
    custom_tracker.record_error(id2, "Error creating note", 20.0)

    id3 = custom_tracker.start_tracking("list_decks", {})
    custom_tracker.record_success(id3, ["Default", "French"], 10.0)

    qtbot.wait(50)
    assert widget.table.rowCount() == 3

    row1 = widget._find_row_by_call_id(id1)
    row2 = widget._find_row_by_call_id(id2)
    row3 = widget._find_row_by_call_id(id3)
    assert row1 is not None and row2 is not None and row3 is not None

    # 1. Filtre par texte "propose"
    widget.edit_search.setText("propose")
    qtbot.wait(20)
    assert not widget.table.isRowHidden(row1)
    assert widget.table.isRowHidden(row2)
    assert widget.table.isRowHidden(row3)

    # Réinitialisation de la recherche
    widget.edit_search.clear()
    qtbot.wait(20)
    assert not widget.table.isRowHidden(row1)
    assert not widget.table.isRowHidden(row2)
    assert not widget.table.isRowHidden(row3)

    # 2. Filtre par statut "Erreurs"
    widget.chip_error.click()
    qtbot.wait(20)
    assert widget.table.isRowHidden(row1)
    assert not widget.table.isRowHidden(row2)
    assert widget.table.isRowHidden(row3)

    # 3. Filtre par statut "Succès"
    widget.chip_success.click()
    qtbot.wait(20)
    assert not widget.table.isRowHidden(row1)
    assert widget.table.isRowHidden(row2)
    assert not widget.table.isRowHidden(row3)

    # 4. Retour à "Tous"
    widget.chip_all.click()
    qtbot.wait(20)
    assert not widget.table.isRowHidden(row1)
    assert not widget.table.isRowHidden(row2)
    assert not widget.table.isRowHidden(row3)


def test_mcp_telemetry_widget_clear_history(qtbot, custom_tracker: MCPActivityTracker) -> None:
    """Vérifie la purge complète de l'historique."""
    widget = MCPTelemetryWidget(tracker=custom_tracker)
    qtbot.addWidget(widget)

    id1 = custom_tracker.start_tracking("propose_card_split", {"id": 1})
    custom_tracker.record_success(id1, "OK", 50.0)
    qtbot.wait(30)

    widget.table.selectRow(0)
    assert widget.inspector_stack.currentIndex() == 1
    assert widget.table.rowCount() == 1

    # Clic sur vider l'historique
    widget.btn_clear_history.click()
    qtbot.wait(30)

    assert widget.table.rowCount() == 0
    assert widget.lbl_kpi_total_val.text() == "0"
    assert widget.inspector_stack.currentIndex() == 0  # Reviens sur l'état vide
    assert len(custom_tracker.get_history()) == 0


def test_mcp_telemetry_widget_realtime_update_of_selected_call(qtbot, custom_tracker: MCPActivityTracker) -> None:
    """Vérifie qu'un appel en cours sélectionné dans l'inspecteur se met à jour en direct dès réception du résultat."""
    widget = MCPTelemetryWidget(tracker=custom_tracker)
    qtbot.addWidget(widget)

    call_id = custom_tracker.start_tracking("long_running_analysis", {"depth": 3})
    qtbot.wait(30)

    widget.table.selectRow(0)
    qtbot.wait(20)

    assert widget.inspector_stack.currentIndex() == 1
    assert "long_running_analysis" in widget.lbl_inspect_tool.text()
    assert "cours" in widget.badge_inspect_status.text().lower()

    # Le résultat arrive
    custom_tracker.record_success(call_id, "Analyse terminée avec 15 constats", duration_ms=1200.0)
    qtbot.wait(30)

    # L'inspecteur a été mis à jour automatiquement sans clic supplémentaire
    assert "succès" in widget.badge_inspect_status.text().lower()
    assert "15 constats" in widget.edit_inspect_result.toPlainText()


def test_mcp_telemetry_widget_refresh_theme(qtbot, custom_tracker: MCPActivityTracker) -> None:
    """Vérifie que refresh_theme applique les styles sans lever d'exception."""
    from ankiforge.ui.style_engine import JETBRAINS_LIGHT

    widget = MCPTelemetryWidget(tracker=custom_tracker)
    qtbot.addWidget(widget)

    widget.refresh_theme(JETBRAINS_LIGHT)
    assert widget.table.rowCount() == 0
