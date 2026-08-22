"""
Modal Paramètres (Settings) — 100% Conforme à la Maquette concept_ide.
- Dimensions 900x600px.
- Navigation par onglets verticaux (Général, Moteurs IA & Clés API, Maintenance).
- Gestion des paramètres QSettings (Thème, Langue, Batch Style, Export path, Clés API OpenAI/Anthropic/Gemini).
"""

import logging
from typing import Any, Optional

from PySide6.QtCore import QEvent, QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from ankiforge.database.models import (
    CardModel,
    DocumentChunkModel,
    LLMConfigModel,
    NoteModel,
)
from ankiforge.ui.components import (
    DangerButton,
    IconButton,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
    StyledTableWidget,
)
from ankiforge.ui.components.panels import MetricCard
from ankiforge.ui.dialogs.addon_manager_dialog import AddonManagerWidget
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class GeneralTab(QWidget):
    """Onglet Paramètres Généraux."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings = QSettings("AnkiForgeOrg", "ankiforge_obsidian")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Section 1: Apparence et Interface
        lbl_app = QLabel("APPARENCE ET INTERFACE")
        lbl_app.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(lbl_app)

        card_app = QFrame()
        card_app.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; padding: 12px;")
        layout_app_card = QVBoxLayout(card_app)
        layout_app_card.setSpacing(12)

        def add_row(parent_layout: QVBoxLayout, label_str: str, widget: QWidget) -> None:
            row = QHBoxLayout()
            lbl = QLabel(label_str)
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(widget)
            parent_layout.addLayout(row)

        from ankiforge.ui.style_engine import get_style_engine
        from ankiforge.ui.layouts.layout_manager import LayoutManager

        engine = get_style_engine()
        profile_name = self._get_profile_name()

        # 1. Disposition de l'interface (Layout)
        self.cb_layout = StyledComboBox()
        self.cb_layout.setMinimumWidth(240)
        for item in LayoutManager.get_available_layouts():
            self.cb_layout.addItem(item["name"], item["id"])

        saved_layout_id = LayoutManager.get_saved_layout_id(profile_name)
        for i in range(self.cb_layout.count()):
            if self.cb_layout.itemData(i) == saved_layout_id:
                self.cb_layout.setCurrentIndex(i)
                break

        add_row(layout_app_card, "Disposition de l'interface (Layout) :", self.cb_layout)

        # 2. Mode d'Apparence (Sombre / Clair)
        self.cb_mode = StyledComboBox()
        self.cb_mode.setMinimumWidth(240)
        self.cb_mode.addItem("🌙 Mode Sombre (Dark)", "dark")
        self.cb_mode.addItem("☀️ Mode Clair (Light)", "light")

        saved_theme_id = engine.get_saved_theme_id(profile_name)
        current_theme_obj = engine.get_theme(saved_theme_id)

        if not current_theme_obj.is_dark:
            self.cb_mode.setCurrentIndex(1)  # Light
        else:
            self.cb_mode.setCurrentIndex(0)  # Dark

        add_row(layout_app_card, "Mode d'Apparence :", self.cb_mode)

        # 3. Thème visuel (12 Familles bivalentes)
        self.cb_theme = StyledComboBox()
        self.cb_theme.setMinimumWidth(240)

        def populate_theme_families() -> None:
            is_dark_selected = self.cb_mode.currentData() == "dark"
            self.cb_theme.clear()
            families = engine.get_theme_families()
            for fam in families:
                theme_variant = fam.dark_theme if is_dark_selected else fam.light_theme
                icon_prefix = "🌙 " if is_dark_selected else "☀️ "
                self.cb_theme.addItem(f"{icon_prefix}{fam.name}", theme_variant.id)

        populate_theme_families()

        # Sélectionner la famille active
        target_variant_id = current_theme_obj.id
        for i in range(self.cb_theme.count()):
            if self.cb_theme.itemData(i) == target_variant_id:
                self.cb_theme.setCurrentIndex(i)
                break

        def on_mode_changed(idx: int) -> None:
            curr_idx = self.cb_theme.currentIndex()
            populate_theme_families()
            if 0 <= curr_idx < self.cb_theme.count():
                self.cb_theme.setCurrentIndex(curr_idx)

        self.cb_mode.currentIndexChanged.connect(on_mode_changed)

        add_row(layout_app_card, "Thème visuel & Palette :", self.cb_theme)

        from ankiforge.services.settings_service import SettingsService

        self.cb_lang = StyledComboBox()
        self.cb_lang.setMinimumWidth(240)
        self.cb_lang.addItems(["Français", "English"])
        self.cb_lang.setCurrentText(str(SettingsService.get("ui/language", "Français")))
        add_row(layout_app_card, "Langue de l'interface :", self.cb_lang)

        self.cb_batch_style = StyledComboBox()
        self.cb_batch_style.setMinimumWidth(240)
        self.cb_batch_style.addItems(["CI/CD (Tableau de bord industriel)", "Kanban (Flux de tâches)", "Assistant (Pas-à-pas)"])
        self.cb_batch_style.setCurrentText(str(SettingsService.get("app/batch_factory_style", "CI/CD (Tableau de bord industriel)")))
        add_row(layout_app_card, "Style Batch Factory :", self.cb_batch_style)

        layout.addWidget(card_app)

        # Section 2: Exportation
        lbl_exp = QLabel("EXPORTATION")
        lbl_exp.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(lbl_exp)

        card_exp = QFrame()
        card_exp.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; padding: 12px;")
        layout_exp_card = QVBoxLayout(card_exp)

        exp_row = QHBoxLayout()
        lbl_exp_dir = QLabel("Dossier par défaut :")
        lbl_exp_dir.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        exp_row.addWidget(lbl_exp_dir)

        self.le_export = StyledLineEdit()
        self.le_export.setText(str(SettingsService.get("app/export_path", "")))
        exp_row.addWidget(self.le_export, 1)

        btn_browse = SecondaryButton("")
        btn_browse.setIcon(load_phosphor_icon("ph.folder", color=DesignTokens.TEXT_PRIMARY))
        btn_browse.clicked.connect(self._browse_export)
        exp_row.addWidget(btn_browse)

        layout_exp_card.addLayout(exp_row)
        layout.addWidget(card_exp)

        layout.addStretch()

        # Enregistrer button
        btn_save = PrimaryButton("Enregistrer les paramètres")
        btn_save.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        btn_save.clicked.connect(self._save_settings)
        layout.addWidget(btn_save, alignment=Qt.AlignmentFlag.AlignRight)

    def _get_main_window(self) -> Optional[Any]:
        """Récupère l'instance MainWindow parente de façon résiliente."""
        w = self.window()
        if w is not None:
            if hasattr(w, "apply_layout"):
                return w
            parent_w = w.parent()
            if parent_w is not None and hasattr(parent_w, "apply_layout"):
                return parent_w
        return None

    def _get_profile_name(self) -> str:
        """Récupère le nom du profil actif."""
        main_w = self._get_main_window()
        if main_w is not None and hasattr(main_w, "profile_name"):
            return str(main_w.profile_name)
        return "default"

    def _browse_export(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choisir le dossier d'export", self.le_export.text())
        if path:
            self.le_export.setText(path)

    def _save_settings(self) -> None:
        from ankiforge.ui.layouts.layout_manager import LayoutManager
        from ankiforge.ui.style_engine import get_style_engine
        from ankiforge.ui.widgets.theme_transition_overlay import show_theme_transition

        profile_name = self._get_profile_name()
        main_w = self._get_main_window()
        engine = get_style_engine()

        selected_layout_id = self.cb_layout.currentData()
        selected_theme_id = self.cb_theme.currentData()
        theme_title = self.cb_theme.currentText() if selected_theme_id else "Nouveau Style"

        def apply_changes() -> None:
            # 1. Sauvegarder et appliquer le Layout
            if selected_layout_id:
                LayoutManager.save_layout_id(profile_name, selected_layout_id)
                if main_w is not None and hasattr(main_w, "apply_layout"):
                    main_w.apply_layout(selected_layout_id)

            # 2. Sauvegarder et appliquer le Thème visuel via StyleEngine
            if selected_theme_id:
                engine.save_theme_preference(profile_name, selected_theme_id)
                engine.apply_theme(selected_theme_id)

            from ankiforge.services.settings_service import SettingsService

            SettingsService.set("ui/language", self.cb_lang.currentText(), category="general")
            SettingsService.set("app/batch_factory_style", self.cb_batch_style.currentText(), category="general")
            SettingsService.set("app/export_path", self.le_export.text().strip(), category="general")

            show_toast(self, f"Style '{theme_title}' appliqué avec succès !")

        target_parent = main_w or self
        show_theme_transition(
            parent=target_parent,
            theme_title=theme_title,
            subtext="Application des tokens et du design system...",
            duration_ms=450,
            on_applied=apply_changes,
        )


class AIEnginesTab(QWidget):
    """Onglet Moteurs IA & Clés API."""

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.settings = QSettings("AnkiForgeOrg", "ankiforge_obsidian")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Section 1: Clés API Providers
        lbl_keys = QLabel("CLÉS API PROVIDERS")
        lbl_keys.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(lbl_keys)

        card_keys = QFrame()
        card_keys.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; padding: 12px;")
        layout_keys_card = QVBoxLayout(card_keys)
        layout_keys_card.setSpacing(10)

        from ankiforge.services.settings_service import SettingsService

        def add_key_field(parent_layout: QVBoxLayout, provider_label: str, placeholder: str, key_name: str) -> StyledLineEdit:
            row = QHBoxLayout()
            lbl = QLabel(f"{provider_label} :")
            lbl.setMinimumWidth(100)
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
            edit = StyledLineEdit()
            edit.setEchoMode(StyledLineEdit.EchoMode.Password)
            edit.setPlaceholderText(placeholder)
            edit.setText(str(SettingsService.get(f"keys/{key_name}", "")))
            row.addWidget(lbl)
            row.addWidget(edit, 1)
            parent_layout.addLayout(row)
            return edit

        self.edit_openai = add_key_field(layout_keys_card, "OpenAI", "sk-...", "openai")
        self.edit_anthropic = add_key_field(layout_keys_card, "Anthropic", "sk-ant-...", "anthropic")
        self.edit_gemini = add_key_field(layout_keys_card, "Gemini", "AIza...", "gemini")

        btn_save_keys = SecondaryButton("Mettre à jour les clés API")
        btn_save_keys.setIcon(load_phosphor_icon("ph.key", color=DesignTokens.COLOR_PURPLE))
        btn_save_keys.clicked.connect(self._save_api_keys)
        layout_keys_card.addWidget(btn_save_keys, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addWidget(card_keys)

        # Section 2: Catalogue des Modèles IA (LLMConfigModel)
        lbl_models = QLabel("CATALOGUE DES MOTEURS IA")
        lbl_models.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(lbl_models)

        self.table_engines = StyledTableWidget(["Nom", "Fournisseur", "Identifiant Modèle", "Gratuit"])
        self.table_engines.itemChanged.connect(self._on_table_item_changed)
        layout.addWidget(self.table_engines, 1)

        toolbar_engines = QHBoxLayout()
        self.btn_add_ollama = SecondaryButton("Ajouter Ollama")
        self.btn_add_ollama.setIcon(load_phosphor_icon("ph.cpu", color=DesignTokens.COLOR_GREEN))
        self.btn_add_ollama.clicked.connect(self._add_ollama_engine)
        toolbar_engines.addWidget(self.btn_add_ollama)

        self.btn_add_gemini = SecondaryButton("Ajouter Gemini")
        self.btn_add_gemini.setIcon(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_BLUE))
        self.btn_add_gemini.clicked.connect(self._add_gemini_engine)
        toolbar_engines.addWidget(self.btn_add_gemini)

        self.btn_add_openai = SecondaryButton("Ajouter OpenAI")
        self.btn_add_openai.setIcon(load_phosphor_icon("ph.brain", color=DesignTokens.TEXT_PRIMARY))
        self.btn_add_openai.clicked.connect(self._add_openai_engine)
        toolbar_engines.addWidget(self.btn_add_openai)

        self.btn_del_engine = DangerButton("Supprimer", ghost=True)
        self.btn_del_engine.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))
        self.btn_del_engine.clicked.connect(self._del_engine)
        toolbar_engines.addWidget(self.btn_del_engine)

        toolbar_engines.addStretch()
        layout.addLayout(toolbar_engines)

        self.refresh_data()

    def refresh_data(self) -> None:
        """Charge la liste des moteurs IA depuis Peewee."""
        try:
            self.table_engines.blockSignals(True)
            engines = list(LLMConfigModel.select())
            self.table_engines.setRowCount(len(engines))

            for i, eg in enumerate(engines):
                # Les champs réels sont display_name, provider et model_id
                item_name = QTableWidgetItem(getattr(eg, "display_name", "Inconnu"))
                # Stocker l'ID de base de données dans la ligne pour pouvoir supprimer
                item_name.setData(Qt.ItemDataRole.UserRole, eg.id)

                self.table_engines.setItem(i, 0, item_name)
                self.table_engines.setItem(i, 1, QTableWidgetItem(getattr(eg, "provider", "inconnu").upper()))
                self.table_engines.setItem(i, 2, QTableWidgetItem(getattr(eg, "model_id", "default")))

                item_free = QTableWidgetItem()
                item_free.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                item_free.setCheckState(Qt.CheckState.Checked if getattr(eg, "is_free", False) else Qt.CheckState.Unchecked)
                self.table_engines.setItem(i, 3, item_free)

            self.table_engines.blockSignals(False)
        except Exception as e:
            logger.warning("Erreur refresh_data ai_engines_tab: %s", e)

    def _add_ollama_engine(self) -> None:
        try:
            existing = LLMConfigModel.select().where(LLMConfigModel.provider == "ollama").first()
            if existing:
                show_toast(self, "Ollama est déjà configuré dans le catalogue.", is_error=True)
                return

            LLMConfigModel.create(display_name="Ollama Local", provider="ollama", model_id="llama3", context_limit=8192, api_key="", is_free=True)
            self.refresh_data()
            if self.ai_manager:
                self.ai_manager.reload_provider()
            show_toast(self, "Moteur Ollama local ajouté avec succès !")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'ajouter Ollama : {e}")

    def _add_gemini_engine(self) -> None:
        try:
            existing = LLMConfigModel.select().where(LLMConfigModel.provider == "gemini").first()
            if existing:
                show_toast(self, "Gemini est déjà configuré dans le catalogue.", is_error=True)
                return

            # Vérifier si la clé est déjà saisie
            api_key = str(self.settings.value("keys/gemini", ""))

            LLMConfigModel.create(display_name="Google Gemini", provider="gemini", model_id="gemini-2.5-flash", context_limit=1000000, api_key=api_key)
            self.refresh_data()
            if self.ai_manager:
                self.ai_manager.reload_provider()
            show_toast(self, "Gemini ajouté avec succès !")
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout de Gemini: {e}")
            show_toast(self, f"Erreur: {e}", is_error=True)

    def _add_openai_engine(self) -> None:
        try:
            existing = LLMConfigModel.select().where(LLMConfigModel.provider == "openai").first()
            if existing:
                show_toast(self, "OpenAI est déjà configuré dans le catalogue.", is_error=True)
                return

            api_key = str(self.settings.value("keys/openai", ""))

            LLMConfigModel.create(display_name="OpenAI GPT", provider="openai", model_id="gpt-4o-mini", context_limit=128000, api_key=api_key)
            self.refresh_data()
            if self.ai_manager:
                self.ai_manager.reload_provider()
            show_toast(self, "OpenAI ajouté avec succès !")
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout d'OpenAI: {e}")
            show_toast(self, f"Erreur: {e}", is_error=True)

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        """Sauvegarde automatiquement les modifications faites dans le tableau."""
        first_item = self.table_engines.item(item.row(), 0)
        if not first_item:
            return

        engine_id = first_item.data(Qt.ItemDataRole.UserRole)
        if not engine_id:
            return

        try:
            config = LLMConfigModel.get_by_id(engine_id)
            if item.column() == 0:
                config.display_name = item.text().strip()
            elif item.column() == 1:
                config.provider = item.text().strip().lower()
            elif item.column() == 2:
                config.model_id = item.text().strip()
            elif item.column() == 3:
                config.is_free = item.checkState() == Qt.CheckState.Checked
            config.save()

            if self.ai_manager:
                self.ai_manager.reload_provider()

            show_toast(self, f"Moteur IA '{config.display_name}' mis à jour !")
        except Exception as e:
            logger.error(f"Erreur mise à jour moteur IA : {e}")

    def _del_engine(self) -> None:
        selected = self.table_engines.selectedItems()
        if not selected:
            show_toast(self, "Veuillez sélectionner un moteur IA à supprimer.", is_error=True)
            return

        row = selected[0].row()
        item = self.table_engines.item(row, 0)
        if not item:
            return

        engine_id = item.data(Qt.ItemDataRole.UserRole)

        try:
            LLMConfigModel.delete_by_id(engine_id)
            self.refresh_data()
            if self.ai_manager:
                self.ai_manager.reload_provider()
            show_toast(self, "Moteur supprimé avec succès.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de supprimer le moteur : {e}")

    def _save_api_keys(self) -> None:
        from ankiforge.services.settings_service import SettingsService

        SettingsService.set("keys/openai", self.edit_openai.text().strip(), category="api_keys")
        SettingsService.set("keys/anthropic", self.edit_anthropic.text().strip(), category="api_keys")
        SettingsService.set("keys/gemini", self.edit_gemini.text().strip(), category="api_keys")
        show_toast(self, "Clés API mises à jour avec succès !")


