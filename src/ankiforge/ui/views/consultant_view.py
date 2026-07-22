"""
Vue AI Consultant — Intégration Métier Complète (master) & UI 100% Maquette concept_ide.
- Raccordement complet à AIManager, LLMConfigModel, DeckModel, DocumentModel et AgentModel.
- Extraction contextuelle réelle des notes et documents (_build_context_data).
- Gestion dynamique des sources attachées (@Deck, @Doc) avec menu contextuel et suppression.
- Moteur asynchrone ConsultantWorker avec signaux progress, finished_signal et error_signal.
- Boutons d'actions avancées (Tags, Division, Attachments) réservés pour les futures extensions.
"""

import datetime
import json
import logging
from typing import Any, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    AgentModel,
    CardModel,
    DeckModel,
    DocumentModel,
    LLMConfigModel,
    NoteModel,
    NoteVersionModel,
)
from ankiforge.services.workers.consultant_worker import ConsultantWorker
from ankiforge.ui.components import (
    Badge,
    IconButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ChatMessageWidget(QWidget):
    """Bulle de message conversationnel (Utilisateur ou Assistant IA)."""

    def __init__(
        self,
        sender: str,
        text: str,
        is_user: bool = False,
        actions: Optional[list[str]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.is_user = is_user

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        # Avatar
        self.avatar_lbl = QLabel()
        self.avatar_lbl.setFixedSize(32, 32)
        self.avatar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if is_user:
            self.avatar_lbl.setText("Vous")
            self.avatar_lbl.setStyleSheet("""
                QLabel {
                    background-color: #3b82f6;
                    color: white;
                    font-weight: bold;
                    font-size: 11px;
                    border-radius: 16px;
                }
            """)
            layout.addStretch()
        else:
            self.avatar_lbl.setPixmap(load_phosphor_icon("ph.robot", color="white").pixmap(18, 18))
            self.avatar_lbl.setStyleSheet("""
                QLabel {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6366f1, stop:1 #8b5cf6);
                    border-radius: 16px;
                }
            """)

        # Bulle de contenu
        content_wrapper = QWidget()
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)

        # Header (Auteur + Heure)
        now_str = datetime.datetime.now().strftime("%H:%M")
        header_lbl = QLabel(f"<b>{sender}</b> <span style='color: {DesignTokens.TEXT_MUTED}; font-size: 11px;'>{now_str}</span>")
        header_lbl.setStyleSheet("border: none; background: transparent;")

        # Corps du message
        body_card = QFrame()
        body_layout = QVBoxLayout(body_card)
        body_layout.setContentsMargins(14, 12, 14, 12)

        msg_body = QLabel(text)
        msg_body.setWordWrap(True)
        msg_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        msg_body.setStyleSheet("border: none; background: transparent; font-size: 13px; line-height: 1.4;")

        if is_user:
            body_card.setStyleSheet(f"""
                QFrame {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(99, 102, 241, 0.18), stop:1 rgba(139, 92, 246, 0.18));
                    border: 1px solid rgba(139, 92, 246, 0.35);
                    border-radius: {DesignTokens.RADIUS_MD}px;
                }}
            """)
            msg_body.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none;")
        else:
            body_card.setStyleSheet(f"""
                QFrame {{
                    background-color: #1e2128;
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                }}
            """)
            msg_body.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none;")
            apply_shadow(body_card, blur=8, offset_y=2)

        body_layout.addWidget(msg_body)

        content_layout.addWidget(header_lbl)
        content_layout.addWidget(body_card)

        # Actions sous la réponse de l'IA (Tags, Copier, Thumbs - Mockées pour extensions futures)
        if not is_user:
            actions_layout = QHBoxLayout()
            actions_layout.setContentsMargins(0, 4, 0, 0)
            actions_layout.setSpacing(6)

            btn_apply_tags = SecondaryButton("Appliquer les tags")
            btn_apply_tags.setIcon(load_phosphor_icon("ph.magic-wand", color=DesignTokens.COLOR_PURPLE))
            btn_apply_tags.setStyleSheet("padding: 4px 8px; font-size: 11px;")
            btn_apply_tags.clicked.connect(lambda: show_toast(self, "Application automatique des tags en cours..."))
            actions_layout.addWidget(btn_apply_tags)

            btn_split = SecondaryButton("Diviser les cartes")
            btn_split.setIcon(load_phosphor_icon("ph.scissors", color=DesignTokens.TEXT_PRIMARY))
            btn_split.setStyleSheet("padding: 4px 8px; font-size: 11px;")
            btn_split.clicked.connect(lambda: show_toast(self, "Analyse pour division des cartes longues..."))
            actions_layout.addWidget(btn_split)

            actions_layout.addStretch()

            btn_copy = IconButton("ph.copy", tooltip="Copier le texte", size=20)
            btn_copy.clicked.connect(lambda: show_toast(self, "Texte copié dans le presse-papier."))
            btn_like = IconButton("ph.thumbs-up", tooltip="Bonne réponse", size=20)
            btn_like.clicked.connect(lambda: show_toast(self, "Merci pour votre retour !"))
            btn_dislike = IconButton("ph.thumbs-down", tooltip="Mauvaise réponse", size=20)
            btn_dislike.clicked.connect(lambda: show_toast(self, "Retour enregistré."))

            actions_layout.addWidget(btn_copy)
            actions_layout.addWidget(btn_like)
            actions_layout.addWidget(btn_dislike)

            content_layout.addLayout(actions_layout)

        if not is_user:
            layout.addWidget(self.avatar_lbl, alignment=Qt.AlignmentFlag.AlignTop)
            layout.addWidget(content_wrapper, 1)
        else:
            layout.addWidget(content_wrapper, 1)
            layout.addWidget(self.avatar_lbl, alignment=Qt.AlignmentFlag.AlignTop)


class ConsultantView(QWidget):
    """
    AI Consultant Studio — Intégration Métier Complète master + UI 100% Maquette concept_ide.
    """

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.worker: Optional[ConsultantWorker] = None
        self.used_tokens_count = 14204
        self.modified_cards_count = 0
        self.active_context: list[str] = []  # Liste d'identifiants (ex: 'deck_1', 'doc_2')

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()
        self._insert_initial_messages()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)

        # --- COL 1: Main Chat Panel ---
        self.chat_panel = IdePanel(detachable=True)

        # Moteur Selector dans le header du chat_panel
        self.model_selector = StyledComboBox()
        self.model_selector.setMinimumWidth(160)
        self.chat_panel.add_header_widget(self.model_selector)
        self.chat_panel.add_header_separator()

        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        # Status label pour la progression de l'IA
        self.lbl_chat_status = QLabel("")
        self.lbl_chat_status.setStyleSheet(f"color: {DesignTokens.COLOR_PURPLE}; font-size: 11px; padding: 4px 16px; font-weight: bold;")
        chat_layout.addWidget(self.lbl_chat_status)

        # Zone d'affichage des messages (Scroll Area)
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_scroll.setStyleSheet("background: transparent;")

        self.chat_scroll_widget = QWidget()
        self.chat_messages_layout = QVBoxLayout(self.chat_scroll_widget)
        self.chat_messages_layout.setContentsMargins(16, 16, 16, 16)
        self.chat_messages_layout.setSpacing(16)
        self.chat_messages_layout.addStretch()

        self.chat_scroll.setWidget(self.chat_scroll_widget)
        chat_layout.addWidget(self.chat_scroll, 1)

        # Zone de saisie utilisateur (Chat Input Area)
        input_area = QWidget()
        input_area_layout = QVBoxLayout(input_area)
        input_area_layout.setContentsMargins(16, 8, 16, 16)
        input_area_layout.setSpacing(10)

        # Quick Prompts Row (Boutons de suggestions rapides)
        quick_prompts_layout = QHBoxLayout()
        quick_prompts_layout.setContentsMargins(0, 0, 0, 0)
        quick_prompts_layout.setSpacing(8)

        prompts = [
            ("ph.sparkle", "Résumer le cours"),
            ("ph.magnifying-glass", "Chercher des doublons"),
            ("ph.cards", "Générer un QCM"),
            ("ph.tag", "Suggérer des tags"),
        ]
        for icon, text in prompts:
            btn = SecondaryButton(text)
            btn.setIcon(load_phosphor_icon(icon, color=DesignTokens.COLOR_PURPLE))
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1a1d24;
                    border: 1px solid #2d313a;
                    border-radius: 12px;
                    padding: 4px 12px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #2d313a;
                    border-color: #8b5cf6;
                }
            """)
            btn.clicked.connect(lambda _, t=text: self._on_quick_prompt_clicked(t))
            quick_prompts_layout.addWidget(btn)

        quick_prompts_layout.addStretch()
        input_area_layout.addLayout(quick_prompts_layout)

        # Chat Box Premium Container
        self.chat_box_frame = QFrame()
        self.chat_box_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #1a1d24;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame:focus-within {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        apply_shadow(self.chat_box_frame, blur=12, offset_y=2)

        box_layout = QVBoxLayout(self.chat_box_frame)
        box_layout.setContentsMargins(12, 10, 12, 10)
        box_layout.setSpacing(8)

        # Badges de mentions actives (@Deck: Cardio_P3)
        self.mentions_layout = QHBoxLayout()
        self.mentions_layout.setContentsMargins(0, 0, 0, 0)
        self.mentions_layout.setSpacing(6)

        self.deck_badge = Badge("Deck: Cardio_P3", variant="outline", color=DesignTokens.COLOR_GREEN)
        self.mentions_layout.addWidget(self.deck_badge)
        self.mentions_layout.addStretch()

        box_layout.addLayout(self.mentions_layout)

        # Textedit de saisie
        self.chat_input = StyledTextEdit()
        self.chat_input.setFixedHeight(50)
        self.chat_input.setPlaceholderText("Posez une question, tapez '/' pour les commandes ou '@' pour mentionner...")
        self.chat_input.setStyleSheet("border: none; background: transparent; font-size: 13px;")
        box_layout.addWidget(self.chat_input)

        # Toolbar inférieure de la chat box
        box_footer = QHBoxLayout()
        box_footer.setContentsMargins(0, 0, 0, 0)

        tools_layout = QHBoxLayout()
        tools_layout.setSpacing(4)
        self.btn_attach = IconButton("ph.paperclip", tooltip="Joindre un fichier (Maquette)", size=22)
        self.btn_attach.clicked.connect(lambda: show_toast(self, "Pièce jointe : Sélection de document."))

        self.btn_mention = IconButton("ph.at", tooltip="Mentionner un contexte (@)", size=22)
        self.btn_mention.clicked.connect(self._on_add_context)

        self.btn_prompts_lib = IconButton("ph.books", tooltip="Bibliothèque de Prompts", size=22)
        self.btn_prompts_lib.clicked.connect(lambda: show_toast(self, "Bibliothèque de Prompts IA ouverte."))

        tools_layout.addWidget(self.btn_attach)
        tools_layout.addWidget(self.btn_mention)
        tools_layout.addWidget(self.btn_prompts_lib)

        box_footer.addLayout(tools_layout)
        box_footer.addStretch()

        self.tokens_badge = QLabel("142 tokens")
        self.tokens_badge.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; margin-right: 8px;")
        box_footer.addWidget(self.tokens_badge)

        self.btn_send = PrimaryButton("")
        self.btn_send.setIcon(load_phosphor_icon("ph.arrow-up", color="white"))
        self.btn_send.setFixedSize(36, 36)
        self.btn_send.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6366f1, stop:1 #8b5cf6);
                border-radius: 18px;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4f46e5, stop:1 #7c3aed);
            }
        """)
        self.btn_send.clicked.connect(self._on_send_clicked)
        box_footer.addWidget(self.btn_send)

        box_layout.addLayout(box_footer)
        input_area_layout.addWidget(self.chat_box_frame)

        disclaimer_lbl = QLabel("L'IA peut faire des erreurs. Vérifiez toujours les cartes générées.")
        disclaimer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disclaimer_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        input_area_layout.addWidget(disclaimer_lbl)

        chat_layout.addWidget(input_area)

        self.chat_panel.add_tab("AI Consultant", chat_container, "ph.chat-centered-text", closable=False)
        self.splitter.addWidget(self.chat_panel)

        # --- COL 2: Right Context Panel ---
        self.context_panel = IdePanel(detachable=True)
        self.context_panel.setMinimumWidth(280)

        context_container = QWidget()
        context_layout = QVBoxLayout(context_container)
        context_layout.setContentsMargins(14, 14, 14, 14)
        context_layout.setSpacing(18)

        # Section 1: Sources Attachées
        lbl_sources_title = QLabel("SOURCES ATTACHÉES")
        lbl_sources_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        context_layout.addWidget(lbl_sources_title)

        self.sources_list = QListWidget()
        self.sources_list.setStyleSheet(f"""
            QListWidget {{
                background-color: #1a1d24;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        self.sources_list.setFixedHeight(110)
        context_layout.addWidget(self.sources_list)

        self.btn_add_context = SecondaryButton("Ajouter un contexte")
        self.btn_add_context.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))
        self.btn_add_context.setStyleSheet("border-style: dashed; padding: 6px;")
        self.btn_add_context.clicked.connect(self._on_add_context)
        context_layout.addWidget(self.btn_add_context)

        # Section 2: Instructions Système
        lbl_sys_title = QLabel("INSTRUCTIONS SYSTÈME")
        lbl_sys_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        context_layout.addWidget(lbl_sys_title)

        self.sys_prompt_card = QFrame()
        self.sys_prompt_card.setStyleSheet(f"""
            QFrame {{
                background-color: #1a1d24;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px;
            }}
        """)
        sys_layout = QVBoxLayout(self.sys_prompt_card)
        sys_layout.setContentsMargins(8, 8, 8, 8)

        self.sys_prompt_lbl = QLabel("\"Tu es un expert médical spécialisé en cardiologie. Ton but est d'optimiser l'apprentissage...\"")
        self.sys_prompt_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        self.sys_prompt_lbl.setWordWrap(True)
        sys_layout.addWidget(self.sys_prompt_lbl)

        context_layout.addWidget(self.sys_prompt_card)
        context_layout.addStretch()

        # Section 3: Mémoire de l'Agent
        lbl_mem_title = QLabel("MÉMOIRE DE L'AGENT")
        lbl_mem_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        context_layout.addWidget(lbl_mem_title)

        mem_box = QFrame()
        mem_box.setStyleSheet(f"""
            QFrame {{
                background-color: #1a1d24;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px;
            }}
        """)
        mem_layout = QVBoxLayout(mem_box)
        mem_layout.setContentsMargins(8, 8, 8, 8)
        mem_layout.setSpacing(6)

        self.lbl_tokens_usage = QLabel("Tokens Utilisés : 14,204")
        self.lbl_tokens_usage.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;")

        self.lbl_cards_modified = QLabel("Cartes Modifiées : 0")
        self.lbl_cards_modified.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; font-size: 12px;")

        mem_layout.addWidget(self.lbl_tokens_usage)
        mem_layout.addWidget(self.lbl_cards_modified)
        context_layout.addWidget(mem_box)

        self.btn_clear_memory = SecondaryButton("Vider la mémoire")
        self.btn_clear_memory.setIcon(load_phosphor_icon("ph.broom", color=DesignTokens.TEXT_PRIMARY))
        self.btn_clear_memory.clicked.connect(self._on_clear_memory)
        context_layout.addWidget(self.btn_clear_memory)

        self.context_panel.add_tab("Contexte Actif", context_container, "ph.bounding-box", closable=False)
        self.splitter.addWidget(self.context_panel)

        self.splitter.setSizes([750, 280])

    def _connect_signals(self) -> None:
        self.chat_input.textChanged.connect(self._on_input_text_changed)

    def refresh_data(self) -> None:
        """Rafraîchit les modèles, decks et agents depuis Peewee."""
        try:
            self.model_selector.blockSignals(True)
            self.model_selector.clear()
            engines = list(LLMConfigModel.select())
            if engines:
                for eg in engines:
                    self.model_selector.addItem(eg.name, userData=eg)
            else:
                self.model_selector.addItem("Claude 3.5 Sonnet")
                self.model_selector.addItem("GPT-4o")
            self.model_selector.blockSignals(False)

            self.refresh_context_list()

            agent = AgentModel.get_or_none(AgentModel.name == "Archiviste Pédagogue")
            if agent and agent.system_prompt:
                self.sys_prompt_lbl.setText(f'"{agent.system_prompt[:120]}..."')

        except Exception as e:
            logger.warning("Erreur refresh_data consultant_view: %s", e)

    def is_dirty(self) -> bool:
        return False

    def refresh_context_list(self) -> None:
        """Met à jour l'affichage des éléments de contexte attachés."""
        self.sources_list.clear()
        if not self.active_context:
            item = QListWidgetItem("Aucun contexte attaché")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.sources_list.addItem(item)
            return

        for ctx_id in self.active_context:
            display_text = "Inconnu"
            if ctx_id.startswith("deck_"):
                try:
                    d_id = int(ctx_id.split("_")[1])
                    deck = DeckModel.get_or_none(DeckModel.id == d_id)
                    display_text = f"🎴 {deck.name} (Deck)" if deck else "Deck inconnu"
                except Exception:
                    display_text = "Deck inconnu"
            elif ctx_id.startswith("doc_"):
                try:
                    d_id = int(ctx_id.split("_")[1])
                    doc = DocumentModel.get_or_none(DocumentModel.id == d_id)
                    display_text = f"📄 {doc.title} (Doc)" if doc else "Doc inconnu"
                except Exception:
                    display_text = "Doc inconnu"

            self.sources_list.addItem(display_text)

    def _insert_initial_messages(self) -> None:
        """Insère les messages de démonstration conformes à la maquette."""
        msg_user = "Peux-tu analyser mon deck <b>'Cardio_P3'</b> et me suggérer des améliorations ? " "J'ai l'impression qu'il manque des tags pertinents et certaines cartes me semblent trop longues."
        msg_ai = (
            "Bien sûr ! J'ai analysé votre deck <b>'Cardio_P3'</b> (142 cartes trouvées).<br><br>"
            "<b>1. Structure et Longueur des Cartes</b><br>"
            "J'ai détecté <b>15 cartes</b> qui dépassent la longueur recommandée (plus de 50 mots au verso).<br><br>"
            "<b>2. Suggestions de Tags</b><br>"
            "Actuellement, le deck n'a que le tag <code>#Cardio</code>. Voici quelques sous-tags recommandés :<br>"
            "<span style='color: #a78bfa; font-weight: bold;'>#Pathologie/IC &nbsp; #ECG/Anormal &nbsp; #Pharma/Diurétiques</span>"
        )

        w1 = ChatMessageWidget("Vous", msg_user, is_user=True)
        w2 = ChatMessageWidget("AnkiForge AI", msg_ai, is_user=False)

        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, w1)
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, w2)

    @Slot()
    def _on_input_text_changed(self) -> None:
        text = self.chat_input.toPlainText()
        tokens = int(len(text.split()) * 1.3)
        self.tokens_badge.setText(f"{tokens} tokens")

    @Slot(str)
    def _on_quick_prompt_clicked(self, prompt_text: str) -> None:
        self.chat_input.setPlainText(prompt_text)
        self.chat_input.setFocus()

    @Slot()
    def _on_add_context(self) -> None:
        """Affiche un menu permettant d'attacher un Deck ou un Document au contexte IA (Master pattern)."""
        menu = QMenu(self)

        menu_decks = menu.addMenu("🎴 Attacher un Paquet (Deck)")
        decks = list(DeckModel.select())
        if decks:
            for d in decks:
                action = QAction(d.name, self)
                action.triggered.connect(lambda _, deck_id=d.id: self._attach_context(f"deck_{deck_id}"))
                menu_decks.addAction(action)
        else:
            no_deck = QAction("Aucun paquet disponible", self)
            no_deck.setEnabled(False)
            menu_decks.addAction(no_deck)

        menu_docs = menu.addMenu("📄 Attacher un Document")
        docs = list(DocumentModel.select())
        if docs:
            for doc in docs:
                action = QAction(doc.title, self)
                action.triggered.connect(lambda _, doc_id=doc.id: self._attach_context(f"doc_{doc_id}"))
                menu_docs.addAction(action)
        else:
            no_doc = QAction("Aucun document disponible", self)
            no_doc.setEnabled(False)
            menu_docs.addAction(no_doc)

        menu.exec(self.btn_add_context.mapToGlobal(self.btn_add_context.rect().bottomLeft()))

    def _attach_context(self, ctx_id: str) -> None:
        if ctx_id not in self.active_context:
            self.active_context.append(ctx_id)
            self.refresh_context_list()
            show_toast(self, "Contexte attaché avec succès !")

    @Slot()
    def _on_clear_memory(self) -> None:
        self.active_context.clear()
        self.refresh_context_list()
        self.used_tokens_count = 0
        self.modified_cards_count = 0
        self.lbl_tokens_usage.setText("Tokens Utilisés : 0")
        self.lbl_cards_modified.setText("Cartes Modifiées : 0")
        show_toast(self, "Mémoire de l'agent réinitialisée avec succès.")

    def _build_context_data(self) -> dict[str, list[dict[str, Any]]]:
        """Extrait le contexte réel depuis la base Peewee (Logique master)."""
        data: dict[str, list[dict[str, Any]]] = {"documents": [], "paquets": []}

        for ctx_id in self.active_context:
            if ctx_id.startswith("doc_"):
                try:
                    d_id = int(ctx_id.split("_")[1])
                    doc = DocumentModel.get_or_none(DocumentModel.id == d_id)
                    if doc:
                        data["documents"].append({"titre": doc.title, "contenu": getattr(doc, "content", "")})
                except Exception:
                    pass  # nosec B110

            elif ctx_id.startswith("deck_"):
                try:
                    d_id = int(ctx_id.split("_")[1])
                    deck = DeckModel.get_or_none(DeckModel.id == d_id)
                    if deck:
                        notes_data = []
                        query = NoteModel.select().join(CardModel).where(CardModel.deck == deck).distinct().limit(100)
                        for note in query:
                            v = NoteVersionModel.get_or_none(note=note, is_active=True)
                            if v and v.content:
                                try:
                                    notes_data.append(json.loads(v.content))
                                except Exception:
                                    notes_data.append({"content": v.content})
                        data["paquets"].append({"nom": deck.name, "notes": notes_data})
                except Exception:
                    pass  # nosec B110

        return data

    @Slot()
    def _on_send_clicked(self) -> None:
        user_text = self.chat_input.toPlainText().strip()
        if not user_text:
            return

        # 1. Ajouter le message utilisateur dans le fil
        user_msg = ChatMessageWidget("Vous", user_text, is_user=True)
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, user_msg)
        self.chat_input.clear()

        # Scroll automatique vers le bas
        QApplication.processEvents()
        self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum())

        # 2. Extraction des données contextuelles réelles (master pattern)
        context_data = self._build_context_data()

        selected_engine = self.model_selector.currentData()
        ai_provider = None
        if self.ai_manager:
            if selected_engine and isinstance(selected_engine, LLMConfigModel) and hasattr(self.ai_manager, "create_provider_from_config"):
                try:
                    ai_provider = self.ai_manager.create_provider_from_config(selected_engine)
                except Exception:
                    pass  # nosec B110
            if not ai_provider and hasattr(self.ai_manager, "get_active_provider"):
                try:
                    ai_provider = self.ai_manager.get_active_provider()
                except Exception:
                    pass  # nosec B110

        self.btn_send.setEnabled(False)
        self.lbl_chat_status.setText("⏳ Extraction du contexte et analyse IA...")

        self.worker = ConsultantWorker(ai_provider=ai_provider, context_data=context_data, instruction=user_text)
        self.worker.progress.connect(self._on_ai_progress)
        self.worker.finished_signal.connect(self._on_ai_response)
        self.worker.error_signal.connect(self._on_ai_error)
        self.worker.start()

    @Slot(str)
    def _on_ai_progress(self, msg: str) -> None:
        self.lbl_chat_status.setText(f"⏳ {msg}")

    @Slot(str)
    def _on_ai_response(self, response: str) -> None:
        self.btn_send.setEnabled(True)
        self.lbl_chat_status.setText("")

        ai_msg = ChatMessageWidget("AnkiForge AI", response, is_user=False)
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, ai_msg)

        QApplication.processEvents()
        self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum())

        self.used_tokens_count += int(len(response.split()) * 1.3)
        self.lbl_tokens_usage.setText(f"Tokens Utilisés : {self.used_tokens_count:,}")

    @Slot(str)
    def _on_ai_error(self, error: str) -> None:
        self.btn_send.setEnabled(True)
        self.lbl_chat_status.setText("❌ Erreur")
        err_msg = ChatMessageWidget("AnkiForge AI", f"⚠️ <b>Erreur IA :</b> {error}", is_user=False)
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, err_msg)


ConsultantTab = ConsultantView
