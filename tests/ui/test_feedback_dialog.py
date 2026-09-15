"""
Tests d'interface headless pour FeedbackDialog.
Vérifie l'instanciation, la bascule d'onglets, la validation des champs,
le tiroir de diagnostic et les actions (Copier, Exporter, GitHub Issues).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from ankiforge.ui.dialogs.feedback_dialog import FeedbackDialog


class TestFeedbackDialog:
    def test_dialog_init_bug_mode(self, qtbot: QtBot) -> None:
        """Vérifie l'initialisation du dialogue en mode Bug par défaut."""
        dialog = FeedbackDialog(tab="bug")
        qtbot.addWidget(dialog)

        assert dialog.windowTitle() == "Retours & Suggestions AnkiForge"
        assert dialog.tab_bar.currentIndex() == 0
        assert dialog.stacked_widget.currentIndex() == 0
        assert dialog.bug_include_diag_cb.isChecked()
        assert not dialog.diag_preview_edit.isVisible()

    def test_dialog_init_feature_mode(self, qtbot: QtBot) -> None:
        """Vérifie l'initialisation du dialogue en mode Feature."""
        dialog = FeedbackDialog(tab="feature")
        qtbot.addWidget(dialog)

        assert dialog.tab_bar.currentIndex() == 1
        assert dialog.stacked_widget.currentIndex() == 1

    def test_dialog_prefill_error_and_title(self, qtbot: QtBot) -> None:
        """Vérifie le pré-remplissage avec une erreur interceptée."""
        error_msg = "ZeroDivisionError: division by zero in orchestrator"
        dialog = FeedbackDialog(tab="bug", initial_title="Erreur de calcul", context_error=error_msg)
        qtbot.addWidget(dialog)

        assert dialog.bug_title_input.text() == "Erreur de calcul"
        assert error_msg in dialog.bug_observed_edit.toPlainText()
        assert dialog.bug_severity_combo.currentText() == "Élevé / Bloquant"

    def test_tab_switching(self, qtbot: QtBot) -> None:
        """Vérifie la bascule dynamique entre les onglets Bug et Idée."""
        dialog = FeedbackDialog()
        qtbot.addWidget(dialog)

        # Passer à l'onglet Idée (index 1)
        dialog.tab_bar.setCurrentIndex(1)
        assert dialog.stacked_widget.currentIndex() == 1

        # Revenir à l'onglet Bug (index 0)
        dialog.tab_bar.setCurrentIndex(0)
        assert dialog.stacked_widget.currentIndex() == 0

    def test_toggle_diagnostic_drawer(self, qtbot: QtBot) -> None:
        """Vérifie le dépliage et repliage du tiroir de diagnostic."""
        dialog = FeedbackDialog()
        qtbot.addWidget(dialog)

        assert dialog.diag_preview_edit.isHidden()
        dialog._toggle_diagnostics_drawer()
        assert not dialog.diag_preview_edit.isHidden()
        assert "Masquer" in dialog.btn_toggle_drawer.text()

        dialog._toggle_diagnostics_drawer()
        assert dialog.diag_preview_edit.isHidden()
        assert "Afficher" in dialog.btn_toggle_drawer.text()

    def test_diag_checkbox_toggle(self, qtbot: QtBot) -> None:
        """Vérifie que décocher la checkbox désactive le tiroir."""
        dialog = FeedbackDialog()
        qtbot.addWidget(dialog)

        dialog.bug_include_diag_cb.setChecked(False)
        assert not dialog.btn_toggle_drawer.isEnabled()
        assert not dialog.diag_preview_edit.isEnabled()

        dialog.bug_include_diag_cb.setChecked(True)
        assert dialog.btn_toggle_drawer.isEnabled()
        assert dialog.diag_preview_edit.isEnabled()

    def test_copy_report_to_clipboard(self, qtbot: QtBot) -> None:
        """Vérifie la copie du rapport Markdown dans le presse-papier."""
        dialog = FeedbackDialog(tab="bug", initial_title="Bug presse papier")
        qtbot.addWidget(dialog)

        dialog._on_copy_clicked()
        clipboard = QApplication.clipboard()
        assert clipboard is not None
        clipboard_text = clipboard.text()
        assert "Bug presse papier" in clipboard_text
        assert "✓" in dialog.lbl_status.text()

    def test_export_report(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Vérifie l'exportation du rapport Markdown via QFileDialog mocké."""
        dialog = FeedbackDialog(tab="feature")
        qtbot.addWidget(dialog)
        dialog.feature_title_input.setText("Idée Export")

        target_file = str(tmp_path / "test_export.md")
        with patch("ankiforge.ui.dialogs.feedback_dialog.QFileDialog.getSaveFileName", return_value=(target_file, "Markdown (*.md)")):
            dialog._on_export_clicked()

        assert Path(target_file).exists()
        content = Path(target_file).read_text(encoding="utf-8")
        assert "Idée Export" in content
        assert "✓ Rapport enregistré" in dialog.lbl_status.text()

    def test_open_github_issues(self, qtbot: QtBot) -> None:
        """Vérifie l'ouverture de l'URL GitHub dans le navigateur."""
        dialog = FeedbackDialog(tab="bug", initial_title="GitHub Test")
        qtbot.addWidget(dialog)

        with patch("ankiforge.ui.dialogs.feedback_dialog.QDesktopServices.openUrl") as mock_open_url:
            dialog._on_github_clicked()
            assert mock_open_url.called
            call_url: QUrl = mock_open_url.call_args[0][0]
            url_str = call_url.toString()
            assert "https://github.com/Skyl9/AnkiForge/issues/new" in url_str
            assert "GitHub+Test" in url_str or "GitHub%20Test" in url_str
            assert "labels=bug" in url_str
            assert "✓ Page GitHub ouverte" in dialog.lbl_status.text()
