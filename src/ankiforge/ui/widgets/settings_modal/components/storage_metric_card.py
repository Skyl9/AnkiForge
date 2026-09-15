from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class StorageMetricCard(QFrame):
    """Carte d'affichage de statistique de stockage avec icône Phosphor et sous-titre."""

    def __init__(self, title: str, value: str, icon_name: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.icon_name = icon_name
        self.setObjectName("StorageMetricCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; text-transform: uppercase;")
        top_row.addWidget(self.lbl_title)
        top_row.addStretch()

        self.lbl_icon = QLabel()
        self.lbl_icon.setPixmap(load_phosphor_icon(icon_name, color=DesignTokens.ACCENT_PRIMARY).pixmap(18, 18))
        top_row.addWidget(self.lbl_icon)
        layout.addLayout(top_row)

        self.lbl_val = QLabel(value)
        self.lbl_val.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 18px; font-weight: bold; font-family: '{DesignTokens.FONT_CODE}';")
        layout.addWidget(self.lbl_val)

        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 11px;")
        layout.addWidget(self.lbl_sub)

        self._apply_style()

    def update_metric(self, value: str, subtitle: str = "") -> None:
        self.lbl_val.setText(value)
        if subtitle:
            self.lbl_sub.setText(subtitle)

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QFrame#StorageMetricCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)

    def refresh_theme(self, profile: Any) -> None:
        self.setStyleSheet(f"""
            QFrame#StorageMetricCard {{
                background-color: {profile.bg_panel};
                border: 1px solid {profile.border_color};
                border-radius: {profile.radius_md}px;
            }}
        """)
        self.lbl_title.setStyleSheet(f"color: {profile.text_muted}; font-size: 11px; font-weight: bold; text-transform: uppercase;")
        self.lbl_val.setStyleSheet(f"color: {profile.text_primary}; font-size: 18px; font-weight: bold; font-family: '{profile.font_code}';")
        self.lbl_sub.setStyleSheet(f"color: {profile.color_green}; font-size: 11px;")
        self.lbl_icon.setPixmap(load_phosphor_icon(self.icon_name, color=profile.accent_primary).pixmap(18, 18))
