"""Tests UI headless pour l'intégration de TagSelectWindow dans GroupEditDialog et NoteTagsEditorWidget."""

from __future__ import annotations

import uuid

import pytest
from pytestqt.qtbot import QtBot

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.ui.views.edition_view.group_edit_dialog import GroupEditDialog
from ankiforge.ui.views.edition_view.note_tags_editor import NoteTagsEditorWidget

pytestmark = pytest.mark.ui


def test_group_edit_dialog_tag_picker_integration(qtbot: QtBot) -> None:
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"ModelGED_{uid}", fields_schema='["Front", "Back"]')
    deck = DeckModel.create(name=f"DeckGED_{uid}")

    note = NoteModel.create(note_type=nt, tags='["existant"]')
    NoteVersionModel.create(note=note, content='{"Front": "Q", "Back": "A"}', is_active=True, version_number=1)
    CardModel.create(note=note, deck=deck, template_index=0)

    dialog = GroupEditDialog(note_ids=[note.id])
    qtbot.addWidget(dialog)

    assert hasattr(dialog, "btn_browse_tags_add")
    assert hasattr(dialog, "btn_browse_tags_remove")

    # Saisie préalable dans le champ d'ajout
    dialog.input_tags_add.setText("premier_tag")

    # Simuler le clic sur le bouton de parcours
    dialog.btn_browse_tags_add.click()
    assert dialog._tag_modal is not None

    # Simuler la sélection d'un tag depuis le modal
    dialog._tag_modal.tag_selected.emit("deuxieme_tag")

    # Vérifier l'insertion non destructive
    assert dialog.input_tags_add.text() == "premier_tag, deuxieme_tag"


def test_note_tags_editor_tag_picker_integration(qtbot: QtBot) -> None:
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"ModelNTE_{uid}", fields_schema='["Front", "Back"]')
    deck = DeckModel.create(name=f"DeckNTE_{uid}")

    note = NoteModel.create(note_type=nt, tags='["tag_base"]')
    NoteVersionModel.create(note=note, content='{"Front": "Q", "Back": "A"}', is_active=True, version_number=1)
    CardModel.create(note=note, deck=deck, template_index=0)

    widget = NoteTagsEditorWidget(note=note)
    qtbot.addWidget(widget)

    assert hasattr(widget, "btn_browse_tag")

    tags_emitted: list[list[str]] = []
    widget.tags_changed.connect(tags_emitted.append)

    # Simuler le clic sur le bouton de parcours
    widget.btn_browse_tag.click()
    assert widget._tag_modal is not None

    # Sélection d'un tag
    widget._tag_modal.tag_selected.emit("nouveau_tag")

    # Le tag doit être ajouté à la note
    assert "nouveau_tag" in widget._tags
    assert len(tags_emitted) > 0
    assert "nouveau_tag" in tags_emitted[-1]
