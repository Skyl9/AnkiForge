from typing import Any

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.utils.icon_loader import load_phosphor_icon


class CicdMetricCard(QFrame):
    """Stat Card épurée et compacte conforme à la maquette concept_ide (L1888-L1916)."""

    def __init__(self, title: str, value: str, icon_name: str, color: str = "#10b981", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title_text = title
        self.icon_name = icon_name
        self.color = color
        self.setFixedHeight(58)
        self._apply_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; border: none; text-transform: uppercase; letter-spacing: 0.5px;")

        self.val_lbl = QLabel(value)
        self.val_lbl.setStyleSheet(f"color: {color}; font-size: 15px; font-weight: bold; border: none; font-family: '{DesignTokens.FONT_CODE}';")

        text_layout.addWidget(self.title_lbl)
        text_layout.addWidget(self.val_lbl)
        layout.addLayout(text_layout, 1)

        self.icon_lbl = QLabel()
        self.icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=color).pixmap(24, 24))
        self.icon_lbl.setStyleSheet("border: none; background: transparent; opacity: 0.85;")
        layout.addWidget(self.icon_lbl)
        apply_shadow(self, blur=8, offset_y=2)

    def _apply_style(self, profile: Any = None) -> None:
        bg_panel = profile.bg_panel if profile else DesignTokens.BG_PANEL
        border_col = profile.border_color if profile else DesignTokens.BORDER_COLOR
        radius_md = profile.radius_md if profile else DesignTokens.RADIUS_MD
        self.setStyleSheet(f"""
            CicdMetricCard {{
                background-color: {bg_panel};
                border: 1px solid {border_col};
                border-radius: {radius_md}px;
                padding: 0px;
            }}
        """)

    def refresh_theme(self, profile: Any) -> None:
        self._apply_style(profile)
        if hasattr(self, "title_lbl"):
            self.title_lbl.setStyleSheet(f"color: {profile.text_muted}; font-size: 10px; font-weight: bold; border: none; text-transform: uppercase; letter-spacing: 0.5px;")
        if hasattr(self, "val_lbl"):
            self.val_lbl.setStyleSheet(f"color: {self.color}; font-size: 15px; font-weight: bold; border: none; font-family: '{profile.font_code}';")
        if hasattr(self, "icon_lbl"):
            self.icon_lbl.setPixmap(load_phosphor_icon(self.icon_name, color=self.color).pixmap(24, 24))
