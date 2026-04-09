# src/ui/views/stats_view.py
import qtawesome as qta
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QFrame, QGridLayout, QTableWidget, QTableWidgetItem,
                               QHeaderView, QPushButton, QAbstractItemView)
from peewee import JOIN, fn

from ankiforge.database.models import DeckModel, NoteModel, CardModel, PipelineModel, TokenUsageModel
# 👇 N'oublie pas d'importer RoundedPanel ici
from ankiforge.ui.components.components import HeaderLabel, ActionButton, MetricCard, RoundedPanel


class StatsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(20)

        # --- En-tête ---
        header_layout = QHBoxLayout()
        title = HeaderLabel("Tableau de Bord AnkiForge")
        header_layout.addWidget(title)

        self.btn_refresh = ActionButton('fa5s.sync', " Rafraîchir les statistiques")
        self.btn_refresh.setFixedWidth(250)
        self.btn_refresh.clicked.connect(self.load_stats)

        header_layout.addStretch()
        header_layout.addWidget(self.btn_refresh)
        self.layout.addLayout(header_layout)

        # --- Section : Métriques Globales (Les grosses "Cartes") ---
        self.metrics_layout = QGridLayout()
        self.metrics_layout.setSpacing(15)  # Aère un peu l'espace entre les 4 cartes

        self.card_total_notes = MetricCard("Total des Notes")
        self.card_total_cards = MetricCard("Total des Cartes")
        self.card_total_decks = MetricCard("Paquets Actifs")
        self.card_total_pipelines = MetricCard("Pipelines IA")

        self.card_total_tokens = MetricCard("Tokens Consommés")
        self.card_total_cost = MetricCard("Coût IA Estimé (USD)")

        self.metrics_layout.addWidget(self.card_total_notes, 0, 0)
        self.metrics_layout.addWidget(self.card_total_cards, 0, 1)
        self.metrics_layout.addWidget(self.card_total_decks, 0, 2)
        self.metrics_layout.addWidget(self.card_total_pipelines, 1, 0)

        self.metrics_layout.addWidget(self.card_total_tokens, 1, 1)
        self.metrics_layout.addWidget(self.card_total_cost, 1, 2)

        self.layout.addLayout(self.metrics_layout)

        # --- Section : Répartition par Paquet (Encapsulé dans une Carte) ---
        table_panel = RoundedPanel()
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(15, 15, 15, 15)

        lbl_subtitle = QLabel("RÉPARTITION PAR PAQUET")
        lbl_subtitle.setStyleSheet(
            "font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        table_layout.addWidget(lbl_subtitle)

        self.deck_table = QTableWidget()
        self.deck_table.setFrameShape(QFrame.Shape.NoFrame)
        self.deck_table.setColumnCount(2)
        self.deck_table.setHorizontalHeaderLabels(["Nom du Paquet", "Nombre de Cartes"])
        self.deck_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.deck_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.deck_table.setAlternatingRowColors(True)

        table_layout.addWidget(self.deck_table)
        self.layout.addWidget(table_panel)

        # Chargement initial des données
        self.load_stats()

    @Slot()
    def refresh_data(self) -> None:
        """Contrat MainWindow : Met à jour les stats automatiquement à l'ouverture de l'onglet."""
        self.load_stats()

    @Slot()
    def load_stats(self) -> None:
        """Récupère les données depuis SQLite (Peewee) et met à jour l'UI."""
        self.card_total_notes.set_value(str(NoteModel.select().count()))
        self.card_total_cards.set_value(str(CardModel.select().count()))
        self.card_total_decks.set_value(str(DeckModel.select().count()))
        self.card_total_pipelines.set_value(str(PipelineModel.select().count()))

        tokens_query = TokenUsageModel.select(
            fn.SUM(TokenUsageModel.total_tokens).alias('sum_tokens'),
            fn.SUM(TokenUsageModel.estimated_cost_usd).alias('sum_cost')
        ).first()
        total_tokens = tokens_query.sum_tokens if tokens_query.sum_tokens else 0
        total_cost = tokens_query.sum_cost if tokens_query.sum_cost else 0.0

        # Formatage lisible (espaces pour les milliers, et 3 décimales pour les micro-centimes)
        self.card_total_tokens.set_value(f"{total_tokens:,}".replace(',', ' '))
        self.card_total_cost.set_value(f"${total_cost:.4f}")
        decks_with_counts = (DeckModel
                             .select(DeckModel, fn.COUNT(CardModel.id).alias('card_count'))
                             .join(CardModel, JOIN.LEFT_OUTER)
                             .group_by(DeckModel)
                             .order_by(DeckModel.name))

        decks_list = list(decks_with_counts)
        self.deck_table.setRowCount(len(decks_list))

        for row, deck in enumerate(decks_list):
            self.deck_table.setItem(row, 0, QTableWidgetItem(deck.name))
            item_count = QTableWidgetItem(str(deck.card_count))
            item_count.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.deck_table.setItem(row, 1, item_count)