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
from ankiforge.ui.views.consultant_view import ConsultantTab
from ankiforge.services.background_daeamon import BackgroundDaemon


class MainWindow(QMainWindow):
    def __init__(self, ai_manager):
        super().__init__()

        self.daemon = BackgroundDaemon()
        self.daemon.start()

        self.setWindowTitle(self.tr("AnkiForge - AI Flashcard Generator"))
        self.settings = QSettings("AnkiForgeOrg", "AnkiForge")
        self.ai_manager = ai_manager

        # --- Principal Layout (Sidebar + Stack) ---
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Dynamic Sidebar with palette
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

        # 2. View container (Stack)
        self.stack = QStackedWidget()

        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.stack)
        self.setCentralWidget(main_widget)

        # --- Views initialization ---
        self.stats_tabs = StatsTab()
        self.batch_tab = BatchTab(self.ai_manager)
        self.tab_edition = EditionTab()
        self.tab_documents = DocumentsTab()
        self.llm_manager_tab = LLMManagerTab(self.ai_manager)
        self.ab_test_tab = ABTestTab()
        self.creation_tab = CreationTab(self.ai_manager)
        self.consultant_tab = ConsultantTab(self.ai_manager)

        # --- Dynamic view addition ---
        self.add_view(self.creation_tab, "fa5s.magic", self.tr("Creation"))
        self.add_view(self.tab_edition, "fa5s.layer-group", self.tr("Edition / Analysis"))
        self.add_view(self.consultant_tab, "fa5s.book-open", self.tr("Consultant"))
        self.add_view(ModelsTab(), "fa5s.paint-brush", self.tr("Models"))
        self.add_view(AgentsTab(), "fa5s.robot", self.tr("Agents & Pipelines"))
        self.add_view(self.stats_tabs, "fa5s.chart-bar", self.tr("Statistics"))
        self.add_view(self.tab_documents, "fa5s.folder-open", self.tr("Documents"))

        self.add_view(self.batch_tab, "fa5s.rocket", self.tr("Automation"))
        self.add_view(self.llm_manager_tab, "fa5s.robot", self.tr("AI Engines"))
        self.add_view(self.ab_test_tab, "fa5s.flask", self.tr("A/B Testing"))
        self.add_view(SettingsTab(), "fa5s.cog", self.tr("AI Settings"))

        # View change signal connection
        self.sidebar.currentRowChanged.connect(self.on_sidebar_changed)

        self.read_settings()

        # --- OMNIBOX (GLOBAL SEARCH) ---
        self.omnibox = Omnibox(self)
        self.omnibox.result_selected.connect(self.handle_omnibox_result)
        self.shortcut_search = QShortcut(QKeySequence("Ctrl+K"), self)
        self.shortcut_search.activated.connect(lambda: self.omnibox.exec_centered(self))

        self.tour_bubble = TourBubble(self)
        self._setup_tour_scenario()

    def add_view(self, widget: QWidget, icon_name: str, title: str):
        self.stack.addWidget(widget)
        item = QListWidgetItem(qta.icon(icon_name, color=get_icon_color()), f"  {title}")

        # Hide icon name in item data (UserRole + 1)
        item.setData(Qt.ItemDataRole.UserRole + 1, icon_name)

        self.sidebar.addItem(item)

    @Slot(int)
    def on_sidebar_changed(self, index: int) -> None:
        """Changes the active view and refreshes data."""
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
        self.daemon.stop()
        self.daemon.wait()

    @Slot(str, int, object)
    def handle_omnibox_result(self, result_type: str, item_id: int, extra_data: object):
        if result_type == "doc":
            index = self.stack.indexOf(self.tab_documents)
            self.sidebar.setCurrentRow(index)
            self.tab_documents.jump_to_document(item_id)
        elif result_type == "note":
            index = self.stack.indexOf(self.tab_edition)
            self.sidebar.setCurrentRow(index)
            # Use English title for view mode
            self.tab_edition.view_mode_cb.setCurrentText(self.tr("View: Notes (Text)"))
            self.tab_edition.jump_to_note(item_id, cast(int, extra_data))

    def changeEvent(self, event):
        """Intercepts global theme changes to refresh the sidebar."""
        if event.type() == QEvent.Type.PaletteChange:
            from ankiforge.ui.theme import get_icon_color

            color = get_icon_color()

            # Loop through all tabs to redraw icons
            for i in range(self.sidebar.count()):
                item = self.sidebar.item(i)
                icon_name = item.data(Qt.ItemDataRole.UserRole + 1)
                if icon_name:
                    item.setIcon(qta.icon(icon_name, color=color))

        super().changeEvent(event)

    def _setup_tour_scenario(self):
        """Defines all tutorial steps."""
        scenario = [
            {
                "title": self.tr("Welcome to AnkiForge!"),
                "text": self.tr(
                    "Artificial Intelligence at the service of your memory.<br><br>"
                    "This short interactive tutorial will guide you through the interface "
                    "to show you how to forge your first flashcards in just a few clicks."
                ),
                "target_widget": None,
                "action": None,
            },
            {
                "title": self.tr("1. The AI Engine"),
                "text": self.tr("This is where it all starts. Enter your OpenAI or Gemini API key, " "or use Ollama locally. Without this engine, generation cannot start."),
                "target_widget": self.llm_manager_tab.le_openai_key,
                "action": lambda: self.sidebar.setCurrentRow(7),
            },
            {
                "title": self.tr("2. Raw Material"),
                "text": self.tr("Import your courses in PDF or type your notes in Markdown here. " "Text will be automatically saved and ready for analysis."),
                "target_widget": self.tab_documents.btn_import,
                "action": lambda: self.sidebar.setCurrentRow(5),
            },
            {
                "title": self.tr("3. The Card Factory"),
                "text": self.tr("Select the imported document, choose an AI Agent, and start generation. " "The AI will extract key concepts and format LaTeX code."),
                "target_widget": self.creation_tab.btn_generate,
                "action": lambda: self.sidebar.setCurrentRow(0),
            },
            {
                "title": self.tr("4. Quality Control"),
                "text": self.tr("Your cards land here. You can edit them, compare versions via history, " "and then export them to Anki."),
                "target_widget": self.tab_edition.note_table,
                "action": lambda: self.sidebar.setCurrentRow(1),
            },
            {
                "title": self.tr("You're ready"),
                "text": self.tr("Don't forget the Automation tab to process entire folders at once " "and the Statistics tab to track your API costs.\n\nHappy studying!"),
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
