# src/ui/main_window.py
from PySide6.QtWidgets import (QMainWindow, QTabWidget)

from src.ui.views.agents_view import AgentsTab
from src.ui.views.creation_view import CreationTab
from src.ui.views.edition_view import EditionTab
from src.ui.views.models_view import ModelsTab


class MainWindow(QMainWindow):
    def __init__(self, ai_provider, prompt_manager):
        super().__init__()
        self.setWindowTitle("AnkiForge - AI Flashcard Generator")
        self.resize(1000, 700)

        # On sauvegarde PROPREMENT les dépendances dans l'instance
        self.ai_provider = ai_provider
        self.prompt_manager = prompt_manager

        # Widget central (Onglets)
        tabs = QTabWidget()
        tabs.addTab(CreationTab(self.ai_provider, self.prompt_manager), "Création")
        tabs.addTab(EditionTab(), "Édition / Analyse")
        tabs.addTab(ModelsTab(), "Modèles (Note Types)")

        tabs.addTab(AgentsTab(), "🤖 Agents & Pipelines")
        self.setCentralWidget(tabs)