"""Tests unitaires et d'interface pour ImportDialog et l'adaptation .colpkg."""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QDialog
from pytestqt.qtbot import QtBot

from ankiforge.services.cards.import_manager import ConflictItem, ImportAnalysisResult
from ankiforge.ui.dialogs.import_dialog import ImportDialog

pytestmark = pytest.mark.ui


def test_import_dialog_initial_state_and_colpkg_toggle(qtbot: QtBot) -> None:
    """Vérifie que ImportDialog bascule dynamiquement ses composants selon l'extension."""
    dialog = ImportDialog()
    qtbot.addWidget(dialog)

    # État initial : mode standard
    assert not dialog.options_frame.isHidden()
    assert dialog.colpkg_warning_card.isHidden()
    assert dialog.btn_import.text() == "Lancer l'Importation"

    # Saisie d'un fichier .colpkg
    dialog.path_input.setText("/home/user/collection.colpkg")
    assert dialog.options_frame.isHidden()
    assert not dialog.colpkg_warning_card.isHidden()
    assert dialog.btn_import.text() == "Remplacer la Collection"

    # Rebascule sur un fichier .apkg
    dialog.path_input.setText("/home/user/deck.apkg")
    assert not dialog.options_frame.isHidden()
    assert dialog.colpkg_warning_card.isHidden()
    assert dialog.btn_import.text() == "Lancer l'Importation"

    # Rebascule sur un fichier .txt
    dialog.path_input.setText("/home/user/export.txt")
    assert not dialog.options_frame.isHidden()
    assert dialog.colpkg_warning_card.isHidden()
    assert dialog.btn_import.text() == "Lancer l'Importation"

    # Support des extensions en majuscules (.COLPKG)
    dialog.path_input.setText("/home/user/BACKUP.COLPKG")
    assert dialog.options_frame.isHidden()
    assert not dialog.colpkg_warning_card.isHidden()
    assert dialog.btn_import.text() == "Remplacer la Collection"


def test_import_dialog_initial_colpkg_path(qtbot: QtBot) -> None:
    """Vérifie que passer un initial_path .colpkg initialise directement le mode remplacement."""
    dialog = ImportDialog(initial_path="/home/user/backup.colpkg")
    qtbot.addWidget(dialog)

    assert dialog.options_frame.isHidden()
    assert not dialog.colpkg_warning_card.isHidden()
    assert dialog.btn_import.text() == "Remplacer la Collection"


def test_import_dialog_colpkg_bypasses_smart_merge(qtbot: QtBot) -> None:
    """Vérifie qu'un import .colpkg court-circuite SmartMergeDialog malgré la présence de conflits."""
    dialog = ImportDialog()
    qtbot.addWidget(dialog)
    dialog.path_input.setText("/home/user/backup.colpkg")

    dummy_conflict = ConflictItem(
        note_id=1,
        guid="guid_test",
        note_type_name="Basic",
        local_content={"Front": "Ancien", "Back": "Ancien"},
        incoming_content={"Front": "Nouveau", "Back": "Nouveau"},
        local_deck="Default",
        incoming_deck="Default",
        local_tags=[],
        incoming_tags=[],
        similarity_score=0.8,
    )

    analysis = ImportAnalysisResult(
        temp_dir="/tmp/test",
        source_type="colpkg",
        sqlite_path=None,
        txt_path=None,
        new_notes=[],
        silent_updates=[],
        identical_count=0,
        conflicts=[dummy_conflict],
        media_map={},
    )

    with (
        patch("ankiforge.ui.dialogs.import_dialog.SmartMergeDialog") as mock_smart_merge,
        patch("ankiforge.ui.dialogs.import_dialog.ImportCardsWorker") as mock_worker_cls,
    ):
        mock_worker_instance = MagicMock()
        mock_worker_cls.return_value = mock_worker_instance

        dialog._on_analysis_ready(analysis)

        # SmartMergeDialog ne doit JAMAIS être instancié pour un .colpkg
        mock_smart_merge.assert_not_called()

        # Le commit worker doit être lancé avec conflict_resolutions vide et target_deck_id=None
        mock_worker_cls.assert_called_once()
        call_kwargs = mock_worker_cls.call_args[1]
        assert call_kwargs["mode"] == "commit"
        assert call_kwargs["conflict_resolutions"] == {}
        assert call_kwargs["target_deck_id"] is None
        assert mock_worker_instance.start.called


def test_import_dialog_apkg_opens_smart_merge_on_conflicts(qtbot: QtBot) -> None:
    """Vérifie qu'un import .apkg avec conflits ouvre bien SmartMergeDialog."""
    dialog = ImportDialog()
    qtbot.addWidget(dialog)
    dialog.path_input.setText("/home/user/deck.apkg")

    dummy_conflict = ConflictItem(
        note_id=1,
        guid="guid_test",
        note_type_name="Basic",
        local_content={"Front": "Ancien", "Back": "Ancien"},
        incoming_content={"Front": "Nouveau", "Back": "Nouveau"},
        local_deck="Default",
        incoming_deck="Default",
        local_tags=[],
        incoming_tags=[],
        similarity_score=0.8,
    )

    analysis = ImportAnalysisResult(
        temp_dir="/tmp/test",
        source_type="apkg",
        sqlite_path=None,
        txt_path=None,
        new_notes=[],
        silent_updates=[],
        identical_count=0,
        conflicts=[dummy_conflict],
        media_map={},
    )

    with (
        patch("ankiforge.ui.dialogs.import_dialog.SmartMergeDialog") as mock_smart_merge,
        patch("ankiforge.ui.dialogs.import_dialog.ImportCardsWorker") as mock_worker_cls,
    ):
        mock_merge_inst = MagicMock()
        mock_merge_inst.exec.return_value = QDialog.DialogCode.Accepted
        mock_merge_inst.get_resolutions.return_value = {"guid_test": "incoming"}
        mock_smart_merge.return_value = mock_merge_inst

        dialog._on_analysis_ready(analysis)

        mock_smart_merge.assert_called_once_with([dummy_conflict], parent=dialog)
        mock_worker_cls.assert_called_once()
        assert mock_worker_cls.call_args[1]["conflict_resolutions"] == {"guid_test": "incoming"}
