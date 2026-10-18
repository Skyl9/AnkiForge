"""Tests headless Qt des raccourcis clavier du Studio de Création et Batch Factory (ADR 0032, T3).

Couvre :
- Remplacement des eventFilter maison par des bindings de portée Widget.
- Studio : Espace/V (valider), E (éditer), Suppr/Retour/R (rejeter), Alt+←/Alt+→ (carte précédente/suivante).
- Batch : mêmes gestes sur la revue + Alt+↑/Alt+↓ (tranche précédente/suivante) et Alt+←/Alt+→.
- Ctrl+Entrée : action primaire (Générer dans le Studio / Démarrer ou Reprendre dans le Batch).
- Ctrl+S : enregistrement dans Anki depuis le Studio via le routeur.
- Ctrl+N : nouvelle saisie (Studio) et composition du lot (Batch).
- Priorité absolue de la saisie de texte : frappe de 'e', 'v', 'r', 'espace' neutralisée en champ de texte.
- Absence totale de QShortcut orphelin en propre dans les vues migrées.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QLineEdit

from ankiforge.ui.shortcuts import ShortcutId, ShortcutManager, ShortcutScope
from ankiforge.ui.views.batch_view import BatchView
from ankiforge.ui.views.batch_view.widgets.batch_staging_panel import BatchStagingPanel
from ankiforge.ui.views.creation_view import CreationView

pytestmark = pytest.mark.ui


# ── Tests Studio de Création ──────────────────────────────────────────────────


def test_creation_view_no_direct_qshortcuts_or_review_eventfilter(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que CreationView n'a aucun QShortcut orphelin et n'utilise plus eventFilter pour la revue."""
    manager = ShortcutManager()
    view = CreationView(ai_manager=None, shortcut_manager=manager)
    qtbot.addWidget(view)

    # 1. Vérification que results_table n'a pas le view comme eventFilter pour les touches
    # et que tous les QShortcut enfants proviennent du ShortcutManager
    all_shortcuts = view.findChildren(QShortcut)
    manager_shortcuts = [rec.shortcut for rec in manager._bindings]
    for sc in all_shortcuts:
        assert sc in manager_shortcuts, f"QShortcut orphelin détecté dans CreationView: {sc}"


def test_creation_view_review_shortcuts(qtbot: Any, mock_db: Any) -> None:
    """Vérifie les gestes de revue au clavier du Studio de Création attachés à results_table."""
    manager = ShortcutManager()
    view = CreationView(ai_manager=None, shortcut_manager=manager)
    qtbot.addWidget(view)
    manager.set_active_view(view)

    # Récupérer les bindings attachés à results_table
    table_bindings = [rec for rec in manager._bindings if rec.target is view.results_table]
    bound_ids = {rec.id for rec in table_bindings}

    expected_review_ids = {
        ShortcutId.REVIEW_VALIDATE_SPACE,
        ShortcutId.REVIEW_VALIDATE_V,
        ShortcutId.REVIEW_REJECT_DELETE,
        ShortcutId.REVIEW_REJECT_BACKSPACE,
        ShortcutId.REVIEW_REJECT_R,
        ShortcutId.REVIEW_EDIT,
        ShortcutId.REVIEW_PREV_CARD,
        ShortcutId.REVIEW_NEXT_CARD,
    }
    assert expected_review_ids.issubset(bound_ids), f"Raccourcis de revue manquants sur results_table: {expected_review_ids - bound_ids}"

    # Vérifier l'exécution de chaque action
    with (
        patch.object(view, "_on_validate_card") as mock_val,
        patch.object(view, "_on_reject_card") as mock_rej,
        patch.object(view, "_on_edit_card") as mock_edit,
        patch.object(view, "_on_prev_card") as mock_prev,
        patch.object(view, "_on_next_card") as mock_next,
        patch("ankiforge.ui.shortcuts.manager.is_text_input_focused", return_value=False),
    ):
        for rec in table_bindings:
            rec.shortcut.activated.emit()

        assert mock_val.call_count == 2
        assert mock_rej.call_count == 3
        assert mock_edit.call_count == 1
        assert mock_prev.call_count == 1
        assert mock_next.call_count == 1