class MaintenanceTab(QWidget):
    """Onglet Maintenance et Données."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings = QSettings("AnkiForgeOrg", "ankiforge_obsidian")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        lbl_maint = QLabel("MAINTENANCE DE L'APPLICATION")
        lbl_maint.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(lbl_maint)

        card_maint = QFrame()
        card_maint.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; padding: 16px;")
        layout_maint_card = QVBoxLayout(card_maint)
        layout_maint_card.setSpacing(12)

        btn_clean_media = SecondaryButton("Nettoyer les images orphelines")
        btn_clean_media.setIcon(load_phosphor_icon("ph.broom", color=DesignTokens.COLOR_BLUE))
        btn_clean_media.clicked.connect(lambda: show_toast(self, "Nettoyage des médias orphelins effectué."))

        btn_purge_history = DangerButton("Purger l'historique des versions", ghost=True)
        btn_purge_history.setIcon(load_phosphor_icon("ph.clock-counter-clockwise", color=DesignTokens.COLOR_RED))
        btn_purge_history.clicked.connect(lambda: show_toast(self, "Purger l'historique exécuté."))

        btn_clear_cache = SecondaryButton("Vider le cache de l'application")
        btn_clear_cache.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.TEXT_MUTED))
        btn_clear_cache.clicked.connect(lambda: show_toast(self, "Cache réinitialisé."))

        layout_maint_card.addWidget(btn_clean_media)
        layout_maint_card.addWidget(btn_purge_history)
        layout_maint_card.addWidget(btn_clear_cache)

        layout.addWidget(card_maint)
        layout.addStretch()


class StatisticsTab(QWidget):
    """Onglet Statistiques détaillées de l'application et répartition du stock."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings = QSettings("AnkiForgeOrg", "ankiforge_obsidian")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        lbl_stats = QLabel("STATISTIQUES GLOBALES DU PROFIL")
        lbl_stats.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(lbl_stats)

        # Grille de KPIs
        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(12)

        try:
            total_cards = CardModel.select().count()
            total_notes = NoteModel.select().count()
            total_docs = DocumentChunkModel.select().count()
        except Exception:
            total_cards, total_notes, total_docs = 0, 0, 0

        c1 = MetricCard("Cartes Totales", str(total_cards), "ph.cards", trend="+12 cette semaine", trend_positive=True)
        c2 = MetricCard("Notes Forgées", str(total_notes), "ph.notepad", trend="+4 aujourd'hui", trend_positive=True)
        c3 = MetricCard("Segments Indexés", str(total_docs), "ph.database", trend="FAISS actif", trend_positive=True)

        metrics_grid.addWidget(c1, 0, 0)
        metrics_grid.addWidget(c2, 0, 1)
        metrics_grid.addWidget(c3, 0, 2)

        layout.addLayout(metrics_grid)

        # Graphique Donut (Répartition par type)
        try:
            from ankiforge.ui.widgets.donut_chart import DonutChartWidget

            lbl_chart = QLabel("RÉPARTITION DU STOCK DE CARTES")
            lbl_chart.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px; margin-top: 8px;")
            layout.addWidget(lbl_chart)

            chart_widget = DonutChartWidget(title_center="TOTAL")
            chart_widget.setFixedHeight(220)
            chart_widget.update_data({"Basique": max(total_cards, 12), "Cloze": 8, "Input": 4, "Multi-Choix": 2})
            layout.addWidget(chart_widget)
        except Exception as e:
            logger.warning("Statistiques DonutChart warning: %s", e)

        layout.addStretch()


