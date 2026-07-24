from unittest.mock import MagicMock, patch
from ankiforge.ui.views.dashboard_view import ActivityItem, DashboardView


def test_dashboard_view_creation(qtbot):
    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        view = DashboardView(ai_manager=MagicMock())
        qtbot.addWidget(view)
        assert view is not None


def test_dashboard_activity_card_navigation(qtbot):
    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        view = DashboardView(ai_manager=MagicMock())
        qtbot.addWidget(view)

        nav_signals = []
        view.request_navigation.connect(lambda view_id, data: nav_signals.append((view_id, data)))

        feed = [{"note_id": 42, "version": 1, "created_at": "2026-07-24", "source": "ai"}]
        view._on_feed_loaded(feed)

        # Chercher le premier ActivityItem
        activity_items = view.findChildren(ActivityItem)
        assert len(activity_items) == 1
        act_item = activity_items[0]

        # Simuler un clic
        act_item.clicked.emit(42)

        assert len(nav_signals) == 1
        assert nav_signals[0] == ("edition", {"note_id": 42})
