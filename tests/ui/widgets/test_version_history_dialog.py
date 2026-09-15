# tests/test_version_history_dialog.py
import json
from datetime import datetime
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox

from ankiforge.database.models import DeckModel, NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.ui.widgets.version_history_dialog import VersionHistoryDialog


@pytest.fixture
def test_note():
    deck = DeckModel.create(name="Deck de Test")
    note_type = NoteTypeModel.create(name="Basique", fields_schema=json.dumps(["Recto", "Verso"]), templates=json.dumps([]), css_style="")
    note = NoteModel.create(guid="test-unique-guid-123", deck=deck, note_type=note_type)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Recto": "Chien", "Verso": "Doggo"}),
        source="ai",
        is_active=False,
        created_at=datetime(2026, 1, 1, 10, 0),
    )
    NoteVersionModel.create(
        note=note,
        version_number=2,
        content=json.dumps({"Recto": "Chien", "Verso": "Dog"}),
        source="manual",
        is_active=True,
        created_at=datetime(2026, 1, 2, 12, 0),
    )
    return note


@pytest.fixture
def dialog(qtbot, test_note):
    dialog = VersionHistoryDialog(note=test_note)
    qtbot.addWidget(dialog)
    return dialog


def test_dialog_initialization(dialog):
    assert dialog.version_list.count() == 2
    assert dialog.active_version is not None
    assert dialog.active_version.version_number == 2
    assert not dialog.btn_restore.isEnabled()


def test_diff_html_generation(dialog):
    from ankiforge.ui.widgets.time_machine_dialog import DiffViewerWidget

    viewer = DiffViewerWidget()
    viewer.set_content_diff({"Verso": "Doggo"}, {"Verso": "Dog"})
    html = viewer.toHtml()
    assert "Champ : Verso" in html


def test_version_selection_updates_diff(dialog, qtbot):
    dialog.version_list.setCurrentRow(1)
    assert dialog.btn_restore.isEnabled()
    selected_ver = dialog.version_list.currentItem().data(Qt.ItemDataRole.UserRole)
    assert selected_ver.version_number == 1


@patch("PySide6.QtWidgets.QMessageBox.question")
def test_restore_version_flow(mock_question, dialog, qtbot, test_note):
    mock_question.return_value = QMessageBox.StandardButton.Yes
    dialog.version_list.setCurrentRow(1)
    qtbot.mouseClick(dialog.btn_restore, Qt.MouseButton.LeftButton)
    mock_question.assert_called_once()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert test_note.versions.count() == 3
    new_active_version = test_note.versions.where(NoteVersionModel.is_active).first()
    assert new_active_version.version_number == 3
    content = json.loads(new_active_version.content)
    assert content["Verso"] == "Doggo"
