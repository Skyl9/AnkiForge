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
