"""
Tests d'interface pour ActivityChartWidget (QPainter 7 jours).
"""

from ankiforge.ui.style_engine import ThemeProfile
from ankiforge.ui.widgets.activity_chart import ActivityChartWidget
from ankiforge.ui.theme import DesignTokens


def test_activity_chart_widget_creation(qtbot):
    widget = ActivityChartWidget()
    qtbot.addWidget(widget)
    assert widget is not None
    assert widget.height() >= 135


def test_activity_chart_widget_data_and_render(qtbot):
    widget = ActivityChartWidget()
    qtbot.addWidget(widget)

    sample_data = [
        {"date": "2026-08-16", "label": "Dim 16", "created": 4, "modified": 1, "total": 5},
        {"date": "2026-08-17", "label": "Lun 17", "created": 10, "modified": 2, "total": 12},
        {"date": "2026-08-18", "label": "Mar 18", "created": 0, "modified": 0, "total": 0},
        {"date": "2026-08-19", "label": "Mer 19", "created": 6, "modified": 4, "total": 10},
        {"date": "2026-08-20", "label": "Jeu 20", "created": 15, "modified": 3, "total": 18},
        {"date": "2026-08-21", "label": "Ven 21", "created": 2, "modified": 1, "total": 3},
        {"date": "2026-08-22", "label": "Sam 22", "created": 8, "modified": 5, "total": 13},
    ]
    widget.set_data(sample_data)
    assert len(widget._data) == 7

    # Forcer le rafraîchissement d'affichage
    widget.repaint()

    # Test refresh_theme
    profile = ThemeProfile(
        id="test",
        name="Test Theme",
        is_dark=True,
        bg_main="#101010",
        bg_sidebar="#151515",
        bg_panel="#202020",
        bg_input="#181818",
        bg_hover="#282828",
        bg_active="rgba(99, 102, 241, 0.2)",
        accent_primary="#6366f1",
        accent_hover="#4f46e5",
        text_primary="#ffffff",
        text_secondary="#cccccc",
        text_muted="#888888",
        border_color="#333333",
        border_focus="#6366f1",
        color_blue="#3b82f6",
        color_green="#10b981",
        color_yellow="#f59e0b",
        color_red="#ef4444",
        description="#ef4444",
        accent_glow="#ef4444",
        border_light="#ef4444",
        color_purple="#ef4444",
        radius_sm=5,
        radius_md=5,
        radius_lg=5,
        font_main=DesignTokens.FONT_MAIN,
        font_code=DesignTokens.FONT_CODE,
    )
    widget.refresh_theme(profile)
