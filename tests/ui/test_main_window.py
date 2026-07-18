from unittest.mock import patch
from ankiforge.ui.main_window import MainWindow


def test_main_window_creation(qtbot, mock_db):
    with patch("ankiforge.services.background_daemon.BackgroundDaemon"), patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None)
        qtbot.addWidget(window)
        assert window is not None