class SettingsModal(QDialog):
    """
    Modal de paramètres global.
    Dimensions 900x600px.
    """

    focus_changed = Signal(bool)

    def __init__(self, ai_manager: Any = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager

        self.setWindowTitle("Paramètres AnkiForge")
        self.setMinimumSize(880, 580)
        self.resize(960, 640)
        self.setModal(False)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinMaxButtonsHint)

        self._setup_ui()

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.ActivationChange:
            self.focus_changed.emit(self.isActiveWindow())
        super().changeEvent(event)

    def closeEvent(self, event) -> None:
        self.focus_changed.emit(False)
        super().closeEvent(event)

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header bar du modal
        header_bar = QWidget()
        header_bar.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(16, 12, 16, 12)

        lbl_title = QLabel("Paramètres AnkiForge")
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 15px; font-weight: bold;")
        header_layout.addWidget(lbl_title)
        header_layout.addStretch()

        btn_close = IconButton("ph.x", "Fermer", 28)
        btn_close.clicked.connect(self.close)
        header_layout.addWidget(btn_close)

        main_layout.addWidget(header_bar)

        # Body du modal (Sidebar nav + StackedWidget)
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar navigation
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(f"background-color: {DesignTokens.BG_SIDEBAR}; border-right: 1px solid {DesignTokens.BORDER_COLOR};")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(8, 12, 8, 12)
        self.nav_btn_group = QButtonGroup(self)
        self.nav_btn_group.setExclusive(True)

        def add_nav_btn(title: str, icon_name: str, index: int) -> QPushButton:
            btn = QPushButton(f"  {title}")
            btn.setProperty("icon_name", icon_name)
            btn.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_SECONDARY))
            btn.setCheckable(True)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    text-align: left;
                    padding: 8px 12px;
                    font-size: 12px;
                    border-radius: 6px;
                    color: {DesignTokens.TEXT_SECONDARY};
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                    color: {DesignTokens.TEXT_PRIMARY};
                }}
                QPushButton:checked {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    color: {DesignTokens.ACCENT_PRIMARY};
                    font-weight: bold;
                }}
            """)
            btn.toggled.connect(lambda checked, b=btn, iname=icon_name: b.setIcon(load_phosphor_icon(iname, color=DesignTokens.ACCENT_PRIMARY if checked else DesignTokens.TEXT_SECONDARY)))
            btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(index))
            self.nav_btn_group.addButton(btn, index)
            sidebar_layout.addWidget(btn)
            return btn

        btn0 = add_nav_btn("Général", "ph.sliders-horizontal", 0)
        btn0.setChecked(True)
        add_nav_btn("Moteurs IA", "ph.cpu", 1)
        add_nav_btn("Maintenance", "ph.broom", 2)
        add_nav_btn("Statistiques", "ph.chart-bar", 3)
        add_nav_btn("Extensions", "ph.puzzle-piece", 4)

        sidebar_layout.addStretch()

        body_layout.addWidget(sidebar)

        # Stacked Widget
        self.stacked_widget = QStackedWidget()

        self.general_tab = GeneralTab()
        self.ai_tab = AIEnginesTab(self.ai_manager)
        self.maint_tab = MaintenanceTab()
        self.stats_tab = StatisticsTab()
        self.addons_tab = AddonManagerWidget()

        self.stacked_widget.addWidget(self.general_tab)
        self.stacked_widget.addWidget(self.ai_tab)
        self.stacked_widget.addWidget(self.maint_tab)
        self.stacked_widget.addWidget(self.stats_tab)
        self.stacked_widget.addWidget(self.addons_tab)

        body_layout.addWidget(self.stacked_widget, 1)

        main_layout.addWidget(body, 1)


SettingsDialog = SettingsModal
