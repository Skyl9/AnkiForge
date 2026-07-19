from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QFont, QPaintEvent
from ankiforge.ui.theme import DesignTokens


class UserAvatar(QWidget):
    """Avatar 32px avec gradient. Affiche les initiales."""

    def __init__(self, initials: str, size: int = 32, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.initials = initials[:2].upper()
        self.size_val = size

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        grad = QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0, QColor(DesignTokens.ACCENT_PRIMARY))
        grad.setColorAt(1, QColor(DesignTokens.COLOR_PURPLE))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(0, 0, self.width(), self.height())

        p.setPen(QColor("#ffffff"))
        font = QFont(DesignTokens.FONT_MAIN, self.size_val // 3, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.initials)


class StyledToolbar(QWidget):
    """Toolbar flex avec gap-8. Variantes: left, right, space-between."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(48)
        self.layout_h = QHBoxLayout(self)
        self.layout_h.setContentsMargins(16, 0, 16, 0)
        self.layout_h.setSpacing(8)

    def add_widget(self, widget: QWidget) -> None:
        self.layout_h.addWidget(widget)

    def add_stretch(self) -> None:
        self.layout_h.addStretch()

    def add_separator(self) -> None:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet(f"color: {DesignTokens.BORDER_COLOR};")
        self.layout_h.addWidget(sep)


class DaemonStatusWidget(QWidget):
    """Pill statut daemon : spinning icon + texte. Usage: topbar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.layout_h = QHBoxLayout(self)
        self.layout_h.setContentsMargins(8, 0, 12, 0)
        self.layout_h.setSpacing(6)

        self.icon_lbl = QLabel("⚙")
        self.text_lbl = QLabel("Idle")
        self.text_lbl.setStyleSheet("font-size: 12px; font-weight: bold;")

        self.layout_h.addWidget(self.icon_lbl)
        self.layout_h.addWidget(self.text_lbl)
        self.set_status("idle", "Idle")

    def set_status(self, status: str, text: str) -> None:
        self.text_lbl.setText(text)

        if status == "active":
            color = DesignTokens.COLOR_YELLOW
            icon = "⚙"
            bg = "rgba(245, 158, 11, 0.1)"
        elif status == "pending":
            color = DesignTokens.COLOR_BLUE
            icon = "◷"
            bg = "rgba(59, 130, 246, 0.1)"
        else:
            color = DesignTokens.TEXT_MUTED
            icon = "✓"
            bg = "transparent"

        self.icon_lbl.setText(icon)
        self.icon_lbl.setStyleSheet(f"color: {color};")
        self.text_lbl.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: bold;")

        self.setStyleSheet(f"""
            DaemonStatusWidget {{
                background-color: {bg};
                border: 1px solid {color if status != "idle" else DesignTokens.BORDER_COLOR};
                border-radius: 14px;
            }}
        """)
