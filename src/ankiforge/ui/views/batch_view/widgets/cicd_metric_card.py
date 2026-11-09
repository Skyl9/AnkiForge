from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class CicdMetricCard(QFrame):
    """Cellule métrique CI/CD intégrée et flush pour la barre supérieure de BatchView."""

    clicked = Signal()

    def __init__(
        self,
        title: str,
        value: str,
        icon_name: str,
        color: str = DesignTokens.COLOR_GREEN,
        parent: QWidget | None = None,
        clickable: bool = False,
        show_right_border: bool = True,
    ) -> None:
        super().__init__(parent)
        self.title_text = title
        self.icon_name = icon_name
        self.color = color
        self._clickable = clickable
        self._show_right_border = show_right_border
        self.setFixedHeight(48)
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(10)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: 700; border: none; background: transparent; text-transform: uppercase; letter-spacing: 0.5px;")

        self.val_lbl = QLabel(value)
        self.val_lbl.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: 700; border: none; background: transparent; font-family: '{DesignTokens.FONT_CODE}';")

        text_layout.addWidget(self.title_lbl)
        text_layout.addWidget(self.val_lbl)
        layout.addLayout(text_layout, 1)

        self.icon_lbl = QLabel()
        self.icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=color).pixmap(20, 20))
        self.icon_lbl.setStyleSheet("border: none; background: transparent; opacity: 0.85;")
        layout.addWidget(self.icon_lbl)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._clickable and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def _apply_style(self, profile: Any = None) -> None:
        bg_panel = profile.bg_panel if profile else DesignTokens.BG_PANEL
        bg_hover = profile.bg_hover if profile else DesignTokens.BG_HOVER
        border_col = profile.border_color if profile else DesignTokens.BORDER_COLOR
        border_right = f"border-right: 1px solid {border_col};" if self._show_right_border else "border-right: none;"
        hover_css = f"CicdMetricCard:hover {{ background-color: {bg_hover}; }}" if self._clickable else ""
        self.setStyleSheet(f"""
            CicdMetricCard {{
                background-color: {bg_panel};
                border: none;
                {border_right}
                border-radius: 0px;
                padding: 0px;
            }}
            {hover_css}
        """)

    def refresh_theme(self, profile: Any) -> None:
        self._apply_style(profile)
        if hasattr(self, "title_lbl"):
            self.title_lbl.setStyleSheet(f"color: {profile.text_muted}; font-size: 10px; font-weight: 700; border: none; background: transparent; text-transform: uppercase; letter-spacing: 0.5px;")
        if hasattr(self, "val_lbl"):
            self.val_lbl.setStyleSheet(f"color: {self.color}; font-size: 14px; font-weight: 700; border: none; background: transparent; font-family: '{profile.font_code}';")
        if hasattr(self, "icon_lbl"):
            self.icon_lbl.setPixmap(load_phosphor_icon(self.icon_name, color=self.color).pixmap(20, 20))
