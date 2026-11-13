"""Tests UI pour la boîte de dialogue ProfileTransferDialog."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from ankidraft.services.profile_content_transfer import TransferReport
from ankidraft.ui.dialogs.profile_transfer_dialog import ProfileTransferDialog

pytestmark = pytest.mark.ui


def test_profile_transfer_dialog_init_and_preview(qtbot, tmp_path: Path):
    profiles_dir = tmp_path / "profiles"
    (profiles_dir / "default").mkdir(parents=True)
    (profiles_dir / "medecine").mkdir(parents=True)

    with (
        patch("ankidraft.ui.dialogs.profile_transfer_dialog.get_active_profile", return_value="default"),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_decks", return_value=["Anatomie", "Physiologie"]),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_tags", return_value=["p1", "difficile"]),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_note_types", return_value=[]),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_albums", return_value=[]),
        patch(
            "ankidraft.services.profile_content_transfer.ProfileContentTransfer.get_transfer_preview",
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

        # Les nouveaux onglets sont vides par défaut
        assert dialog.list_models.count() == 0
        assert dialog.list_albums.count() == 0

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
        patch("ankidraft.ui.dialogs.profile_transfer_dialog.get_active_profile", return_value="default"),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_decks", return_value=["Deck1"]),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_tags", return_value=[]),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_note_types", return_value=[]),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_albums", return_value=[]),
    ):
        dialog = ProfileTransferDialog(profiles_dir=profiles_dir)
        qtbot.addWidget(dialog)

        # Décocher tout
        dialog.btn_deselect_all_decks.click()
        assert dialog.get_selected_decks() == []

        with (
            patch.object(QMessageBox, "warning") as mock_warn,
            patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.transfer_content") as mock_transfer,
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
        patch("ankidraft.ui.dialogs.profile_transfer_dialog.get_active_profile", return_value="default"),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_decks", return_value=["Deck1"]),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_tags", return_value=["Tag1"]),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_note_types", return_value=[]),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_albums", return_value=[]),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.transfer_content", return_value=fake_report) as mock_transfer,
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


def test_profile_transfer_dialog_populate_modeles_et_albums(qtbot, tmp_path: Path):
    profiles_dir = tmp_path / "profiles"
    (profiles_dir / "default").mkdir(parents=True)
    (profiles_dir / "medecine").mkdir(parents=True)

    modeles = [
        {
            "id": 7,
            "name": "Modèle A",
            "description": "Desc A",
            "templates_count": 2,
            "fields_schema": '["Recto", "Verso"]',
            "templates": "[]",
            "css_style": "",
        }
    ]
    albums = [{"id": 42, "title": "Album Anatomie", "total_pages": 3, "created_at": None}]

    with (
        patch("ankidraft.ui.dialogs.profile_transfer_dialog.get_active_profile", return_value="default"),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_decks", return_value=["Deck1"]),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_tags", return_value=["Tag1"]),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_note_types", return_value=modeles),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_albums", return_value=albums),
        patch(
            "ankidraft.services.profile_content_transfer.ProfileContentTransfer.get_transfer_preview",
            return_value={
                "notes_count": 0,
                "note_types_count": 0,
                "cards_count": 0,
                "media_count": 0,
                "total_media_size": 0,
                "models_count": 1,
                "albums_count": 1,
            },
        ),
    ):
        dialog = ProfileTransferDialog(profiles_dir=profiles_dir)
        qtbot.addWidget(dialog)

        assert dialog.list_models.count() == 1
        item_modele = dialog.list_models.item(0)
        assert item_modele.text() == "Modèle A"
        assert item_modele.data(Qt.ItemDataRole.UserRole) == "Modèle A"
        assert item_modele.checkState() == Qt.CheckState.Unchecked

        assert dialog.list_albums.count() == 1
        item_album = dialog.list_albums.item(0)
        assert item_album.text() == "Album Anatomie (3 planches)"
        assert item_album.data(Qt.ItemDataRole.UserRole) == 42


def test_profile_transfer_dialog_transfer_modeles_et_albums(qtbot, tmp_path: Path):
    profiles_dir = tmp_path / "profiles"
    (profiles_dir / "default").mkdir(parents=True)
    (profiles_dir / "source").mkdir(parents=True)

    fake_report = TransferReport(
        notes_imported=0,
        notes_updated=0,
        notes_skipped=0,
        media_transferred=0,
        decks_created=0,
        note_types_created=0,
        errors=[],
    )

    with (
        patch("ankidraft.ui.dialogs.profile_transfer_dialog.get_active_profile", return_value="default"),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_decks", return_value=["Deck1"]),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_tags", return_value=[]),
        patch(
            "ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_note_types",
            return_value=[
                {"id": 7, "name": "Modèle A", "description": "", "templates_count": 1, "fields_schema": '["A"]', "templates": "[]", "css_style": ""},
            ],
        ),
        patch(
            "ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_albums",
            return_value=[
                {"id": 42, "title": "Album X", "total_pages": 3, "created_at": None},
            ],
        ),
        patch(
            "ankidraft.services.profile_content_transfer.ProfileContentTransfer.get_transfer_preview",
            return_value={
                "notes_count": 0,
                "note_types_count": 0,
                "cards_count": 0,
                "media_count": 0,
                "total_media_size": 0,
                "models_count": 1,
                "albums_count": 1,
            },
        ),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.transfer_content", return_value=fake_report) as mock_transfer,
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.import_note_type") as mock_import_nt,
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.import_album") as mock_import_album,
        patch.object(QMessageBox, "information") as mock_info,
    ):
        dialog = ProfileTransferDialog(profiles_dir=profiles_dir)
        qtbot.addWidget(dialog)

        dialog.list_decks.item(0).setCheckState(Qt.CheckState.Checked)
        dialog.list_models.item(0).setCheckState(Qt.CheckState.Checked)
        dialog.list_albums.item(0).setCheckState(Qt.CheckState.Checked)

        signal_spy = MagicMock()
        dialog.transfer_completed.connect(signal_spy)

        dialog.btn_transfer.click()

        mock_transfer.assert_called_once_with(
            source_profile="source",
            deck_names=["Deck1"],
            tag_names=[],
            update_existing_notes=False,
            profiles_dir=profiles_dir,
        )
        mock_import_nt.assert_called_once_with(
            profile_name="source",
            note_type_id_or_name="Modèle A",
            target_profile=None,
            profiles_dir=profiles_dir,
        )
        mock_import_album.assert_called_once_with(
            profile_name="source",
            album_id_or_title=42,
            target_profile=None,
            profiles_dir=profiles_dir,
        )
        mock_info.assert_called_once()
        signal_spy.assert_called_once_with(fake_report)


def test_profile_transfer_dialog_transfer_sans_selection_leve_avertissement(qtbot, tmp_path: Path):
    profiles_dir = tmp_path / "profiles"
    (profiles_dir / "default").mkdir(parents=True)
    (profiles_dir / "source").mkdir(parents=True)

    with (
        patch("ankidraft.ui.dialogs.profile_transfer_dialog.get_active_profile", return_value="default"),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_decks", return_value=["Deck1"]),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_tags", return_value=[]),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_note_types", return_value=[]),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.list_albums", return_value=[]),
        patch("ankidraft.services.profile_content_transfer.ProfileContentTransfer.transfer_content") as mock_transfer,
        patch.object(QMessageBox, "warning") as mock_warn,
    ):
        dialog = ProfileTransferDialog(profiles_dir=profiles_dir)
        qtbot.addWidget(dialog)

        dialog.btn_deselect_all_decks.click()

        dialog.btn_transfer.click()

        mock_warn.assert_called_once()
        mock_transfer.assert_not_called()
