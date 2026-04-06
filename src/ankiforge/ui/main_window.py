# src/ui/main_window.py
import qtawesome as qta
from PySide6.QtCore import Slot, QSettings
from PySide6.QtGui import QCloseEvent, QShortcut, QKeySequence
from PySide6.QtWidgets import QMainWindow, QTabWidget

from ankiforge.ui.views.agents_view import AgentsTab
from ankiforge.ui.views.batch_view import BatchTab
from ankiforge.ui.views.creation_view import CreationTab
from ankiforge.ui.views.documents_view import DocumentsTab
from ankiforge.ui.views.edition_view import EditionTab
from ankiforge.ui.views.llm_manager_view import LLMManagerTab
from ankiforge.ui.views.models_view import ModelsTab
from ankiforge.ui.views.settings_view import SettingsTab
from ankiforge.ui.views.stats_view import StatsTab
from ankiforge.ui.widgets.omnibox import Omnibox


class MainWindow(QMainWindow):
    def __init__(self, ai_manager):
        super().__init__()
        self.setWindowTitle("AnkiForge - AI Flashcard Generator")
        self.settings = QSettings("AnkiForgeOrg", "AnkiForge")
        self.ai_manager = ai_manager

        # Initialisation des onglets
        self.stats_tabs = StatsTab()
        self.batch_tab = BatchTab(self.ai_manager)
        self.tab_edition = EditionTab()
        self.tab_documents = DocumentsTab()
        self.tabs = QTabWidget()
        self.llm_manager_tab = LLMManagerTab(self.ai_manager)
        iconColor = '#E0E0E0'

        self.tabs.addTab(CreationTab(self.ai_manager), qta.icon('fa5s.magic', color=iconColor), "Création")
        self.tabs.addTab(self.tab_edition, qta.icon('fa5s.layer-group', color=iconColor), "Édition / Analyse")
        self.tabs.addTab(ModelsTab(), qta.icon('fa5s.paint-brush', color=iconColor), "Modèles")
        self.tabs.addTab(AgentsTab(), qta.icon('fa5s.robot', color=iconColor), "Agents & Pipelines")
        self.tabs.addTab(self.stats_tabs, qta.icon('fa5s.chart-bar', color=iconColor), "Statistiques")
        self.tabs.addTab(self.tab_documents, qta.icon('fa5s.folder-open', color=iconColor), "Documents")
        self.tabs.addTab(SettingsTab(), qta.icon('fa5s.cog', color=iconColor), "Paramètres IA")
        self.tabs.addTab(self.batch_tab, qta.icon('fa5s.rocket', color=iconColor), "Automatisation")
        self.tabs.addTab(self.llm_manager_tab, qta.icon('fa5s.robot'), " Moteurs IA")

        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.setCentralWidget(self.tabs)
        self.read_settings()

        # --- OMNIBOX (RECHERCHE GLOBALE) ---
        self.omnibox = Omnibox(self)
        self.omnibox.result_selected.connect(self.handle_omnibox_result)

        # Le raccourci magique Ctrl+K (Cmd+K sur Mac)
        self.shortcut_search = QShortcut(QKeySequence("Ctrl+K"), self)
        self.shortcut_search.activated.connect(lambda: self.omnibox.exec_centered(self))


    @Slot(int)
    def on_tab_changed(self, index: int) -> None:
        """Rafraîchit les données de l'onglet actif quand on clique dessus."""
        current_widget = self.tabs.widget(index)
        refresh_method = getattr(current_widget, "refresh_data", None)
        if callable(refresh_method):
            refresh_method()

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
            self.resize(1100, 800)  # Taille par défaut si premier lancement

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
        self.write_settings()
        event.accept()

    @Slot(str, int, object)
    def handle_omnibox_result(self, result_type: str, item_id: int, extra_data: object):
        """Reçoit l'ordre de l'Omnibox et change d'onglet."""
        if result_type == "doc":
            # On suppose que ton onglet Documents est à l'index 3 (à adapter selon ton code)
            self.tabs.setCurrentWidget(self.tab_documents)
            self.tab_documents.jump_to_document(item_id)

        elif result_type == "note":
            # On suppose que ton onglet Édition est à l'index 1 (à adapter)
            self.tabs.setCurrentWidget(self.tab_edition)
            self.tab_edition.view_mode_cb.setCurrentText("Vue : Notes (Texte)")  # Force la bonne vue
            self.tab_edition.jump_to_note(item_id, extra_data)