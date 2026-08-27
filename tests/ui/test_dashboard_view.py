"""
Tests d'interface pour DashboardView (Cockpit Global, KPIs, diagnostics et macro-activités).
"""

from unittest.mock import MagicMock, patch
from ankiforge.ui.views.dashboard_view import ActivityItem, DashboardView, DiagnosticCardWidget
from ankiforge.ui.widgets.notification_menu import NotificationMenuPopup


def test_dashboard_view_creation(qtbot):
    with patch("ankiforge.ui.views.dashboard_view.DashboardWorker.start"):
        view = DashboardView(ai_manager=MagicMock())
        qtbot.addWidget(view)
        assert view is not None
        assert view.hero_banner is not None
        assert view.stat_wozniak is not None


def test_dashboard_macro_activity_navigation(qtbot):
    with patch("ankiforge.ui.views.dashboard_view.DashboardWorker.start"):
        view = DashboardView(ai_manager=MagicMock())
        qtbot.addWidget(view)

        nav_signals = []
        view.request_navigation.connect(lambda view_id, data: nav_signals.append((view_id, data)))

        sample_data = {
            "kpis": {
                "wozniak": {"score": 85},
                "coverage": {"coverage": 90},
                "telemetry": {"total_cost_usd": 1.25, "total_tokens": 5000},
                "duplicates_count": 2,
            },
            "diagnostics": [
                {
                    "type": "wozniak",
                    "title": "Violations Wozniak",
                    "message": "3 cartes avec violations",
                    "severity": "warning",
                    "action_label": "⚡ Lancer l'audit",
                    "target_view": "analysis",
                    "target_tab": "audit",
                }
            ],
            "macro_activities": [
                {
                    "title": "Génération IA (12 cartes)",
                    "subtitle": "Forgées • Paquet 'Droit' • 2026-08-22 14:00",
                    "source": "ai_generator",
                    "count": 12,
                    "deck_name": "Droit",
                    "icon": "ph.sparkle",
                    "bg_color": "rgba(99, 102, 241, 0.15)",
                    "sample_note_id": 42,
                }
            ],
        }

        view._on_data_loaded(sample_data)

        # 1. Vérification des KPIs affichés
        assert "85%" in view.stat_wozniak.val_label.text()
        assert "90%" in view.stat_coverage.val_label.text()
        assert "1.25" in view.stat_cost.val_label.text()
        assert "2" in view.stat_duplicates.val_label.text()

        # 2. Vérification du flux de macro-activités
        activity_items = view.findChildren(ActivityItem)
        assert len(activity_items) == 1
        act_item = activity_items[0]
        act_item.clicked.emit(42)
        assert ("edition", {"note_id": 42}) in nav_signals

        # 3. Vérification des cartes de diagnostics proactifs
        diag_cards = view.findChildren(DiagnosticCardWidget)
        assert len(diag_cards) == 1
        diag_cards[0].action_btn.click()
        assert ("analysis", {"tab": "audit"}) in nav_signals


def test_notification_menu_popup(qtbot):
    popup = NotificationMenuPopup()
    qtbot.addWidget(popup)

    notifs = [
        {
            "type": "coverage",
            "title": "Lacunes RAG",
            "message": "5 chunks non couverts",
            "severity": "info",
            "action_label": "Forger",
            "target_view": "analysis",
            "target_tab": "sources",
            "icon": "ph.book-open",
        }
    ]

    action_signals = []
    popup.action_triggered.connect(lambda v, d: action_signals.append((v, d)))

    popup.set_notifications(notifs)
    assert popup.count_badge.text() == "1"

    # Simuler le clic sur le bouton de l'alerte
    from ankiforge.ui.widgets.notification_menu import NotificationItemWidget

    items = popup.findChildren(NotificationItemWidget)
    assert len(items) == 1
    items[0].btn_action.click()

    assert len(action_signals) == 1
    assert action_signals[0] == ("analysis", {"tab": "sources"})
