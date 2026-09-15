from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QWidget

from ankiforge.ui.components.panels import MetricCard
from ankiforge.ui.theme import apply_shadow


def test_apply_shadow_with_qcolor(qtbot):
    """Vérifie que apply_shadow accepte directement un objet QColor sans lever AttributeError."""
    widget = QWidget()
    qtbot.addWidget(widget)

    color = QColor(99, 102, 241, 40)
    apply_shadow(widget, blur=12, offset_y=4, color=color)

    effect = widget.graphicsEffect()
    assert isinstance(effect, QGraphicsDropShadowEffect)
    assert effect.blurRadius() == 12
    assert effect.yOffset() == 4
    assert effect.color() == color


def test_apply_shadow_with_rgba_string(qtbot):
    """Vérifie que apply_shadow parse correctement les chaînes rgba(...)."""
    widget = QFrame()
    qtbot.addWidget(widget)

    apply_shadow(widget, blur=16, offset_y=6, color="rgba(100, 150, 200, 0.5)")

    effect = widget.graphicsEffect()
    assert isinstance(effect, QGraphicsDropShadowEffect)
    assert effect.blurRadius() == 16
    assert effect.yOffset() == 6
    assert effect.color().red() == 100
    assert effect.color().green() == 150
    assert effect.color().blue() == 200
    assert effect.color().alpha() == int(0.5 * 255)


def test_apply_shadow_with_hex_and_named_string(qtbot):
    """Vérifie que apply_shadow accepte des chaînes hexadécimales et nommées."""
    widget = QWidget()
    qtbot.addWidget(widget)

    apply_shadow(widget, blur=8, offset_y=2, color="#6366f1")
    effect = widget.graphicsEffect()
    assert isinstance(effect, QGraphicsDropShadowEffect)
    assert effect.color().name().lower() == "#6366f1"


def test_metric_card_shadow(qtbot):
    """Vérifie que MetricCard s'initialise correctement avec son ombre QColor."""
    card = MetricCard("Cartes Totales", "42", "ph.cards", trend="+5 cette semaine", trend_positive=True)
    qtbot.addWidget(card)

    effect = card.graphicsEffect()
    assert isinstance(effect, QGraphicsDropShadowEffect)
    assert effect.color().alpha() == 40
