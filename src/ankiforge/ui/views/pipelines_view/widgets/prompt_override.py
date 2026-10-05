"""Indicateur de surcharge locale : dit si un prompt est figé et si son agent a bougé depuis."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.ai.persona_override import PersonaOverrideState
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

_STYLE = """
QFrame#PromptOverrideIndicator {{
    background: {bg};
    border: 1px solid {border};
    border-radius: {radius}px;
}}
QFrame#PromptOverrideIndicator QLabel {{
    background: transparent;
}}
QPushButton#PromptOverrideRemove {{
    background: transparent;
    border: none;
    color: {text};
    font-size: 11px;
    padding: 2px 6px;
}}
QPushButton#PromptOverrideRemove:hover {{
    color: {strong};
}}
"""


class PromptOverrideIndicator(QFrame):
    """Rend visible l'état d'une surcharge locale et permet de la lever.

    L'indicateur n'apparaît que lorsqu'une surcharge existe : son silence est le message
    « l'étape suit son agent », et c'est cette absence qu'il faut préserver.
    """

    remove_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PromptOverrideIndicator")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(8)

        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(16, 16)
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.lbl_icon, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.lbl_summary = QLabel()
        self.lbl_summary.setWordWrap(True)
        self.lbl_summary.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        row.addWidget(self.lbl_summary, 1, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_remove = QPushButton(self.tr("Retirer"))
        self.btn_remove.setObjectName("PromptOverrideRemove")
        self.btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove.setToolTip(self.tr("Retirer la surcharge locale et rendre à l'agent son prompt d'origine."))
        self.btn_remove.clicked.connect(self.remove_requested.emit)
        row.addWidget(self.btn_remove, alignment=Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(row)
        self.setVisible(False)

    def set_state(self, state: PersonaOverrideState) -> None:
        """Affiche ou efface l'indicateur selon l'état de la surcharge.

        La dérive de l'agent change la teinte, pas la structure : un badge d'alerte qui
        clignoterait à chaque frappe d'agent serait plus fatigant qu'utile.
        """
        if not state.active:
            self.setVisible(False)
            return

        drifted = state.persona_changed_since_freeze
        self._restyle(drifted)
        self.lbl_icon.setPixmap(load_phosphor_icon("ph.snowflake", color=DesignTokens.COLOR_YELLOW_TEXT if drifted else DesignTokens.BRANCH_A).pixmap(16, 16))
        self.lbl_summary.setText(state.summary)
        self.setVisible(True)

    def _restyle(self, drifted: bool) -> None:
        self.setStyleSheet(
            _STYLE.format(
                bg=DesignTokens.COLOR_YELLOW_BG if drifted else DesignTokens.BRANCH_A_BG,
                border=DesignTokens.COLOR_YELLOW_BORDER if drifted else DesignTokens.BRANCH_A_BORDER,
                radius=DesignTokens.RADIUS_SM,
                text=DesignTokens.COLOR_YELLOW_TEXT if drifted else DesignTokens.TEXT_SECONDARY,
                strong=DesignTokens.TEXT_PRIMARY,
            )
        )


__all__ = ["PromptOverrideIndicator"]
