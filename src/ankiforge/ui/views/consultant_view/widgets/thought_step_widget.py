from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class ThoughtStepWidget(QFrame):
    """Cartouche repliable minimaliste affichant la pensée / le raisonnement de l'agent (Thinking Block)."""

    def __init__(self, step: int = 1, thought_text: str = "", is_running: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.step = step
        self.is_running = is_running
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ThoughtStepWidget {{
                background-color: {DesignTokens.BG_ACTIVE};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
            }}
            ThoughtStepWidget QLabel {{
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        self.icon_lbl = QLabel()
        self._update_icon()
        header_row.addWidget(self.icon_lbl)

        self.lbl_title = QLabel("Pensée" if not is_running else "Réflexion en cours...")
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-weight: 500; font-size: 11px;")
        header_row.addWidget(self.lbl_title, 1)

        self.btn_toggle = QPushButton("Détails ▾")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {DesignTokens.TEXT_MUTED};
                font-size: 10px;
            }}
            QPushButton:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self.btn_toggle.clicked.connect(self._toggle_content)
        header_row.addWidget(self.btn_toggle)
        layout.addLayout(header_row)

        self.lbl_content = QLabel(thought_text)
        self.lbl_content.setWordWrap(True)
        self.lbl_content.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; line-height: 1.4; padding-top: 2px;")
        self.lbl_content.hide()
        layout.addWidget(self.lbl_content)

    def _update_icon(self) -> None:
        icon_name = "ph.spinner" if self.is_running else "ph.brain"
        icon_color = DesignTokens.COLOR_YELLOW if self.is_running else DesignTokens.TEXT_MUTED
        self.icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(13, 13))

    def update_text(self, text: str, is_running: bool = False) -> None:
        self.lbl_content.setText(text)
        self.is_running = is_running
        self.lbl_title.setText("Réflexion en cours..." if is_running else "Pensée")
        self._update_icon()

    def _toggle_content(self) -> None:
        if self.lbl_content.isHidden():
            self.lbl_content.show()
            self.btn_toggle.setText("Masquer ▴")
        else:
            self.lbl_content.hide()
            self.btn_toggle.setText("Détails ▾")

    def refresh_theme(self, profile: Any) -> None:
        self.setStyleSheet(f"""
            ThoughtStepWidget {{
                background-color: {profile.bg_active};
                border: 1px solid {profile.border_color};
                border-radius: 6px;
            }}
            ThoughtStepWidget QLabel {{
                background: transparent;
            }}
        """)
        self.icon_lbl.setPixmap(load_phosphor_icon("ph.brain", color=profile.text_muted).pixmap(13, 13))
        self.lbl_title.setStyleSheet(f"color: {profile.text_muted}; font-weight: 500; font-size: 11px;")
        self.lbl_content.setStyleSheet(f"color: {profile.text_secondary}; font-size: 11px; line-height: 1.4; padding-top: 2px;")
