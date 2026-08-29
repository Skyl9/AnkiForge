from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class ThoughtStepWidget(QFrame):
    """Cartouche repliable affichant la pensée / le raisonnement ReAct d'une étape."""

    def __init__(self, step: int, thought_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ThoughtStepWidget {{
                background-color: {DesignTokens.BG_ACTIVE};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 8px;
            }}
            ThoughtStepWidget QLabel {{
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.brain", color=DesignTokens.ACCENT_PRIMARY).pixmap(14, 14))
        header_row.addWidget(icon_lbl)

        lbl_title = QLabel(f"Raisonnement ReAct — Étape {step}")
        lbl_title.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-weight: bold; font-size: 11px;")
        header_row.addWidget(lbl_title, 1)

        self.btn_toggle = QPushButton("Détails ▾")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {DesignTokens.TEXT_MUTED};
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self.btn_toggle.clicked.connect(self._toggle_content)
        header_row.addWidget(self.btn_toggle)
        layout.addLayout(header_row)

        self.icon_lbl = icon_lbl
        self.lbl_title = lbl_title
        self.lbl_content = QLabel(thought_text)
        self.lbl_content.setWordWrap(True)
        self.lbl_content.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; line-height: 1.4;")
        self.lbl_content.hide()
        layout.addWidget(self.lbl_content)

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
                border-radius: 8px;
            }}
            ThoughtStepWidget QLabel {{
                background: transparent;
            }}
        """)
        self.icon_lbl.setPixmap(load_phosphor_icon("ph.brain", color=profile.accent_primary).pixmap(14, 14))
        self.lbl_title.setStyleSheet(f"color: {profile.accent_primary}; font-weight: bold; font-size: 11px;")
        self.lbl_content.setStyleSheet(f"color: {profile.text_secondary}; font-size: 11px; line-height: 1.4;")
