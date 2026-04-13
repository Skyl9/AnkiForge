import json
import logging
import os
from typing import Any

import markdown
import qtawesome as qta
from PySide6.QtCore import Qt, Signal, Slot, QPoint, QThread
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QFrame,
    QComboBox,
    QToolButton,
)

from ankiforge.database.models import DocumentModel, DeckModel, LLMConfigModel, NoteVersionModel, CardModel, NoteModel
from ankiforge.services.ai.base import MockProvider, LLMProvider
from ankiforge.services.ai.flexible_service import OpenAICompatibleProvider, GroqProvider, OllamaProvider
from ankiforge.services.ai.gemini_service import GeminiService
from ankiforge.ui.components.components import PrimaryButton, RoundedPanel, HeaderLabel

logger = logging.getLogger(__name__)


# ==========================================
# 1. COMPOSANTS DE SAISIE INTELLIGENTE
# ==========================================


class ChatConsultantThread(QThread):
    """Thread qui envoie le contexte massif à l'IA pour obtenir des conseils."""

    progress = Signal(str)
    finished_signal = Signal(str)
    error_signal = Signal(str)

    def __init__(self, ai_provider: Any, context_data: dict[str, Any], instruction: str):
        super().__init__()
        self.ai_provider = ai_provider
        self.context_data = context_data
        self.instruction = instruction

    def run(self):
        try:
            self.progress.emit("L'IA analyse vos sources...")

            system_prompt = (
                "Tu es un expert en mémorisation, pédagogie et création de flashcards Anki.\n"
                "Ton rôle est d'analyser les documents et les paquets de cartes fournis en contexte.\n"
                "Réponds aux questions de l'utilisateur pour l'aider à améliorer son apprentissage.\n"
                "RÈGLES :\n"
                "1. Réponds en Markdown avec une structure claire.\n"
                "2. Si l'utilisateur demande un audit (/audit), cherche les incohérences ou les cartes trop complexes.\n"
                "3. Sois direct, pédagogique et critique si nécessaire."
            )

            user_payload = {"contexte_fourni": self.context_data, "requete_utilisateur": self.instruction}

            user_prompt = json.dumps(user_payload, ensure_ascii=False, indent=2)

            # Appel API
            raw_response = self.ai_provider.generate(system_prompt=system_prompt, user_prompt=user_prompt, response_format="text")

            self.finished_signal.emit(raw_response)

        except Exception as e:
            logger.exception("Erreur dans le ChatConsultantThread :")
            self.error_signal.emit(str(e))


class MentionPopup(QListWidget):
    """Le menu flottant qui apparaît quand on tape @ ou /"""

    item_selected = Signal(str, str)  # type (cmd ou context), valeur

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("""
            QListWidget {
                background-color: palette(window);
                border: 1px solid palette(alternate-base);
                border-radius: 6px;
                padding: 4px;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 6px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: palette(highlight);
                color: palette(highlighted-text);
            }
        """)
        self.itemClicked.connect(self._on_item_clicked)
        self.hide()
        self.current_mode = ""

    def populate(self, mode: str, query: str = ""):
        self.clear()
        self.current_mode = mode
        query = query.lower()

        if mode == "/":
            commands = [
                ("audit", "🔍 /audit : Analyser et trouver des erreurs"),
                ("explain", "📖 /explain : Expliquer un concept"),
                ("mnemonics", "🧠 /mnemonics : Créer des mnémotechniques"),
                ("clear", "🧹 /clear : Vider le contexte actuel"),
            ]
            for cmd_id, display in commands:
                if query in cmd_id or query in display.lower():
                    item = QListWidgetItem(display)
                    item.setData(Qt.ItemDataRole.UserRole, cmd_id)
                    self.addItem(item)

        elif mode == "@":
            for deck in DeckModel.select():
                if query in deck.name.lower():
                    item = QListWidgetItem(f"📦 Paquet : {deck.name}")
                    item.setData(Qt.ItemDataRole.UserRole, f"deck_{deck.id}")
                    self.addItem(item)
            for doc in DocumentModel.select():
                if query in doc.title.lower():
                    item = QListWidgetItem(f"📄 Doc : {doc.title}")
                    item.setData(Qt.ItemDataRole.UserRole, f"doc_{doc.id}")
                    self.addItem(item)

        if self.count() > 0:
            self.setCurrentRow(0)

    def _on_item_clicked(self, item: QListWidgetItem):
        self.item_selected.emit(self.current_mode, item.data(Qt.ItemDataRole.UserRole))


