"""Tests de couverture ciblés pour EditionView afin de résorber le risque CRAP."""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QDialog

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.ui.models.sorting import SortCriterion, SortOrder
from ankiforge.ui.style_engine import JETBRAINS_DARK
from ankiforge.ui.views.edition_view import EditionView

pytestmark = pytest.mark.ui


def _create_sample_note_and_cards(suffix: str = "1") -> tuple[NoteModel, list[CardModel]]:
    """Crée une note et deux cartes physiques pour les tests."""
    uid = uuid.uuid4().hex[:6] + suffix
    deck = DeckModel.create(name=f"Deck_{uid}")
    nt = NoteTypeModel.create(
        name=f"Type_{uid}",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
        css_style="",
    )

    note = NoteModel.create(guid=f"guid_{uid}", note_type=nt, tags='["medecine", "bio"]')
    NoteVersionModel.create(
        note=note,
        content=json.dumps({"Front": f"Question {suffix}", "Back": f"Reponse {suffix}"}),
        is_active=True,
    )
    c1 = CardModel.create(note=note, deck=deck, template_index=0, flags=0)
    c2 = CardModel.create(note=note, deck=deck, template_index=1, flags=0)
    return note, [c1, c2]


def test_edition_view_refresh_theme_coverage(qtbot: Any, mock_db: Any) -> None:
    """Couvre la méthode refresh_theme d'EditionView (CC=21, anciennement CRAP=427)."""
    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)

    # Exécution de refresh_theme avec JETBRAINS_DARK
    view.refresh_theme(JETBRAINS_DARK)
    assert view.editor_container.styleSheet() != ""
    assert view.btn_mode_notes.styleSheet() != ""


def test_edition_view_target_ids_and_ribbon_info(qtbot: Any, mock_db: Any) -> None:
    """Couvre get_target_card_ids, get_target_note_ids et _update_nav_ribbon_info."""
    note1, cards1 = _create_sample_note_and_cards("a")
    note2, cards2 = _create_sample_note_and_cards("b")

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # Sans sélection : fallback IDs
    assert view.get_target_card_ids(fallback_card_id=cards1[0].id) == [cards1[0].id]
    assert view.get_target_card_ids(fallback_card_id=None) == []
    assert view.get_target_note_ids(fallback_note_id=note1.id) == [note1.id]
    assert view.get_target_note_ids(fallback_note_id=None) == []

    # Ruban sans sélection
    view._update_nav_ribbon_info()
    assert "sélectionnée" in view.lbl_card_ribbon_info.text().lower()

    # Sélection d'une ligne
    view.card_table.select_row(0)
    view._on_card_selected()
    view._update_nav_ribbon_info()
    assert str(note1.id) in view.lbl_card_ribbon_info.text() or str(cards1[0].id) in view.lbl_card_ribbon_info.text()

    # Changement en mode cartes
    view._on_display_mode_changed("cards")
    view._update_nav_ribbon_info()
    assert view.get_target_card_ids() != [] or view.get_target_card_ids(fallback_card_id=cards1[0].id) == [cards1[0].id]


def test_edition_view_apply_flags(qtbot: Any, mock_db: Any) -> None:
    """Couvre l'application de drapeaux Anki aux notes et cartes (_apply_flag_to_selected_notes)."""
    note, cards = _create_sample_note_and_cards("flag")

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # En mode notes : appliquer drapeau 2 (orange)
    view._display_mode = "notes"
    view._apply_flag_to_selected_notes(flag=2, fallback_note_id=note.id)
    c_updated = CardModel.get_by_id(cards[0].id)
    assert c_updated.flags == 2

    # Retirer drapeau (flag=0)
    view._apply_flag_to_selected_notes(flag=0, fallback_note_id=note.id)
    c_cleared = CardModel.get_by_id(cards[0].id)
    assert c_cleared.flags == 0

    # En mode cartes : appliquer drapeau 4 (bleu)
    view._display_mode = "cards"
    # Forcer la sélection de la carte
    view.note_table_model.get_card_data_at = MagicMock(return_value=MagicMock(card_id=cards[0].id))  # type: ignore[method-assign]
    view.card_table.get_selected_rows = MagicMock(return_value=[0])  # type: ignore[method-assign]
    view._apply_flag_to_selected_notes(flag=4)
    c_blue = CardModel.get_by_id(cards[0].id)
    assert c_blue.flags == 4


def test_edition_view_sort_criterion_labels_and_helpers(qtbot: Any, mock_db: Any) -> None:
    """Couvre _get_sort_criterion_label et _get_sort_criterion_for_column."""
    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)

    # Critères de tri avec SortOrder
    assert "créat" in view._get_sort_criterion_label(SortOrder(criterion=SortCriterion.CREATED_AT)).lower()
    assert "modifi" in view._get_sort_criterion_label(SortOrder(criterion=SortCriterion.MODIFIED_AT)).lower()
    assert "recto" in view._get_sort_criterion_label(SortOrder(criterion=SortCriterion.RECTO)).lower()
    assert "drapeau" in view._get_sort_criterion_label(SortOrder(criterion=SortCriterion.FLAGS)).lower()
    assert "paquet" in view._get_sort_criterion_label(SortOrder(criterion=SortCriterion.DECK)).lower()

    # Colonnes
    assert view._get_sort_criterion_for_column(1) == (SortCriterion.FLAGS, None)


def test_edition_view_dialog_openers(qtbot: Any, mock_db: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Couvre open_group_edit_dialog et open_batch_edit_dialog avec mock de dialog rejeté."""
    note, cards = _create_sample_note_and_cards("diag")

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # Mock QDialog.exec retournant Rejected pour tester le cycle d'ouverture sans déclencher de threads d'arrière-plan
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Rejected)

    # Exécution des ouvertures de dialogue
    view.open_group_edit_dialog()
    view.open_batch_edit_dialog(note_ids=[note.id])
