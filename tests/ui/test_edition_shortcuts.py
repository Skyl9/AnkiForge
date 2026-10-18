"""Tests headless Qt des raccourcis clavier de la vue Édition & Navigateur (ADR 0032, T2).

Couvre :
- Absence totale de QShortcut orphelin en propre (tous les gestes passent par ShortcutManager.bind).
- Ctrl+D ouvre « Déplacer vers un paquet… ».
- Non-collision export : Ctrl+Alt+E exporte, Ctrl+Shift+E déclenche l'édition groupée.
- Touches nues ('!' et 'E') neutralisées hors table et saisie de texte prioritaire.
- Préservation de l'ensemble des gestes d'Anki et d'AnkiForge.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import patch

import pytest
from PySide6.QtGui import QShortcut

from ankiforge.database.models import NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.ui.shortcuts import ShortcutId, ShortcutManager, ShortcutScope
from ankiforge.ui.views.edition_view import EditionView

pytestmark = pytest.mark.ui


@pytest.fixture
def sample_edition_data(mock_db: Any) -> tuple[NoteTypeModel, NoteModel, NoteModel]:
    """Crée deux notes et leur type de note pour alimenter la vue Édition."""
    uid = uuid.uuid4().hex[:6]
    templates_json = '[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]'
    nt = NoteTypeModel.create(
        name=f"Model {uid}",
        fields_schema='["Front", "Back"]',
        templates=templates_json,
        css_style="",
    )
    n1 = NoteModel.create(guid=f"g1_{uid}", note_type=nt, tags='["tag1"]')
    NoteVersionModel.create(
        note=n1,
        content=json.dumps({"Front": "Question 1", "Back": "Réponse 1"}),
        is_active=True,
    )
    n2 = NoteModel.create(guid=f"g2_{uid}", note_type=nt, tags='["tag2"]')
    NoteVersionModel.create(
        note=n2,
        content=json.dumps({"Front": "Question 2", "Back": "Réponse 2"}),
        is_active=True,
    )
    return nt, n1, n2


def test_edition_view_no_direct_qshortcuts(qtbot: Any, sample_edition_data: Any) -> None:
    """Vérifie que EditionView n'instancie plus aucun QShortcut en propre hors ShortcutManager."""
    manager = ShortcutManager()
    view = EditionView(ai_manager=None, shortcut_manager=manager)
    qtbot.addWidget(view)
    view.refresh_data()

    # Tous les QShortcut trouvés comme enfants de la vue doivent appartenir au ShortcutManager
    all_shortcuts = view.findChildren(QShortcut)
    manager_shortcuts = [rec.shortcut for rec in manager._bindings]
    for sc in all_shortcuts:
        assert sc in manager_shortcuts, f"QShortcut orphelin détecté non lié au ShortcutManager: {sc}"


def test_ctrl_d_opens_move_to_deck_modal(qtbot: Any, sample_edition_data: Any) -> None:
    """Vérifie que Ctrl+D ouvre le sélecteur de paquet sur la sélection."""
    manager = ShortcutManager()
    view = EditionView(ai_manager=None, shortcut_manager=manager)
    qtbot.addWidget(view)
    view.refresh_data()
    manager.set_active_view(view)

    # Sélectionner la première ligne
    view.card_table.select_row(0)

    with patch.object(view, "_open_move_to_deck_modal") as mock_move:
        # Trouver le raccourci lié à EDITION_MOVE_TO_DECK
        matching = [rec for rec in manager._bindings if rec.id == ShortcutId.EDITION_MOVE_TO_DECK]
        assert len(matching) == 1, "Binding EDITION_MOVE_TO_DECK manquant"
        rec = matching[0]
        assert rec.sequence == "Ctrl+D"
        rec.shortcut.activated.emit()
        mock_move.assert_called_once()


def test_export_non_collision_with_group_edit(qtbot: Any, sample_edition_data: Any) -> None:
    """Vérifie que Ctrl+Shift+E déclenche l'édition groupée et non l'export (Ctrl+Alt+E)."""
    manager = ShortcutManager()
    view = EditionView(ai_manager=None, shortcut_manager=manager)
    qtbot.addWidget(view)
    view.refresh_data()
    manager.set_active_view(view)

    # Lier l'export global sur le manager (portée APPLICATION)
    export_called = False

    def on_export() -> None:
        nonlocal export_called
        export_called = True

    manager.bind(view, {ShortcutId.APP_EXPORT: on_export}, scope=ShortcutScope.APPLICATION)

    # Vérifier les séquences
    export_rec = [rec for rec in manager._bindings if rec.id == ShortcutId.APP_EXPORT][0]
    group_rec = [rec for rec in manager._bindings if rec.id == ShortcutId.EDITION_GROUP_EDIT][0]

    assert export_rec.sequence == "Ctrl+Alt+E"
    assert group_rec.sequence == "Ctrl+Shift+E"

    # Déclencher Ctrl+Shift+E (Group Edit)
    with patch.object(view, "open_group_edit_dialog") as mock_group_edit:
        group_rec.shortcut.activated.emit()
        mock_group_edit.assert_called_once()
        assert export_called is False, "L'export ne doit pas être déclenché par Ctrl+Shift+E"

    # Déclencher Ctrl+Alt+E (Export)
    export_rec.shortcut.activated.emit()
    assert export_called is True


