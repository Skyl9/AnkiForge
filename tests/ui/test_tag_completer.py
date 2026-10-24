"""Tests UI headless pour TagAutocompleter et TagCompleterPopup (ADR 0040)."""

from __future__ import annotations

import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit
from pytestqt.qtbot import QtBot

from ankiforge.database.models import DeckModel, NoteModel, NoteTypeModel
from ankiforge.ui.components.tag_completer import TagAutocompleter

pytestmark = pytest.mark.ui


@pytest.fixture
def completer_setup(mock_db):
    deck = DeckModel.create(name="Deck_Medecine")
    nt = NoteTypeModel.create(
        name="Model_Test",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
    )
    # Créer quelques notes avec des tags
    NoteModel.create(note_type=nt, tags='["anatomie", "physiologie"]')
    NoteModel.create(note_type=nt, tags='["anatomie::coeur"]')
    NoteModel.create(note_type=nt, tags='["anatomie::cerveau"]')
    NoteModel.create(note_type=nt, tags='["chimie"]')
    return {"deck": deck, "nt": nt}


def test_tag_completer_popup_appears_on_typing(qtbot: QtBot, completer_setup) -> None:
    """Vérifie que le menu déroulant riche apparaît dès la saisie d'un préfixe."""
    line_edit = QLineEdit()
    qtbot.addWidget(line_edit)
    line_edit.show()

    completer = TagAutocompleter(
        line_edit=line_edit,
        deck_id=None,  # Profil entier
    )

    # Taper "anat"
    line_edit.setText("anat")
    completer.trigger_completion("anat")

    assert completer.popup.isVisible()
    # Doit proposer "anatomie", "anatomie::cerveau", "anatomie::coeur"
    count = completer.popup.list_widget.count()
    assert count == 3

    completer.hide_popup()
    assert not completer.popup.isVisible()


def test_tag_completer_tab_selection(qtbot: QtBot, completer_setup) -> None:
    """Vérifie la sélection d'une suggestion via la touche Tab ou Entrée."""
    line_edit = QLineEdit()
    qtbot.addWidget(line_edit)
    line_edit.show()

    completer = TagAutocompleter(
        line_edit=line_edit,
        deck_id=None,
    )

    line_edit.setText("chim")
    completer.trigger_completion("chim")
    assert completer.popup.isVisible()

    # Simuler appui sur Tab
    qtbot.keyClick(line_edit, Qt.Key.Key_Tab)

    assert line_edit.text() == "chimie"
    assert not completer.popup.isVisible()


def test_tag_completer_space_key_completion(qtbot: QtBot, completer_setup) -> None:
    """Vérifie que la frappe de l'espace valide et normalise le tag en cours."""
    line_edit = QLineEdit()
    qtbot.addWidget(line_edit)
    line_edit.show()

    confirmed_tags: list[str] = []
    completer = TagAutocompleter(
        line_edit=line_edit,
        single_tag_mode=True,  # Mode pour champ d'ajout d'un seul tag
    )
    completer.tag_confirmed.connect(confirmed_tags.append)

    line_edit.setText("nouveau_tag")
    # Simuler appui sur Espace
    qtbot.keyClick(line_edit, Qt.Key.Key_Space)

    assert confirmed_tags == ["nouveau_tag"]
    assert line_edit.text() == ""
