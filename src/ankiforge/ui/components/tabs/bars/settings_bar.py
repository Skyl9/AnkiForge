from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QPushButton, QVBoxLayout, QWidget

from ankiforge.ui.theme import DesignTokens


class SettingsTabBar(QWidget):
    """Tab bar verticale pour le modal Settings."""

    tab_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.layout_v = QVBoxLayout(self)
        self.layout_v.setContentsMargins(0, 0, 0, 0)
        self.layout_v.setSpacing(4)
        self.btn_group = QButtonGroup(self)
        self.btn_group.idClicked.connect(self.tab_changed.emit)
        self.tabs: list[QPushButton] = []
        self.layout_v.addStretch()

    def add_tab(self, title: str, icon_name: str) -> int:
        idx = len(self.tabs)
        btn = QPushButton(f"{icon_name}  {title}")
        btn.setCheckable(True)
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        btn.setStyleSheet(f"""
            QPushButton {{
                text-align: left;
                background-color: transparent;
                color: {DesignTokens.TEXT_SECONDARY};
                border: none;
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 0 12px;
                font-family: "{DesignTokens.FONT_MAIN}";
            }}
            QPushButton:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
            QPushButton:checked {{
                background-color: {DesignTokens.BG_ACTIVE};
                color: {DesignTokens.ACCENT_PRIMARY};
                font-weight: bold;
            }}
        """)

        self.btn_group.addButton(btn, idx)
        self.tabs.append(btn)
        self.layout_v.insertWidget(idx, btn)

        if len(self.tabs) == 1:
            btn.setChecked(True)

        return idx

    def set_tab_text(self, index: int, text: str) -> None:
        if 0 <= index < len(self.tabs):
            btn = self.tabs[index]
            icon_name = btn.property("icon_name") or ""
            display_text = f" {text}" if icon_name else text
            btn.setText(display_text)
