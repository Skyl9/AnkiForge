from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components import Badge, IconButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget


class FlashcardPreview(QWidget):
    """Composant d'inspection et de validation des cartes générées."""

    def __init__(self, parent: QWidget | None = None) -> None:
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
        self.status_badge = Badge("À valider ⏳", variant="warning")

        top_toolbar.addWidget(self.btn_prev)
        top_toolbar.addWidget(self.lbl_counter)
        top_toolbar.addWidget(self.btn_next)
        top_toolbar.addSpacing(8)
        top_toolbar.addWidget(self.status_badge)
        top_toolbar.addStretch()

        layout.addLayout(top_toolbar)

        # Intégration de CardPreviewWidget (Moteur WebEngine + MathJax + multi-appareils)
        self.card_preview_widget = CardPreviewWidget(show_header=False)
        layout.addWidget(self.card_preview_widget, 1)

    def set_status(self, status: str, profile: Any = None) -> None:
        """Met à jour le badge de statut in-situ de la carte visualisée."""
        status_map: dict[str, tuple[str, str]] = {
            "Validée": ("Validée ✓", "success"),
            "Acceptée": ("Validée ✓", "success"),
            "Refusée": ("Refusée ✗", "danger"),
            "À valider": ("À valider ⏳", "warning"),
            "En attente": ("En attente ⏳", "warning"),
            "Enregistrée": ("Enregistrée 💾", "info"),
        }
        text, variant = status_map.get(status, (status, "status"))
        self.status_badge.setText(text)
        self.status_badge.set_variant(variant, profile=profile)
