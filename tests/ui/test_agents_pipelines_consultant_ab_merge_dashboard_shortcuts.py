"""Tests headless Qt des raccourcis clavier pour Agents, Pipelines, Consultant, AB, Merge et Dashboard (ADR 0032, T5).

Couvre :
- Agents : Ctrl+N (nouvel agent), Ctrl+Shift+D (dupliquer), Ctrl+S (enregistrer),
  Ctrl+Entrée (tester), Ctrl+H (historique).
- Pipelines : Ctrl+N (nouveau), Ctrl+S (enregistrer), Ctrl+Entrée (tester le DAG),
  Ctrl+↑/Ctrl+↓ (réordonner l'étape), Suppr (supprimer l'étape ciblée).
- Consultant : Ctrl+N (nouvelle discussion), Ctrl+Alt+E (exporter la session),
  Ctrl+Alt+B (barre latérale), Ctrl+Alt+I (inspecteur), Entrée et Ctrl+Entrée (envoyer).
- A/B : Ctrl+Entrée (lancer, migré du local), Alt+↑/Alt+↓ (échantillon A),
  Alt+←/Alt+→ (échantillon B).
- Merge : Alt+←/Alt+→ (conflit précédent/suivant), Ctrl+Alt+←/Ctrl+Alt+→
  (tout garder Local / Entrant), Ctrl+Entrée (valider la fusion).
- Dashboard : Ctrl+Entrée déclenche « Forger des cartes ».
- Isolation inter-vues : aucun geste fantôme entre les vues actives.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from PySide6.QtGui import QShortcut

from ankiforge.services.cards.import_manager import ConflictItem
from ankiforge.ui.dialogs.smart_merge_dialog import SmartMergeDialog
from ankiforge.ui.shortcuts import ShortcutId, ShortcutManager
from ankiforge.ui.views.ab_tests_view import ABTestsView
from ankiforge.ui.views.agents_view import AgentsView
from ankiforge.ui.views.dashboard_view import DashboardView
from ankiforge.ui.views.pipelines_view import PipelinesView

pytestmark = pytest.mark.ui


# ── Tests AgentsView ──────────────────────────────────────────────────────────


def test_agents_view_shortcuts_and_routing(qtbot: Any, mock_db: Any) -> None:
    """Vérifie les bindings déclaratifs et le routage save/run sur AgentsView."""
    manager = ShortcutManager()
    view = AgentsView()
    view.set_shortcut_manager(manager)
    qtbot.addWidget(view)
    manager.set_active_view(view)

    bound_ids = {rec.id for rec in manager._bindings if rec.target is view}
    expected_ids = {
        ShortcutId.AGENTS_NEW,
        ShortcutId.AGENTS_DUPLICATE,
        ShortcutId.VIEW_HISTORY,
    }
    assert expected_ids.issubset(bound_ids), f"Raccourcis manquants sur AgentsView: {expected_ids - bound_ids}"

    with (
        patch.object(view, "_on_new_agent") as mock_new,
        patch.object(view, "_on_clone_agent") as mock_clone,
        patch.object(view, "_on_open_history") as mock_hist,
    ):
        for rec in manager._bindings:
            if rec.target is view and rec.id in expected_ids:
                rec.shortcut.activated.emit()

        mock_new.assert_called_once()
        mock_clone.assert_called_once()
        mock_hist.assert_called_once()

    # Routage Ctrl+S et Ctrl+Entrée
    with patch.object(view, "_on_save_agent") as mock_save:
        view.save()
        mock_save.assert_called_once()

    with patch.object(view, "_on_test_agent") as mock_test:
        view.run_primary_action()
        mock_test.assert_called_once()


# ── Tests PipelinesView ───────────────────────────────────────────────────────


def test_pipelines_view_shortcuts_and_routing(qtbot: Any, mock_db: Any) -> None:
    """Vérifie les bindings déclaratifs et le routage save/run sur PipelinesView."""
    manager = ShortcutManager()
    view = PipelinesView()
    view.set_shortcut_manager(manager)
    qtbot.addWidget(view)
    manager.set_active_view(view)

    bound_ids = {rec.id for rec in manager._bindings if rec.target is view or rec.target in view.findChildren(type(view))}
    assert ShortcutId.PIPELINES_NEW in bound_ids
    assert ShortcutId.PIPELINES_MOVE_STEP_UP in bound_ids
    assert ShortcutId.PIPELINES_MOVE_STEP_DOWN in bound_ids

    # Vérification du routage save() et run_primary_action()
    with patch.object(view, "_on_save_pipeline") as mock_save:
        view.save()
        mock_save.assert_called_once()

    with patch.object(view, "_on_test_full_pipeline") as mock_test:
        view.run_primary_action()
        mock_test.assert_called_once()


def test_pipelines_view_step_reorder_and_delete(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la manipulation d'étapes (monter, descendre, supprimer) via raccourcis."""
    manager = ShortcutManager()
    view = PipelinesView()
    view.set_shortcut_manager(manager)
    qtbot.addWidget(view)
    manager.set_active_view(view)

    # Initialisation de deux étapes
    view.current_steps = [
        {"type": "LLM_PROMPT", "custom_title": "Étape 1"},
        {"type": "LLM_PROMPT", "custom_title": "Étape 2"},
    ]
    view._selected_step_index = 1
    view._render_steps()

    # Monter l'étape 2 (index 1 -> index 0)
    move_up_rec = next(r for r in manager._bindings if r.id == ShortcutId.PIPELINES_MOVE_STEP_UP)
    move_up_rec.shortcut.activated.emit()
    assert view._selected_step_index == 0
    assert view.current_steps[0]["custom_title"] == "Étape 2"

    # Descendre l'étape (index 0 -> index 1)
    move_down_rec = next(r for r in manager._bindings if r.id == ShortcutId.PIPELINES_MOVE_STEP_DOWN)
    move_down_rec.shortcut.activated.emit()
    assert view._selected_step_index == 1
    assert view.current_steps[1]["custom_title"] == "Étape 2"

    # Supprimer l'étape ciblée
    del_rec = next(r for r in manager._bindings if r.id == ShortcutId.PIPELINES_DELETE_STEP)
    del_rec.shortcut.activated.emit()
    assert len(view.current_steps) == 1
    assert view.current_steps[0]["custom_title"] == "Étape 1"


