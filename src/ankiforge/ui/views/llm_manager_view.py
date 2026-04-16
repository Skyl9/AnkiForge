import logging
from typing import Any

import qtawesome as qta
from PySide6.QtCore import Slot, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QMessageBox,
    QFormLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView,
    QHeaderView,
    QSpinBox,
    QSplitter,
    QFrame,
    QGraphicsDropShadowEffect,
    QSizePolicy,
)

from ankiforge.database.models import db, LLMConfigModel
from ankiforge.services.ai.flexible_service import OllamaProvider
from ankiforge.ui.components.components import HeaderLabel, ActionButton, PrimaryButton, DangerButton, RoundedPanel
from ankiforge.ui.widgets.toast import show_toast

logger = logging.getLogger(__name__)


class LLMManagerTab(QWidget):
    """
    Vue de gestion des moteurs d'Intelligence Artificielle.
    Permet de configurer les clés d'API (OpenAI, Anthropic, etc.) et
    de maintenir le catalogue des modèles LLM disponibles pour l'application.
    """

    def __init__(self, ai_manager: Any) -> None:
        """
        Initialise l'onglet de gestion des IA.

        Args:
            ai_manager (AIManager): Le gestionnaire central de l'IA de l'application.
        """
        super().__init__()
        self.ai_manager = ai_manager
        self.current_llm_id_editing: int | None = None

        self._setup_ui()
        self._connect_signals()

        # Chargement initial des données
        self.load_llms_table()
        self.on_provider_changed(self.cb_provider.currentText())

    def _setup_ui(self) -> None:
        """Initialise et organise les layouts et widgets principaux de la vue."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)

        title = HeaderLabel("Configuration de l'Intelligence Artificielle")
        self.main_layout.addWidget(title)

        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setHandleWidth(10)

        self._build_api_keys_panel()
        self._build_catalog_panel()

        self.main_splitter.setSizes([200, 600])
        self.main_layout.addWidget(self.main_splitter)

    def _build_api_keys_panel(self) -> None:
        """Construit le panneau de saisie des clés d'authentification API."""
        api_panel = RoundedPanel()

        # Effet d'ombre portée pour détacher le panneau
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 4)
        api_panel.setGraphicsEffect(shadow)

        api_layout = QVBoxLayout(api_panel)
        api_layout.setContentsMargins(15, 15, 15, 15)

        lbl_api = QLabel("1. CLÉS D'AUTHENTIFICATION API")
        lbl_api.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px")
        lbl_api.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        api_layout.addWidget(lbl_api)

        form_api = QFormLayout()
        form_api.setHorizontalSpacing(20)

        # RÉCUPÉRATION DES CLÉS DEPUIS LA BDD
        def get_key_for(provider: str) -> str:
            llm = LLMConfigModel.get_or_none(LLMConfigModel.provider == provider)
            return llm.api_key if llm and llm.api_key else ""

        self.le_openai_key = QLineEdit(get_key_for("openai"))
        self.le_openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.le_openai_key.setPlaceholderText("sk-...")
        self.le_openai_key.setMaximumWidth(450)
        form_api.addRow(self._make_bold_label("Clé OpenAI :"), self.le_openai_key)

        self.le_anthropic_key = QLineEdit(get_key_for("anthropic"))
        self.le_anthropic_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.le_anthropic_key.setPlaceholderText("sk-ant-...")
        self.le_anthropic_key.setMaximumWidth(450)
        form_api.addRow(self._make_bold_label("Clé Anthropic :"), self.le_anthropic_key)

        self.le_gemini_key = QLineEdit(get_key_for("gemini"))
        self.le_gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.le_gemini_key.setMaximumWidth(450)
        form_api.addRow(self._make_bold_label("Clé Gemini :"), self.le_gemini_key)

        self.le_groq_key = QLineEdit(get_key_for("groq"))
        self.le_groq_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.le_groq_key.setMaximumWidth(450)
        form_api.addRow(self._make_bold_label("Clé Groq :"), self.le_groq_key)

        api_layout.addLayout(form_api)

        btn_api_layout = QHBoxLayout()
        btn_api_layout.addStretch()

        self.btn_save_keys = PrimaryButton(qta.icon("fa5s.save", color="white"), " Mettre à jour les clés API")

        btn_api_layout.addWidget(self.btn_save_keys)
        btn_api_layout.addStretch()
        api_layout.addLayout(btn_api_layout)

        self.main_splitter.addWidget(api_panel)

    def _build_catalog_panel(self) -> None:
        """Construit le panneau inférieur scindé (Tableau des modèles et Éditeur)."""
        self.llm_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.llm_splitter.setHandleWidth(10)
        self.llm_splitter.setChildrenCollapsible(False)

        # Panneau Gauche : Le Tableau
        table_panel = RoundedPanel()
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(15, 15, 15, 15)

        lbl_table = QLabel("2. CATALOGUE DES MODÈLES")
        lbl_table.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 5px;")
        table_layout.addWidget(lbl_table)

        self.table_llms = QTableWidget()
        self.table_llms.setFrameShape(QFrame.Shape.NoFrame)
        self.table_llms.setColumnCount(4)
        self.table_llms.setHorizontalHeaderLabels(["Nom d'affichage", "Fournisseur", "Modèle", "Tokens Max"])
        self.table_llms.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_llms.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_llms.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_llms.setAlternatingRowColors(True)
        table_layout.addWidget(self.table_llms)

        table_panel.setMinimumWidth(150)
        self.llm_splitter.addWidget(table_panel)

        # Panneau Droit : L'Éditeur
        editor_panel = RoundedPanel()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(15, 15, 15, 15)

        self.lbl_edit = QLabel("AJOUTER / MODIFIER UN MODÈLE")
        self.lbl_edit.setStyleSheet("font-weight: bold; color: palette(highlight); font-size: 11px; letter-spacing: 1px; margin-bottom: 15px;")
        editor_layout.addWidget(self.lbl_edit)

        form_editor = QFormLayout()
        form_editor.setHorizontalSpacing(15)

        self.le_display_name = QLineEdit()
        self.le_display_name.setPlaceholderText("Ex: GPT-4o (Rapide)")
        self.le_display_name.setMinimumWidth(80)
        form_editor.addRow(self._make_bold_label("Nom d'affichage :"), self.le_display_name)

        self.cb_provider = QComboBox()
        self.cb_provider.setMinimumWidth(80)
        self.cb_provider.addItems(["openai", "anthropic", "ollama", "groq", "gemini"])
        form_editor.addRow(self._make_bold_label("Fournisseur :"), self.cb_provider)

        model_id_layout = QHBoxLayout()
        self.cb_model_id = QComboBox()
        self.cb_model_id.setMinimumWidth(80)
        self.cb_model_id.setEditable(True)
        self.cb_model_id.setPlaceholderText("Ex: gpt-4o")

        self.btn_refresh_ollama = ActionButton("fa5s.sync", "")
        self.btn_refresh_ollama.setToolTip("Rafraîchir les modèles locaux")
        self.btn_refresh_ollama.hide()

        model_id_layout.addWidget(self.cb_model_id, stretch=1)
        model_id_layout.addWidget(self.btn_refresh_ollama)
        form_editor.addRow(self._make_bold_label("ID du Modèle :"), model_id_layout)

        self.spin_context = QSpinBox()
        self.spin_context.setRange(1000, 2000000)
        self.spin_context.setSingleStep(1000)
        self.spin_context.setValue(8192)
        form_editor.addRow(self._make_bold_label("Limite de Tokens :"), self.spin_context)

        editor_layout.addLayout(form_editor)
        editor_layout.addStretch()

        # Boutons d'action du modèle
        action_layout = QHBoxLayout()
        self.btn_clear_form = ActionButton("fa5s.plus", " Nouveau")
        self.btn_delete_llm = DangerButton(qta.icon("fa5s.trash", color="white"), " Supprimer")
        self.btn_delete_llm.setEnabled(False)
        self.btn_save_llm = PrimaryButton(qta.icon("fa5s.save", color="white"), " Ajouter")

        action_layout.addWidget(self.btn_clear_form)
        action_layout.addStretch()
        action_layout.addWidget(self.btn_delete_llm)
        action_layout.addWidget(self.btn_save_llm)

        editor_layout.addLayout(action_layout)
        editor_panel.setMinimumWidth(200)
        self.llm_splitter.addWidget(editor_panel)

        self.llm_splitter.setSizes([500, 300])
        self.main_splitter.addWidget(self.llm_splitter)

    def _connect_signals(self) -> None:
        """Centralise le branchement des signaux de l'interface."""
        self.btn_save_keys.clicked.connect(self.save_api_keys)
        self.table_llms.itemSelectionChanged.connect(self.on_table_selection_changed)
        self.cb_provider.currentTextChanged.connect(self.on_provider_changed)
        self.btn_refresh_ollama.clicked.connect(self.refresh_ollama_models)
        self.btn_clear_form.clicked.connect(self.clear_llm_form)
        self.btn_delete_llm.clicked.connect(self.delete_llm_config)
        self.btn_save_llm.clicked.connect(self.save_llm_config)

    @Slot()
    def refresh_data(self) -> None:
        self.load_llms_table()

    @Slot()
    def save_api_keys(self) -> None:
        keys_map = {
            "openai": self.le_openai_key.text().strip(),
            "anthropic": self.le_anthropic_key.text().strip(),
            "gemini": self.le_gemini_key.text().strip(),
            "groq": self.le_groq_key.text().strip(),
        }

        try:
            with db.atomic():
                for provider, key in keys_map.items():
                    LLMConfigModel.update(api_key=key).where(LLMConfigModel.provider == provider).execute()

            self.ai_manager.reload_provider()
            logger.info("Clés API sauvegardées en base de données et moteurs rechargés.")
            show_toast(self, "Clés API sauvegardées en BDD !")
        except Exception as e:
            logger.exception("Erreur lors de la sauvegarde des clés API :")
            show_toast(self, f"Erreur lors de la sauvegarde : {e}", is_error=True)

    def load_llms_table(self) -> None:
        self.table_llms.blockSignals(True)
        self.table_llms.setRowCount(0)

        for row_idx, llm in enumerate(LLMConfigModel.select().order_by(LLMConfigModel.provider, LLMConfigModel.display_name)):
            self.table_llms.insertRow(row_idx)
            item_name = QTableWidgetItem(llm.display_name)
            item_name.setData(Qt.ItemDataRole.UserRole, llm.id)
            self.table_llms.setItem(row_idx, 0, item_name)
            self.table_llms.setItem(row_idx, 1, QTableWidgetItem(llm.provider))
            self.table_llms.setItem(row_idx, 2, QTableWidgetItem(llm.model_id))
            self.table_llms.setItem(row_idx, 3, QTableWidgetItem(f"{llm.context_limit:,}".replace(",", " ")))

        self.table_llms.blockSignals(False)

    @Slot()
    def on_table_selection_changed(self) -> None:
        selected_items = self.table_llms.selectedItems()
        if not selected_items:
            self.clear_llm_form()
            return

        llm_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
        llm = LLMConfigModel.get_by_id(llm_id)

        self.current_llm_id_editing = llm.id
        self.lbl_edit.setText(f"✏️ MODIFIER LE MODÈLE : {llm.display_name.upper()}")
        self.lbl_edit.setStyleSheet("font-weight: bold; color: #FF9800; font-size: 11px; letter-spacing: 1px; margin-bottom: 15px;")
        self.le_display_name.setText(llm.display_name)
        self.cb_provider.setCurrentText(llm.provider)
        self.cb_model_id.setCurrentText(llm.model_id)
        self.spin_context.setValue(llm.context_limit)

        self.btn_delete_llm.setEnabled(True)
        self.btn_save_llm.setText(" Mettre à jour")

    @Slot()
    def clear_llm_form(self) -> None:
        self.table_llms.clearSelection()
        self.current_llm_id_editing = None
        self.lbl_edit.setText("AJOUTER UN NOUVEAU MODÈLE")
        self.lbl_edit.setStyleSheet("font-weight: bold; color: palette(highlight); font-size: 11px; letter-spacing: 1px; margin-bottom: 15px;")
        self.le_display_name.clear()
        self.cb_model_id.clear()
        self.spin_context.setValue(8192)
        self.btn_delete_llm.setEnabled(False)
        self.btn_save_llm.setText(" Ajouter")

    @Slot(str)
    def on_provider_changed(self, provider_name: str) -> None:
        self.cb_model_id.clear()
        if provider_name == "ollama":
            self.btn_refresh_ollama.show()
            self.refresh_ollama_models()
        else:
            self.btn_refresh_ollama.hide()
            if provider_name == "openai":
                self.cb_model_id.addItems(["gpt-4o", "gpt-4o-mini", "o1-preview"])
            elif provider_name == "anthropic":
                self.cb_model_id.addItems(["claude-3-5-sonnet-20240620", "claude-3-haiku-20240307"])
            elif provider_name == "gemini":
                self.cb_model_id.addItems(["gemini-2.5-flash", "gemini-1.5-pro"])
            elif provider_name == "groq":
                self.cb_model_id.addItems(["llama3-8b-8192", "mixtral-8x7b-32768"])

    @Slot()
    def refresh_ollama_models(self) -> None:
        self.btn_refresh_ollama.setEnabled(False)
        models = OllamaProvider.get_available_models()
        self.cb_model_id.clear()
        if models:
            self.cb_model_id.addItems(models)
        self.btn_refresh_ollama.setEnabled(True)

    @Slot()
    def save_llm_config(self) -> None:
        name = self.le_display_name.text().strip()
        provider = self.cb_provider.currentText()
        model_id = self.cb_model_id.currentText().strip()
        context = self.spin_context.value()

        if not name or not model_id:
            logger.warning("Tentative de sauvegarde d'un modèle sans nom ou ID.")
            show_toast(self, "Le nom d'affichage et l'ID du modèle sont obligatoires.", is_error=True)
            return

        try:
            with db.atomic():
                if self.current_llm_id_editing:
                    llm = LLMConfigModel.get_by_id(self.current_llm_id_editing)
                    llm.display_name = name
                    llm.provider = provider
                    llm.model_id = model_id
                    llm.context_limit = context
                    llm.save()
                    logger.info(f"Moteur mis à jour : {name}")
                    show_toast(self, "Moteur mis à jour !")
                else:
                    LLMConfigModel.create(display_name=name, provider=provider, model_id=model_id, context_limit=context)
                    logger.info(f"Nouveau moteur ajouté : {name}")
                    show_toast(self, "Nouveau moteur ajouté !")

            self.load_llms_table()
            self.clear_llm_form()

        except Exception as e:
            logger.exception(f"Erreur lors de la sauvegarde du moteur '{name}' :")
            if "UNIQUE constraint" in str(e):
                show_toast(self, "Ce nom d'affichage existe déjà.", is_error=True)
            else:
                show_toast(self, f"Erreur BDD : {str(e)}", is_error=True)

    @Slot()
    def delete_llm_config(self) -> None:
        if not self.current_llm_id_editing:
            return

        reply = QMessageBox.question(
            self,
            "Confirmation",
            "Supprimer définitivement ce moteur IA de la base ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                with db.atomic():
                    LLMConfigModel.delete_by_id(self.current_llm_id_editing)
                self.load_llms_table()
                self.clear_llm_form()
                logger.info("Moteur supprimé de la base.")
                show_toast(self, "Moteur supprimé.")
            except Exception as e:
                logger.exception("Impossible de supprimer le moteur :")
                QMessageBox.critical(self, "Erreur BDD", f"Impossible de supprimer : {e}")

    @staticmethod
    def _make_bold_label(text: str) -> QLabel:
        """Utilitaire pour formater les labels des formulaires."""
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; color: palette(text); font-size: 11px;")
        return lbl
