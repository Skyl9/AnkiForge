from PySide6.QtWidgets import (QMainWindow, QTabWidget)

from src.ui.views.agents_view import AgentsTab
from src.ui.views.batch_view import BatchTab
from src.ui.views.creation_view import CreationTab
from src.ui.views.documents_view import DocumentsTab
from src.ui.views.edition_view import EditionTab
from src.ui.views.models_view import ModelsTab
from src.ui.views.settings_view import SettingsTab
from src.ui.views.stats_view import StatsTab


class MainWindow(QMainWindow):
    def __init__(self, ai_manager):
        super().__init__()
        self.setWindowTitle("AnkiForge - AI Flashcard Generator")
        self.resize(1000, 700)

        # On sauvegarde PROPREMENT les dépendances dans l'instance
        self.ai_manager = ai_manager
        self.stats_tabs = StatsTab()
        self.batch_tab = BatchTab(self.ai_manager)
        # Widget central (Onglets)
        self.tabs = QTabWidget()
        self.tabs.addTab(CreationTab(self.ai_manager), "Création")
        self.tabs.addTab(EditionTab(), "Édition / Analyse")
        self.tabs.addTab(ModelsTab(), "Modèles (Note Types)")
        self.tabs.addTab(AgentsTab(), "🤖 Agents & Pipelines")
        self.tabs.addTab(self.stats_tabs, "📊 Statistiques")
        self.tabs.addTab(DocumentsTab(),"Onglet des documents")
        self.tabs.addTab(SettingsTab(self.ai_manager), "⚙️ Paramètres IA")

        self.tabs.addTab(self.batch_tab, "🚀 Automatisation")
        self.setCentralWidget(self.tabs)
