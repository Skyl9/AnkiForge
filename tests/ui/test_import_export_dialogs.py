from unittest.mock import MagicMock, patch

from ankiforge.database.models import DeckModel
from ankiforge.ui.dialogs.export_dialog import ExportDialog
from ankiforge.ui.dialogs.import_dialog import ImportDialog


def test_import_dialog_init(qtbot):
    dialog = ImportDialog()
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "Importer un Paquet ou une Collection Anki"
    assert dialog.radio_keep_tree.isChecked()

    # Test de la sélection de paquet cible via modal
    dialog._on_target_deck_selected_from_modal(12, "Langues::Japonais")
    assert dialog.target_deck_id == 12
    assert "Langues::Japonais" in dialog.btn_select_target_deck.text()
    assert dialog.radio_merge_deck.isChecked()


def test_export_dialog_init(qtbot):
    d1 = DeckModel.create(name="Sciences")
    d2 = DeckModel.create(name="Langues::Espagnol")

    dialog = ExportDialog(default_deck_id=d1.id)
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "Exporter un Paquet Anki"
    assert dialog.selected_deck_id == d1.id
    assert "Sciences" in dialog.btn_select_deck.text()
    assert dialog.radio_all.isChecked()
    assert dialog.chk_include_media.isChecked()

    # Changement de paquet via modal callback
    dialog._on_deck_selected_from_modal(d2.id, "Langues::Espagnol")
    assert dialog.selected_deck_id == d2.id
    assert "Langues::Espagnol" in dialog.btn_select_deck.text()
    assert "Langues_Espagnol" in dialog.dest_input.text()

    # Sélection de toute la collection
    dialog._on_deck_selected_from_modal(-1, "Tous les paquets (Collection entière)")
    assert dialog.selected_deck_id is None
    assert "export_collection.apkg" in dialog.dest_input.text()


@patch("ankiforge.ui.dialogs.export_dialog.QMessageBox.information")
@patch("ankiforge.ui.dialogs.export_dialog.show_toast")
def test_export_dialog_trigger(mock_toast, mock_info, qtbot):
    dialog = ExportDialog()
    qtbot.addWidget(dialog)

    mock_export_manager = MagicMock()
    mock_export_manager.export_package.return_value = 5
    dialog.export_manager = mock_export_manager
    dialog.dest_input.setText("/tmp/test_export.apkg")

    dialog._start_export()
    mock_export_manager.export_package.assert_called_once()
    assert mock_info.called


@patch("ankiforge.ui.dialogs.export_dialog.QFileDialog.getSaveFileName")
def test_export_dialog_browse_destination_adds_apkg_suffix(mock_save_dialog, qtbot):
    dialog = ExportDialog()
    qtbot.addWidget(dialog)

    mock_save_dialog.return_value = ("/tmp/custom_name", "Archives Anki (*.apkg)")
    dialog._browse_destination()
    assert dialog.dest_input.text() == "/tmp/custom_name.apkg"

    mock_save_dialog.return_value = ("/tmp/existing.apkg", "Archives Anki (*.apkg)")
    dialog._browse_destination()
    assert dialog.dest_input.text() == "/tmp/existing.apkg"


@patch("ankiforge.ui.dialogs.export_dialog.QMessageBox.information")
@patch("ankiforge.ui.dialogs.export_dialog.show_toast")
def test_export_dialog_normalizes_directory_and_missing_extension(mock_toast, mock_info, qtbot, tmp_path):
    dialog = ExportDialog()
    qtbot.addWidget(dialog)

    mock_export_manager = MagicMock()
    mock_export_manager.export_package.return_value = 3
    dialog.export_manager = mock_export_manager

    # 1. Directory path
    dialog.dest_input.setText(str(tmp_path))
    dialog._start_export()
    expected_path = str(tmp_path / "export_collection.apkg")
    assert dialog.dest_input.text() == expected_path
    mock_export_manager.export_package.assert_called_with(
        output_path=expected_path,
        deck_id=None,
        tags=None,
        status_filter="all",
        include_media=True,
        sync_flags_and_suspension_tags=True,
        progress_callback=dialog.lbl_status.setText,
    )

    # 2. Missing extension
    no_ext_path = str(tmp_path / "my_custom_export")
    dialog.dest_input.setText(no_ext_path)
    dialog._start_export()
    assert dialog.dest_input.text() == f"{no_ext_path}.apkg"

    # 3. Toast call
    assert mock_toast.called
    toast_parent, toast_msg = mock_toast.call_args[0][:2]
    assert toast_parent == dialog
    assert "3 cartes" in toast_msg


def test_export_dialog_buttons_default_states(qtbot):
    from ankiforge.ui.components.buttons import SecondaryButton

    dialog = ExportDialog()
    qtbot.addWidget(dialog)

    assert dialog.btn_export.isDefault()
    for child in dialog.findChildren(SecondaryButton):
        if child.text() == "Annuler":
            assert not child.autoDefault()