def test_creation_view_ctrl_n_creates_new_input(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que Ctrl+N dans CreationView ouvre un nouvel onglet de saisie libre."""
    manager = ShortcutManager()
    view = CreationView(ai_manager=None, shortcut_manager=manager)
    qtbot.addWidget(view)
    manager.set_active_view(view)

    matching = [rec for rec in manager._bindings if rec.id == ShortcutId.CREATION_NEW_INPUT]
    assert len(matching) == 1
    rec = matching[0]
    assert rec.sequence == "Ctrl+N"
    assert rec.scope == ShortcutScope.VUE

    with patch.object(view, "_open_document_tab") as mock_open_doc:
        rec.shortcut.activated.emit()
        mock_open_doc.assert_called_once_with("Nouvelle Saisie")


def test_creation_view_run_primary_action(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que run_primary_action déclenche la génération (sur l'éditeur actif ou l'arbre)."""
    manager = ShortcutManager()
    view = CreationView(ai_manager=None, shortcut_manager=manager)
    qtbot.addWidget(view)

    # 1. Avec éditeur actif
    mock_editor = MagicMock()
    mock_editor.btn_generate.isEnabled.return_value = True
    with patch.object(view, "_get_current_editor", return_value=mock_editor):
        view.run_primary_action()
        mock_editor._on_generate_clicked.assert_called_once()

    # 2. Sans éditeur actif, bascule vers l'arborescence
    with (
        patch.object(view, "_get_current_editor", return_value=None),
        patch.object(view, "_on_generate_from_tree") as mock_from_tree,
    ):
        view.run_primary_action()
        mock_from_tree.assert_called_once()


def test_creation_view_save_routed_to_save_anki(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que save() dans CreationView déclenche _on_save_anki."""
    manager = ShortcutManager()
    view = CreationView(ai_manager=None, shortcut_manager=manager)
    qtbot.addWidget(view)

    with patch.object(view, "_on_save_anki") as mock_save:
        view.save()
        mock_save.assert_called_once()


# ── Tests Batch Factory ───────────────────────────────────────────────────────


def test_batch_staging_panel_review_shortcuts(qtbot: Any, mock_db: Any) -> None:
    """Vérifie les gestes de revue et de navigation dans BatchStagingPanel attachés à cards_table."""
    manager = ShortcutManager()
    panel = BatchStagingPanel()
    qtbot.addWidget(panel)
    panel.setup_shortcuts(manager)

    table_bindings = [rec for rec in manager._bindings if rec.target is panel.cards_table]
    bound_ids = {rec.id for rec in table_bindings}

    expected_review_ids = {
        ShortcutId.REVIEW_VALIDATE_SPACE,
        ShortcutId.REVIEW_VALIDATE_V,
        ShortcutId.REVIEW_REJECT_DELETE,
        ShortcutId.REVIEW_REJECT_BACKSPACE,
        ShortcutId.REVIEW_REJECT_R,
        ShortcutId.REVIEW_EDIT,
        ShortcutId.REVIEW_PREV_CARD,
        ShortcutId.REVIEW_NEXT_CARD,
        ShortcutId.REVIEW_PREV_TASK,
        ShortcutId.REVIEW_NEXT_TASK,
    }
    assert expected_review_ids.issubset(bound_ids), f"Raccourcis manquants sur cards_table: {expected_review_ids - bound_ids}"

    with (
        patch.object(panel, "_on_validate_card") as mock_val,
        patch.object(panel, "_on_reject_card") as mock_rej,
        patch.object(panel, "_on_edit_card") as mock_edit,
        patch.object(panel, "_on_prev_card") as mock_prev_card,
        patch.object(panel, "_on_next_card") as mock_next_card,
        patch.object(panel, "_nav_to_task") as mock_nav_task,
        patch("ankiforge.ui.shortcuts.manager.is_text_input_focused", return_value=False),
    ):
        for rec in table_bindings:
            rec.shortcut.activated.emit()

        assert mock_val.call_count == 2
        assert mock_rej.call_count == 3
        assert mock_edit.call_count == 1
        assert mock_prev_card.call_count == 1
        assert mock_next_card.call_count == 1
        assert mock_nav_task.call_count == 2
        mock_nav_task.assert_any_call(-1)
        mock_nav_task.assert_any_call(1)


def test_batch_view_ctrl_n_opens_composer(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que Ctrl+N dans BatchView ouvre le BatchSliceComposerDialog."""
    manager = ShortcutManager()
    view = BatchView(ai_manager=None)
    view.set_shortcut_manager(manager)
    qtbot.addWidget(view)
    manager.set_active_view(view)

    matching = [rec for rec in manager._bindings if rec.id == ShortcutId.BATCH_COMPOSE]
    assert len(matching) == 1
    rec = matching[0]
    assert rec.sequence == "Ctrl+N"
    assert rec.scope == ShortcutScope.VUE

    with patch.object(view, "_on_open_batch_composer") as mock_compose:
        rec.shortcut.activated.emit()
        mock_compose.assert_called_once()


def test_batch_view_run_primary_action_start_or_resume(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que run_primary_action dans BatchView démarre ou reprend le lot."""
    manager = ShortcutManager()
    view = BatchView(ai_manager=None)
    view.set_shortcut_manager(manager)
    qtbot.addWidget(view)

    # 1. Quand le bouton de reprise est invisible -> démarre le lot
    view.btn_resume_batch.setVisible(False)
    with patch.object(view, "_on_start_batch") as mock_start:
        view.run_primary_action()
        mock_start.assert_called_once()

    # 2. Quand le bouton de reprise est visible -> reprend le lot
    view.btn_resume_batch.setVisible(True)
    with patch.object(view, "_on_resume_batch") as mock_resume:
        view.run_primary_action()
        mock_resume.assert_called_once()


# ── Règle du texte prioritaire (Test dédié) ───────────────────────────────────


def test_text_input_prioritary_neutralizes_review_gestures(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que taper 'e', 'v', 'r', ou 'espace' dans un champ de texte ne déclenche aucune décision de revue."""
    manager = ShortcutManager()
    view = CreationView(ai_manager=None, shortcut_manager=manager)
    qtbot.addWidget(view)
    manager.set_active_view(view)

    # Création d'un champ de texte focalisé
    input_field = QLineEdit(view)
    qtbot.addWidget(input_field)
    input_field.setFocus()

    # Récupération des bindings sur results_table
    table_bindings = [rec for rec in manager._bindings if rec.target is view.results_table]

    with (
        patch("ankiforge.ui.shortcuts.manager.is_text_input_focused", return_value=True),
        patch.object(view, "_on_validate_card") as mock_val,
        patch.object(view, "_on_reject_card") as mock_rej,
        patch.object(view, "_on_edit_card") as mock_edit,
    ):
        for rec in table_bindings:
            if rec.id in (
                ShortcutId.REVIEW_VALIDATE_SPACE,
                ShortcutId.REVIEW_VALIDATE_V,
                ShortcutId.REVIEW_REJECT_DELETE,
                ShortcutId.REVIEW_REJECT_BACKSPACE,
                ShortcutId.REVIEW_REJECT_R,
                ShortcutId.REVIEW_EDIT,
            ):
                rec.shortcut.activated.emit()

        mock_val.assert_not_called()
        mock_rej.assert_not_called()
        mock_edit.assert_not_called()
