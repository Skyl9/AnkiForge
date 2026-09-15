# tests/test_duplicate_resolver.py
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from ankiforge.database.models import DeckModel, IgnoredDuplicateModel, NoteModel, NoteTypeModel
from ankiforge.ui.widgets.duplicate_resolver import DuplicateResolverDialog


@pytest.fixture
def mock_db_notes():
    deck = DeckModel.create(name="Deck de Conflits")
    note_type = NoteTypeModel.create(name="Basique", fields_schema='["Recto", "Verso"]', templates="[]", css_style="")

    note_a = NoteModel.create(guid="guid-A", deck=deck, note_type=note_type)
    note_b = NoteModel.create(guid="guid-B", deck=deck, note_type=note_type)
    note_c = NoteModel.create(guid="guid-C", deck=deck, note_type=note_type)
    note_d = NoteModel.create(guid="guid-D", deck=deck, note_type=note_type)

    return note_a, note_b, note_c, note_d


@pytest.fixture
def conflicts_data(mock_db_notes):
    note_a, note_b, note_c, note_d = mock_db_notes
    content_a = {"Recto": "Chien", "Verso": "Doggo"}
    content_b = {"Recto": "Chien", "Verso": "Dog"}
    content_c = {"Recto": "Chat", "Verso": "Cat"}
    content_d = {"Recto": "Chat", "Verso": "Kitten"}

    return [(note_a, content_a, note_b, content_b), (note_c, content_c, note_d, content_d)]


@pytest.fixture
def dialog(qtbot, conflicts_data):
    dialog = DuplicateResolverDialog(conflicts=conflicts_data)
    qtbot.addWidget(dialog)
    return dialog


def test_generate_diff_html(dialog):
    html_a, html_b = dialog.generate_diff_html("Doggo", "Dog")
    assert "Dog" in html_a
    assert "text-decoration: line-through" in html_a  # Fix : on cherche le barré HTML, pas le #5c1b1b codé en dur
    assert ">go</span>" in html_a
    assert "Dog" in html_b
    assert "go" not in html_b


def test_dialog_initialization_and_ui(dialog):
    assert dialog.current_index == 0
    assert dialog.progress_bar.maximum() == 2
    assert "Conflit 1 sur 2" in dialog.lbl_status.text()
    html_left = dialog.text_left.toHtml()
    assert "Champ : Recto" in html_left
    assert "Identique" in html_left


def test_keep_a_deletes_b(dialog, qtbot, mock_db_notes):
    note_a, note_b, note_c, note_d = mock_db_notes
    qtbot.mouseClick(dialog.btn_keep_a, Qt.MouseButton.LeftButton)
    assert NoteModel.get_or_none(id=note_a.id) is not None
    assert NoteModel.get_or_none(id=note_b.id) is None
    assert dialog.current_index == 1


def test_keep_b_deletes_a(dialog, qtbot, mock_db_notes):
    note_a, note_b, _, _ = mock_db_notes
    qtbot.mouseClick(dialog.btn_keep_b, Qt.MouseButton.LeftButton)
    assert NoteModel.get_or_none(id=note_a.id) is None
    assert NoteModel.get_or_none(id=note_b.id) is not None


def test_ignore_conflict_saves_to_db(dialog, qtbot, mock_db_notes):
    note_a, note_b, _, _ = mock_db_notes
    qtbot.mouseClick(dialog.btn_ignore, Qt.MouseButton.LeftButton)
    assert NoteModel.get_or_none(id=note_a.id) is not None
    assert NoteModel.get_or_none(id=note_b.id) is not None
    ignored_entry = IgnoredDuplicateModel.select().first()
    assert ignored_entry is not None
    expected_id_1 = min(note_a.id, note_b.id)
    expected_id_2 = max(note_a.id, note_b.id)
    assert ignored_entry.note_a.id == expected_id_1
    assert ignored_entry.note_b.id == expected_id_2


@patch("ankiforge.ui.widgets.duplicate_resolver.QMessageBox.information")
def test_end_of_conflicts_closes_dialog(mock_info, dialog, qtbot):
    qtbot.mouseClick(dialog.btn_ignore, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(dialog.btn_ignore, Qt.MouseButton.LeftButton)
    mock_info.assert_called_once()
    assert dialog.result() == QDialog.DialogCode.Accepted
