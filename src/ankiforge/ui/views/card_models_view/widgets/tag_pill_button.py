from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QSizePolicy, QWidget

from ankiforge.ui.theme import DesignTokens


class TagPillButton(QPushButton):
    """Bouton style pilule avec relief, halo subtil et affordance tactile."""

    def __init__(
        self,
        text: str,
        variant: str = "field",  # "field" | "cloze" | "css" | "structure" | "condition"
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        if variant == "cloze":
            bg_tint = DesignTokens.COLOR_PURPLE_BG
            border_color = DesignTokens.COLOR_PURPLE_BORDER
            text_color = DesignTokens.SYNTAX_KEYWORD
        elif variant == "css":
            bg_tint = DesignTokens.BRANCH_B_BG
            border_color = DesignTokens.BRANCH_B_BORDER
            text_color = DesignTokens.SYNTAX_NUMBER
        elif variant == "structure":
            bg_tint = DesignTokens.COLOR_YELLOW_BG
            border_color = DesignTokens.COLOR_YELLOW_BORDER
            text_color = DesignTokens.COLOR_YELLOW_TEXT
        elif variant == "condition":
            bg_tint = DesignTokens.COLOR_GREEN_BG
            border_color = DesignTokens.COLOR_GREEN_BORDER
            text_color = DesignTokens.COLOR_GREEN_TEXT
        else:  # field
            bg_tint = DesignTokens.ACCENT_BG
            border_color = DesignTokens.ACCENT_BORDER
            text_color = DesignTokens.COLOR_PURPLE_TEXT

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_tint};
                border: 1px solid {border_color};
                border-radius: 12px;
                color: {text_color};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 11px;
                font-weight: 600;
                padding: 1px 9px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
                border-color: {DesignTokens.ACCENT_PRIMARY};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QPushButton:pressed {{
                background-color: {DesignTokens.BG_ACTIVE};
                padding-top: 2px;
            }}
        """)
