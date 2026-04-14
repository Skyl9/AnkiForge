import json
import logging
from typing import Any

import markdown
import qtawesome as qta
from PySide6.QtCore import QPoint, Qt, Signal, Slot
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import CardModel, DeckModel, DocumentModel, LLMConfigModel, NoteModel, NoteVersionModel
from ankiforge.services.workers.consultant_worker import ConsultantWorker
from ankiforge.ui.components.components import HeaderLabel, PrimaryButton, RoundedPanel, DBComboBox

logger = logging.getLogger(__name__)


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
    """
    Vue du Studio Consultant IA.
    Interface conversationnelle permettant à l'utilisateur d'interagir avec l'IA
    en lui fournissant un contexte dynamique (documents ou paquets) via des mentions.
    """

    def __init__(self, ai_manager: Any) -> None:
        """
        Initialise l'onglet du Consultant IA.

        Args:
            ai_manager (AIManager): Instance du gestionnaire d'IA central.
        """
        super().__init__()
        self.ai_manager = ai_manager
        self.active_context: list[str] = []
        self.chat_thread: ConsultantWorker | None = None

        self._setup_ui()
        self._connect_signals()

        self.refresh_context_chips()

    def _setup_ui(self) -> None:
        """Initialise et organise les composants graphiques de la vue."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        self._build_header()
        self._build_input_panel()
        self._build_console_panel()

    def _build_header(self) -> None:
        """Construit l'en-tête contenant le titre et le sélecteur de modèle IA."""
        header_layout = QHBoxLayout()
        header_layout.addWidget(HeaderLabel("🧠 Studio Consultant IA"))
        header_layout.addStretch()

        self.llm_selector = DBComboBox(LLMConfigModel, display_field="display_name", sort_field="display_name")
        self.llm_selector.setMinimumHeight(32)
        self.llm_selector.setMinimumWidth(150)
        header_layout.addWidget(self.llm_selector)

        self.main_layout.addLayout(header_layout)

    def _build_input_panel(self) -> None:
        """Construit le panneau de saisie incluant la barre de contexte et l'éditeur de texte."""
        input_panel = RoundedPanel()
        input_layout = QVBoxLayout(input_panel)
        input_layout.setContentsMargins(15, 15, 15, 15)

        # Barre des pilules de contexte (Chips)
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

        # Zone de saisie principale et bouton d'envoi
        chat_actions_layout = QHBoxLayout()
        self.chat_input = CommandTextEdit()
        self.chat_input.setMinimumHeight(120)

        self.btn_send = PrimaryButton(qta.icon("fa5s.paper-plane", color="white"), "")
        self.btn_send.setFixedSize(50, 50)

        chat_actions_layout.addWidget(self.chat_input, stretch=1)
        chat_actions_layout.addWidget(self.btn_send, alignment=Qt.AlignmentFlag.AlignBottom)

        input_layout.addLayout(chat_actions_layout)
        self.main_layout.addWidget(input_panel)

    def _build_console_panel(self) -> None:
        """Construit la zone d'affichage de l'historique de discussion."""
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

        self.main_layout.addWidget(console_panel, stretch=1)

    def _connect_signals(self) -> None:
        """Branche les signaux de l'interface aux slots de la classe."""
        self.chat_input.mention_inserted.connect(self.on_mention_inserted)
        self.chat_input.send_requested.connect(self.send_message)
        self.btn_send.clicked.connect(self.send_message)

    def _populate_llms(self) -> None:
        """Remplit le menu déroulant avec les moteurs IA disponibles en base de données."""
        self.llm_selector.clear()
        for llm in LLMConfigModel.select().order_by(LLMConfigModel.display_name):
            self.llm_selector.addItem(llm.display_name, userData=llm.id)

    @Slot(str, str)
    def on_mention_inserted(self, mode: str, data_id: str) -> None:
        """
        Gère l'insertion d'une commande ou d'un élément de contexte.

        Args:
            mode (str): Type d'insertion ('/' pour commande, '@' pour contexte).
            data_id (str): Identifiant de l'élément sélectionné.
        """
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
    def remove_context_item(self, data_id: str) -> None:
        """Retire un élément spécifique du contexte actif."""
        if data_id in self.active_context:
            self.active_context.remove(data_id)
            self.refresh_context_chips()

    def clear_context(self) -> None:
        """Vide l'intégralité du contexte actif."""
        self.active_context.clear()
        self.refresh_context_chips()

    def refresh_context_chips(self) -> None:
        """Redessine les éléments visuels (chips) représentant le contexte chargé."""
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

            chip = ContextChip(ctx_id, display_text)
            chip.removed.connect(self.remove_context_item)
            self.context_chips_layout.addWidget(chip)

    @Slot()
    def send_message(self) -> None:
        """Prépare les données contextuelles et lance le thread de discussion IA."""
        instruction = self.chat_input.toPlainText().strip()
        if not instruction:
            return

        # Rétractation de la zone de saisie pour libérer l'espace d'affichage
        self.chat_input.setMinimumHeight(40)
        self.chat_input.setMaximumHeight(80)
        self.btn_send.setEnabled(False)
        self.lbl_chat_status.setText("📦 Collecte des données...")

        context_names = []
        for ctx_id in self.active_context:
            if ctx_id.startswith("doc_"):
                doc = DocumentModel.get_or_none(DocumentModel.id == int(ctx_id.split("_")[1]))
                if doc:
                    context_names.append(f"📄 {doc.title}")
            elif ctx_id.startswith("deck_"):
                deck = DeckModel.get_or_none(DeckModel.id == int(ctx_id.split("_")[1]))
                if deck:
                    context_names.append(f"📦 {deck.name}")

        ctx_display = ", ".join(context_names) if context_names else "Aucun contexte"

        echo_html = (
            f"<hr><div style='margin-bottom:10px; padding-left:10px; border-left: 3px solid palette(highlight);'>"
            f"<b style='color: palette(highlight);'>&gt; COMMANDE :</b> {instruction}<br>"
            f"<span style='font-size: 11px; color: palette(placeholder-text);'><i>Cible(s) : {ctx_display}</i></span>"
            f"</div>"
        )
        self.chat_history.append(echo_html)
        self.chat_input.clear()

        context_data = self._build_context_data()

        llm_id = self.llm_selector.currentData()
        llm_config = LLMConfigModel.get_or_none(LLMConfigModel.id == llm_id)
        if not llm_config:
            self.chat_history.append("<div style='color:red;'>⚠️ Aucun moteur IA sélectionné.</div>")
            self.btn_send.setEnabled(True)
            return

        active_provider = self.ai_manager.create_provider_from_config(llm_config)

        self.chat_thread = ConsultantWorker(active_provider, context_data, instruction)
        self.chat_thread.progress.connect(self.on_chat_progress)
        self.chat_thread.finished_signal.connect(self.on_chat_success)
        self.chat_thread.error_signal.connect(self.on_chat_error)
        self.chat_thread.start()

    @Slot(str)
    def on_chat_progress(self, msg: str) -> None:
        """Affiche les états intermédiaires renvoyés par le thread."""
        self.lbl_chat_status.setText(f"⏳ {msg}")

    def _build_context_data(self) -> dict:
        """
        Extrait le contenu réel (texte et JSON des cartes) correspondant aux IDs de contexte actifs.

        Returns:
            dict: Données contextuelles structurées prêtes à l'envoi.
        """
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
                    notes = []
                    # Limite conservatrice pour prévenir le dépassement de la fenêtre de contexte
                    query = NoteModel.select().join(CardModel).where(CardModel.deck == deck).distinct().limit(100)

                    for note in query:
                        v = NoteVersionModel.get_or_none(note=note, is_active=True)
                        if v:
                            notes.append(json.loads(v.content))

                    data["paquets"].append({"nom": deck.name, "notes": notes, "modele": json.loads(note.note_type.templates) if notes and note.note_type else []})
        return data

    @Slot(str)
    def on_chat_success(self, response_text: str) -> None:
        """Affiche la réponse formatée et réactive l'interface."""
        html_response = markdown.markdown(response_text, extensions=["extra", "codehilite", "tables"])

        self.lbl_chat_status.setText("")

        final_html = (
            f"<div style='margin-top:10px; margin-bottom:20px; padding:15px; background-color:palette(alternate-base); border-radius:8px; border: 1px solid palette(window);'>"
            f"<b>🤖 Réponse de l'IA :</b><br><br>"
            f"<div style='font-size: 13px; line-height: 1.5;'>{html_response}</div>"
            f"</div>"
        )
        self.chat_history.append(final_html)

        self.btn_send.setEnabled(True)
        scrollbar = self.chat_history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @Slot(str)
    def on_chat_error(self, error_msg: str) -> None:
        """Affiche les erreurs remontées par l'IA ou le processus d'extraction."""
        self.lbl_chat_status.setText("❌ Erreur")
        self.chat_history.append(f"<div style='color:red;'><b>Erreur de l'IA :</b> {error_msg}</div>")
        self.btn_send.setEnabled(True)
