from typing import Optional, Any

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTextEdit, QListWidget, QLabel, QComboBox
from PySide6.QtCore import Qt

from ankiforge.ui.components.panels import IdePanel
from ankiforge.ui.components.buttons import PrimaryButton
from ankiforge.database.models import DeckModel, AgentModel, LLMConfigModel
from ankiforge.ui.theme import DesignTokens


class ConsultantView(QWidget):
    """
    AI Consultant View:
    - 2-column layout with IdePanel
    - Left: Interactive AI Chat view (message thread, input text area, model selector).
    - Right: Active Context panel (attached sources, system prompt editor).
    """

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)

        # --- Left Panel: Interactive AI Chat ---
        self.chat_panel = IdePanel(title="Chat IA")
        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)

        # Model Selector
        self.model_selector = QComboBox()
        self._load_models()
        chat_layout.addWidget(self.model_selector)

        # Message Thread
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.setStyleSheet(f"border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_SM}px;")
        chat_layout.addWidget(self.chat_history, stretch=1)

        # Input Area
        input_layout = QHBoxLayout()
        self.chat_input = QTextEdit()
        self.chat_input.setFixedHeight(80)
        self.chat_input.setPlaceholderText("Posez votre question à l'assistant (utilisez @ pour mentionner un deck)...")
        input_layout.addWidget(self.chat_input, stretch=1)

        self.btn_send = PrimaryButton("Envoyer")
        self.btn_send.clicked.connect(self._on_send_clicked)
        input_layout.addWidget(self.btn_send)

        chat_layout.addLayout(input_layout)

        self.chat_panel.add_tab("Assistant", chat_container, "ph.chat-circle-dots")
        self.splitter.addWidget(self.chat_panel)

        # --- Right Panel: Active Context ---
        self.context_panel = IdePanel(title="Contexte Actif")
        context_container = QWidget()
        context_layout = QVBoxLayout(context_container)

        # Attached Sources / Decks
        context_layout.addWidget(QLabel("Decks / Sources liés:"))
        self.sources_list = QListWidget()
        self.sources_list.setFixedHeight(120)
        context_layout.addWidget(self.sources_list)

        # System Prompt Editor
        context_layout.addWidget(QLabel("Prompt Système (Agent):"))
        self.system_prompt_editor = QTextEdit()
        context_layout.addWidget(self.system_prompt_editor, stretch=1)

        # Memory Tokens Indicator
        self.memory_indicator = QLabel("Mémoire: 0 tokens utilisés")
        self.memory_indicator.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED};")
        context_layout.addWidget(self.memory_indicator)

        self.context_panel.add_tab("Contexte", context_container, "ph.brain")
        self.splitter.addWidget(self.context_panel)

        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 1)

        self.refresh_data()

    def _load_models(self) -> None:
        self.model_selector.clear()
        models = LLMConfigModel.select()
        for m in models:
            self.model_selector.addItem(m.display_name, m.model_id)

    def refresh_data(self) -> None:
        """Rafraîchit les données du contexte."""
        # Load available decks
        self.sources_list.clear()
        decks = DeckModel.select()
        for d in decks:
            self.sources_list.addItem(f"Deck: {d.name}")

        # Load default agent prompt
        agent = AgentModel.get_or_none(AgentModel.name == "Archiviste Pédagogue")
        if agent:
            self.system_prompt_editor.setPlainText(agent.system_prompt)

    def is_dirty(self) -> bool:
        return False

    def _on_send_clicked(self) -> None:
        user_text = self.chat_input.toPlainText().strip()
        if not user_text:
            return

        # Append user message
        user_bg = (
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            "stop:0 rgba(99, 102, 241, 0.2), stop:1 rgba(139, 92, 246, 0.2)); "
            "border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 8px; "
            "padding: 8px; margin: 4px 0;"
        )
        user_html = f'<div style="{user_bg}"><b>Vous:</b> {user_text}</div>'
        self.chat_history.append(user_html)
        self.chat_input.clear()

        # In a real scenario, this would start the ConsultantWorker or use AIManager
        # We simulate the response for now.
        system_prompt = self.system_prompt_editor.toPlainText()
        model_id = self.model_selector.currentData()

        # Simulate worker processing
        self.chat_history.append("<i>L'assistant réfléchit...</i>")

        # Note: True integration would connect to AIManager / ConsultantWorker here.
        # This is a stub for the UI integration.
        ai_html = f"""
        <div style="background-color: #1e2128; border: 1px solid #2d313a; border-radius: 8px; padding: 8px; margin: 4px 0;">
            <b>Assistant:</b> Réponse simulée avec {model_id} (Contexte: {len(system_prompt)} chars)
        </div>
        """
        self.chat_history.append(ai_html)


ConsultantTab = ConsultantView
