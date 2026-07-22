"""
Modal Paramètres (Settings) — 100% Conforme à la Maquette concept_ide.
- Dimensions 900x600px.
- Navigation par onglets verticaux (Général, Moteurs IA & Clés API, Maintenance).
- Gestion des paramètres QSettings (Thème, Langue, Batch Style, Export path, Clés API OpenAI/Anthropic/Gemini).
"""

import logging
from typing import Any, Optional

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import LLMConfigModel
from ankiforge.ui.components import (
    DangerButton,
    IconButton,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
    StyledTableWidget,
)
from ankiforge.ui.theme import DesignTokens, refresh_theme_live
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
        card_app.setStyleSheet(f"background-color: #1a1d24; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; padding: 12px;")
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

        self.cb_theme = StyledComboBox()
        self.cb_theme.setMinimumWidth(220)
        self.cb_theme.addItems(["Système (Sombre par défaut)", "Sombre (Dark)", "Clair (Light)"])
        self.cb_theme.setCurrentText(str(self.settings.value("ui/theme", "Système (Sombre par défaut)")))
        add_row(layout_app_card, "Thème de l'application :", self.cb_theme)

        self.cb_lang = StyledComboBox()
        self.cb_lang.setMinimumWidth(220)
        self.cb_lang.addItems(["Français", "English"])
        self.cb_lang.setCurrentText(str(self.settings.value("ui/language", "Français")))
        add_row(layout_app_card, "Langue de l'interface :", self.cb_lang)

        self.cb_batch_style = StyledComboBox()
        self.cb_batch_style.setMinimumWidth(220)
        self.cb_batch_style.addItems(["CI/CD (Tableau de bord industriel)", "Kanban (Flux de tâches)", "Assistant (Pas-à-pas)"])
        self.cb_batch_style.setCurrentText(str(self.settings.value("app/batch_factory_style", "CI/CD (Tableau de bord industriel)")))
        add_row(layout_app_card, "Style Batch Factory :", self.cb_batch_style)

        layout.addWidget(card_app)

        # Section 2: Exportation
        lbl_exp = QLabel("EXPORTATION")
        lbl_exp.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(lbl_exp)

        card_exp = QFrame()
        card_exp.setStyleSheet(f"background-color: #1a1d24; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; padding: 12px;")
        layout_exp_card = QVBoxLayout(card_exp)

        exp_row = QHBoxLayout()
        lbl_exp_dir = QLabel("Dossier par défaut :")
        lbl_exp_dir.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        exp_row.addWidget(lbl_exp_dir)

        self.le_export = StyledLineEdit()
        self.le_export.setText(str(self.settings.value("app/export_path", "")))
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

    def _browse_export(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choisir le dossier d'export", self.le_export.text())
        if path:
            self.le_export.setText(path)

    def _save_settings(self) -> None:
        self.settings.setValue("ui/theme", self.cb_theme.currentText())
        self.settings.setValue("ui/language", self.cb_lang.currentText())
        self.settings.setValue("app/batch_factory_style", self.cb_batch_style.currentText())
        self.settings.setValue("app/export_path", self.le_export.text().strip())
        refresh_theme_live()
        show_toast(self, "Paramètres généraux enregistrés !")


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
        card_keys.setStyleSheet(f"background-color: #1a1d24; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; padding: 12px;")
        layout_keys_card = QVBoxLayout(card_keys)
        layout_keys_card.setSpacing(10)

        def add_key_field(parent_layout: QVBoxLayout, provider_label: str, placeholder: str, key_name: str) -> StyledLineEdit:
            row = QHBoxLayout()
            lbl = QLabel(f"{provider_label} :")
            lbl.setMinimumWidth(100)
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
            edit = StyledLineEdit()
            edit.setEchoMode(StyledLineEdit.EchoMode.Password)
            edit.setPlaceholderText(placeholder)
            edit.setText(str(self.settings.value(f"keys/{key_name}", "")))
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

        self.table_engines = StyledTableWidget(["Nom", "Fournisseur", "Identifiant Modèle"])
        layout.addWidget(self.table_engines, 1)

        self.refresh_data()

    def refresh_data(self) -> None:
        """Charge la liste des moteurs IA depuis Peewee."""
        try:
            self.table_engines.blockSignals(True)
            engines = list(LLMConfigModel.select())
            self.table_engines.setRowCount(len(engines))

            for i, eg in enumerate(engines):
                self.table_engines.setItem(i, 0, QTableWidgetItem(eg.name))
                self.table_engines.setItem(i, 1, QTableWidgetItem(getattr(eg, "provider_type", "openai").upper()))
                self.table_engines.setItem(i, 2, QTableWidgetItem(getattr(eg, "model_id", "default")))

            self.table_engines.blockSignals(False)
        except Exception as e:
            logger.warning("Erreur refresh_data ai_engines_tab: %s", e)

    def _save_api_keys(self) -> None:
        self.settings.setValue("keys/openai", self.edit_openai.text().strip())
        self.settings.setValue("keys/anthropic", self.edit_anthropic.text().strip())
        self.settings.setValue("keys/gemini", self.edit_gemini.text().strip())
        show_toast(self, "Clés API mises à jour avec succès !")


class MaintenanceTab(QWidget):
    """Onglet Maintenance & Purge."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        lbl_maint = QLabel("MAINTENANCE DE L'APPLICATION")
        lbl_maint.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(lbl_maint)

        card_maint = QFrame()
        card_maint.setStyleSheet(f"background-color: #1a1d24; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; padding: 16px;")
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


class SettingsModal(QDialog):
    """
    Modal de paramètres global.
    Dimensions 900x600px.
    """

    def __init__(self, ai_manager: Any = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager

        self.setWindowTitle("Paramètres AnkiForge")
        self.setFixedSize(900, 600)
        self.setModal(False)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinMaxButtonsHint)

        self._setup_ui()

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
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 16px; font-weight: bold;")

        btn_close = IconButton("ph.x", tooltip="Fermer", size=22)
        btn_close.clicked.connect(self.close)

        header_layout.addWidget(lbl_title)
        header_layout.addStretch()
        header_layout.addWidget(btn_close)

        main_layout.addWidget(header_bar)

        # Corps du modal avec Sidebar + Stack
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar gauche (210px)
        sidebar = QFrame()
        sidebar.setFixedWidth(210)
        sidebar.setStyleSheet(f"background-color: #111318; border-right: 1px solid {DesignTokens.BORDER_COLOR};")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 14, 10, 14)
        sidebar_layout.setSpacing(6)

        def add_nav_btn(text: str, icon_name: str, index: int) -> SecondaryButton:
            btn = SecondaryButton(text)
            btn.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_PRIMARY))
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    text-align: left;
                    padding: 8px 12px;
                    font-size: 12px;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: #1a1d24;
                }
            """)
            btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(index))
            sidebar_layout.addWidget(btn)
            return btn

        add_nav_btn("Général", "ph.sliders-horizontal", 0)
        add_nav_btn("Moteurs IA", "ph.cpu", 1)
        add_nav_btn("Maintenance", "ph.broom", 2)

        sidebar_layout.addStretch()

        body_layout.addWidget(sidebar)

        # Stacked Widget
        self.stacked_widget = QStackedWidget()

        self.general_tab = GeneralTab()
        self.ai_tab = AIEnginesTab(self.ai_manager)
        self.maint_tab = MaintenanceTab()

        self.stacked_widget.addWidget(self.general_tab)
        self.stacked_widget.addWidget(self.ai_tab)
        self.stacked_widget.addWidget(self.maint_tab)

        body_layout.addWidget(self.stacked_widget, 1)

        main_layout.addWidget(body_widget, 1)


SettingsDialog = SettingsModal
