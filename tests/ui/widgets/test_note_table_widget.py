import json

import pytest

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel, NoteVersionModel, db
from ankiforge.ui.widgets.note_table_widget import NoteTableWidget


@pytest.fixture
def note_table(qtbot):
    table = NoteTableWidget()
    qtbot.addWidget(table)
    return table


def test_note_table_refresh(note_table, mock_db):
    with db.atomic():
        nt = NoteTypeModel.create(name="Basic", fields_schema=json.dumps(["Front", "Back"]), templates="[]", css_style="")
        deck = DeckModel.create(name="Science")
        note = NoteModel.create(note_type=nt, tags=json.dumps(["tag1"]), status="new", guid="guid_refresh")
        NoteVersionModel.create(note=note, content=json.dumps({"Front": "Ma Question", "Back": "Ma Réponse"}), is_active=True)
        CardModel.create(note=note, deck=deck)

    note_table.view_mode_cb.setCurrentText("Vue : Notes (Texte)")
    note_table.refresh_table(deck.id)

    assert note_table.data_table.rowCount() == 1
    assert "Ma Question" in note_table.data_table.item(0, 0).text()


def test_note_table_selection(note_table, qtbot, mock_db):
    with db.atomic():
        nt = NoteTypeModel.create(name="Basic", fields_schema=json.dumps(["Front", "Back"]), templates="[]", css_style="")
        deck = DeckModel.create(name="Science")
        note = NoteModel.create(note_type=nt, tags=json.dumps(["tag1"]), status="new", guid="guid_selection")
        NoteVersionModel.create(note=note, content=json.dumps({"Front": "Q", "Back": "R"}), is_active=True)
        CardModel.create(note=note, deck=deck)

    note_table.view_mode_cb.setCurrentText("Vue : Notes (Texte)")
    note_table.refresh_table(deck.id)

    with qtbot.waitSignal(note_table.note_selected) as blocker:
        note_table.data_table.selectRow(0)

    assert blocker.args == [note.id]
    assert note_table.get_selected_note_ids() == [note.id]
