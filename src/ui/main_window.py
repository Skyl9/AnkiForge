from PySide6.QtWidgets import (QMainWindow, QTabWidget)

from src.ui.views.agents_view import AgentsTab
from src.ui.views.creation_view import CreationTab
from src.ui.views.edition_view import EditionTab
from src.ui.views.models_view import ModelsTab
from src.ui.views.stats_view import StatsTab


class MainWindow(QMainWindow):
    def __init__(self, ai_provider):
        super().__init__()
        self.setWindowTitle("AnkiForge - AI Flashcard Generator")
        self.resize(1000, 700)

        # On sauvegarde PROPREMENT les dépendances dans l'instance
        self.ai_provider = ai_provider
        self.stats_tabs = StatsTab()
        # Widget central (Onglets)
        tabs = QTabWidget()
        tabs.addTab(CreationTab(self.ai_provider), "Création")
        tabs.addTab(EditionTab(), "Édition / Analyse")
        tabs.addTab(ModelsTab(), "Modèles (Note Types)")
        tabs.addTab(AgentsTab(), "🤖 Agents & Pipelines")
        tabs.addTab(self.stats_tabs, "📊 Statistiques")

        self.setCentralWidget(tabs)