def test_bare_keys_suspended_and_edit_isolated_to_table(qtbot: Any, sample_edition_data: Any) -> None:
    """Vérifie que les touches nues ('!' et 'E') n'agissent que quand la table est ciblée et respectent la saisie de texte."""
    manager = ShortcutManager()
    view = EditionView(ai_manager=None, shortcut_manager=manager)
    qtbot.addWidget(view)
    view.refresh_data()
    manager.set_active_view(view)

    view.show()
    view.card_table.select_row(0)

    # Trouver les bindings des touches nues
    bare_suspend = [rec for rec in manager._bindings if rec.id == ShortcutId.EDITION_SUSPEND_BARE][0]
    bare_edit = [rec for rec in manager._bindings if rec.id == ShortcutId.EDITION_EDIT_NOTE_BARE][0]

    assert bare_suspend.sequence == "!"
    assert bare_suspend.scope == ShortcutScope.WIDGET
    assert bare_suspend.target is view.card_table

    assert bare_edit.sequence == "E"
    assert bare_edit.scope == ShortcutScope.WIDGET
    assert bare_edit.target is view.card_table

    # 1. Simuler focus sur un champ de texte (saisie prioritaire absorbant les touches nues)
    with (
        patch("ankiforge.ui.shortcuts.manager.is_text_input_focused", return_value=True),
        patch.object(view, "_toggle_suspend_selected") as mock_suspend,
        patch.object(view, "_edit_focused_card") as mock_edit,
    ):
        bare_suspend.shortcut.activated.emit()
        bare_edit.shortcut.activated.emit()

        mock_suspend.assert_not_called()
        mock_edit.assert_not_called()

    # 2. Quand la saisie n'est pas focalisée (table focalisée)
    with (
        patch("ankiforge.ui.shortcuts.manager.is_text_input_focused", return_value=False),
        patch.object(view, "_toggle_suspend_selected") as mock_suspend,
        patch.object(view, "_edit_focused_card") as mock_edit,
    ):
        bare_suspend.shortcut.activated.emit()
        mock_suspend.assert_called_once()

        bare_edit.shortcut.activated.emit()
        mock_edit.assert_called_once()


def test_all_preserved_gestures_bound_in_edition_view(qtbot: Any, sample_edition_data: Any) -> None:
    """Vérifie que l'ensemble des gestes de la spécification sont bien liés et fonctionnels."""
    manager = ShortcutManager()
    view = EditionView(ai_manager=None, shortcut_manager=manager)
    qtbot.addWidget(view)
    view.refresh_data()
    manager.set_active_view(view)

    bound_ids = {rec.id for rec in manager._bindings}

    expected_ids = {
        ShortcutId.EDITION_MOVE_TO_DECK,
        ShortcutId.EDITION_NEW_DECK,
        ShortcutId.EDITION_DESELECT_ALL,
        ShortcutId.EDITION_EDIT_NOTE,
        ShortcutId.EDITION_EDIT_NOTE_BARE,
        ShortcutId.EDITION_CHANGE_MODEL,
        ShortcutId.EDITION_TOGGLE_DISPLAY_MODE,
        ShortcutId.EDITION_FIND_REPLACE,
        ShortcutId.EDITION_DELETE,
        ShortcutId.EDITION_SUSPEND,
        ShortcutId.EDITION_SUSPEND_BARE,
        ShortcutId.EDITION_GROUP_EDIT,
        ShortcutId.EDITION_TOGGLE_PREVIEW,
        ShortcutId.EDITION_TOGGLE_TABLE,
        ShortcutId.EDITION_PREV_CARD,
        ShortcutId.EDITION_NEXT_CARD,
        ShortcutId.EDITION_FORMAT_BOLD,
        ShortcutId.EDITION_FORMAT_ITALIC,
        ShortcutId.EDITION_FORMAT_UNDERLINE,
        ShortcutId.EDITION_FORMAT_CLOZE,
        ShortcutId.EDITION_FORMAT_MATH,
        ShortcutId.VIEW_HISTORY,
    }
    for f in range(8):
        expected_ids.add(getattr(ShortcutId, f"EDITION_FLAG_{f}"))

    assert expected_ids.issubset(bound_ids), f"Gestes manquants: {expected_ids - bound_ids}"
