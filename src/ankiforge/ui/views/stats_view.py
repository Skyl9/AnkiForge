from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QGridLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QSplitter,
)
from peewee import JOIN, fn

from ankiforge.database.models import DeckModel, NoteModel, CardModel, PipelineModel, TokenUsageModel
from ankiforge.ui.components.components import HeaderLabel, ActionButton, MetricCard, RoundedPanel
from ankiforge.ui.widgets.donut_chart import DonutChartWidget


class StatsTab(QWidget):
    """
    AnkiForge application dashboard.
    Displays global metrics (cards, decks, pipelines) as well as
    monitoring of AI token usage and estimated costs.
    """

    def __init__(self) -> None:
        """Initializes the statistics view."""
        super().__init__()

        self._setup_ui()
        self._connect_signals()

        # Initial data loading
        self.load_stats()

    def _setup_ui(self) -> None:
        """Organizes main layouts and triggers the construction of sub-panels."""
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(20)

        self._build_header()
        self._build_metrics_section()
        self._build_charts_section()

    def _build_header(self) -> None:
        """Builds the header containing the title and the refresh button."""
        header_layout = QHBoxLayout()
        header_layout.addWidget(HeaderLabel(self.tr("AnkiForge Dashboard")))

        self.btn_refresh = ActionButton("fa5s.sync", self.tr(" Refresh statistics"))
        self.btn_refresh.setFixedWidth(250)

        header_layout.addStretch()
        header_layout.addWidget(self.btn_refresh)

        self.layout.addLayout(header_layout)

    def _build_metrics_section(self) -> None:
        """Builds the upper grid displaying metric cards (KPIs)."""
        self.metrics_layout = QGridLayout()
        self.metrics_layout.setSpacing(15)

        self.card_total_notes = MetricCard(self.tr("Total Notes"))
        self.card_total_cards = MetricCard(self.tr("Total Cards"))
        self.card_total_decks = MetricCard(self.tr("Active Decks"))
        self.card_total_pipelines = MetricCard(self.tr("AI Pipelines"))
        self.card_total_tokens = MetricCard(self.tr("Tokens Consumed"))
        self.card_total_cost = MetricCard(self.tr("Estimated AI Cost (USD)"))

        self.metrics_layout.addWidget(self.card_total_notes, 0, 0)
        self.metrics_layout.addWidget(self.card_total_cards, 0, 1)
        self.metrics_layout.addWidget(self.card_total_decks, 0, 2)
        self.metrics_layout.addWidget(self.card_total_pipelines, 1, 0)
        self.metrics_layout.addWidget(self.card_total_tokens, 1, 1)
        self.metrics_layout.addWidget(self.card_total_cost, 1, 2)

        self.layout.addLayout(self.metrics_layout)

    def _build_charts_section(self) -> None:
        """Builds the lower area containing the distribution table and the donut chart."""
        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter.setHandleWidth(15)

        # --- Left Panel: The Distribution Table ---
        table_panel = RoundedPanel()
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(15, 15, 15, 15)

        lbl_subtitle = QLabel(self.tr("DISTRIBUTION BY DECK"))
        lbl_subtitle.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        table_layout.addWidget(lbl_subtitle)

        self.deck_table = QTableWidget()
        self.deck_table.setFrameShape(QFrame.Shape.NoFrame)
        self.deck_table.setColumnCount(2)
        self.deck_table.setHorizontalHeaderLabels([self.tr("Deck Name"), self.tr("Number of Cards")])
        self.deck_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.deck_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.deck_table.setAlternatingRowColors(True)

        table_layout.addWidget(self.deck_table)
        bottom_splitter.addWidget(table_panel)

        # --- Right Panel: The Chart (Donut Chart) ---
        chart_panel = RoundedPanel()
        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.setContentsMargins(15, 15, 15, 15)

        lbl_chart = QLabel(self.tr("GLOBAL VIEW"))
        lbl_chart.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        chart_layout.addWidget(lbl_chart)

        self.deck_chart = DonutChartWidget(title_center=self.tr("CARDS"))
        chart_layout.addWidget(self.deck_chart)

        bottom_splitter.addWidget(chart_panel)

        # Proportions 50/50
        bottom_splitter.setSizes([500, 500])
        self.layout.addWidget(bottom_splitter)

    def _connect_signals(self) -> None:
        """Branche les signaux de l'interface aux slots associés."""
        self.btn_refresh.clicked.connect(self.load_stats)

    @Slot()
    def refresh_data(self) -> None:
        """Contrat MainWindow : Met à jour les stats automatiquement à l'ouverture de l'onglet."""
        self.load_stats()

    @Slot()
    def load_stats(self) -> None:
        """Récupère les données depuis SQLite (Peewee), calcule les agrégations et met à jour l'interface."""
        # Mise à jour des compteurs simples
        self.card_total_notes.set_value(str(NoteModel.select().count()))
        self.card_total_cards.set_value(str(CardModel.select().count()))
        self.card_total_decks.set_value(str(DeckModel.select().count()))
        self.card_total_pipelines.set_value(str(PipelineModel.select().count()))

        # Mise à jour des métriques financières et de tokens
        tokens_query = TokenUsageModel.select(
            fn.SUM(TokenUsageModel.total_tokens).alias("sum_tokens"),
            fn.SUM(TokenUsageModel.estimated_cost_usd).alias("sum_cost"),
        ).first()

        total_tokens = tokens_query.sum_tokens if tokens_query.sum_tokens else 0
        total_cost = tokens_query.sum_cost if tokens_query.sum_cost else 0.0

        # Formatage lisible (espaces pour les milliers, et 4 décimales pour les micro-centimes)
        self.card_total_tokens.set_value(f"{total_tokens:,}".replace(",", " "))
        self.card_total_cost.set_value(f"${total_cost:.4f}")

        # Agrégation des cartes par paquet
        decks_with_counts = DeckModel.select(DeckModel, fn.COUNT(CardModel.id).alias("card_count")).join(CardModel, JOIN.LEFT_OUTER).group_by(DeckModel).order_by(DeckModel.name)

        decks_list = list(decks_with_counts)
        self.deck_table.setRowCount(len(decks_list))

        chart_data = {}

        for row, deck in enumerate(decks_list):
            self.deck_table.setItem(row, 0, QTableWidgetItem(deck.name))

            item_count = QTableWidgetItem(str(deck.card_count))
            item_count.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.deck_table.setItem(row, 1, item_count)

            if deck.card_count > 0:
                # Extraction de la hiérarchie finale pour ne pas surcharger le graphique
                short_name = deck.name.split("::")[-1]
                chart_data[short_name] = deck.card_count

        self.deck_chart.update_data(chart_data)
