"""Tests headless du dialogue de consentement et place disque Marker OCR (MarkerInstallDialog)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from ankiforge.ui.dialogs.marker_install_dialog import MarkerInstallAction, MarkerInstallDialog

pytestmark = pytest.mark.ui


def test_marker_install_dialog_sufficient_space(qtbot, tmp_path: Path) -> None:
    """Vérifie l'affichage initial lorsque l'espace disque est largement suffisant (> 5 Go)."""
    with patch("ankiforge.services.parsing.marker_service.MarkerService.get_available_disk_space", return_value=25 * 1024**3):
        dialog = MarkerInstallDialog(target_dir=tmp_path)
        qtbot.addWidget(dialog)

        assert "Marker OCR" in dialog.windowTitle()
        assert dialog.required_space_bytes == 5 * 1024**3
        assert dialog.available_space_bytes == 25 * 1024**3
        assert str(tmp_path) in dialog.loc_val.text()

        # La bannière d'avertissement doit être masquée
        assert dialog.warning_frame.isHidden()

        # Le bouton d'installation doit être actif et explicite
        assert dialog.btn_install.isEnabled() is True
        assert dialog.btn_install.autoDefault() is False
        assert dialog.btn_install.isDefault() is False
        assert dialog.btn_standard.autoDefault() is False
        assert dialog.btn_cancel.autoDefault() is False


def test_marker_install_dialog_low_space_warning(qtbot, tmp_path: Path) -> None:
    """Vérifie l'affichage de la bannière d'avertissement si l'espace libre est inférieur au seuil (< 5 Go)."""
    with patch("ankiforge.services.parsing.marker_service.MarkerService.get_available_disk_space", return_value=2 * 1024**3):
        dialog = MarkerInstallDialog(target_dir=tmp_path)
        qtbot.addWidget(dialog)

        # La bannière d'avertissement doit être visible
        assert not dialog.warning_frame.isHidden()
        # L'installation reste possible mais avertie
        assert dialog.btn_install.isEnabled() is True


def test_marker_install_dialog_critically_low_space_disables_install(qtbot, tmp_path: Path) -> None:
    """Vérifie que le bouton d'installation est désactivé si l'espace libre est critique (< 1 Go)."""
    with patch("ankiforge.services.parsing.marker_service.MarkerService.get_available_disk_space", return_value=400 * 1024**2):
        dialog = MarkerInstallDialog(target_dir=tmp_path)
        qtbot.addWidget(dialog)

        assert not dialog.warning_frame.isHidden()
        assert dialog.btn_install.isEnabled() is False
        assert "Espace disque insuffisant" in dialog.btn_install.toolTip()


def test_marker_install_dialog_action_install(qtbot, tmp_path: Path) -> None:
    """Vérifie que le clic sur 'Confirmer et installer' sélectionne INSTALL et valide le dialogue."""
    with patch("ankiforge.services.parsing.marker_service.MarkerService.get_available_disk_space", return_value=15 * 1024**3):
        dialog = MarkerInstallDialog(target_dir=tmp_path)
        qtbot.addWidget(dialog)

        assert dialog.selected_action == MarkerInstallAction.CANCEL
        qtbot.mouseClick(dialog.btn_install, Qt.MouseButton.LeftButton)

        assert dialog.selected_action == MarkerInstallAction.INSTALL
        assert dialog.result() == QDialog.DialogCode.Accepted


def test_marker_install_dialog_action_standard_fallback(qtbot, tmp_path: Path) -> None:
    """Vérifie que le clic sur 'Extraction standard' sélectionne STANDARD_FALLBACK et valide le dialogue."""
    with patch("ankiforge.services.parsing.marker_service.MarkerService.get_available_disk_space", return_value=15 * 1024**3):
        dialog = MarkerInstallDialog(target_dir=tmp_path)
        qtbot.addWidget(dialog)

        qtbot.mouseClick(dialog.btn_standard, Qt.MouseButton.LeftButton)

        assert dialog.selected_action == MarkerInstallAction.STANDARD_FALLBACK
        assert dialog.result() == QDialog.DialogCode.Accepted


def test_marker_install_dialog_action_cancel(qtbot, tmp_path: Path) -> None:
    """Vérifie que le clic sur 'Annuler' sélectionne CANCEL et rejette le dialogue."""
    with patch("ankiforge.services.parsing.marker_service.MarkerService.get_available_disk_space", return_value=15 * 1024**3):
        dialog = MarkerInstallDialog(target_dir=tmp_path)
        qtbot.addWidget(dialog)

        qtbot.mouseClick(dialog.btn_cancel, Qt.MouseButton.LeftButton)

        assert dialog.selected_action == MarkerInstallAction.CANCEL
        assert dialog.result() == QDialog.DialogCode.Rejected


def test_marker_install_dialog_reject_resets_to_cancel(qtbot, tmp_path: Path) -> None:
    """Vérifie que la fermeture via reject() (ex: touche Échap) garantit l'action CANCEL."""
    with patch("ankiforge.services.parsing.marker_service.MarkerService.get_available_disk_space", return_value=15 * 1024**3):
        dialog = MarkerInstallDialog(target_dir=tmp_path)
        qtbot.addWidget(dialog)

        dialog.selected_action = MarkerInstallAction.INSTALL  # simule une valeur pré-remplie
        dialog.reject()

        assert dialog.selected_action == MarkerInstallAction.CANCEL
        assert dialog.result() == QDialog.DialogCode.Rejected
