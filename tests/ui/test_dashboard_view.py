from unittest.mock import MagicMock
from ankiforge.ui.views.dashboard_view import DashboardView

from unittest.mock import patch


def test_dashboard_view_creation(qtbot):
    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        view = DashboardView(ai_manager=MagicMock())
        qtbot.addWidget(view)
        assert view is not None
