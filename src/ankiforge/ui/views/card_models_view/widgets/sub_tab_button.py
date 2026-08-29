from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QWidget

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class SubTabButton(QPushButton):
    """Bouton d'onglet style IDE avec relief et affordance tactile."""

    def __init__(self, text: str, icon_name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.icon_name = icon_name
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(30)
        self.set_active(False)

    def set_active(self, active: bool) -> None:
        if active:
            self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.ACCENT_PRIMARY))
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_PANEL};
                    color: {DesignTokens.TEXT_PRIMARY};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-bottom: 2px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 4px 14px;
                    font-size: 11px;
                    font-weight: bold;
                }}
            """)
        else:
            self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.TEXT_MUTED))
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {DesignTokens.TEXT_SECONDARY};
                    border: 1px solid transparent;
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 4px 14px;
                    font-size: 11px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                    color: {DesignTokens.TEXT_PRIMARY};
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                }}
                QPushButton:pressed {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    padding-top: 5px;
                }}
            """)
