from PySide6.QtWidgets import QLabel, QPushButton, QWidget
from PySide6.QtCore import Signal
from ..theme import DesignTokens


class Badge(QLabel):
    """Pill badge. Variantes: filled, outline, status, glass."""

    def __init__(self, text: str, variant: str = "filled", color: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        base_color = color if color else DesignTokens.ACCENT_PRIMARY

        if variant == "filled":
            self.setStyleSheet(f"background-color: {base_color}; color: #ffffff; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: bold;")
        elif variant == "outline":
            self.setStyleSheet(f"background-color: transparent; color: {base_color}; border: 1px solid {base_color}; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: bold;")
        elif variant == "status":
            self.setStyleSheet(f"background-color: rgba(16, 185, 129, 0.1); color: {DesignTokens.COLOR_GREEN}; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: bold;")


class TagButton(QPushButton):
    """Tag pill avec code font + tint accent. Usage: tags de notes."""

    removed = Signal(str)

    def __init__(self, text: str, removable: bool = False, parent: QWidget | None = None):
        super().__init__(text, parent)
        self._text = text
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(99, 102, 241, 0.1);
                color: {DesignTokens.ACCENT_PRIMARY};
                border: 1px solid rgba(99, 102, 241, 0.2);
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 8px;
                font-family: {DesignTokens.FONT_CODE};
                font-size: 11px;
            }}
        """)
        if removable:
            self.clicked.connect(lambda: self.removed.emit(self._text))
