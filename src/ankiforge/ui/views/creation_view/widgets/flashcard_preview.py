from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components import IconButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget


class FlashcardPreview(QWidget):
    """Composant d'inspection et de validation des cartes générées."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Barre supérieure de navigation dans les résultats
        top_toolbar = QHBoxLayout()
        self.btn_prev = IconButton("ph.caret-left", "Carte précédente", 24)
        self.btn_next = IconButton("ph.caret-right", "Carte suivante", 24)
        self.lbl_counter = QLabel("0 / 0")
        self.lbl_counter.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE}; font-weight: bold;")

        top_toolbar.addWidget(self.btn_prev)
        top_toolbar.addWidget(self.lbl_counter)
        top_toolbar.addWidget(self.btn_next)
        top_toolbar.addStretch()

        layout.addLayout(top_toolbar)

        # Intégration de CardPreviewWidget (Moteur WebEngine + MathJax + multi-appareils)
        self.card_preview_widget = CardPreviewWidget(show_header=False)
        layout.addWidget(self.card_preview_widget, 1)
