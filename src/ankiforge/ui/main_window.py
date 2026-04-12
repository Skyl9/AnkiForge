from typing import cast

import qtawesome as qta
from PySide6.QtCore import Slot, QSettings, Qt, QSize, QEvent, QTimer
from PySide6.QtGui import QCloseEvent, QShortcut, QKeySequence
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QListWidget, QStackedWidget, QListWidgetItem

from ankiforge.ui.theme import get_icon_color
from ankiforge.ui.views.ab_test_view import ABTestTab
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
from ankiforge.ui.widgets.tour_guide import TourBubble


class MainWindow(QMainWindow):
    def __init__(self, ai_manager):
        super().__init__()
        self.setWindowTitle("AnkiForge - AI Flashcard Generator")
        self.settings = QSettings("AnkiForgeOrg", "AnkiForge")
        self.ai_manager = ai_manager

        # --- Layout Principal (Sidebar + Stack) ---
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. La Barre Latérale (Sidebar) dynamique avec la palette
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(220)
        self.sidebar.setIconSize(QSize(20, 20))
        self.sidebar.setStyleSheet("""
            QListWidget {
                background-color: palette(alternate-base);
                border: none;
                border-right: 1px solid palette(window);
                padding-top: 10px;
                outline: none;
            }
            QListWidget::item {
                padding: 10px 15px;
                margin: 2px 10px;
                border-radius: 6px;
                color: palette(text);
            }
            QListWidget::item:selected {
                background-color: palette(highlight);
                color: palette(highlighted-text);
            }
            QListWidget::item:hover:!selected {
                background-color: palette(base);
            }
        """)

        # 2. Le conteneur des vues (Stack)
        self.stack = QStackedWidget()

        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.stack)
        self.setCentralWidget(main_widget)

        # --- Initialisation des vues ---
        self.stats_tabs = StatsTab()
        self.batch_tab = BatchTab(self.ai_manager)
        self.tab_edition = EditionTab()
        self.tab_documents = DocumentsTab()
        self.llm_manager_tab = LLMManagerTab(self.ai_manager)
        self.ab_test_tab = ABTestTab()
        self.creation_tab = CreationTab(self.ai_manager)
        # --- Ajout dynamique des éléments ---
        self.add_view(self.creation_tab, "fa5s.magic", "Création")
        self.add_view(self.tab_edition, "fa5s.layer-group", "Édition / Analyse")
        self.add_view(ModelsTab(), "fa5s.paint-brush", "Modèles")
        self.add_view(AgentsTab(), "fa5s.robot", "Agents & Pipelines")
        self.add_view(self.stats_tabs, "fa5s.chart-bar", "Statistiques")
        self.add_view(self.tab_documents, "fa5s.folder-open", "Documents")

        self.add_view(self.batch_tab, "fa5s.rocket", "Automatisation")
        self.add_view(self.llm_manager_tab, "fa5s.robot", "Moteurs IA")
        self.add_view(self.ab_test_tab, "fa5s.flask", "Tests A/B")
        self.add_view(SettingsTab(), "fa5s.cog", "Paramètres IA")

        # Connexion du signal de changement de vue
        self.sidebar.currentRowChanged.connect(self.on_sidebar_changed)

        self.read_settings()

        # --- OMNIBOX (RECHERCHE GLOBALE) ---
        self.omnibox = Omnibox(self)
        self.omnibox.result_selected.connect(self.handle_omnibox_result)
        self.shortcut_search = QShortcut(QKeySequence("Ctrl+K"), self)
        self.shortcut_search.activated.connect(lambda: self.omnibox.exec_centered(self))

        self.tour_bubble = TourBubble(self)
        self._setup_tour_scenario()

    def add_view(self, widget: QWidget, icon_name: str, title: str):
        self.stack.addWidget(widget)
        item = QListWidgetItem(qta.icon(icon_name, color=get_icon_color()), f"  {title}")

        # On cache le nom de l'icône dans la donnée de l'item (UserRole + 1 pour ne pas écraser d'autres datas)
        item.setData(Qt.ItemDataRole.UserRole + 1, icon_name)

        self.sidebar.addItem(item)

    @Slot(int)
    def on_sidebar_changed(self, index: int) -> None:
        """Change la vue active et rafraîchit les données."""
        self.stack.setCurrentIndex(index)
        current_widget = self.stack.widget(index)
        refresh_method = getattr(current_widget, "refresh_data", None)
        if callable(refresh_method):
            refresh_method()

    def read_settings(self):
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(1100, 800)

        last_tab: int = cast(int, self.settings.value("last_tab_index", 0, type=int))
        if last_tab < self.sidebar.count():
            self.sidebar.setCurrentRow(last_tab)

    def write_settings(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("last_tab_index", self.sidebar.currentRow())

    def closeEvent(self, event: QCloseEvent):
        self.write_settings()
        event.accept()

    @Slot(str, int, object)
    def handle_omnibox_result(self, result_type: str, item_id: int, extra_data: object):
        if result_type == "doc":
            index = self.stack.indexOf(self.tab_documents)
            self.sidebar.setCurrentRow(index)
            self.tab_documents.jump_to_document(item_id)
        elif result_type == "note":
            index = self.stack.indexOf(self.tab_edition)
            self.sidebar.setCurrentRow(index)
            self.tab_edition.view_mode_cb.setCurrentText("Vue : Notes (Texte)")
            self.tab_edition.jump_to_note(item_id, cast(int, extra_data))

    def changeEvent(self, event):
        """Intercepte le changement de thème global pour rafraîchir la sidebar."""
        if event.type() == QEvent.Type.PaletteChange:
            from ankiforge.ui.theme import get_icon_color

            color = get_icon_color()

            # On boucle sur tous les onglets pour redessiner leur icône
            for i in range(self.sidebar.count()):
                item = self.sidebar.item(i)
                icon_name = item.data(Qt.ItemDataRole.UserRole + 1)
                if icon_name:
                    item.setIcon(qta.icon(icon_name, color=color))

        super().changeEvent(event)

    def _setup_tour_scenario(self):
        """Définit toutes les étapes du tutoriel."""
        scenario = [
            {
                "title": "Bienvenue dans AnkiForge !",
                "text": "L'Intelligence Artificielle au service de votre mémoire.<br><br>Ce court tutoriel interactif "
                "va vous guider à travers l'interface pour vous montrer c"
                "omment forger vos premières flashcards en quelques clics.",
                "target_widget": None,  # S'affiche au centre
                "action": None,  # Pas d'action spéciale
            },
            {
                "title": "1. Le Moteur IA",
                "text": "C'est ici que tout commence. Entrez votre clé API OpenAI, Gemini, ou utilisez Ollama en local. Sans ce moteur, la génération ne pourra pas démarrer.",
                "target_widget": self.llm_manager_tab.le_openai_key,
                "action": lambda: self.sidebar.setCurrentRow(7),
            },
            {
                "title": "2. La Matière Première",
                "text": "Importez vos cours en PDF ou tapez vos notes en Markdown ici. Le texte sera automatiquement sauvegardé et prêt à être analysé.",
                "target_widget": self.tab_documents.btn_import,
                "action": lambda: self.sidebar.setCurrentRow(5),
            },
            {
                "title": "3. L'Usine à Cartes",
                "text": "Sélectionnez le document importé, choisissez un Agent IA, et lancez la génération. L'IA va extraire les concepts clés et formater le code LaTeX.",
                "target_widget": self.creation_tab.btn_generate,
                "action": lambda: self.sidebar.setCurrentRow(0),
            },
            {
                "title": "4. Le Contrôle Qualité",
                "text": "Vos cartes atterrissent ici. Vous pouvez les éditer, comparer les différentes versions via l'historique, puis les exporter vers Anki.",
                "target_widget": self.tab_edition.data_table,
                "action": lambda: self.sidebar.setCurrentRow(1),
            },
            {
                "title": "Vous êtes prêt",
                "text": "N'oubliez pas l'onglet Automatisation pour traiter des dossiers entiers d'un seul coup et l'onglet Statistiques pour suivre vos coûts API.\n\nBonnes révisions !",
                "target_widget": None,
                "action": None,
            },
        ]
        self.tour_bubble.set_scenario(scenario)

    def showEvent(self, event):
        """Déclenche le tour au premier affichage."""
        super().showEvent(event)

        tour_done = self.settings.value("app/tour_completed", False, type=bool)
        if not tour_done:
            # On utilise un timer pour laisser la fenêtre apparaître avant de lancer la bulle
            QTimer.singleShot(500, self.tour_bubble.start_tour)
