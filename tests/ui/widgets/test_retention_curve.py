"""
Tests d'interface pour RetentionCurveWidget (courbe d'oubli projetée, QPainter).

Le widget est piloté par la sortie de ``FsrsProjectionService`` : aucune donnée
n'est fabriquée côté UI, et l'absence de projection exploitable affiche un état
vide explicite sans lever d'exception au rendu.
"""

import pytest

from ankiforge.ui.style_engine import ThemeProfile
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.retention_curve import RetentionCurveWidget

pytestmark = pytest.mark.ui


def _sample_projection() -> dict:
    """Projection minimale au format canonique de ``FsrsProjectionService``."""
    return {
        "deck_id": None,
        "available": True,
        "retention_target": 0.90,
        "total_cards": 12,
        "new_cards": 2,
        "studied_cards": 10,
        "suspended_cards": 1,
        "load_cards": 9,
        "mean_stability_days": 21.4,
        "checkpoints": [
            {"day": 1, "retention": 0.9541},
            {"day": 3, "retention": 0.9005},
            {"day": 7, "retention": 0.8321},
            {"day": 14, "retention": 0.7512},
        ],
        "curve": [
            {"day": 0.0, "retention": 1.0},
            {"day": 0.25, "retention": 0.9942},
            {"day": 7.0, "retention": 0.8321},
            {"day": 14.0, "retention": 0.7512},
        ],
        "equilibrium_load_per_day": 0.52,
    }


def _theme_profile() -> ThemeProfile:
    return ThemeProfile(
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


def test_retention_curve_widget_creation(qtbot):
    widget = RetentionCurveWidget()
    qtbot.addWidget(widget)
    assert widget.height() >= 180
    # État initial : aucune projection chargée.
    assert widget._available is False
    assert widget._load_badge.text() == "Charge : —"
    assert widget._stability_label.text() == "S moy. : —"


def test_retention_curve_widget_applies_projection(qtbot):
    widget = RetentionCurveWidget()
    qtbot.addWidget(widget)

    widget.set_projection(_sample_projection())

    assert widget._available is True
    assert len(widget._curve) == 4
    assert len(widget._checkpoints) == 4
    assert "0.5" in widget._load_badge.text()
    assert "21" in widget._stability_label.text()
    # Le rendu ne doit jamais lever d'exception avec des données valides.
    widget.resize(400, 220)
    widget.repaint()


def test_retention_curve_widget_empty_projection(qtbot):
    widget = RetentionCurveWidget()
    qtbot.addWidget(widget)

    widget.set_projection(None)
    assert widget._available is False

    widget.set_projection({"available": False, "curve": [], "checkpoints": []})
    assert widget._available is False
    assert widget._load_badge.text() == "Charge : —"

    # Rendu de l'état vide : ne doit pas lever d'exception.
    widget.resize(400, 220)
    widget.repaint()


def test_retention_curve_widget_refresh_theme(qtbot):
    widget = RetentionCurveWidget()
    qtbot.addWidget(widget)
    widget.set_projection(_sample_projection())

    widget.refresh_theme(_theme_profile())

    assert "#ffffff" in widget._title_label.styleSheet()
    assert "#888888" in widget._stability_label.styleSheet()
