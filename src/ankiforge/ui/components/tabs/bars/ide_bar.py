from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class IdeTabBar(QWidget):
    """Tab bar style JetBrains avec indicateur accent 2px en haut."""

    tab_changed = Signal(int)
    tab_reordered = Signal(int, int)
    tab_close_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)
        self.layout_h = QHBoxLayout(self)
        self.layout_h.setContentsMargins(0, 0, 0, 0)
        self.layout_h.setSpacing(0)
        self.btn_group = QButtonGroup(self)
        self.btn_group.idClicked.connect(self.tab_changed.emit)
        self.tabs: list[QPushButton] = []
        self.layout_h.addStretch()

    def add_tab(self, title: str, icon_name: str = "", closable: bool = False) -> int:
        idx = len(self.tabs)
        btn = QPushButton(f" {title}" if icon_name else title)

        if icon_name:
            btn.setProperty("icon_name", icon_name)
            btn.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_SECONDARY))

        btn.setCheckable(True)
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {DesignTokens.TEXT_SECONDARY};
                border: none;
                border-right: 1px solid {DesignTokens.BORDER_COLOR};
                border-top: 2px solid transparent;
                padding: 0 16px;
                font-family: "{DesignTokens.FONT_MAIN}";
            }}
            QPushButton:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
            QPushButton:checked {{
                color: {DesignTokens.TEXT_PRIMARY};
                border-top: 2px solid {DesignTokens.ACCENT_PRIMARY};
                border-right: 1px solid {DesignTokens.BORDER_COLOR};
                background-color: {DesignTokens.BG_PANEL};
                font-weight: bold;
            }}
        """)

        self.btn_group.addButton(btn, idx)
        self.tabs.append(btn)
        self.layout_h.insertWidget(idx, btn)

        if len(self.tabs) == 1:
            btn.setChecked(True)

        return idx

    def set_active(self, index: int) -> None:
        if 0 <= index < len(self.tabs):
            self.tabs[index].setChecked(True)
            self.tab_changed.emit(index)

    def refresh_theme(self, profile: Any = None) -> None:
        for btn in self.tabs:
            icon_name = btn.property("icon_name")
            if icon_name:
                c = DesignTokens.ACCENT_PRIMARY if btn.isChecked() else DesignTokens.TEXT_SECONDARY
                btn.setIcon(load_phosphor_icon(icon_name, color=c))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {DesignTokens.TEXT_SECONDARY};
                    border: none;
                    border-right: 1px solid {DesignTokens.BORDER_COLOR};
                    border-top: 2px solid transparent;
                    padding: 0 16px;
                    font-family: "{DesignTokens.FONT_MAIN}";
                }}
                QPushButton:hover {{
                    color: {DesignTokens.TEXT_PRIMARY};
                    background-color: {DesignTokens.BG_HOVER};
                }}
                QPushButton:checked {{
                    color: {DesignTokens.TEXT_PRIMARY};
                    border-top: 2px solid {DesignTokens.ACCENT_PRIMARY};
                    border-right: 1px solid {DesignTokens.BORDER_COLOR};
                    background-color: {DesignTokens.BG_PANEL};
                    font-weight: bold;
                }}
            """)
