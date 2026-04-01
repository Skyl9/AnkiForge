# src/ui/main_window.py
import qtawesome as qta
from PySide6.QtCore import Slot, QSettings
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow, QTabWidget

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
        self.settings = QSettings("AnkiForgeOrg", "AnkiForge")

        self.ai_manager = ai_manager

        # Initialisation des onglets
        self.stats_tabs = StatsTab()
        self.batch_tab = BatchTab(self.ai_manager)

        self.tabs = QTabWidget()
        iconColor = 'orange'
        # Ajout des onglets avec les icônes vectorielles FontAwesome 5
        self.tabs.addTab(CreationTab(self.ai_manager), qta.icon('fa5s.magic', color=iconColor), "Création")
        self.tabs.addTab(EditionTab(), qta.icon('fa5s.layer-group', color=iconColor), "Édition / Analyse")
        self.tabs.addTab(ModelsTab(), qta.icon('fa5s.paint-brush', color=iconColor), "Modèles")
        self.tabs.addTab(AgentsTab(), qta.icon('fa5s.robot', color=iconColor), "Agents & Pipelines")
        self.tabs.addTab(self.stats_tabs, qta.icon('fa5s.chart-bar', color=iconColor), "Statistiques")
        self.tabs.addTab(DocumentsTab(), qta.icon('fa5s.folder-open', color=iconColor), "Documents")
        self.tabs.addTab(SettingsTab(self.ai_manager), qta.icon('fa5s.cog', color=iconColor), "Paramètres IA")
        self.tabs.addTab(self.batch_tab, qta.icon('fa5s.rocket', color=iconColor), "Automatisation")

        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.setCentralWidget(self.tabs)
        self.read_settings()

    @Slot(int)
    def on_tab_changed(self, index: int) -> None:
        """Rafraîchit les données de l'onglet actif quand on clique dessus."""
        current_widget = self.tabs.widget(index)

        # On vérifie si l'onglet a une fonction de rafraîchissement
        if hasattr(current_widget, "refresh_selectors"):
            current_widget.refresh_selectors()

        if hasattr(current_widget, "load_documents"):
            current_widget.load_documents()

        if hasattr(current_widget, "load_tree_source"):
            current_widget.load_tree_source()

        if hasattr(current_widget, "refresh_deck_tree"):
            current_widget.refresh_deck_tree()

# ==========================================
    # 💾 GESTION DE L'ÉTAT (QSettings)
    # ==========================================

    def read_settings(self):
        """Restaure la taille de la fenêtre et l'onglet actif."""
        # Restaure la géométrie (Taille et position)
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(1100, 800) # Taille par défaut si premier lancement

        # Restaure l'onglet actif
        last_tab = self.settings.value("last_tab_index", 0, type=int)
        if last_tab < self.tabs.count():
            self.tabs.setCurrentIndex(last_tab)

    def write_settings(self):
        """Enregistre la configuration actuelle."""
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("last_tab_index", self.tabs.currentIndex())

    def closeEvent(self, event: QCloseEvent):
        """Se déclenche à la fermeture de l'application."""
        self.write_settings() # Sauvegarde avant de quitter
        event.accept()