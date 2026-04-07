# tests/test_version_history_dialog.py
import pytest
import json
from datetime import datetime
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QDialog

from ankiforge.ui.widgets.version_history_dialog import VersionHistoryDialog
from ankiforge.database.models import DeckModel, NoteTypeModel, NoteModel, NoteVersionModel

@pytest.fixture
def test_note():
    deck = DeckModel.create(name="Deck de Test")
    note_type = NoteTypeModel.create(
        name="Basique",
        fields_schema=json.dumps(["Recto", "Verso"]),
        templates=json.dumps([]),
        css_style=""
    )
    note = NoteModel.create(
        guid="test-unique-guid-123",
        deck=deck,
        note_type=note_type
    )
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Recto": "Chien", "Verso": "Doggo"}),
        source="ai",
        is_active=False,
        created_at=datetime(2026, 1, 1, 10, 0)
    )
    NoteVersionModel.create(
        note=note,
        version_number=2,
        content=json.dumps({"Recto": "Chien", "Verso": "Dog"}),
        source="manual",
        is_active=True,
        created_at=datetime(2026, 1, 2, 12, 0)
    )
    return note

@pytest.fixture
def dialog(qtbot, test_note):
    dialog = VersionHistoryDialog(note=test_note)
    qtbot.addWidget(dialog)
    return dialog

def test_dialog_initialization(dialog):
    assert dialog.list_versions.count() == 2
    item_active = dialog.list_versions.item(0)
    assert "v2 (Actuelle)" in item_active.text()
    assert dialog.btn_restore.isEnabled() == False

def test_diff_html_generation(dialog):
    html = dialog.generate_diff_html(old_text="Doggo", new_text="Dog")
    assert "text-decoration: line-through" in html
    assert "Dog" in html
    assert ">go</span>" in html
    html_add = dialog.generate_diff_html(old_text="Chat", new_text="Le Chat")
    assert "Le " in html_add
    assert "line-through" not in html_add

def test_version_selection_updates_diff(dialog, qtbot):
    dialog.list_versions.setCurrentRow(1)
    assert dialog.btn_restore.isEnabled() == True
    displayed_html = dialog.text_diff.toHtml()
    assert "Champ : Recto" in displayed_html
    assert "Identique" in displayed_html
    assert "Dog" in displayed_html
    assert ">go</span>" in displayed_html

@patch('ankiforge.ui.widgets.version_history_dialog.QMessageBox.question')
@patch('ankiforge.ui.widgets.version_history_dialog.show_toast')
def test_restore_version_flow(mock_toast, mock_question, dialog, qtbot, test_note):
    mock_question.return_value = QMessageBox.StandardButton.Yes
    dialog.list_versions.setCurrentRow(1)
    qtbot.mouseClick(dialog.btn_restore, Qt.MouseButton.LeftButton)
    mock_question.assert_called_once()
    mock_toast.assert_called_once()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert test_note.versions.count() == 3
    new_active_version = test_note.versions.where(NoteVersionModel.is_active == True).first()
    assert new_active_version.version_number == 3
    assert new_active_version.source == "manual"
    content = json.loads(new_active_version.content)
    assert content["Verso"] == "Doggo"