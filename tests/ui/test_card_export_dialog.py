"""
Tests d'interface graphique pour CardExportDialog (Export rapide en texte ou JSON).
Valide l'initialisation, le choix de portée, le basculement de formats et le déclenchement de l'export.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from ankiforge.database.models import DeckModel, NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.ui.dialogs.card_export_dialog import CardExportDialog

pytestmark = pytest.mark.ui


@pytest.fixture
def mock_notes_db():
    DeckModel.create(name="Histoire::France")
    nt = NoteTypeModel.create(name="Basique", fields_schema='["Front", "Back"]')

    notes = []
    for i in range(3):
        n = NoteModel.create(guid=f"note_guid_{i}", note_type=nt, tags='["histoire"]')
        NoteVersionModel.create(
            note=n,
            content=json.dumps({"Front": f"Question {i}", "Back": f"Réponse {i}"}),
            is_active=True,
        )
        notes.append(n)
    return notes


def test_card_export_dialog_init_with_selection(mock_notes_db, qtbot):
    notes = mock_notes_db
    selected_ids = [notes[0].id, notes[1].id]

    dialog = CardExportDialog(selected_note_ids=selected_ids)
    qtbot.addWidget(dialog)

    assert "Export" in dialog.windowTitle()
    # Portée : sélection cochée car IDs fournis
    assert dialog.radio_selection.isChecked()
    assert dialog.radio_selection.isEnabled()
    assert "2" in dialog.radio_selection.text()

    # Format par défaut : JSON
    assert dialog.radio_json.isChecked()
    assert dialog.dest_input.text().endswith(".json")


def test_card_export_dialog_init_without_selection(mock_notes_db, qtbot):
    notes = mock_notes_db
    dialog = CardExportDialog(selected_note_ids=[])
    qtbot.addWidget(dialog)

    # Sans sélection, l'option sélection est désactivée et la collection ou filtre est cochée
    assert not dialog.radio_selection.isEnabled()
    assert dialog.radio_all.isChecked()
    assert str(len(notes)) in dialog.radio_all.text()


def test_card_export_dialog_format_switch(mock_notes_db, qtbot):
    dialog = CardExportDialog(selected_note_ids=[mock_notes_db[0].id])
    qtbot.addWidget(dialog)

    # Basculer vers JSONL
    dialog.radio_jsonl.setChecked(True)
    dialog._on_format_changed()
    assert dialog.dest_input.text().endswith(".jsonl")

    # Basculer vers Texte
    dialog.radio_text.setChecked(True)
    dialog._on_format_changed()
    assert dialog.dest_input.text().endswith(".txt")

    # Basculer vers Markdown
    dialog.radio_markdown.setChecked(True)
    dialog._on_format_changed()
    assert dialog.dest_input.text().endswith(".md")


@patch("ankiforge.ui.dialogs.card_export_dialog.show_toast")
@patch("ankiforge.ui.dialogs.card_export_dialog.QMessageBox.information")
def test_card_export_dialog_trigger(mock_info, mock_toast, mock_notes_db, tmp_path, qtbot):
    notes = mock_notes_db
    selected_ids = [notes[0].id]

    dialog = CardExportDialog(selected_note_ids=selected_ids)
    qtbot.addWidget(dialog)

    out_file = tmp_path / "exported_cards.json"
    dialog.dest_input.setText(str(out_file))

    finished_spy = []
    dialog.export_finished.connect(lambda p, c: finished_spy.append((p, c)))

    dialog._start_export()

    assert out_file.exists()
    assert len(finished_spy) == 1
    assert finished_spy[0][1] == 1
    assert mock_toast.called


@patch("ankiforge.ui.dialogs.card_export_dialog.CardExportDialog.exec")
def test_edition_view_quick_export_button_and_dialog(mock_exec, mock_notes_db, qtbot):
    from ankiforge.ui.views.edition_view.view import EditionView

    view = EditionView()
    qtbot.addWidget(view)

    assert hasattr(view, "btn_export_quick")
    assert view.btn_export_quick is not None

    # Déclenchement de l'ouverture du dialogue
    view.btn_export_quick.click()
    assert mock_exec.called
    assert view._quick_export_dialog is not None
