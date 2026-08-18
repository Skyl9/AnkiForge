from PySide6.QtWidgets import QLabel, QPushButton, QWidget, QHBoxLayout
from PySide6.QtCore import Signal, Qt
from ankiforge.ui.theme import DesignTokens


class Badge(QLabel):
    """Pill badge. Variantes: filled, outline, status, glass."""

    def __init__(self, text: str, variant: str = "filled", color: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.base_color = color or DesignTokens.ACCENT_PRIMARY
        self.set_variant(variant)

    def set_variant(self, variant: str) -> None:
        style = """
            border-radius: 9999px;
            padding: 3px 12px;
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 0.4px;
        """

        if variant == "filled":
            style += f"background-color: {self.base_color}; color: #ffffff;"
        elif variant == "outline":
            style += f"background-color: transparent; border: 1px solid {self.base_color}; color: {self.base_color};"
        elif variant == "status":
            style += f"background-color: rgba(99, 102, 241, 0.1); color: {self.base_color}; border: 1px solid rgba(99, 102, 241, 0.2);"
        elif variant == "glass":
            style += "background-color: rgba(255, 255, 255, 0.1); color: #ffffff; border: 1px solid rgba(255, 255, 255, 0.2);"
        elif variant == "success":
            style += "background-color: rgba(16, 185, 129, 0.15); color: #10b981;"
        elif variant == "warning":
            style += "background-color: rgba(245, 158, 11, 0.15); color: #f59e0b;"
        elif variant == "info":
            style += "background-color: rgba(59, 130, 246, 0.15); color: #3b82f6;"
        elif variant == "danger":
            style += "background-color: rgba(239, 68, 68, 0.15); color: #ef4444;"
        elif variant == "neutral":
            style += f"background-color: #2d313a; color: {DesignTokens.TEXT_MUTED}; border: 1px solid {DesignTokens.BORDER_COLOR};"

        self.setStyleSheet(f"QLabel {{ {style} }}")


class TagButton(QPushButton):
    """Tag pill avec code font + tint accent. Usage: tags de notes."""

    removed = Signal(str)

    def __init__(self, text: str, removable: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tag_text = text
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(4)

        lbl = QLabel(text)
        lbl.setStyleSheet(f"""
            color: {DesignTokens.ACCENT_PRIMARY};
            font-family: "{DesignTokens.FONT_CODE}";
            font-size: 11px;
        """)
        layout.addWidget(lbl)

        if removable:
            del_lbl = QLabel("×")
            del_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 14px;")
            layout.addWidget(del_lbl)

        self.setStyleSheet(f"""
            TagButton {{
                background-color: {DesignTokens.BG_ACTIVE};
                border: 1px solid rgba(99, 102, 241, 0.2);
                border-radius: 9999px;
            }}
            TagButton:hover {{
                background-color: rgba(99, 102, 241, 0.15);
                border: 1px solid rgba(99, 102, 241, 0.4);
            }}
        """)

    def mouseReleaseEvent(self, event) -> None:
        from PySide6.QtGui import QMouseEvent

        if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.LeftButton:
            self.removed.emit(self.tag_text)
        super().mouseReleaseEvent(event)