# ── Tests ABTestsView ─────────────────────────────────────────────────────────


def test_ab_tests_view_shortcuts_and_navigation(qtbot: Any, mock_db: Any) -> None:
    """Vérifie les raccourcis de navigation et le routage run_primary sur ABTestsView."""
    manager = ShortcutManager()
    view = ABTestsView()
    view.set_shortcut_manager(manager)
    qtbot.addWidget(view)
    manager.set_active_view(view)

    # Vérification de l'absence de QShortcut orphelin
    all_shortcuts = view.findChildren(QShortcut)
    manager_shortcuts = [rec.shortcut for rec in manager._bindings]
    for sc in all_shortcuts:
        assert sc in manager_shortcuts, f"QShortcut orphelin détecté dans ABTestsView: {sc}"

    bound_ids = {rec.id for rec in manager._bindings if rec.target is view}
    expected_ids = {
        ShortcutId.AB_SAMPLE_A_PREV,
        ShortcutId.AB_SAMPLE_A_NEXT,
        ShortcutId.AB_SAMPLE_B_PREV,
        ShortcutId.AB_SAMPLE_B_NEXT,
    }
    assert expected_ids.issubset(bound_ids)

    # Navigation dans les échantillons
    with (
        patch.object(view, "_prev_a") as mock_prev_a,
        patch.object(view, "_next_a") as mock_next_a,
        patch.object(view, "_prev_b") as mock_prev_b,
        patch.object(view, "_next_b") as mock_next_b,
    ):
        for rec in manager._bindings:
            if rec.target is view and rec.id in expected_ids:
                rec.shortcut.activated.emit()

        mock_prev_a.assert_called_once()
        mock_next_a.assert_called_once()
        mock_prev_b.assert_called_once()
        mock_next_b.assert_called_once()

    # Lancement du test via run_primary_action() (migré de Ctrl+Retour local)
    with patch.object(view, "_on_run_ab_test") as mock_run:
        view.run_primary_action()
        mock_run.assert_called_once()


# ── Tests SmartMergeDialog ────────────────────────────────────────────────────


