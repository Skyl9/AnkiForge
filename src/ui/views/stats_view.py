# src/ui/views/stats_view.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QFrame, QGridLayout, QTableWidget, QTableWidgetItem,
                               QHeaderView, QPushButton)

from src.database.models import DeckModel, NoteModel, CardModel, PipelineModel


class StatsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(20)

        # --- En-tête ---
        header_layout = QHBoxLayout()
        title = QLabel("<b>📊 Tableau de Bord AnkiForge</b>")
        title.setStyleSheet("font-size: 24px;")
        header_layout.addWidget(title)

        self.btn_refresh = QPushButton("🔄 Rafraîchir les statistiques")
        self.btn_refresh.setFixedWidth(200)
        self.btn_refresh.setStyleSheet("padding: 8px; font-weight: bold;")
        self.btn_refresh.clicked.connect(self.load_stats)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_refresh)

        self.layout.addLayout(header_layout)

        # --- Section : Métriques Globales (Les grosses "Cartes") ---
        self.metrics_layout = QGridLayout()

        self.lbl_total_notes = self._create_metric_card("Total des Notes", "0")
        self.lbl_total_cards = self._create_metric_card("Total des Cartes", "0")
        self.lbl_total_decks = self._create_metric_card("Paquets Actifs", "0")
        self.lbl_total_pipelines = self._create_metric_card("Pipelines IA", "0")

        self.metrics_layout.addWidget(self.lbl_total_notes[0], 0, 0)
        self.metrics_layout.addWidget(self.lbl_total_cards[0], 0, 1)
        self.metrics_layout.addWidget(self.lbl_total_decks[0], 0, 2)
        self.metrics_layout.addWidget(self.lbl_total_pipelines[0], 0, 3)

        self.layout.addLayout(self.metrics_layout)

        # --- Section : Répartition par Paquet ---
        self.layout.addWidget(QLabel("<b>📦 Répartition par Paquet :</b>"))
        self.deck_table = QTableWidget()
        self.deck_table.setColumnCount(2)
        self.deck_table.setHorizontalHeaderLabels(["Nom du Paquet", "Nombre de Cartes"])
        self.deck_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.deck_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.deck_table.setAlternatingRowColors(True)
        self.layout.addWidget(self.deck_table)

        # Chargement initial des données
        self.load_stats()

    def _create_metric_card(self, title: str, initial_value: str):
        """Crée un petit widget stylisé pour afficher un gros chiffre."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #2b2b2b;
                border-radius: 10px;
                border: 1px solid #3a3a3a;
            }
        """)
        vbox = QVBoxLayout(card)
        vbox.setAlignment(Qt.AlignCenter)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #aaaaaa; font-size: 14px;")
        lbl_title.setAlignment(Qt.AlignCenter)

        lbl_value = QLabel(initial_value)
        lbl_value.setStyleSheet("color: #4CAF50; font-size: 32px; font-weight: bold;")
        lbl_value.setAlignment(Qt.AlignCenter)

        vbox.addWidget(lbl_title)
        vbox.addWidget(lbl_value)

        return card, lbl_value

    def load_stats(self) -> None:
        """Récupère les données depuis SQLite (Peewee) et met à jour l'UI."""
        # 1. Mise à jour des métriques globales
        total_notes = NoteModel.select().count()
        total_cards = CardModel.select().count()
        total_decks = DeckModel.select().count()
        total_pipes = PipelineModel.select().count()

        self.lbl_total_notes[1].setText(str(total_notes))
        self.lbl_total_cards[1].setText(str(total_cards))
        self.lbl_total_decks[1].setText(str(total_decks))
        self.lbl_total_pipelines[1].setText(str(total_pipes))

        # 2. Mise à jour du tableau des paquets
        decks = list(DeckModel.select())
        self.deck_table.setRowCount(len(decks))

        for row, deck in enumerate(decks):
            # On compte le nombre de cartes associées à ce paquet
            card_count = CardModel.select().where(CardModel.deck == deck).count()

            self.deck_table.setItem(row, 0, QTableWidgetItem(deck.name))

            item_count = QTableWidgetItem(str(card_count))
            item_count.setTextAlignment(Qt.AlignCenter)
            self.deck_table.setItem(row, 1, item_count)