class CommandTextEdit(QTextEdit):
    """Éditeur de texte qui écoute les frappes pour déclencher le popup."""

    mention_inserted = Signal(str, str)
    send_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.popup = MentionPopup()
        self.popup.item_selected.connect(self._on_popup_selected)
        self.setPlaceholderText("Tapez / pour une commande, ou @ pour charger du contexte (Doc, Paquet)...")
        # Police plus grande pour l'effet "Barre de commande"
        font = self.font()
        font.setPointSize(12)
        self.setFont(font)

        self.is_typing_mention = False
        self.mention_start_pos = 0
        self.current_mention_mode = ""

    def keyPressEvent(self, event: QKeyEvent):
        if self.popup.isVisible():
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.popup.currentRow()
                if event.key() == Qt.Key.Key_Down:
                    self.popup.setCurrentRow((row + 1) % self.popup.count())
                else:
                    self.popup.setCurrentRow((row - 1) % self.popup.count())
                return
            elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                item = self.popup.currentItem()
                if item:
                    self.popup._on_item_clicked(item)
                return
            elif event.key() == Qt.Key.Key_Escape:
                self.hide_popup()
                return

        # Shift+Enter = Saut de ligne. Enter simple = Envoi.
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.send_requested.emit()
            return

        super().keyPressEvent(event)

        cursor = self.textCursor()
        text_before_cursor = cursor.block().text()[: cursor.positionInBlock()]

        if text_before_cursor.endswith("@") and (len(text_before_cursor) == 1 or text_before_cursor[-2] == " "):
            self.start_mention("@", cursor.position())
        elif text_before_cursor.endswith("/") and (len(text_before_cursor) == 1 or text_before_cursor[-2] == " "):
            self.start_mention("/", cursor.position())
        elif self.is_typing_mention:
            if event.key() == Qt.Key.Key_Space or cursor.position() < self.mention_start_pos:
                self.hide_popup()
            else:
                query = self.toPlainText()[self.mention_start_pos : cursor.position()]
                self.popup.populate(self.current_mention_mode, query)
                if self.popup.count() == 0:
                    self.hide_popup()
                else:
                    self.update_popup_position()

    def start_mention(self, mode: str, pos: int):
        self.is_typing_mention = True
        self.current_mention_mode = mode
        self.mention_start_pos = pos
        self.popup.populate(mode, "")
        self.update_popup_position()
        self.popup.show()

    def update_popup_position(self):
        cursor_rect = self.cursorRect()
        global_pos = self.mapToGlobal(cursor_rect.bottomLeft())
        self.popup.move(global_pos + QPoint(0, 5))
        self.popup.resize(300, 150)

    def hide_popup(self):
        self.is_typing_mention = False
        self.popup.hide()

    @Slot(str, str)
    def _on_popup_selected(self, mode: str, data_id: str):
        self.hide_popup()
        cursor = self.textCursor()
        cursor.setPosition(self.mention_start_pos - 1, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        self.mention_inserted.emit(mode, data_id)


# ==========================================
# 2. LE WIDGET CHIP (Pilule interactive)
# ==========================================


class ContextChip(QFrame):
    """Une petite pilule visuelle représentant un élément de contexte, avec un bouton supprimer."""

    removed = Signal(str)

    def __init__(self, data_id: str, display_text: str, parent=None):
        super().__init__(parent)
        self.data_id = data_id

        self.setStyleSheet("""
            QFrame {
                background-color: palette(highlight);
                border-radius: 12px;
                padding: 2px 4px;
            }
            QLabel {
                color: palette(highlighted-text);
                font-weight: bold;
                font-size: 11px;
                padding-left: 4px;
                background: transparent;
            }
            QToolButton {
                background: transparent;
                color: palette(highlighted-text);
                border: none;
                font-weight: bold;
                font-size: 14px;
                border-radius: 8px;
            }
            QToolButton:hover {
                background-color: rgba(0, 0, 0, 0.2);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        lbl = QLabel(display_text)

        btn_close = QToolButton()
        btn_close.setText("×")
        btn_close.setFixedSize(16, 16)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self._on_remove)

        layout.addWidget(lbl)
        layout.addWidget(btn_close)

    def _on_remove(self):
        self.removed.emit(self.data_id)


# ==========================================
# 3. L'ONGLET PRINCIPAL
# ==========================================


class ConsultantTab(QWidget):
    """La vue complète du Studio Consultant"""

    def __init__(self, ai_manager: Any):
        super().__init__()
        self.ai_manager = ai_manager
        self.active_context: list[str] = []  # Liste des identifiants (ex: 'deck_1', 'doc_3')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # --- HEADER ---
        header_layout = QHBoxLayout()
        header_layout.addWidget(HeaderLabel("🧠 Studio Consultant IA"))
        header_layout.addStretch()

        self.llm_selector = QComboBox()
        self.llm_selector.setMinimumHeight(32)
        self.llm_selector.setMinimumWidth(150)
        self._populate_llms()
        header_layout.addWidget(self.llm_selector)

        layout.addLayout(header_layout)

        # --- BLOC DE SAISIE (Haut) ---
        input_panel = RoundedPanel()
        input_layout = QVBoxLayout(input_panel)
        input_layout.setContentsMargins(15, 15, 15, 15)

        # Barre des Chips (Contexte)
        self.context_bar = QHBoxLayout()
        self.context_bar.setAlignment(Qt.AlignmentFlag.AlignLeft)

        lbl_ctx = QLabel("Contexte :")
        lbl_ctx.setStyleSheet("font-size: 11px; font-weight: bold; color: palette(placeholder-text);")
        self.context_bar.addWidget(lbl_ctx)

        self.context_chips_layout = QHBoxLayout()
        self.context_chips_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.context_bar.addLayout(self.context_chips_layout)
        self.context_bar.addStretch()

        input_layout.addLayout(self.context_bar)

        # Zone de texte principale
        chat_actions_layout = QHBoxLayout()
        self.chat_input = CommandTextEdit()
        # Au démarrage, le champ est grand et accueillant
        self.chat_input.setMinimumHeight(120)
        self.chat_input.mention_inserted.connect(self.on_mention_inserted)
        self.chat_input.send_requested.connect(self.send_message)

        self.btn_send = PrimaryButton(qta.icon("fa5s.paper-plane", color="white"), "")
        self.btn_send.setFixedSize(50, 50)
        self.btn_send.clicked.connect(self.send_message)

        chat_actions_layout.addWidget(self.chat_input, stretch=1)
        chat_actions_layout.addWidget(self.btn_send, alignment=Qt.AlignmentFlag.AlignBottom)

        input_layout.addLayout(chat_actions_layout)
        layout.addWidget(input_panel)

        # --- CONSOLE DE LOGS (Bas) ---
        console_panel = RoundedPanel()
        console_layout = QVBoxLayout(console_panel)

        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_history.setStyleSheet("background: transparent; font-size: 14px;")
        self.chat_history.append(
            "<div style='color: gray; text-align: center; margin-top: 40px;'>"
            "<h2>Bienvenue dans votre Studio</h2>"
            "<i>Chargez vos documents et paquets avec <b>@</b>.<br>"
            "Lancez des requêtes ciblées avec <b>/</b> (ex: /audit).</i></div>"
        )
        self.lbl_chat_status = QLabel("")

        console_layout.addWidget(self.chat_history)
        console_layout.addWidget(self.lbl_chat_status)
        layout.addWidget(console_panel, stretch=1)  # Le stretch=1 permet à la console de prendre tout l'espace restant
        self.refresh_context_chips()

    def _populate_llms(self):
        """Remplit le menu déroulant avec les moteurs IA de la base de données."""
        self.llm_selector.clear()
        for llm in LLMConfigModel.select().order_by(LLMConfigModel.display_name):
            self.llm_selector.addItem(llm.display_name, userData=llm.id)

    @Slot(str, str)
    def on_mention_inserted(self, mode: str, data_id: str):
        """Gère l'insertion d'un tag depuis le popup."""
        if mode == "/":
            if data_id == "clear":
                self.clear_context()
                self.chat_history.append("<div style='color: orange;'>🧹 <i>Le contexte a été vidé.</i></div>")
            else:
                self.chat_input.insertPlainText(f"/{data_id} ")

        elif mode == "@":
            if data_id not in self.active_context:
                self.active_context.append(data_id)
                self.refresh_context_chips()
            self.chat_input.setFocus()

    @Slot(str)
    def remove_context_item(self, data_id: str):
        """Supprime une pilule de contexte via la croix (X)."""
        if data_id in self.active_context:
            self.active_context.remove(data_id)
            self.refresh_context_chips()

    def clear_context(self):
        self.active_context.clear()
        self.refresh_context_chips()

    def refresh_context_chips(self):
        """Redessine les pilules interactives."""
        while self.context_chips_layout.count():
            child = self.context_chips_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not self.active_context:
            lbl = QLabel("Aucun (L'IA répondra de manière générique)")
            lbl.setStyleSheet("color: palette(placeholder-text); font-style: italic; font-size: 11px;")
            self.context_chips_layout.addWidget(lbl)
            return

        for ctx_id in self.active_context:
            display_text = "Inconnu"
            if ctx_id.startswith("deck_"):
                d_id = int(ctx_id.split("_")[1])
                deck = DeckModel.get_or_none(DeckModel.id == d_id)
                display_text = f"📦 {deck.name}" if deck else "Paquet inconnu"
            elif ctx_id.startswith("doc_"):
                d_id = int(ctx_id.split("_")[1])
                doc = DocumentModel.get_or_none(DocumentModel.id == d_id)
                display_text = f"📄 {doc.title}" if doc else "Doc inconnu"

            # Création de notre nouveau widget interactif
            chip = ContextChip(ctx_id, display_text)
            chip.removed.connect(self.remove_context_item)
            self.context_chips_layout.addWidget(chip)

    @Slot()
    def send_message(self):
        instruction = self.chat_input.toPlainText().strip()
        if not instruction:
            return

        # 1. Animation UI
        self.chat_input.setMinimumHeight(40)
        self.chat_input.setMaximumHeight(80)

        # 2. Collecte des données de contexte
        self.lbl_chat_status.setText("📦 Collecte des données...")
        context_data = self._build_context_data()

        # 3. Récupération de l'IA sélectionnée
        llm_id = self.llm_selector.currentData()
        llm_config = LLMConfigModel.get_or_none(LLMConfigModel.id == llm_id)
        if not llm_config:
            self.chat_history.append("<div style='color:red;'>⚠️ Aucun moteur IA sélectionné.</div>")
            return

        active_provider = self._get_ai_provider(llm_config)

        # 4. Affichage de l'écho dans la console
        context_info = f"({len(self.active_context)} sources)" if self.active_context else "(Sans contexte)"
        self.chat_history.append(f"<hr><div style='margin-bottom:10px;'><b>👤 Vous {context_info} :</b><br>{instruction}</div>")
        self.chat_input.clear()
        self.btn_send.setEnabled(False)

        # 5. Lancement du Thread
        self.chat_thread = ChatConsultantThread(active_provider, context_data, instruction)
        self.chat_thread.finished_signal.connect(self.on_chat_success)
        self.chat_thread.error_signal.connect(self.on_chat_error)
        self.chat_thread.start()

    def _build_context_data(self) -> dict:
        """Transforme les IDs de contexte en données réelles (texte, cartes)."""
        data: dict[str, list] = {"documents": [], "paquets": []}

        for ctx_id in self.active_context:
            if ctx_id.startswith("doc_"):
                d_id = int(ctx_id.split("_")[1])
                doc = DocumentModel.get_or_none(DocumentModel.id == d_id)
                if doc:
                    data["documents"].append({"titre": doc.title, "contenu": doc.content})

            elif ctx_id.startswith("deck_"):
                d_id = int(ctx_id.split("_")[1])
                deck = DeckModel.get_or_none(DeckModel.id == d_id)
                if deck:
                    # On récupère les notes de ce paquet
                    notes = []
                    # On limite à 100 pour éviter d'exploser les limites de tokens, modifiez selon besoin
                    query = NoteModel.select().join(CardModel).where(CardModel.deck == deck).distinct().limit(100)

                    for note in query:
                        v = NoteVersionModel.get_or_none(note=note, is_active=True)
                        if v:
                            notes.append(json.loads(v.content))

                    data["paquets"].append({"nom": deck.name, "notes": notes, "modele": json.loads(note.note_type.templates) if notes and note.note_type else []})
        return data

    def _get_ai_provider(self, config) -> LLMProvider:
        """Instancie le bon service IA selon la config."""
        p_name = config.provider.lower()
        if p_name == "ollama":
            return OllamaProvider(model_name=config.model_id)
        elif p_name == "gemini":
            return GeminiService(model_name=config.model_id)
        elif p_name == "groq":
            return GroqProvider(model_name=config.model_id)
        elif p_name == "openai":
            return OpenAICompatibleProvider(
                base_url="https://api.openai.com/v1",
                model_name=config.model_id,
                api_key=os.environ.get("OPENAI_API_KEY", ""),
            )
        return MockProvider()

    @Slot(str)
    def on_chat_success(self, response_text: str):
        # Conversion Markdown -> HTML
        html_response = markdown.markdown(response_text, extensions=["extra", "codehilite"])

        self.lbl_chat_status.setText("✅ Prêt")
        self.chat_history.append(f"<div style='margin-bottom:20px; padding:15px; background-color:palette(alternate-base); border-radius:8px;'>" f"<b>🤖 IA :</b><br>{html_response}</div>")
        self.btn_send.setEnabled(True)
        # Scroll automatique vers le bas
        self.chat_history.verticalScrollBar().setValue(self.chat_history.verticalScrollBar().maximum())

    @Slot(str)
    def on_chat_error(self, error_msg: str):
        self.lbl_chat_status.setText("❌ Erreur")
        self.chat_history.append(f"<div style='color:red;'><b>Erreur de l'IA :</b> {error_msg}</div>")
        self.btn_send.setEnabled(True)
