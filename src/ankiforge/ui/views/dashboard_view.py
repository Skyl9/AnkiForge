from peewee import fn
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame
from PySide6.QtCore import Signal, Qt, QThread, Slot

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.components.buttons import PremiumActionCard
from ankiforge.ui.components.misc import DropZone
from ankiforge.ui.components.panels import StatCard
from ankiforge.database.models import NoteModel, CardModel, DeckModel, TokenUsageModel, NoteVersionModel
from ankiforge.services.ai.flexible_service import AIManager


class StatsWorker(QThread):
    stats_loaded = Signal(dict)
    feed_loaded = Signal(list)

    def run(self):
        try:
            notes_count = NoteModel.select().count()
            cards_count = CardModel.select().count()
            decks_count = DeckModel.select().count()
            cost_query = TokenUsageModel.select(fn.SUM(TokenUsageModel.estimated_cost_usd)).scalar()
            cost = cost_query if cost_query else 0.0

            self.stats_loaded.emit({"notes": notes_count, "cards": cards_count, "decks": decks_count, "cost": cost})

            feed_items = []
            recent_versions = NoteVersionModel.select(NoteVersionModel, NoteModel).join(NoteModel).order_by(NoteVersionModel.created_at.desc()).limit(10)

            for version in recent_versions:
                feed_items.append({"note_id": version.note.id, "source": version.source, "created_at": version.created_at.strftime("%Y-%m-%d %H:%M"), "version": version.version_number})
            self.feed_loaded.emit(feed_items)
        except Exception:
            # Si la DB n'est pas encore initialisée ou autre erreur
            pass  # nosec B110


class DashboardView(QWidget):
    navigate_creation = Signal()
    navigate_documents = Signal()
    navigate_batch = Signal()

    def __init__(self, ai_manager: AIManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager

        self._setup_ui()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # Main Panel (Left) - stretch=3
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(20)

        # Hero Banner
        hero_banner = QFrame()
        hero_banner.setObjectName("HeroBanner")
        hero_banner.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        hero_banner.setStyleSheet(f"""
            #HeroBanner {{
                background-color: {DesignTokens.BG_PANEL};
                border-radius: {DesignTokens.RADIUS_LG}px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        hero_layout = QVBoxLayout(hero_banner)
        hero_layout.setContentsMargins(30, 30, 30, 30)

        hero_layout.addStretch()

        icon_lbl = QLabel("📚")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 48px; border: none; background: transparent;")

        welcome_lbl = QLabel("Bienvenue sur AnkiForge")
        welcome_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 24px; font-weight: bold; border: none; background: transparent;")

        sub_lbl = QLabel("Générez et gérez vos cartes Anki facilement avec l'IA.")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 14px; border: none; background: transparent;")

        hero_layout.addWidget(icon_lbl)
        hero_layout.addWidget(welcome_lbl)
        hero_layout.addWidget(sub_lbl)

        hero_layout.addStretch()

        left_layout.addWidget(hero_banner)

        # Premium Action Cards
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(16)

        self.card_create = PremiumActionCard("✨", "Créer des cartes", "Générez de nouvelles cartes via IA.")
        self.card_import = PremiumActionCard("📄", "Importer un document", "Analysez un PDF/DOCX pour créer des cartes.")
        self.card_batch = PremiumActionCard("🚀", "Lancer un batch", "Générez des cartes en masse depuis vos notes.")

        self.card_create.clicked.connect(self.navigate_creation.emit)
        self.card_import.clicked.connect(self.navigate_documents.emit)
        self.card_batch.clicked.connect(self.navigate_batch.emit)

        cards_layout.addWidget(self.card_create)
        cards_layout.addWidget(self.card_import)
        cards_layout.addWidget(self.card_batch)

        left_layout.addLayout(cards_layout)

        # DropZone
        self.drop_zone = DropZone("Glissez vos fichiers ici (PDF/DOCX/PPTX)", accept_extensions=[".pdf", ".docx", ".pptx"])
        left_layout.addWidget(self.drop_zone)

        # Right Panel - stretch=1
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(20)

        # Stats Grid
        stats_widget = QFrame()
        stats_widget.setObjectName("StatsWidget")
        stats_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        stats_widget.setStyleSheet(f"""
            #StatsWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        stats_layout = QVBoxLayout(stats_widget)
        stats_layout.setContentsMargins(15, 15, 15, 15)
        stats_layout.setSpacing(10)

        stats_title = QLabel("Statistiques")
        stats_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: bold; border: none;")
        stats_layout.addWidget(stats_title)

        grid_layout1 = QHBoxLayout()
        self.stat_notes = StatCard("Notes", "0")
        self.stat_cards = StatCard("Cartes", "0")
        grid_layout1.addWidget(self.stat_notes)
        grid_layout1.addWidget(self.stat_cards)

        grid_layout2 = QHBoxLayout()
        self.stat_decks = StatCard("Decks", "0")
        self.stat_cost = StatCard("Coût API ($)", "0.00")
        grid_layout2.addWidget(self.stat_decks)
        grid_layout2.addWidget(self.stat_cost)

        stats_layout.addLayout(grid_layout1)
        stats_layout.addLayout(grid_layout2)

        right_layout.addWidget(stats_widget)

        # Activity Feed
        feed_widget = QFrame()
        feed_widget.setObjectName("FeedWidget")
        feed_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        feed_widget.setStyleSheet(f"""
            #FeedWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        feed_layout = QVBoxLayout(feed_widget)
        feed_layout.setContentsMargins(15, 15, 15, 15)
        feed_layout.setSpacing(10)

        feed_title = QLabel("Activité Récente")
        feed_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: bold; border: none;")
        feed_layout.addWidget(feed_title)

        self.feed_container = QVBoxLayout()
        self.feed_container.setSpacing(8)
        self.feed_container.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("background-color: transparent;")

        feed_content = QWidget()
        feed_content.setStyleSheet("background-color: transparent;")
        feed_content.setLayout(self.feed_container)
        scroll_area.setWidget(feed_content)

        feed_layout.addWidget(scroll_area)
        right_layout.addWidget(feed_widget)

        main_layout.addWidget(left_panel, stretch=3)
        main_layout.addWidget(right_panel, stretch=1)

    def refresh_data(self) -> None:
        self.worker = StatsWorker()
        self.worker.stats_loaded.connect(self._on_stats_loaded)
        self.worker.feed_loaded.connect(self._on_feed_loaded)
        self.worker.start()

    @Slot(dict)
    def _on_stats_loaded(self, stats: dict) -> None:
        self.stat_notes.lbl_value.setText(str(stats["notes"]))
        self.stat_cards.lbl_value.setText(str(stats["cards"]))
        self.stat_decks.lbl_value.setText(str(stats["decks"]))
        self.stat_cost.lbl_value.setText(f"{stats['cost']:.2f}")

    @Slot(list)
    def _on_feed_loaded(self, feed: list) -> None:
        # Clear previous items
        while self.feed_container.count():
            item = self.feed_container.takeAt(0)
            if item:
                widget = item.widget()
                if widget:
                    widget.deleteLater()

        for item in feed:
            lbl = QLabel(f"Note #{item['note_id']} v{item['version']} via {item['source']}\\n{item['created_at']}")
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px; background-color: {DesignTokens.BG_INPUT}; padding: 8px; border-radius: {DesignTokens.RADIUS_SM}px;")
            self.feed_container.addWidget(lbl)
