from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout
from PySide6.QtCore import Signal
from ..theme import DesignTokens


class IdeTabBar(QWidget):
    """Tab bar style JetBrains avec indicateur accent 2px en haut."""

    tab_changed = Signal(int)
    tab_reordered = Signal(int, int)
    tab_close_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.layout_main = QHBoxLayout(self)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        self.layout_main.setSpacing(2)
        self.buttons: list[QPushButton] = []
        self.active_index = -1

    def add_tab(self, title: str, icon_name: str = "", closable: bool = False) -> int:
        btn = QPushButton(f"{icon_name} {title}".strip())
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {DesignTokens.TEXT_SECONDARY};
                border: none;
                border-top: 2px solid transparent;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        index = len(self.buttons)
        btn.clicked.connect(lambda: self.set_active(index))
        self.buttons.append(btn)
        self.layout_main.addWidget(btn)
        return index

    def set_active(self, index: int) -> None:
        if 0 <= index < len(self.buttons):
            self.active_index = index
            for i, btn in enumerate(self.buttons):
                if i == index:
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background-color: {DesignTokens.BG_PANEL};
                            color: {DesignTokens.TEXT_PRIMARY};
                            border: none;
                            border-top: 2px solid {DesignTokens.ACCENT_PRIMARY};
                            padding: 6px 12px;
                        }}
                    """)
                else:
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background-color: transparent;
                            color: {DesignTokens.TEXT_SECONDARY};
                            border: none;
                            border-top: 2px solid transparent;
                            padding: 6px 12px;
                        }}
                        QPushButton:hover {{
                            background-color: {DesignTokens.BG_HOVER};
                        }}
                    """)
            self.tab_changed.emit(index)


class PillTabBar(QWidget):
    """Tab bar style pill/segment. Usage: sous-navigation dans les panneaux."""

    tab_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.layout_main = QHBoxLayout(self)
        self.layout_main.setContentsMargins(4, 4, 4, 4)
        self.layout_main.setSpacing(4)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_INPUT}; border-radius: {DesignTokens.RADIUS_MD}px;")
        self.buttons: list[QPushButton] = []

    def add_tab(self, title: str) -> int:
        btn = QPushButton(title)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {DesignTokens.TEXT_SECONDARY};
                border: none;
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        index = len(self.buttons)
        btn.clicked.connect(lambda: self._on_clicked(index))
        self.buttons.append(btn)
        self.layout_main.addWidget(btn)
        return index

    def _on_clicked(self, index: int):
        for i, btn in enumerate(self.buttons):
            if i == index:
                btn.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; color: {DesignTokens.TEXT_PRIMARY}; border-radius: {DesignTokens.RADIUS_SM}px; padding: 6px 12px;")
            else:
                btn.setStyleSheet(f"background-color: transparent; color: {DesignTokens.TEXT_SECONDARY}; border-radius: {DesignTokens.RADIUS_SM}px; padding: 6px 12px;")
        self.tab_changed.emit(index)


class SettingsTabBar(QWidget):
    """Tab bar verticale pour le modal Settings."""

    tab_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        self.layout_main.setSpacing(4)
        self.buttons: list[QPushButton] = []

    def add_tab(self, title: str, icon_name: str) -> int:
        btn = QPushButton(f"{icon_name}  {title}")
        btn.setStyleSheet(f"text-align: left; padding: 8px; color: {DesignTokens.TEXT_SECONDARY}; border: none; border-radius: {DesignTokens.RADIUS_SM}px;")
        index = len(self.buttons)
        btn.clicked.connect(lambda: self._on_clicked(index))
        self.buttons.append(btn)
        self.layout_main.addWidget(btn)
        return index

    def _on_clicked(self, index: int):
        for i, btn in enumerate(self.buttons):
            if i == index:
                btn.setStyleSheet(
                    f"text-align: left; padding: 8px; background-color: {DesignTokens.BG_ACTIVE}; color: {DesignTokens.ACCENT_PRIMARY}; border: none; border-radius: {DesignTokens.RADIUS_SM}px;"
                )
            else:
                btn.setStyleSheet(f"text-align: left; padding: 8px; background-color: transparent; color: {DesignTokens.TEXT_SECONDARY}; border: none; border-radius: {DesignTokens.RADIUS_SM}px;")
        self.tab_changed.emit(index)
