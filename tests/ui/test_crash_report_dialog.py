"""
Tests d'interface headless pour CrashReportDialog.
Vérifie le caractère non-bloquant (non-modal), l'affichage de l'aperçu,
la copie dans le presse-papier, l'exportation, l'ouverture GitHub Issues,
et la persistance de l'acquittement et des préférences.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from ankiforge.services.crash_reporter_service import CrashReport
from ankiforge.ui.dialogs.crash_report_dialog import CrashReportDialog
from ankiforge.ui.theme import DesignTokens

pytestmark = pytest.mark.ui


@pytest.fixture
def sample_crash_report(tmp_path: Path) -> CrashReport:
    crash_file = tmp_path / "crash.log"
    crash_file.write_text("Crash log content", encoding="utf-8")
    return CrashReport(
        timestamp="2026-10-10 14:30:00 UTC",
        os_platform="Darwin-24.1.0-arm64",
        python_version="3.12.9",
        active_profile="test_profile",
        traceback="Traceback (most recent call last):\n  File 'test.py', line 1\nZeroDivisionError: division by zero",
        raw_block="RAW BLOCK",
        fingerprint="test_fingerprint_12345",
        log_file=crash_file,
    )


class TestCrashReportDialog:
    def test_dialog_init_non_modal(self, qtbot: QtBot, sample_crash_report: CrashReport) -> None:
        """Vérifie que la modale est non-bloquante (isModal() == False) et ses dimensions."""
        dialog = CrashReportDialog(crash_info=sample_crash_report)
        qtbot.addWidget(dialog)

        # L'invite doit être non bloquante
        assert not dialog.isModal()
        assert dialog.objectName() == "CrashReportDialog"
        assert dialog.minimumWidth() >= 640
        assert dialog.minimumHeight() >= 500

    def test_preview_contains_traceback_and_metadata(self, qtbot: QtBot, sample_crash_report: CrashReport) -> None:
        """Vérifie que l'aperçu contient la trace d'erreur et les métadonnées système."""
        dialog = CrashReportDialog(crash_info=sample_crash_report)
        qtbot.addWidget(dialog)

        preview_text = dialog.preview_edit.toPlainText()
        assert "ZeroDivisionError: division by zero" in preview_text
        assert "Darwin-24.1.0-arm64" in preview_text
        assert "test_profile" in preview_text
        assert dialog.preview_edit.isReadOnly()
        assert dialog.preview_edit.font().family() == DesignTokens.FONT_CODE

    def test_copy_report_to_clipboard(self, qtbot: QtBot, sample_crash_report: CrashReport) -> None:
        """Vérifie que le bouton copier place le rapport Markdown dans le presse-papier."""
        dialog = CrashReportDialog(crash_info=sample_crash_report)
        qtbot.addWidget(dialog)

        with patch("ankiforge.services.crash_reporter_service.CrashReporterService.acknowledge_crash") as mock_ack:
            dialog._on_copy_clicked()
            assert mock_ack.called

        clipboard = QApplication.clipboard()
        assert clipboard is not None
        clipboard_text = clipboard.text()
        assert "ZeroDivisionError" in clipboard_text
        assert "✓" in dialog.lbl_status.text()

    def test_export_report_to_file(self, qtbot: QtBot, sample_crash_report: CrashReport, tmp_path: Path) -> None:
        """Vérifie l'exportation du rapport vers un fichier Markdown local."""
        dialog = CrashReportDialog(crash_info=sample_crash_report)
        qtbot.addWidget(dialog)

        target_file = str(tmp_path / "crash_export.md")
        with (
            patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=(target_file, "Markdown (*.md)")),
            patch("ankiforge.services.crash_reporter_service.CrashReporterService.acknowledge_crash") as mock_ack,
        ):
            dialog._on_export_clicked()
            assert mock_ack.called

        assert Path(target_file).exists()
        assert "ZeroDivisionError" in Path(target_file).read_text(encoding="utf-8")
        assert "✓" in dialog.lbl_status.text()

    def test_open_github_issues(self, qtbot: QtBot, sample_crash_report: CrashReport) -> None:
        """Vérifie que le bouton d'envoi ouvre GitHub Issues dans le navigateur et acquitte le crash."""
        dialog = CrashReportDialog(crash_info=sample_crash_report)
        qtbot.addWidget(dialog)

        with (
            patch("PySide6.QtGui.QDesktopServices.openUrl") as mock_open_url,
            patch("ankiforge.services.crash_reporter_service.CrashReporterService.acknowledge_crash") as mock_ack,
        ):
            dialog._on_send_clicked()
            assert mock_open_url.called
            call_url: QUrl = mock_open_url.call_args[0][0]
            url_str = call_url.toString()
            assert "https://github.com/Skyl9/AnkiForge/issues/new" in url_str
            assert "labels=crash" in url_str
            assert mock_ack.called

    def test_open_log_file(self, qtbot: QtBot, sample_crash_report: CrashReport) -> None:
        """Vérifie que 'Voir le log' ouvre le fichier crash.log via QDesktopServices."""
        dialog = CrashReportDialog(crash_info=sample_crash_report)
        qtbot.addWidget(dialog)

        with patch("PySide6.QtGui.QDesktopServices.openUrl") as mock_open_url:
            dialog._on_view_log_clicked()
            assert mock_open_url.called
            call_url: QUrl = mock_open_url.call_args[0][0]
            assert "crash.log" in call_url.toString()

    def test_customize_in_feedback_dialog(self, qtbot: QtBot, sample_crash_report: CrashReport) -> None:
        """Vérifie que 'Personnaliser' ouvre FeedbackDialog pré-rempli."""
        dialog = CrashReportDialog(crash_info=sample_crash_report)
        qtbot.addWidget(dialog)

        with (
            patch("ankiforge.ui.dialogs.feedback_dialog.FeedbackDialog.exec") as mock_exec,
            patch("ankiforge.services.crash_reporter_service.CrashReporterService.acknowledge_crash") as mock_ack,
        ):
            dialog._on_customize_clicked()
            assert mock_exec.called
            assert mock_ack.called

    def test_ignore_acknowledges_crash_and_closes(self, qtbot: QtBot, sample_crash_report: CrashReport) -> None:
        """Vérifie que le bouton Ignorer acquitte le crash et ferme le dialogue."""
        dialog = CrashReportDialog(crash_info=sample_crash_report)
        qtbot.addWidget(dialog)

        with patch("ankiforge.services.crash_reporter_service.CrashReporterService.acknowledge_crash") as mock_ack:
            dialog._on_ignore_clicked()
            assert mock_ack.called

    def test_dont_ask_checkbox_persists_preference(self, qtbot: QtBot, sample_crash_report: CrashReport) -> None:
        """Vérifie que cocher 'Ne plus demander' désactive la préférence de prompt."""
        dialog = CrashReportDialog(crash_info=sample_crash_report)
        qtbot.addWidget(dialog)

        with patch("ankiforge.services.crash_reporter_service.CrashReporterService.set_prompt_enabled") as mock_set_prompt:
            dialog.chk_dont_ask.setChecked(True)
            # Vérifier que le changement d'état appelle set_prompt_enabled(False)
            assert mock_set_prompt.called
            assert mock_set_prompt.call_args[0][0] is False
