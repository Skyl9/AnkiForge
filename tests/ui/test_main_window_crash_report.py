"""
Tests d'intégration UI headless pour la détection et l'affichage des crash reports dans MainWindow.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from pytestqt.qtbot import QtBot

from ankiforge.services.crash_reporter_service import CrashReport
from ankiforge.ui.main_window import MainWindow

pytestmark = pytest.mark.ui


@pytest.fixture
def sample_crash_report(tmp_path: Path) -> CrashReport:
    crash_file = tmp_path / "crash.log"
    crash_file.write_text("crash", encoding="utf-8")
    return CrashReport(
        timestamp="2026-10-10 12:00:00 UTC",
        os_platform="macOS",
        python_version="3.12.9",
        active_profile="default",
        traceback="RuntimeError: Fatal mock crash",
        raw_block="RAW",
        fingerprint="fp123",
        log_file=crash_file,
    )


class TestMainWindowCrashReport:
    def test_check_pending_crash_triggers_dialog_show(
        self,
        qtbot: QtBot,
        sample_crash_report: CrashReport,
    ) -> None:
        """Vérifie que _check_pending_crash_report instancie et affiche CrashReportDialog si un crash est en attente."""
        with (
            patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"),
            patch("ankiforge.services.crash_reporter_service.CrashReporterService.has_pending_crash", return_value=True),
            patch("ankiforge.services.crash_reporter_service.CrashReporterService.get_latest_crash", return_value=sample_crash_report),
        ):
            window = MainWindow(ai_manager=None, profile_name="test")
            qtbot.addWidget(window)

            # Appel direct du slot de vérification
            window._check_pending_crash_report()

            assert window._crash_dialog is not None
            assert not window._crash_dialog.isModal()
            assert window._crash_dialog.isVisible()

    def test_check_pending_crash_ignored_if_none_pending(
        self,
        qtbot: QtBot,
    ) -> None:
        """Vérifie qu'aucun dialogue n'est ouvert si aucun crash n'est en attente."""
        with (
            patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"),
            patch("ankiforge.services.crash_reporter_service.CrashReporterService.has_pending_crash", return_value=False),
        ):
            window = MainWindow(ai_manager=None, profile_name="test")
            qtbot.addWidget(window)

            window._check_pending_crash_report()
            assert window._crash_dialog is None

    def test_open_crash_report_via_command_palette(
        self,
        qtbot: QtBot,
        sample_crash_report: CrashReport,
    ) -> None:
        """Vérifie l'ouverture via l'action action.crash_report de la palette de commandes."""
        with (
            patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"),
            patch("ankiforge.services.crash_reporter_service.CrashReporterService.get_latest_crash", return_value=sample_crash_report),
        ):
            window = MainWindow(ai_manager=None, profile_name="test")
            qtbot.addWidget(window)

            window._on_command_selected("action.crash_report")
            assert window._crash_dialog is not None
            assert window._crash_dialog.isVisible()
