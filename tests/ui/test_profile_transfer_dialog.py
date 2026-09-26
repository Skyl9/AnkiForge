"""Tests UI pour la boîte de dialogue ProfileTransferDialog."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QMessageBox

from ankiforge.services.profile_content_transfer import TransferReport
from ankiforge.ui.dialogs.profile_transfer_dialog import ProfileTransferDialog

pytestmark = pytest.mark.ui


def test_profile_transfer_dialog_init_and_preview(qtbot, tmp_path: Path):
    profiles_dir = tmp_path / "profiles"
    (profiles_dir / "default").mkdir(parents=True)
    (profiles_dir / "medecine").mkdir(parents=True)

    with (
        patch("ankiforge.ui.dialogs.profile_transfer_dialog.get_active_profile", return_value="default"),
        patch("ankiforge.services.profile_content_transfer.ProfileContentTransfer.list_decks", return_value=["Anatomie", "Physiologie"]),
        patch("ankiforge.services.profile_content_transfer.ProfileContentTransfer.list_tags", return_value=["p1", "difficile"]),
        patch(
            "ankiforge.services.profile_content_transfer.ProfileContentTransfer.get_transfer_preview",
            return_value={
                "notes_count": 12,
                "note_types_count": 2,
                "cards_count": 24,
                "media_count": 3,
                "total_media_size": 2048,
            },
        ),
    ):
        dialog = ProfileTransferDialog(profiles_dir=profiles_dir)
        qtbot.addWidget(dialog)

        # Vérifier que le profil actif est exclu et 'medecine' est sélectionné
        assert dialog.combo_source.count() == 1
        assert dialog.combo_source.currentText() == "medecine"

        # Vérifier les listes de paquets et tags
        assert dialog.list_decks.count() == 2
        assert dialog.list_tags.count() == 2

        # Vérifier les métriques estimées
        assert dialog.lbl_metric_notes[1].text() == "12"
        assert dialog.lbl_metric_models[1].text() == "2"
        assert dialog.lbl_metric_cards[1].text() == "24"
        assert "3" in dialog.lbl_metric_media[1].text()


def test_profile_transfer_dialog_empty_selection_warning(qtbot, tmp_path: Path):
    profiles_dir = tmp_path / "profiles"
    (profiles_dir / "default").mkdir(parents=True)
    (profiles_dir / "source").mkdir(parents=True)

    with (
        patch("ankiforge.ui.dialogs.profile_transfer_dialog.get_active_profile", return_value="default"),
        patch("ankiforge.services.profile_content_transfer.ProfileContentTransfer.list_decks", return_value=["Deck1"]),
        patch("ankiforge.services.profile_content_transfer.ProfileContentTransfer.list_tags", return_value=[]),
    ):
        dialog = ProfileTransferDialog(profiles_dir=profiles_dir)
        qtbot.addWidget(dialog)

        # Décocher tout
        dialog.btn_deselect_all_decks.click()
        assert dialog.get_selected_decks() == []

        with (
            patch.object(QMessageBox, "warning") as mock_warn,
            patch("ankiforge.services.profile_content_transfer.ProfileContentTransfer.transfer_content") as mock_transfer,
        ):
            dialog.btn_transfer.click()
            mock_warn.assert_called_once()
            mock_transfer.assert_not_called()


def test_profile_transfer_dialog_execution(qtbot, tmp_path: Path):
    profiles_dir = tmp_path / "profiles"
    (profiles_dir / "default").mkdir(parents=True)
    (profiles_dir / "source").mkdir(parents=True)

    fake_report = TransferReport(
        notes_imported=5,
        notes_updated=1,
        notes_skipped=0,
        media_transferred=2,
        decks_created=1,
        note_types_created=1,
        errors=[],
    )

    with (
        patch("ankiforge.ui.dialogs.profile_transfer_dialog.get_active_profile", return_value="default"),
        patch("ankiforge.services.profile_content_transfer.ProfileContentTransfer.list_decks", return_value=["Deck1"]),
        patch("ankiforge.services.profile_content_transfer.ProfileContentTransfer.list_tags", return_value=["Tag1"]),
        patch("ankiforge.services.profile_content_transfer.ProfileContentTransfer.transfer_content", return_value=fake_report) as mock_transfer,
        patch.object(QMessageBox, "information") as mock_info,
    ):
        dialog = ProfileTransferDialog(profiles_dir=profiles_dir)
        qtbot.addWidget(dialog)

        signal_spy = MagicMock()
        dialog.transfer_completed.connect(signal_spy)

        dialog.chk_update_existing.setChecked(True)
        dialog.btn_transfer.click()

        mock_transfer.assert_called_once_with(
            source_profile="source",
            deck_names=["Deck1"],
            tag_names=[],
            update_existing_notes=True,
            profiles_dir=profiles_dir,
        )
        mock_info.assert_called_once()
        signal_spy.assert_called_once_with(fake_report)