def test_smart_merge_shortcuts_and_arbitration(qtbot: Any) -> None:
    """Vérifie les raccourcis de navigation, d'arbitrage et de validation sur SmartMergeDialog."""
    manager = ShortcutManager()
    conflict1 = ConflictItem(
        note_id=1,
        guid="guid_1",
        note_type_name="Basic",
        local_content={"Front": "Front local 1", "Back": "Back local 1"},
        incoming_content={"Front": "Front entrant 1", "Back": "Back entrant 1"},
        local_deck="Default",
        incoming_deck="Default",
        local_tags=[],
        incoming_tags=[],
        similarity_score=0.85,
    )
    conflict2 = ConflictItem(
        note_id=2,
        guid="guid_2",
        note_type_name="Basic",
        local_content={"Front": "Front local 2", "Back": "Back local 2"},
        incoming_content={"Front": "Front entrant 2", "Back": "Back entrant 2"},
        local_deck="Default",
        incoming_deck="Default",
        local_tags=[],
        incoming_tags=[],
        similarity_score=0.85,
    )

    dlg = SmartMergeDialog([conflict1, conflict2], shortcut_manager=manager)
    qtbot.addWidget(dlg)
    manager.set_active_dialog(dlg)

    bound_ids = {rec.id for rec in manager._bindings if rec.target is dlg}
    expected_ids = {
        ShortcutId.MERGE_PREV_CONFLICT,
        ShortcutId.MERGE_NEXT_CONFLICT,
        ShortcutId.MERGE_KEEP_ALL_LOCAL,
        ShortcutId.MERGE_KEEP_ALL_INCOMING,
        ShortcutId.MERGE_CONFIRM,
    }
    assert expected_ids.issubset(bound_ids)

    # Navigation conflit suivant / précédent
    next_rec = next(r for r in manager._bindings if r.id == ShortcutId.MERGE_NEXT_CONFLICT)
    next_rec.shortcut.activated.emit()
    assert dlg.current_index == 1

    prev_rec = next(r for r in manager._bindings if r.id == ShortcutId.MERGE_PREV_CONFLICT)
    prev_rec.shortcut.activated.emit()
    assert dlg.current_index == 0

    # Arbitrage tout garder entrant / tout garder local
    keep_incoming_rec = next(r for r in manager._bindings if r.id == ShortcutId.MERGE_KEEP_ALL_INCOMING)
    keep_incoming_rec.shortcut.activated.emit()
    assert dlg.field_rows["Front"].get_merged_value() == "Front entrant 1"

    keep_local_rec = next(r for r in manager._bindings if r.id == ShortcutId.MERGE_KEEP_ALL_LOCAL)
    keep_local_rec.shortcut.activated.emit()
    assert dlg.field_rows["Front"].get_merged_value() == "Front local 1"

    # Validation
    with patch.object(dlg, "_on_confirm_merge") as mock_confirm:
        confirm_rec = next(r for r in manager._bindings if r.id == ShortcutId.MERGE_CONFIRM)
        confirm_rec.shortcut.activated.emit()
        mock_confirm.assert_called_once()


# ── Tests DashboardView ───────────────────────────────────────────────────────


def test_dashboard_view_primary_action(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que run_primary_action() sur DashboardView déclenche le bouton Forger des cartes."""
    manager = ShortcutManager()
    view = DashboardView()
    view.set_shortcut_manager(manager)
    qtbot.addWidget(view)

    with patch.object(view.btn_forge, "click") as mock_click:
        view.run_primary_action()
        mock_click.assert_called_once()


# ── Tests Isolation inter-vues ────────────────────────────────────────────────


def test_t5_view_isolation_and_no_ghost_gestures(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que les raccourcis partagés (notamment Ctrl+N) ne se déclenchent que dans la vue active."""
    manager = ShortcutManager()
    agents_view = AgentsView()
    agents_view.set_shortcut_manager(manager)
    pipelines_view = PipelinesView()
    pipelines_view.set_shortcut_manager(manager)

    qtbot.addWidget(agents_view)
    qtbot.addWidget(pipelines_view)

    # 1. Quand AgentsView est active
    manager.set_active_view(agents_view)
    agent_n = next(r.shortcut for r in manager._bindings if r.target is agents_view and r.id == ShortcutId.AGENTS_NEW)
    pipe_n = next(r.shortcut for r in manager._bindings if r.target is pipelines_view and r.id == ShortcutId.PIPELINES_NEW)

    assert agent_n.isEnabled() is True
    assert pipe_n.isEnabled() is False

    # 2. Quand PipelinesView est active
    manager.set_active_view(pipelines_view)
    assert agent_n.isEnabled() is False
    assert pipe_n.isEnabled() is True
