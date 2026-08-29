from typing import Any

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QLabel, QPushButton, QVBoxLayout, QWidget

from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.utils.icon_loader import load_phosphor_icon


class PrimaryButton(QPushButton):
    """Bouton principal avec glow et affordance tactile. Usage: actions primaires."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(36)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setProperty("role", "primary")

        apply_shadow(self, blur=10, offset_y=0, color="rgba(99,102,241,0.4)")
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            self.anim = QPropertyAnimation(effect, b"blurRadius")
            self.anim.setDuration(150)
            self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            self.default_blur = 10
            self.hover_blur = 16

    def enterEvent(self, event: Any) -> None:
        if hasattr(self, "anim"):
            self.anim.setEndValue(self.hover_blur)
            self.anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        if hasattr(self, "anim"):
            self.anim.setEndValue(self.default_blur)
            self.anim.start()
        super().leaveEvent(event)

    def refresh_theme(self, profile: Any = None) -> None:
        pass


class SecondaryButton(QPushButton):
    """Bouton secondaire avec relief, contour d'accentuation au survol et affordance tactile."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(36)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setProperty("role", "secondary")

        apply_shadow(self, blur=2, offset_y=1, color="rgba(0,0,0,0.18)")
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            self.anim = QPropertyAnimation(effect, b"blurRadius")
            self.anim.setDuration(150)
            self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            self.default_blur = 2
            self.hover_blur = 10

    def enterEvent(self, event: Any) -> None:
        if hasattr(self, "anim"):
            self.anim.setEndValue(self.hover_blur)
            self.anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        if hasattr(self, "anim"):
            self.anim.setEndValue(self.default_blur)
            self.anim.start()
        super().leaveEvent(event)

    def refresh_theme(self, profile: Any = None) -> None:
        pass


class ActionButton(SecondaryButton):
    """Bouton d'action avec icône Phosphor/FA optionnelle et libellé textuel."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        icon_name = ""
        parent = kwargs.pop("parent", None)

        if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], str):
            icon_name = args[0]
            text = args[1]
            if len(args) > 2 and isinstance(args[2], QWidget):
                parent = args[2]
            super().__init__(text, parent, **kwargs)
        elif len(args) == 1 and isinstance(args[0], str):
            text = args[0]
            super().__init__(text, parent, **kwargs)
        else:
            super().__init__(*args, **kwargs)

        self.icon_name = icon_name
        if icon_name:
            self.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_PRIMARY))

    def refresh_theme(self, profile: Any = None) -> None:
        if hasattr(self, "icon_name") and self.icon_name:
            color = profile.text_primary if profile else DesignTokens.TEXT_PRIMARY
            self.setIcon(load_phosphor_icon(self.icon_name, color=color))


class DangerButton(QPushButton):
    """Bouton danger rouge avec halo lumineux au survol. Variantes: filled et ghost."""

    def __init__(self, text: str, ghost: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(36)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setProperty("role", "danger")

        apply_shadow(self, blur=2, offset_y=1, color="rgba(239,68,68,0.25)")
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            self.anim = QPropertyAnimation(effect, b"blurRadius")
            self.anim.setDuration(150)
            self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            self.default_blur = 2
            self.hover_blur = 12

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

    def refresh_theme(self, profile: Any = None) -> None:
        pass


class IconButton(QPushButton):
    """Bouton icône carré avec relief et affordance tactile."""

    def __init__(self, icon_name: str, tooltip: str = "", size: int = 32, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.icon_name = icon_name
        self.setFixedSize(size, size)
        self.setToolTip(tooltip)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setProperty("role", "icon")

        if icon_name:
            self.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_PRIMARY))
            self.setIconSize(self.size() * 0.6)
            self.setText("")

        apply_shadow(self, blur=2, offset_y=1, color="rgba(0,0,0,0.15)")
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            self.anim = QPropertyAnimation(effect, b"blurRadius")
            self.anim.setDuration(150)
            self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            self.default_blur = 2
            self.hover_blur = 8

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

    def refresh_theme(self, profile: Any = None) -> None:
        if self.icon_name:
            color = profile.text_primary if profile else DesignTokens.TEXT_PRIMARY
            self.setIcon(load_phosphor_icon(self.icon_name, color=color))


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
        if hasattr(self, "title_label"):
            self.title_label.setStyleSheet(f"font-weight: bold; color: {profile.text_primary};")
        if hasattr(self, "desc_label"):
            self.desc_label.setStyleSheet(f"color: {profile.text_secondary};")

    def mouseReleaseEvent(self, event) -> None:
        from PySide6.QtGui import QMouseEvent

        if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)
