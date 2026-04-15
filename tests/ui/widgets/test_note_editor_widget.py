import pytest
import json
from ankiforge.ui.widgets.note_editor_widget import NoteEditorWidget
from ankiforge.database.models import DeckModel, NoteModel, NoteTypeModel, NoteVersionModel, db


@pytest.fixture
def note_editor(qtbot):
    editor = NoteEditorWidget()
    qtbot.addWidget(editor)
    return editor


def test_note_editor_load_note(note_editor, mock_db):
    with db.atomic():
        nt = NoteTypeModel.create(name="Basic", fields_schema=json.dumps(["Front", "Back"]), templates="[]", css_style="")
        note = NoteModel.create(note_type=nt, tags=json.dumps([]), guid="guid1")
        NoteVersionModel.create(note=note, content=json.dumps({"Front": "Hello", "Back": "World"}), is_active=True)

    note_editor.load_note(note.id)

    assert "Hello" in note_editor.field_editors["Front"].toPlainText()
    assert "World" in note_editor.field_editors["Back"].toPlainText()


def test_note_editor_save_note(note_editor, qtbot, mock_db):
    with db.atomic():
        nt = NoteTypeModel.create(name="Basic", fields_schema=json.dumps(["Front", "Back"]), templates="[]", css_style="")
        note = NoteModel.create(note_type=nt, tags=json.dumps([]), guid="guid2")
        NoteVersionModel.create(note=note, content=json.dumps({"Front": "H", "Back": "W"}), is_active=True)

    note_editor.load_note(note.id)
    note_editor.field_editors["Front"].setPlainText("Modified")

    with qtbot.waitSignal(note_editor.note_updated) as blocker:
        note_editor.btn_save_edits.click()

    assert blocker.args[0] == note.id
    assert blocker.args[1]["Front"] == "Modified"
    assert blocker.args[2] == 2

    latest_v = NoteVersionModel.get(note=note, is_active=True)
    assert "Modified" in latest_v.content


def test_note_editor_creation_mode(note_editor, qtbot, mock_db):
    with db.atomic():
        _ = NoteTypeModel.create(name="Basic", fields_schema=json.dumps(["Front", "Back"]), templates="[]", css_style="")
        deck = DeckModel.create(name="Default")

    note_editor.set_current_deck(deck.id)
    note_editor.enter_creation_mode()

    note_editor.creation_model_cb.setCurrentIndex(0)

    note_editor.field_editors["Front"].setPlainText("New Q")
    note_editor.field_editors["Back"].setPlainText("New A")

    with qtbot.waitSignal(note_editor.note_created) as blocker:
        note_editor.btn_save_edits.click()

    assert blocker.args[0] is not None
    assert NoteModel.select().count() == 1
