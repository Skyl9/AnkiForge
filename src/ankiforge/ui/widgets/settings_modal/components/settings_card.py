from typing import Any, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QWidget

from ankiforge.ui.theme import DesignTokens


def apply_pill_badge_style(badge: QLabel, color_hex: str) -> None:
    """Applique un style de capsule/pill arrondie avec fond translucide et bordure assortie."""
    hex_c = color_hex.lstrip("#")
    try:
        r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    except Exception:
        r, g, b = 99, 102, 241
    badge.setStyleSheet(f"""
        QLabel {{
            background-color: rgba({r}, {g}, {b}, 0.14) !important;
            color: {color_hex};
            border: 1px solid rgba({r}, {g}, {b}, 0.40);
            border-radius: 9999px;
            padding: 2px 10px;
            font-size: 11px;
            font-weight: bold;
        }}
    """)


class SettingsCard(QFrame):
    """Conteneur stylé garantissant l'absence de cascade QSS parasite sur les QLabel enfants."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QFrame#SettingsCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame#SettingsCard QLabel {{
                background: transparent;
                border: none;
            }}
        """)

    def refresh_theme(self, profile: Any) -> None:
        self.setStyleSheet(f"""
            QFrame#SettingsCard {{
                background-color: {profile.bg_panel};
                border: 1px solid {profile.border_color};
                border-radius: {profile.radius_md}px;
            }}
            QFrame#SettingsCard QLabel {{
                background: transparent;
                border: none;
            }}
        """)
