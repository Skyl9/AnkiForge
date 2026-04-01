import os

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QLineEdit,
                               QPushButton, QComboBox, QMessageBox, QFormLayout, QGroupBox, QHBoxLayout)
from dotenv import set_key
import qtawesome as qta
from PySide6.QtCore import Slot

from src.ui.widgets.toast import show_toast


class SettingsTab(QWidget):
    def __init__(self, ai_manager) -> None:
        super().__init__()
        self.ai_manager = ai_manager

        layout = QVBoxLayout(self)

        title = QLabel("<h2>Paramètres de l'Intelligence Artificielle</h2>")
        title.setStyleSheet("margin-bottom: 20px;")
        layout.addWidget(title)

        # Groupe de paramètres IA
        ai_group = QGroupBox("Configuration du Moteur IA")
        form_layout = QFormLayout(ai_group)

        # Choix du service
        self.cb_provider = QComboBox()
        self.cb_provider.addItems(["Ollama", "Gemini", "Groq"])
        current_provider = os.getenv("AI_PROVIDER", "Ollama")
        self.cb_provider.setCurrentText(current_provider)
        form_layout.addRow("Service IA :", self.cb_provider)

        # 👇 ZONE MODIFIÉE POUR LE MODÈLE 👇
        self.cb_model = QComboBox()
        self.cb_model.setEditable(True)  # Permet à l'utilisateur de taper du texte libre
        self.cb_model.setCurrentText(os.getenv("AI_MODEL", "qwen2.5:7b"))

        self.btn_refresh_models = QPushButton(qta.icon('fa5s.sync'), " Actualiser")
        self.btn_refresh_models.clicked.connect(self.refresh_models_list)

        model_layout = QHBoxLayout()
        model_layout.addWidget(self.cb_model, stretch=1)
        model_layout.addWidget(self.btn_refresh_models)

        form_layout.addRow("Nom du Modèle :", model_layout)

        # Connexion pour changer les modèles dispo selon le provider
        self.cb_provider.currentTextChanged.connect(self.on_provider_changed)
        # 👆 FIN DE LA ZONE MODIFIÉE 👆
        # Clé API Gemini
        self.le_gemini_key = QLineEdit()
        self.le_gemini_key.setText(os.getenv("GEMINI_API_KEY", ""))
        self.le_gemini_key.setEchoMode(QLineEdit.Password)  # Masque la clé
        self.le_gemini_key.setPlaceholderText("Obligatoire uniquement pour Gemini")
        form_layout.addRow("Clé API Gemini :", self.le_gemini_key)

        # Clé API Groq
        self.le_groq_key = QLineEdit()
        self.le_groq_key.setText(os.getenv("GROQ_API_KEY", ""))
        self.le_groq_key.setEchoMode(QLineEdit.Password)
        self.le_groq_key.setPlaceholderText("Obligatoire uniquement pour Groq")
        form_layout.addRow("Clé API Groq :", self.le_groq_key)

        layout.addWidget(ai_group)

        # Bouton de sauvegarde
        self.btn_save = QPushButton(qta.icon('fa5s.save', color='white'), " Sauvegarder et Reconnecter l'IA")
        self.btn_save.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        self.btn_save.clicked.connect(self.save_settings)
        layout.addWidget(self.btn_save)

        layout.addStretch()

        # 👇 NOUVELLES MÉTHODES À AJOUTER À LA CLASSE 👇
    @Slot(str)
    def on_provider_changed(self, provider_name: str) -> None:
        """Adapte l'interface quand on change de fournisseur."""
        current_text = self.cb_model.currentText()
        self.cb_model.clear()

        if provider_name == "Ollama":
            self.btn_refresh_models.show()
            self.refresh_models_list()
        else:
            self.btn_refresh_models.hide()
            # Suggestions par défaut pour le cloud
            if provider_name == "Gemini":
                self.cb_model.addItems(["gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"])
            elif provider_name == "Groq":
                self.cb_model.addItems(["llama3-8b-8192", "mixtral-8x7b-32768", "gemma2-9b-it"])

            # On remet le texte que l'utilisateur avait tapé, s'il y en avait un
            if current_text:
                self.cb_model.setCurrentText(current_text)
    @Slot()
    def refresh_models_list(self) -> None:
        """Va chercher les modèles Ollama en local."""
        if self.cb_provider.currentText() != "Ollama":
            return

        self.btn_refresh_models.setText("⏳...")
        self.btn_refresh_models.setEnabled(False)

        from src.services.ai.flexible_service import OllamaProvider
        models = OllamaProvider.get_available_models()

        current_text = self.cb_model.currentText()
        self.cb_model.clear()

        if models:
            self.cb_model.addItems(models)
            if current_text in models:
                self.cb_model.setCurrentText(current_text)
            else:
                self.cb_model.setCurrentIndex(0)
        else:
            self.cb_model.setCurrentText(current_text)  # Fallback si Ollama est éteint

        self.btn_refresh_models.setText("🔄 Actualiser")
        self.btn_refresh_models.setEnabled(True)
    @Slot()
    def save_settings(self) -> None:
        env_path = self.ai_manager.env_path

        # ATTENTION: Remplacer self.le_model.text() par self.cb_model.currentText()
        set_key(env_path, "AI_PROVIDER", self.cb_provider.currentText())
        set_key(env_path, "AI_MODEL", self.cb_model.currentText().strip())
        set_key(env_path, "GEMINI_API_KEY", self.le_gemini_key.text().strip())
        set_key(env_path, "GROQ_API_KEY", self.le_groq_key.text().strip())

        self.ai_manager.reload_provider()

        from src.services.ai.base import MockProvider
        if isinstance(self.ai_manager.provider, MockProvider) and self.cb_provider.currentText() != "Mock":
            QMessageBox.warning(self, "Erreur",
                                "Connexion IA échouée. Passage en mode simulation.")
        else:
            show_toast(self, "Paramètres enregistrés !")