from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget

from ankiforge.ui.theme import DesignTokens


class PillTabBar(QWidget):
    """Tab bar style pill/segment. Usage: sous-navigation dans les panneaux."""

    tab_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        self.layout_h = QHBoxLayout(self)
        self.layout_h.setContentsMargins(2, 2, 2, 2)
        self.layout_h.setSpacing(2)
        self.setStyleSheet(f"""
            PillTabBar {{
                background-color: {DesignTokens.BG_INPUT};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        self.btn_group = QButtonGroup(self)
        self.btn_group.idClicked.connect(self.tab_changed.emit)
        self.tabs: list[QPushButton] = []

    def add_tab(self, title: str) -> int:
        idx = len(self.tabs)
        btn = QPushButton(title)
        btn.setCheckable(True)
        btn.setFixedHeight(28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {DesignTokens.TEXT_SECONDARY};
                border: none;
                border-radius: {DesignTokens.RADIUS_SM - 2}px;
                padding: 0 12px;
                font-family: "{DesignTokens.FONT_MAIN}";
            }}
            QPushButton:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QPushButton:checked {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                font-weight: bold;
            }}
        """)

        self.btn_group.addButton(btn, idx)
        self.tabs.append(btn)
        self.layout_h.addWidget(btn)

        if len(self.tabs) == 1:
            btn.setChecked(True)

        return idx
