import logging
from typing import Any

import qtawesome as qta
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import LLMConfigModel, db
from ankiforge.services.ai.flexible_service import OllamaProvider
from ankiforge.ui.components.components import ActionButton, DangerButton, HeaderLabel, PrimaryButton, RoundedPanel
from ankiforge.ui.widgets.toast import show_toast

logger = logging.getLogger(__name__)


class LLMManagerTab(QWidget):
    """
    Artificial Intelligence engine management view.
    Allows configuring API keys (OpenAI, Anthropic, etc.) and
    maintaining the catalog of LLM models available for the application.
    """

    def __init__(self, ai_manager: Any) -> None:
        """
        Initializes the AI management tab.

        Args:
            ai_manager (AIManager): The application's central AI manager.
        """
        super().__init__()
        self.ai_manager = ai_manager
        self.current_llm_id_editing: int | None = None

        self._setup_ui()
        self._connect_signals()

        # Initial data loading
        self.load_llms_table()
        self.on_provider_changed(self.cb_provider.currentText())

    def _setup_ui(self) -> None:
        """Initializes and organizes the main layouts and widgets of the view."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)

        title = HeaderLabel(self.tr("AI Configuration"))
        self.main_layout.addWidget(title)

        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setHandleWidth(10)

        self._build_api_keys_panel()
        self._build_catalog_panel()

        self.main_splitter.setSizes([200, 600])
        self.main_layout.addWidget(self.main_splitter)

    def _build_api_keys_panel(self) -> None:
        """Builds the API authentication keys input panel."""
        api_panel = RoundedPanel()

        # Drop shadow effect to detach the panel
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 4)
        api_panel.setGraphicsEffect(shadow)

        api_layout = QVBoxLayout(api_panel)
        api_layout.setContentsMargins(15, 15, 15, 15)

        lbl_api = QLabel(self.tr("1. API AUTHENTICATION KEYS"))
        lbl_api.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px")
        lbl_api.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        api_layout.addWidget(lbl_api)

        form_api = QFormLayout()
        form_api.setHorizontalSpacing(20)

        # RETRIEVING KEYS FROM DB
        def get_key_for(provider: str) -> str:
            llm = LLMConfigModel.get_or_none(LLMConfigModel.provider == provider)
            return llm.api_key if llm and llm.api_key else ""

        self.le_openai_key = QLineEdit(get_key_for("openai"))
        self.le_openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.le_openai_key.setPlaceholderText("sk-...")
        self.le_openai_key.setMaximumWidth(450)
        form_api.addRow(self._make_bold_label(self.tr("OpenAI Key :")), self.le_openai_key)

        self.le_anthropic_key = QLineEdit(get_key_for("anthropic"))
        self.le_anthropic_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.le_anthropic_key.setPlaceholderText("sk-ant-...")
        self.le_anthropic_key.setMaximumWidth(450)
        form_api.addRow(self._make_bold_label(self.tr("Anthropic Key :")), self.le_anthropic_key)

        self.le_gemini_key = QLineEdit(get_key_for("gemini"))
        self.le_gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.le_gemini_key.setMaximumWidth(450)
        form_api.addRow(self._make_bold_label(self.tr("Gemini Key :")), self.le_gemini_key)

        self.le_groq_key = QLineEdit(get_key_for("groq"))
        self.le_groq_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.le_groq_key.setMaximumWidth(450)
        form_api.addRow(self._make_bold_label(self.tr("Groq Key :")), self.le_groq_key)

        api_layout.addLayout(form_api)

        btn_api_layout = QHBoxLayout()
        btn_api_layout.addStretch()

        self.btn_save_keys = PrimaryButton(qta.icon("fa5s.save", color="white"), self.tr(" Update API Keys"))

        btn_api_layout.addWidget(self.btn_save_keys)
        btn_api_layout.addStretch()
        api_layout.addLayout(btn_api_layout)

        self.main_splitter.addWidget(api_panel)

    def _build_catalog_panel(self) -> None:
        """Builds the split bottom panel (Model table and Editor)."""
        self.llm_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.llm_splitter.setHandleWidth(10)
        self.llm_splitter.setChildrenCollapsible(False)

        # Left Panel: The Table
        table_panel = RoundedPanel()
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(15, 15, 15, 15)

        lbl_table = QLabel(self.tr("2. MODEL CATALOG"))
        lbl_table.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 5px;")
        table_layout.addWidget(lbl_table)

        self.table_llms = QTableWidget()
        self.table_llms.setFrameShape(QFrame.Shape.NoFrame)
        self.table_llms.setColumnCount(4)
        self.table_llms.setHorizontalHeaderLabels([self.tr("Display Name"), self.tr("Provider"), self.tr("Model"), self.tr("Max Tokens")])
        self.table_llms.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_llms.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_llms.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_llms.setAlternatingRowColors(True)
        table_layout.addWidget(self.table_llms)

        table_panel.setMinimumWidth(150)
        self.llm_splitter.addWidget(table_panel)

        # Right Panel: The Editor
        editor_panel = RoundedPanel()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(15, 15, 15, 15)

        self.lbl_edit = QLabel(self.tr("ADD / MODIFY A MODEL"))
        self.lbl_edit.setStyleSheet("font-weight: bold; color: palette(highlight); font-size: 11px; letter-spacing: 1px; margin-bottom: 15px;")
        editor_layout.addWidget(self.lbl_edit)

        form_editor = QFormLayout()
        form_editor.setHorizontalSpacing(15)

        self.le_display_name = QLineEdit()
        self.le_display_name.setPlaceholderText(self.tr("Ex: GPT-4o (Fast)"))
        self.le_display_name.setMinimumWidth(80)
        form_editor.addRow(self._make_bold_label(self.tr("Display Name :")), self.le_display_name)

        self.cb_provider = QComboBox()
        self.cb_provider.setMinimumWidth(80)
        self.cb_provider.addItems(["openai", "anthropic", "ollama", "groq", "gemini"])
        form_editor.addRow(self._make_bold_label(self.tr("Provider :")), self.cb_provider)

        model_id_layout = QHBoxLayout()
        self.cb_model_id = QComboBox()
        self.cb_model_id.setMinimumWidth(80)
        self.cb_model_id.setEditable(True)
        self.cb_model_id.setPlaceholderText("Ex: gpt-4o")

        self.btn_refresh_ollama = ActionButton("fa5s.sync", "")
        self.btn_refresh_ollama.setToolTip(self.tr("Refresh local models"))
        self.btn_refresh_ollama.hide()

        model_id_layout.addWidget(self.cb_model_id, stretch=1)
        model_id_layout.addWidget(self.btn_refresh_ollama)
        form_editor.addRow(self._make_bold_label(self.tr("Model ID :")), model_id_layout)

        self.spin_context = QSpinBox()
        self.spin_context.setRange(1000, 2000000)
        self.spin_context.setSingleStep(1000)
        self.spin_context.setValue(8192)
        form_editor.addRow(self._make_bold_label(self.tr("Token Limit :")), self.spin_context)

        editor_layout.addLayout(form_editor)
        editor_layout.addStretch()

        # Model action buttons
        action_layout = QHBoxLayout()
        self.btn_clear_form = ActionButton("fa5s.plus", self.tr(" New"))
        self.btn_delete_llm = DangerButton(qta.icon("fa5s.trash", color="white"), self.tr(" Delete"))
        self.btn_delete_llm.setEnabled(False)
        self.btn_save_llm = PrimaryButton(qta.icon("fa5s.save", color="white"), self.tr(" Add"))

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
        """Centralizes signal connections."""
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
            logger.info("API keys saved in database and engines reloaded.")
            show_toast(self, self.tr("API keys saved in DB!"))
        except Exception as e:
            logger.exception("Error while saving API keys")
            show_toast(self, self.tr("Error during save: {0}").format(str(e)), is_error=True)

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
        self.lbl_edit.setText(self.tr("EDIT MODEL : {0}").format(llm.display_name.upper()))
        self.lbl_edit.setStyleSheet("font-weight: bold; color: #FF9800; font-size: 11px; letter-spacing: 1px; margin-bottom: 15px;")
        self.le_display_name.setText(llm.display_name)
        self.cb_provider.setCurrentText(llm.provider)
        self.cb_model_id.setCurrentText(llm.model_id)
        self.spin_context.setValue(llm.context_limit)

        self.btn_delete_llm.setEnabled(True)
        self.btn_save_llm.setText(self.tr(" Update"))

    @Slot()
    def clear_llm_form(self) -> None:
        self.table_llms.clearSelection()
        self.current_llm_id_editing = None
        self.lbl_edit.setText(self.tr("ADD A NEW MODEL"))
        self.lbl_edit.setStyleSheet("font-weight: bold; color: palette(highlight); font-size: 11px; letter-spacing: 1px; margin-bottom: 15px;")
        self.le_display_name.clear()
        self.cb_model_id.clear()
        self.spin_context.setValue(8192)
        self.btn_delete_llm.setEnabled(False)
        self.btn_save_llm.setText(self.tr(" Add"))

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
            logger.warning("Attempted save without name or model ID")
            show_toast(self, self.tr("Display name and model ID are required."), is_error=True)
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
                    logger.info(f"Engine updated: {name}")
                    show_toast(self, self.tr("Engine updated!"))
                else:
                    LLMConfigModel.create(display_name=name, provider=provider, model_id=model_id, context_limit=context)
                    logger.info(f"New engine added: {name}")
                    show_toast(self, self.tr("New engine added!"))

            self.load_llms_table()
            self.clear_llm_form()

        except Exception as e:
            logger.exception(f"Error while saving engine '{name}'")
            if "UNIQUE constraint" in str(e):
                show_toast(self, self.tr("This display name already exists."), is_error=True)
            else:
                show_toast(self, self.tr("DB Error: {0}").format(str(e)), is_error=True)

    @Slot()
    def delete_llm_config(self) -> None:
        if not self.current_llm_id_editing:
            return

        reply = QMessageBox.question(
            self,
            self.tr("Confirmation"),
            self.tr("Confirm permanently delete this AI engine from the database?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                with db.atomic():
                    LLMConfigModel.delete_by_id(self.current_llm_id_editing)
                self.load_llms_table()
                self.clear_llm_form()
                logger.info("Engine deleted from DB.")
                show_toast(self, self.tr("Engine deleted."))
            except Exception as e:
                logger.exception("Unable to delete engine")
                QMessageBox.critical(self, self.tr("Database Error"), self.tr("Unable to delete: {0}").format(str(e)))

    @staticmethod
    def _make_bold_label(text: str) -> QLabel:
        """Utilitaire pour formater les labels des formulaires."""
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; color: palette(text); font-size: 11px;")
        return lbl
