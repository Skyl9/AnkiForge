from typing import Any
from PySide6.QtWidgets import QPushButton, QWidget, QFrame, QVBoxLayout, QLabel, QGraphicsDropShadowEffect
from PySide6.QtCore import Signal, Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QCursor
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.utils.icon_loader import load_phosphor_icon


class PrimaryButton(QPushButton):
    """Bouton principal avec glow. Usage: actions primaires."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(36)
        self.setProperty("role", "primary")

        apply_shadow(self, blur=10, offset_y=0, color="rgba(99,102,241,0.4)")
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            self.anim = QPropertyAnimation(effect, b"blurRadius")
            self.anim.setDuration(150)
            self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            self.default_blur = 10
            self.hover_blur = 16

    def enterEvent(self, event) -> None:
        if hasattr(self, "anim"):
            self.anim.setEndValue(self.hover_blur)
            self.anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if hasattr(self, "anim"):
            self.anim.setEndValue(self.default_blur)
            self.anim.start()
        super().leaveEvent(event)


class SecondaryButton(QPushButton):
    """Bouton secondaire avec bordure. Usage: actions secondaires."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(36)
        self.setProperty("role", "secondary")


class DangerButton(QPushButton):
    """Bouton danger rouge. Variantes: filled et ghost."""

    def __init__(self, text: str, ghost: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(36)
        self.setProperty("role", "danger")


class IconButton(QPushButton):
    """Bouton icône carré. Usage: actions secondaires, close, toggle."""

    def __init__(self, icon_name: str, tooltip: str = "", size: int = 32, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.icon_name = icon_name
        self.setFixedSize(size, size)
        self.setToolTip(tooltip)
        self.setProperty("role", "icon")

        if icon_name:
            self.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_PRIMARY))
            self.setIconSize(self.size() * 0.6)
            self.setText("")

    def refresh_theme(self, profile: Any) -> None:
        if self.icon_name:
            self.setIcon(load_phosphor_icon(self.icon_name, color=profile.text_primary))


class PremiumActionCard(QFrame):
    """Grande carte d'action avec icône + titre + description. Usage: Dashboard."""

    clicked = Signal()

    def __init__(self, icon_name: str, title: str, description: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.icon_name = icon_name
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMinimumHeight(100)
        self.setProperty("card-style", "elevated")
        apply_shadow(self, blur=12, offset_y=4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self.icon_label = QLabel()
        pixmap = load_phosphor_icon(icon_name, color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24)
        self.icon_label.setPixmap(pixmap)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")

        self.desc_label = QLabel(description)
        self.desc_label.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY};")
        self.desc_label.setWordWrap(True)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.desc_label)
        layout.addStretch()

    def refresh_theme(self, profile: Any) -> None:
        if hasattr(self, "icon_name") and self.icon_name:
            pixmap = load_phosphor_icon(self.icon_name, color=profile.accent_primary).pixmap(24, 24)
            self.icon_label.setPixmap(pixmap)

    def mouseReleaseEvent(self, event) -> None:
        from PySide6.QtGui import QMouseEvent

        if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)
