"""
Overlay d'animation de chargement et de transition de style / thème.
Affiche un rideau fluide et élégant avec indicateur animé lors de l'application d'un nouveau thème.
"""

from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QFont, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class SpinningIconLabel(QWidget):
    """Widget d'icône avec rotation fluide et gestion propre du cycle de vie QPainter."""

    def __init__(self, icon_name: str = "ph.palette", color: str = "#6366f1", size: int = 36, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle = 0
        self._icon_name = icon_name
        self._color = color
        self._size = size
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._pixmap = load_phosphor_icon(icon_name, color=color).pixmap(size, size)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(30)  # ~33 FPS

    def _rotate(self) -> None:
        self._angle = (self._angle + 12) % 360
        self.update()

    def stop(self) -> None:
        if self._timer.isActive():
            self._timer.stop()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter()
        if not painter.begin(self):
            return
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

            cx, cy = self.width() / 2.0, self.height() / 2.0
            painter.translate(cx, cy)
            painter.rotate(self._angle)
            painter.translate(-cx, -cy)

            painter.drawPixmap(0, 0, self._pixmap)
        finally:
            painter.end()


class ThemeTransitionOverlay(QWidget):
    """
    Overlay semi-transparent affichant une carte animée pendant le changement de thème.
    """

    def __init__(
        self,
        parent: QWidget,
        theme_title: str = "Nouveau Thème",
        subtext: str = "Application des composants et du design system...",
        duration_ms: int = 400,
        on_applied: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._parent_widget = parent
        self._duration_ms = duration_ms
        self._on_applied = on_applied

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setGeometry(parent.rect())

        if parent:
            parent.installEventFilter(self)

        self._setup_ui(theme_title, subtext)
        self._start_transition()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched == self._parent_widget and event.type() == QEvent.Type.Resize:
            self.setGeometry(self._parent_widget.rect())
        return super().eventFilter(watched, event)

    def _setup_ui(self, title: str, subtext: str) -> None:
        # Opacity effect sur l'overlay global
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(0.0)

        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Fond assombri
        self.setStyleSheet("background-color: rgba(10, 12, 16, 0.75);")

        # Carte centrale
        self.card = QFrame()
        self.card.setFixedSize(380, 150)
        self.card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(12)

        # Ligne d'en-tête avec icône rotative
        header_row = QHBoxLayout()
        header_row.setSpacing(14)

        self.spinner = SpinningIconLabel(icon_name="ph.palette", color=DesignTokens.ACCENT_PRIMARY, size=32)
        header_row.addWidget(self.spinner)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        lbl_title = QLabel(f"Application : {title}")
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

        lbl_sub = QLabel(subtext)
        lbl_sub.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        lbl_sub.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")

        text_col.addWidget(lbl_title)
        text_col.addWidget(lbl_sub)
        header_row.addLayout(text_col, 1)

        card_layout.addLayout(header_row)

        # Barre de progression indéterminée
        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 0)  # Indéterminé
        self.prog_bar.setFixedHeight(4)
        self.prog_bar.setTextVisible(False)
        self.prog_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {DesignTokens.BG_INPUT};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-radius: 2px;
            }}
        """)
        card_layout.addWidget(self.prog_bar)

        main_layout.addWidget(self.card)

    def _start_transition(self) -> None:
        self.show()
        self.raise_()

        # Fade in
        self._anim_in = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._anim_in.setDuration(120)
        self._anim_in.setStartValue(0.0)
        self._anim_in.setEndValue(1.0)
        self._anim_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_in.finished.connect(self._on_fade_in_finished)
        self._anim_in.start()

    def _on_fade_in_finished(self) -> None:
        # Exécuter l'action de changement de thème
        if self._on_applied:
            self._on_applied()

        # Attendre un court instant pour laisser l'utilisateur apprécier l'animation
        QTimer.singleShot(max(180, self._duration_ms - 240), self._fade_out)

    def _fade_out(self) -> None:
        self._anim_out = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._anim_out.setDuration(180)
        self._anim_out.setStartValue(1.0)
        self._anim_out.setEndValue(0.0)
        self._anim_out.setEasingCurve(QEasingCurve.Type.InCubic)

        self._anim_out.finished.connect(self._cleanup)
        self._anim_out.start()

    def _cleanup(self) -> None:
        if hasattr(self, "spinner") and self.spinner:
            self.spinner.stop()
        if self._parent_widget:
            self._parent_widget.removeEventFilter(self)
        self.deleteLater()


def show_theme_transition(
    parent: QWidget | None,
    theme_title: str = "Nouveau Thème",
    subtext: str = "Application des composants et du design system...",
    duration_ms: int = 400,
    on_applied: Callable[[], None] | None = None,
) -> ThemeTransitionOverlay | None:
    """
    Lance une animation de transition fluide par-dessus le widget parent.
    """
    if not parent:
        if on_applied:
            on_applied()
        return None

    return ThemeTransitionOverlay(
        parent=parent,
        theme_title=theme_title,
        subtext=subtext,
        duration_ms=duration_ms,
        on_applied=on_applied,
    )
