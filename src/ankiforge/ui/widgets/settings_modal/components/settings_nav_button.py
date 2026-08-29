from typing import Any, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QWidget

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class SettingsNavButton(QPushButton):
    """Bouton de navigation latérale avec indicateur d'accent vertical gauche."""

    def __init__(self, title: str, icon_name: str, index: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(f"  {title}", parent)
        self.icon_name = icon_name
        self.tab_index = index
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(38)
        self._apply_style()

    def _apply_style(self) -> None:
        self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.ACCENT_PRIMARY if self.isChecked() else DesignTokens.TEXT_SECONDARY))
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-left: 3px solid transparent;
                text-align: left;
                padding: 6px 14px;
                font-size: 12.5px;
                font-weight: 500;
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QPushButton:checked {{
                background-color: {DesignTokens.BG_ACTIVE};
                color: {DesignTokens.ACCENT_PRIMARY};
                font-weight: bold;
                border-left: 3px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

    def refresh_theme(self, profile: Any) -> None:
        self.setIcon(load_phosphor_icon(self.icon_name, color=profile.accent_primary if self.isChecked() else profile.text_secondary))
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-left: 3px solid transparent;
                text-align: left;
                padding: 6px 14px;
                font-size: 12.5px;
                font-weight: 500;
                border-radius: {profile.radius_sm}px;
                color: {profile.text_secondary};
            }}
            QPushButton:hover {{
                background-color: {profile.bg_hover};
                color: {profile.text_primary};
            }}
            QPushButton:checked {{
                background-color: {profile.bg_active};
                color: {profile.accent_primary};
                font-weight: bold;
                border-left: 3px solid {profile.accent_primary};
            }}
        """)
