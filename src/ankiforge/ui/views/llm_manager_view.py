import os

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QLineEdit,
                               QComboBox, QMessageBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QSpinBox, QSplitter)
from dotenv import set_key
import qtawesome as qta
from PySide6.QtCore import Slot, Qt

from ankiforge.database.models import db, LLMConfigModel
from ankiforge.services.ai.flexible_service import OllamaProvider
from ankiforge.ui.components.components import HeaderLabel, ActionButton, PrimaryButton, DangerButton
from ankiforge.ui.widgets.toast import show_toast


class LLMManagerTab(QWidget):
    def __init__(self, ai_manager) -> None:
        super().__init__()
        self.ai_manager = ai_manager
        self.current_llm_id_editing = None

        layout = QVBoxLayout(self)
        title = HeaderLabel("Configuration de l'Intelligence Artificielle")
        layout.addWidget(title)

        main_splitter = QSplitter(Qt.Orientation.Vertical)

        # ==========================================
        # SECTION 1 : CLÉS API (Fichier .env)
        # ==========================================
        api_group = QGroupBox("1. Clés d'authentification API")
        api_layout = QFormLayout(api_group)

        self.le_openai_key = QLineEdit(os.getenv("OPENAI_API_KEY", ""))
        self.le_openai_key.setEchoMode(QLineEdit.Password)
        self.le_openai_key.setPlaceholderText("sk-...")
        # ActionButton automatically adapts icon color to text color in light/dark mode
        api_layout.addRow("Clé OpenAI :", self.le_openai_key)

        self.le_anthropic_key = QLineEdit(os.getenv("ANTHROPIC_API_KEY", ""))
        self.le_anthropic_key.setEchoMode(QLineEdit.Password)
        self.le_anthropic_key.setPlaceholderText("sk-ant-...")
        api_layout.addRow(f"Clé Anthropic :", self.le_anthropic_key)

        self.le_gemini_key = QLineEdit(os.getenv("GEMINI_API_KEY", ""))
        self.le_gemini_key.setEchoMode(QLineEdit.Password)
        api_layout.addRow(f"Clé Gemini :", self.le_gemini_key)

        self.le_groq_key = QLineEdit(os.getenv("GROQ_API_KEY", ""))
        self.le_groq_key.setEchoMode(QLineEdit.Password)
        api_layout.addRow(f"Clé Groq :", self.le_groq_key)

        self.btn_save_keys = PrimaryButton(qta.icon('fa5s.save', color='white'), " Mettre à jour les clés API")
        self.btn_save_keys.clicked.connect(self.save_api_keys)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save_keys)
        api_layout.addRow("", btn_layout)

        main_splitter.addWidget(api_group)

        # ==========================================
        # SECTION 2 : MOTEURS IA (Base de données)
        # ==========================================
        llm_group = QGroupBox("2. Catalogue des Modèles")
        llm_layout = QVBoxLayout(llm_group)

        llm_splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Panneau Gauche : La Table ---
        self.table_llms = QTableWidget()
        self.table_llms.setColumnCount(4)
        self.table_llms.setHorizontalHeaderLabels(["Nom d'affichage", "Fournisseur", "Modèle", "Tokens Max"])
        self.table_llms.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_llms.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_llms.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_llms.setAlternatingRowColors(True) # Added for better UX
        self.table_llms.itemSelectionChanged.connect(self.on_table_selection_changed)
        llm_splitter.addWidget(self.table_llms)

        # --- Panneau Droit : L'Éditeur ---
        editor_widget = QWidget()
        editor_layout = QFormLayout(editor_widget)

        self.le_display_name = QLineEdit()
        self.le_display_name.setPlaceholderText("Ex: GPT-4o (Rapide)")
        editor_layout.addRow("Nom d'affichage :", self.le_display_name)

        self.cb_provider = QComboBox()
        self.cb_provider.addItems(["openai", "anthropic", "ollama", "groq", "gemini"])
        self.cb_provider.currentTextChanged.connect(self.on_provider_changed)
        editor_layout.addRow("Fournisseur :", self.cb_provider)

        model_id_layout = QHBoxLayout()
        self.cb_model_id = QComboBox()
        self.cb_model_id.setEditable(True)
        self.cb_model_id.setPlaceholderText("Ex: gpt-4o")

        self.btn_refresh_ollama = ActionButton('fa5s.sync', "")
        self.btn_refresh_ollama.setToolTip("Rafraîchir les modèles locaux")
        self.btn_refresh_ollama.clicked.connect(self.refresh_ollama_models)
        self.btn_refresh_ollama.hide()

        model_id_layout.addWidget(self.cb_model_id, stretch=1)
        model_id_layout.addWidget(self.btn_refresh_ollama)
        editor_layout.addRow("ID du Modèle :", model_id_layout)

        self.spin_context = QSpinBox()
        self.spin_context.setRange(1000, 2000000)
        self.spin_context.setSingleStep(1000)
        self.spin_context.setValue(8192)
        editor_layout.addRow("Limite de Tokens :", self.spin_context)

        action_layout = QHBoxLayout()
        self.btn_save_llm = PrimaryButton(qta.icon('fa5s.save', color='white'), " Ajouter")
        self.btn_save_llm.clicked.connect(self.save_llm_config)

        self.btn_delete_llm = DangerButton(qta.icon('fa5s.trash', color='white'), " Supprimer")
        self.btn_delete_llm.clicked.connect(self.delete_llm_config)
        self.btn_delete_llm.setEnabled(False)

        self.btn_clear_form = ActionButton('fa5s.plus', " Nouveau")
        self.btn_clear_form.clicked.connect(self.clear_llm_form)

        action_layout.addWidget(self.btn_clear_form)
        action_layout.addWidget(self.btn_save_llm)
        action_layout.addWidget(self.btn_delete_llm)
        editor_layout.addRow("", action_layout)

        llm_splitter.addWidget(editor_widget)
        llm_splitter.setSizes([450, 350])

        llm_layout.addWidget(llm_splitter)
        main_splitter.addWidget(llm_group)

        main_splitter.setSizes([150, 650])
        layout.addWidget(main_splitter)

        self.load_llms_table()
        self.on_provider_changed(self.cb_provider.currentText())

    @Slot()
    def refresh_data(self) -> None:
        self.load_llms_table()

    @Slot()
    def save_api_keys(self) -> None:
        env_path_str = str(self.ai_manager.env_path)
        set_key(env_path_str, "OPENAI_API_KEY", self.le_openai_key.text().strip())
        set_key(env_path_str, "ANTHROPIC_API_KEY", self.le_anthropic_key.text().strip())
        set_key(env_path_str, "GEMINI_API_KEY", self.le_gemini_key.text().strip())
        set_key(env_path_str, "GROQ_API_KEY", self.le_groq_key.text().strip())

        self.ai_manager.reload_provider()
        show_toast(self, "Clés API sauvegardées et rechargées !")

    def load_llms_table(self) -> None:
        self.table_llms.blockSignals(True)
        self.table_llms.setRowCount(0)

        for row_idx, llm in enumerate(
                LLMConfigModel.select().order_by(LLMConfigModel.provider, LLMConfigModel.display_name)):
            self.table_llms.insertRow(row_idx)
            item_name = QTableWidgetItem(llm.display_name)
            item_name.setData(Qt.UserRole, llm.id)
            self.table_llms.setItem(row_idx, 0, item_name)
            self.table_llms.setItem(row_idx, 1, QTableWidgetItem(llm.provider))
            self.table_llms.setItem(row_idx, 2, QTableWidgetItem(llm.model_id))
            self.table_llms.setItem(row_idx, 3, QTableWidgetItem(f"{llm.context_limit:,}".replace(',', ' ')))

        self.table_llms.blockSignals(False)

    @Slot()
    def on_table_selection_changed(self) -> None:
        selected_items = self.table_llms.selectedItems()
        if not selected_items:
            self.clear_llm_form()
            return

        llm_id = selected_items[0].data(Qt.UserRole)
        llm = LLMConfigModel.get_by_id(llm_id)

        self.current_llm_id_editing = llm.id
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
            QMessageBox.warning(self, "Erreur", "Le nom d'affichage et l'ID du modèle sont obligatoires.")
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
                    show_toast(self, "Moteur mis à jour !")
                else:
                    LLMConfigModel.create(
                        display_name=name, provider=provider,
                        model_id=model_id, context_limit=context
                    )
                    show_toast(self, "Nouveau moteur ajouté !")

            self.load_llms_table()
            self.clear_llm_form()

        except Exception as e:
            if "UNIQUE constraint" in str(e):
                QMessageBox.critical(self, "Erreur", "Ce nom d'affichage existe déjà. Veuillez en choisir un autre.")
            else:
                QMessageBox.critical(self, "Erreur BDD", str(e))

    @Slot()
    def delete_llm_config(self) -> None:
        if not self.current_llm_id_editing: return

        reply = QMessageBox.question(self, "Confirmation", "Supprimer définitivement ce moteur IA de la base ?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            try:
                with db.atomic():
                    LLMConfigModel.delete_by_id(self.current_llm_id_editing)
                self.load_llms_table()
                self.clear_llm_form()
                show_toast(self, "Moteur supprimé.")
            except Exception as e:
                QMessageBox.critical(self, "Erreur BDD", f"Impossible de supprimer : {e}")