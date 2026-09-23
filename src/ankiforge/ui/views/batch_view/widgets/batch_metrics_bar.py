"""
Batch Metrics Bar — Barre supérieure de 4 KPI cards pour l'Atelier de Production.

Qt equivalent : QWidget (HBoxLayout of CicdMetricCard)
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.batch_view.widgets.cicd_metric_card import CicdMetricCard


class BatchMetricsBar(QWidget):
    """
    Barre de 4 CicdMetricCard rétrocompatibles avec l'API existante de BatchView :
      - self.card_status  (STATUT GLOBAL)
      - self.card_time    (TEMPS ÉCOULÉ)
      - self.card_cards   (CARTES GÉNÉRÉES — badge cliquable ouvrant la revue)
      - self.card_cost    (COÛT ESTIMÉ)

    Qt equivalent: QWidget (HBoxLayout)
    """

    staging_review_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("batchMetricsContainer")

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(12)

        self.card_status = CicdMetricCard(
            "STATUT GLOBAL",
            "En attente",
            "ph.check-circle",
            color=DesignTokens.COLOR_GREEN,
        )
        self.card_time = CicdMetricCard(
            "TEMPS ÉCOULÉ",
            "--:--:--",
            "ph.timer",
            color=DesignTokens.COLOR_BLUE,
        )
        self.card_cards = CicdMetricCard(
            "CARTES GÉNÉRÉES",
            "0 cartes",
            "ph.cards",
            color=DesignTokens.COLOR_PURPLE,
            clickable=True,
        )
        self.card_cards.title_lbl.setToolTip("Ouvrir la revue des cartes en attente de validation")
        self.card_cards.clicked.connect(self.staging_review_requested)
        self.card_cost = CicdMetricCard(
            "COÛT ESTIMÉ",
            "$0.00",
            "ph.coin",
            color=DesignTokens.COLOR_YELLOW,
        )

        row.addWidget(self.card_status, 1)
        row.addWidget(self.card_time, 1)
        row.addWidget(self.card_cards, 1)
        row.addWidget(self.card_cost, 1)

    def set_review_count(self, count: int) -> None:
        self.card_cards.val_lbl.setText(f"{count} à valider" if count else "0 à valider")

    def refresh_theme(self, profile: Any) -> None:
        for card in (self.card_status, self.card_time, self.card_cards, self.card_cost):
            card.refresh_theme(profile)
