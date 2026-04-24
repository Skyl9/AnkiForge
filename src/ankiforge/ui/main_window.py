from typing import Any

import qtawesome as qta
from PySide6.QtCore import QEvent, QSettings, QSize, Qt, QTimer, Slot
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut, QShowEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QStackedWidget, QToolButton, QVBoxLayout, QWidget

from ankiforge.services.background_daeamon import BackgroundDaemon
from ankiforge.ui.theme import get_icon_color
from ankiforge.ui.views.ab_test_view import ABTestTab
from ankiforge.ui.views.agents_view import AgentsTab
from ankiforge.ui.views.batch_view import BatchTab
from ankiforge.ui.views.consultant_view import ConsultantTab
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
    def __init__(self, ai_manager: Any) -> None:
        super().__init__()

        self.daemon = BackgroundDaemon()
        self.daemon.start()

        self.setWindowTitle(self.tr("AnkiForge - AI Flashcard Generator"))
        self.settings = QSettings("AnkiForgeOrg", "AnkiForge")
        self.ai_manager = ai_manager

        # --- État de la navigation ---
        self.current_category: str | None = None
        self.category_map: dict[str, list[dict[str, Any]]] = {}

        self._setup_ui()
        self._connect_signals()

        # Initialisation des vues et raccourcis
        self._setup_omnibox()
        self._setup_tour()

        self.read_settings()

    def _setup_ui(self) -> None:
        main_widget = QWidget()
        self.main_layout = QHBoxLayout(main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 1. ACTIVITY BAR (Barre d'icônes étroite)
        self.activity_bar = QFrame()
        self.activity_bar.setFixedWidth(60)
        self.activity_bar.setStyleSheet("""
            QFrame { 
                background-color: palette(window); 
                border-right: 1px solid palette(alternate-base);
            }
            QToolButton { 
                border: none; 
                padding: 15px; 
                border-left: 3px solid transparent;
            }
            QToolButton:checked { 
                background-color: palette(alternate-base); 
                border-left: 3px solid palette(highlight);
            }
            QToolButton:hover:!checked {
                background-color: palette(alternate-base);
            }
        """)
        self.activity_layout = QVBoxLayout(self.activity_bar)
        self.activity_layout.setContentsMargins(0, 10, 0, 10)
        self.activity_layout.setSpacing(5)

        # 2. DRAWER (La liste textuelle)
        self.drawer = QListWidget()
        self.drawer.setFixedWidth(180)
        self.drawer.setIconSize(QSize(18, 18))
        self.drawer.setFrameShape(QFrame.Shape.NoFrame)
        self.drawer.setStyleSheet("""
            QListWidget {
                background-color: palette(alternate-base);
                border-right: 1px solid palette(window);
                outline: none;
            }
            QListWidget::item { padding: 10px 15px; color: palette(text); border-radius: 4px; margin: 2px 8px; }
            QListWidget::item:selected { background-color: palette(highlight); color: palette(highlighted-text); }
        """)

        # 3. STACK (Le contenu)
        self.stack = QStackedWidget()

        # Assemblage
        self.main_layout.addWidget(self.activity_bar)
        self.main_layout.addWidget(self.drawer)
        self.main_layout.addWidget(self.stack, stretch=1)
        self.setCentralWidget(main_widget)

        # --- Construction des Piliers ---
        self._build_navigation()

        # 4. INDICATEUR DU DÉMON DE FOND
        self.btn_daemon_status = QToolButton()
        self.btn_daemon_status.setIcon(qta.icon("fa5s.circle", color="gray"))
        self.btn_daemon_status.setIconSize(QSize(16, 16))
        self.btn_daemon_status.setToolTip(self.tr("Forge au repos"))
        self.btn_daemon_status.setStyleSheet("QToolButton { border: none; padding: 15px; }")
        self.activity_layout.addWidget(self.btn_daemon_status)

    def _build_navigation(self) -> None:
        """Définit la hiérarchie de navigation IDE."""
        piliers = [("forge", "fa5s.hammer", self.tr("Forge")), ("library", "fa5s.book", self.tr("Library")), ("lab", "fa5s.flask", self.tr("Laboratory")), ("admin", "fa5s.cog", self.tr("Settings"))]

        for key, icon, tooltip in piliers:
            btn = QToolButton()
            btn.setIcon(qta.icon(icon, color=get_icon_color()))
            btn.setIconSize(QSize(24, 24))
            btn.setCheckable(True)
            btn.setToolTip(tooltip)
            btn.setProperty("category", key)
            btn.clicked.connect(self._on_category_clicked)

            self.activity_layout.addWidget(btn)
            self.category_map[key] = []
            if key == piliers[-1][0]:  # Si c'est le dernier (Settings), on pousse vers le haut
                self.activity_layout.insertStretch(self.activity_layout.count() - 1)

        # Catégorie Forge
        self._register_view("forge", CreationTab(self.ai_manager), "fa5s.magic", self.tr("Flashcard Creation"))
        self._register_view("forge", EditionTab(), "fa5s.layer-group", self.tr("Edition / Analysis"))
        self._register_view("forge", ConsultantTab(self.ai_manager), "fa5s.robot", self.tr("AI Consultant"))

        # Catégorie Library
        self._register_view("library", DocumentsTab(), "fa5s.file-alt", self.tr("My Documents"))
        self._register_view("library", ModelsTab(), "fa5s.paint-brush", self.tr("Card Models"))

        # Catégorie Laboratory
        self._register_view("lab", BatchTab(self.ai_manager), "fa5s.rocket", self.tr("Batch Factory"))
        self._register_view("lab", AgentsTab(), "fa5s.user-cog", self.tr("Agents & Pipelines"))
        self._register_view("lab", ABTestTab(), "fa5s.vial", self.tr("A/B Testing"))

        # Catégorie Settings
        self._register_view("admin", StatsTab(), "fa5s.chart-bar", self.tr("Statistics"))
        self._register_view("admin", LLMManagerTab(self.ai_manager), "fa5s.microchip", self.tr("AI Engines"))
        self._register_view("admin", SettingsTab(), "fa5s.sliders-h", self.tr("Preferences"))

    def _register_view(self, category: str, widget: QWidget, icon: str, title: str) -> None:
        """Ajoute une vue au stack et la référence dans sa catégorie."""
        idx = self.stack.addWidget(widget)
        self.category_map[category].append({"index": idx, "icon": icon, "title": title, "widget": widget})

    def _connect_signals(self) -> None:
        self.drawer.currentRowChanged.connect(self._on_drawer_selection_changed)
        self.daemon.job_updated.connect(self._update_daemon_status)

    @Slot()
    def _on_category_clicked(self) -> None:
        sender = self.sender()
        if not isinstance(sender, QToolButton):
            return

        category = sender.property("category")

        if self.current_category != category and not self._can_switch_tab() and self.current_category is not None:
            sender.setChecked(False)
            # On réactive visuellement le bouton précédent
            prev_btn = self._get_category_button(self.current_category)
            if prev_btn:
                prev_btn.setChecked(True)
            return

        # Décocher les autres boutons de l'activity bar
        for i in range(self.activity_layout.count()):
            layout_item = self.activity_layout.itemAt(i)
            if layout_item:
                w = layout_item.widget()
                if isinstance(w, QToolButton) and w != sender and w != self.btn_daemon_status:
                    w.setChecked(False)

        # Si on reclique sur la catégorie active -> on ferme le tiroir
        if self.current_category == category and self.drawer.isVisible():
            self.drawer.hide()
            sender.setChecked(False)
            return

        # Sinon, on ouvre/met à jour le drawer
        self.current_category = category
        self._populate_drawer(category)
        self.drawer.show()
        sender.setChecked(True)

    def _populate_drawer(self, category: str) -> None:
        self.drawer.clear()
        for item_data in self.category_map[category]:
            item = QListWidgetItem(qta.icon(item_data["icon"], color=get_icon_color()), item_data["title"])
            item.setData(Qt.ItemDataRole.UserRole, item_data["index"])
            self.drawer.addItem(item)

        # Sélectionner le premier par défaut si rien n'est sélectionné
        self.drawer.setCurrentRow(0)

    def _can_switch_tab(self) -> bool:
        """
        Vérifie si la vue actuelle autorise le départ.
        Affiche une popup de confirmation si nécessaire.
        """
        current_widget = self.stack.currentWidget()

        # On vérifie si le widget possède la méthode is_dirty et si elle renvoie True
        if hasattr(current_widget, "is_dirty") and current_widget.is_dirty():
            reply = QMessageBox.question(
                self,
                self.tr("Données non sauvegardées"),
                self.tr("Vous avez des modifications ou des notes non sauvegardées. Voulez-vous vraiment quitter cet onglet et perdre vos données ?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                # 👇 NOUVEAU : On force la vue à nettoyer son désordre avant de partir
                if hasattr(current_widget, "reset_unsaved_state"):
                    current_widget.reset_unsaved_state()
                return True
            return False
        return True

    @Slot(int)
    def _on_drawer_selection_changed(self, row: int) -> None:
        if row < 0:
            return
        if not self._can_switch_tab():
            self.drawer.blockSignals(True)
            for i in range(self.drawer.count()):
                if self.drawer.item(i).data(Qt.ItemDataRole.UserRole) == self.stack.currentIndex():
                    self.drawer.setCurrentRow(i)
                    break
            self.drawer.blockSignals(False)
            return
        item = self.drawer.item(row)
        stack_idx = item.data(Qt.ItemDataRole.UserRole)

        self.stack.setCurrentIndex(stack_idx)
        current_widget = self.stack.widget(stack_idx)

        # Appel auto du refresh si dispo
        refresh_method = getattr(current_widget, "refresh_data", None)
        if callable(refresh_method):
            refresh_method()

    @Slot()
    def _update_daemon_status(self) -> None:
        """Met à jour l'icône de l'Activity Bar selon l'activité de la base de données."""
        from ankiforge.database.models import JobModel

        active_jobs = JobModel.select().where(JobModel.status == "processing").count()
        pending_jobs = JobModel.select().where(JobModel.status == "pending").count()

        if active_jobs > 0:
            self.btn_daemon_status.setIcon(qta.icon("fa5s.sync", color="#FF9800", animation=qta.Spin(self.btn_daemon_status)))
            self.btn_daemon_status.setToolTip(self.tr("Forge en cours : {0} tâche(s) active(s)").format(active_jobs))
        elif pending_jobs > 0:
            self.btn_daemon_status.setIcon(qta.icon("fa5s.clock", color="#2196F3"))
            self.btn_daemon_status.setToolTip(self.tr("File d'attente : {0} tâche(s) en attente").format(pending_jobs))
        else:
            self.btn_daemon_status.setIcon(qta.icon("fa5s.circle", color="gray"))
            self.btn_daemon_status.setToolTip(self.tr("Forge au repos"))

    def _setup_omnibox(self) -> None:
        self.omnibox = Omnibox(self)
        self.omnibox.result_selected.connect(self.handle_omnibox_result)
        self.shortcut_search = QShortcut(QKeySequence("Ctrl+K"), self)
        self.shortcut_search.activated.connect(lambda: self.omnibox.exec_centered(self))

    # --- Setup Helpers ---
    def _setup_tour(self) -> None:
        self.tour_bubble = TourBubble(self)
        self._setup_tour_scenario()

    def _get_category_button(self, category: str) -> QToolButton | None:
        """Cherche dynamiquement un bouton de l'Activity Bar par son ID."""
        for i in range(self.activity_layout.count()):
            layout_item = self.activity_layout.itemAt(i)
            if layout_item:
                w = layout_item.widget()
                if isinstance(w, QToolButton) and w.property("category") == category:
                    return w
        return None

    def _jump_to_tab(self, category: str, drawer_row: int) -> None:
        """
        Utilitaire robuste pour le Wizard : force l'ouverture d'un pilier
        sans risquer de le refermer accidentellement.
        """
        btn = self._get_category_button(category)

        if btn:
            # On force l'état "Ouvert" au lieu de simuler un clic
            if self.current_category != category or not self.drawer.isVisible():
                self.current_category = category
                self._populate_drawer(category)
                self.drawer.show()
                btn.setChecked(True)

                # Décocher les autres boutons proprement
                for i in range(self.activity_layout.count()):
                    layout_item = self.activity_layout.itemAt(i)
                    if layout_item:
                        w = layout_item.widget()
                        if isinstance(w, QToolButton) and w != btn and w != self.btn_daemon_status:
                            w.setChecked(False)

        if self.drawer.count() > drawer_row:
            self.drawer.setCurrentRow(drawer_row)

    def _setup_tour_scenario(self) -> None:
        """Scénario du tutoriel avec typage natif selon GEMINI.md."""
        from typing import Any

        scenario: list[dict[str, Any]] = [
            {
                "title": self.tr("Bienvenue dans AnkiForge !"),
                "text": self.tr("L'Intelligence Artificielle au service de votre mémoire.<br><br>Suivez ce guide pour découvrir comment transformer vos cours en flashcards en un temps record."),
                "target_widget": None,
                "action": None,
            },
            {
                "title": self.tr("1. Configuration des Moteurs"),
                "text": self.tr("C'est ici que vous configurez vos clés API (OpenAI, Gemini) ou votre modèle local Ollama. <b>Indispensable pour commencer.</b>"),
                "target_widget": self._get_category_button("admin"),
                "action": lambda: self._jump_to_tab("admin", 1),
            },
            {
                "title": self.tr("2. Gestion des Documents"),
                "text": self.tr("Importez vos PDF, fichiers Word ou pages Web ici. AnkiForge les transformera en Markdown structuré prêt pour l'IA."),
                "target_widget": self._get_category_button("library"),
                "action": lambda: self._jump_to_tab("library", 0),
            },
            {
                "title": self.tr("3. Création Assistée"),
                "text": self.tr("C'est le cœur de l'application. Sélectionnez un cours, un Agent (ex: Archiviste), et l'IA générera vos cartes en respectant vos modèles."),
                "target_widget": self._get_category_button("forge"),
                "action": lambda: self._jump_to_tab("forge", 0),
            },
            {
                "title": self.tr("4. Édition et Analyse"),
                "text": self.tr("Modifiez vos cartes, gérez les tags et vérifiez la qualité avant l'exportation. Vous pouvez même comparer les versions via l'historique."),
                "target_widget": self._get_category_button("forge"),
                "action": lambda: self._jump_to_tab("forge", 1),
            },
            {
                "title": self.tr("5. Consultant IA"),
                "text": self.tr("Posez des questions à l'IA sur vos documents ou vos paquets existants pour obtenir des explications ou des conseils pédagogiques."),
                "target_widget": self._get_category_button("forge"),
                "action": lambda: self._jump_to_tab("forge", 2),
            },
            {
                "title": self.tr("6. Automatisation (Batch)"),
                "text": self.tr("Pour les gros volumes : traitez des dossiers entiers de PDF en arrière-plan pendant que vous continuez à travailler."),
                "target_widget": self._get_category_button("lab"),
                "action": lambda: self._jump_to_tab("lab", 0),
            },
            {
                "title": self.tr("7. Laboratoire A/B"),
                "text": self.tr("Comparez deux modèles IA ou deux prompts différents pour trouver la configuration qui donne les meilleurs résultats."),
                "target_widget": self._get_category_button("lab"),
                "action": lambda: self._jump_to_tab("lab", 2),
            },
            {
                "title": self.tr("Prêt pour la Forge !"),
                "text": self.tr("Vous avez maintenant toutes les clés. N'oubliez pas d'utiliser <b>Ctrl+K</b> pour rechercher n'importe quoi dans l'appli.<br><br>Bonnes révisions !"),
                "target_widget": None,
                "action": None,
            },
        ]
        self.tour_bubble.set_scenario(scenario)

    # --- Standard Qt Events ---
    def handle_omnibox_result(self, result_type: str, item_id: int, extra_data: object) -> None:
        pass  # À adapter selon la nouvelle hiérarchie

    def read_settings(self) -> None:
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(1200, 850)

        # Par défaut, ouvrir la forge
        item = self.activity_layout.itemAt(0)
        first_btn = item.widget() if item else None
        if first_btn and isinstance(first_btn, QToolButton):
            first_btn.click()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        self.daemon.stop()
        self.daemon.wait()
        event.accept()

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.PaletteChange:
            color = get_icon_color()
            piliers_icons = ["fa5s.hammer", "fa5s.book", "fa5s.flask", "fa5s.cog"]
            for i, icon_name in enumerate(piliers_icons):
                item = self.activity_layout.itemAt(i)
                w = item.widget() if item else None
                if isinstance(w, QToolButton):
                    w.setIcon(qta.icon(icon_name, color=color))
        super().changeEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        tour_done = self.settings.value("app/tour_completed", False, type=bool)
        if not tour_done:
            QTimer.singleShot(500, self.tour_bubble.start_tour)
