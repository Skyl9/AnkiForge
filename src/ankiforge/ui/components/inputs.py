from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QWidget, QComboBox
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPainter, QColor
from ..theme import DesignTokens


class StyledLineEdit(QLineEdit):
    """Input avec style design system. Focus = glow indigo."""

    pass


class StyledTextEdit(QPlainTextEdit):
    """Textarea avec style design system."""

    pass


class GlowLineEdit(QLineEdit):
    """Input avec glow accentué au focus. Usage: recherche, omnibox."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px 16px;
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_MAIN};
            }}
        """)


class ToggleSwitch(QWidget):
    """Toggle iOS-style (36x20px). Usage: Settings."""

    toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(36, 20)
        self._checked = False

    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, checked: bool) -> None:
        self._checked = checked
        self.update()
        self.toggled.emit(self._checked)

    def mousePressEvent(self, event):
        self.set_checked(not self._checked)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_color = QColor(DesignTokens.ACCENT_PRIMARY) if self._checked else QColor(DesignTokens.BORDER_COLOR)
        painter.setBrush(bg_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 10, 10)

        painter.setBrush(QColor("#ffffff"))
        x_pos = self.width() - 18 if self._checked else 2
        painter.drawEllipse(x_pos, 2, 16, 16)


class StyledComboBox(QComboBox):
    """ComboBox avec style design system."""

    pass
