"""Batch Metrics Bar — Bandeau technique supérieur de 4 cellules métriques pour l'Atelier de Production.

Qt equivalent : QWidget (HBoxLayout of CicdMetricCard)
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from ankidraft.ui.theme import DesignTokens
from ankidraft.ui.views.batch_view.widgets.cicd_metric_card import CicdMetricCard
from ankidraft.utils.i18n import tr


class BatchMetricsBar(QWidget):
    """Barre supérieure flush de 4 cellules métriques CI/CD encastrées dans BatchView.

      - self.card_status  (STATUT GLOBAL)
      - self.card_time    (TEMPS ÉCOULÉ)
      - self.card_cards   (CARTES GÉNÉRÉES — cellule cliquable ouvrant la revue)
      - self.card_cost    (COÛT ESTIMÉ).

    Qt equivalent: QWidget (HBoxLayout flush)
    """

    staging_review_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("batchMetricsContainer")
        self.setFixedHeight(48)
        self._apply_style()

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self.card_status = CicdMetricCard(
            tr("STATUT GLOBAL"),
            "En attente",
            "ph.check-circle",
            color=DesignTokens.COLOR_GREEN,
            show_right_border=True,
        )
        self.card_time = CicdMetricCard(
            tr("TEMPS ÉCOULÉ"),
            "--:--:--",
            "ph.timer",
            color=DesignTokens.COLOR_BLUE,
            show_right_border=True,
        )
        self.card_cards = CicdMetricCard(
            tr("CARTES GÉNÉRÉES"),
            "0 cartes",
            "ph.cards",
            color=DesignTokens.COLOR_PURPLE,
            clickable=True,
            show_right_border=True,
        )
        self.card_cards.title_lbl.setToolTip(self.tr("Ouvrir la revue des cartes en attente de validation"))
        self.card_cards.clicked.connect(self.staging_review_requested)
        self.card_cost = CicdMetricCard(
            tr("COÛT ESTIMÉ"),
            "$0.00",
            "ph.coin",
            color=DesignTokens.COLOR_YELLOW,
            show_right_border=False,
        )

        row.addWidget(self.card_status, 1)
        row.addWidget(self.card_time, 1)
        row.addWidget(self.card_cards, 1)
        row.addWidget(self.card_cost, 1)

    def _apply_style(self, profile: Any = None) -> None:
        bg_panel = profile.bg_panel if profile else DesignTokens.BG_PANEL
        border_col = profile.border_color if profile else DesignTokens.BORDER_COLOR
        self.setStyleSheet(f"""
            QWidget#batchMetricsContainer {{
                background-color: {bg_panel};
                border-bottom: 1px solid {border_col};
            }}
        """)

    def set_review_count(self, count: int) -> None:
        self.card_cards.val_lbl.setText(f"{count} à valider" if count else "0 à valider")

    def refresh_theme(self, profile: Any) -> None:
        self._apply_style(profile)
        for card in (self.card_status, self.card_time, self.card_cards, self.card_cost):
            card.refresh_theme(profile)
