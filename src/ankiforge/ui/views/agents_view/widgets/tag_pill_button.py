from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QSizePolicy, QWidget

from ankiforge.ui.theme import DesignTokens


class TagPillButton(QPushButton):
    """Bouton pastille pour insérer des variables Jinja2 au curseur avec relief et affordance."""

    def __init__(
        self,
        text: str,
        template_code: str,
        tooltip: str = "",
        variant: str = "field",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(text, parent)
        self.template_code = template_code
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setToolTip(f"{tooltip}\nInsère : {template_code}")

        if variant == "cloze":
            bg_tint = "rgba(168, 85, 247, 0.12)"
            border_color = "rgba(168, 85, 247, 0.45)"
            text_color = "#c084fc"
        elif variant == "css":
            bg_tint = "rgba(6, 182, 212, 0.12)"
            border_color = "rgba(6, 182, 212, 0.45)"
            text_color = "#67e8f9"
        elif variant == "structure":
            bg_tint = "rgba(245, 158, 11, 0.12)"
            border_color = "rgba(245, 158, 11, 0.45)"
            text_color = "#fcd34d"
        elif variant == "condition":
            bg_tint = "rgba(16, 185, 129, 0.12)"
            border_color = "rgba(16, 185, 129, 0.45)"
            text_color = "#6ee7b7"
        else:  # field
            bg_tint = "rgba(99, 102, 241, 0.10)"
            border_color = "rgba(99, 102, 241, 0.40)"
            text_color = "#a5b4fc"

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_tint};
                border: 1px solid {border_color};
                border-radius: 12px;
                color: {text_color};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 11px;
                font-weight: 600;
                padding: 1px 10px;
            }}
            QPushButton:hover {{
                border: 1.5px solid {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {DesignTokens.BG_ACTIVE};
            }}
        """)
