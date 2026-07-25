"""
Vue AI Consultant — Intégration Métier Complète (master) & UI 100% Maquette concept_ide.
- Suppression des messages mockés. Vrais inputs/outputs via ConsultantWorker & AIManager.
- Suggestions de prompts rapides (Quick Prompts) conservées et fonctionnelles.
- Panneau de contexte actif à droite raccordé aux vrais Decks, Documents et AgentModel (Jinja2 System Prompt).
- Sélecteur de Moteurs LLMConfigModel avec affichage display_name et auto-seeding.
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
    """Bulle de message conversationnel (Utilisateur ou Assistant IA) conforme à la maquette concept_ide."""

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
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        # Avatar
        self.avatar_lbl = QLabel()
        self.avatar_lbl.setFixedSize(34, 34)
        self.avatar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if is_user:
            self.avatar_lbl.setText("Vous")
            self.avatar_lbl.setStyleSheet(f"""
                QLabel {{
                    background-color: {DesignTokens.ACCENT_PRIMARY};
                    color: white;
                    font-weight: 700;
                    font-size: 11px;
                    border-radius: 17px;
                }}
            """)
            layout.addStretch()
        else:
            self.avatar_lbl.setPixmap(load_phosphor_icon("ph.robot", color="white").pixmap(18, 18))
            self.avatar_lbl.setStyleSheet(f"""
                QLabel {{
                    background-color: {DesignTokens.ACCENT_PRIMARY};
                    border-radius: 17px;
                }}
            """)

        # Bulle de contenu
        content_wrapper = QWidget()
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)

        # Header (Auteur + Heure)
        now_str = datetime.datetime.now().strftime("%H:%M")
        header_lbl = QLabel(
            f"<span style='font-weight: 600; color: {DesignTokens.TEXT_PRIMARY};'>{sender}</span> <span style='color: {DesignTokens.TEXT_MUTED}; font-size: 11px; margin-left: 6px;'>{now_str}</span>"
        )
        header_lbl.setStyleSheet("border: none; background: transparent;")

        # Corps du message
        body_card = QFrame()
        body_layout = QVBoxLayout(body_card)
        body_layout.setContentsMargins(16, 14, 16, 14)

        msg_body = QLabel()
        msg_body.setWordWrap(True)
        msg_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # Activer le rendu HTML/Markdown propre si présent
        if "<" in text and ">" in text:
            msg_body.setText(text)
        else:
            msg_body.setText(text.replace("\n", "<br>"))

        if is_user:
            body_card.setStyleSheet(f"""
                QFrame {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(99, 102, 241, 0.16), stop:1 rgba(139, 92, 246, 0.16));
                    border: 1px solid rgba(139, 92, 246, 0.35);
                    border-radius: {DesignTokens.RADIUS_MD}px;
                }}
            """)
            msg_body.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; font-size: 13px; line-height: 1.5;")
        else:
            body_card.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                }}
            """)
            msg_body.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; font-size: 13px; line-height: 1.5;")
            apply_shadow(body_card, blur=10, offset_y=2)

        body_layout.addWidget(msg_body)

        content_layout.addWidget(header_lbl)
        content_layout.addWidget(body_card)

        # Actions sous la réponse de l'IA
        if not is_user:
            actions_layout = QHBoxLayout()
            actions_layout.setContentsMargins(0, 6, 0, 0)
            actions_layout.setSpacing(6)

            btn_copy = IconButton("ph.copy", tooltip="Copier le texte", size=18)
            btn_copy.clicked.connect(lambda: (QApplication.clipboard().setText(text), show_toast(self, "Texte copié dans le presse-papiers !")))

            btn_like = IconButton("ph.thumbs-up", tooltip="Bonne réponse", size=18)
            btn_like.clicked.connect(lambda: show_toast(self, "Merci pour votre retour !"))

            btn_dislike = IconButton("ph.thumbs-down", tooltip="Mauvaise réponse", size=18)
            btn_dislike.clicked.connect(lambda: show_toast(self, "Retour enregistré."))

            actions_layout.addStretch()
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
    AI Consultant Studio — Vrais inputs/outputs et raccordement contextuel aux données réelles Peewee.
    """

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.worker: Optional[ConsultantWorker] = None
        self.used_tokens_count = 0
        self.modified_cards_count = 0
        self.active_context: list[str] = []  # Ex: ['deck_1', 'doc_2']

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()
        self._insert_welcome_message()

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
        self.model_selector.setMinimumWidth(180)
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

        # Quick Prompts Row (Boutons de suggestions rapides conservés)
        quick_prompts_layout = QHBoxLayout()
        quick_prompts_layout.setContentsMargins(0, 0, 0, 0)
        quick_prompts_layout.setSpacing(8)

        prompts = [
            ("ph.sparkle", "💡 Résumer le cours"),
            ("ph.magnifying-glass", "🔍 Chercher des doublons"),
            ("ph.cards", "🧠 Générer un QCM"),
            ("ph.tag", "🏷️ Suggérer des tags"),
        ]
        for icon, text in prompts:
            btn = SecondaryButton(text)
            btn.setIcon(load_phosphor_icon(icon, color=DesignTokens.ACCENT_PRIMARY))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 14px;
                    padding: 5px 12px;
                    font-size: 11px;
                    color: {DesignTokens.TEXT_PRIMARY};
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                }}
            """)
            btn.clicked.connect(lambda _, t=text: self._on_quick_prompt_clicked(t))
            quick_prompts_layout.addWidget(btn)

        quick_prompts_layout.addStretch()
        input_area_layout.addLayout(quick_prompts_layout)

        # Chat Box Premium Container (Maquette concept_ide)
        self.chat_box_frame = QFrame()
        self.chat_box_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_LG}px;
            }}
            QFrame:focus-within {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        apply_shadow(self.chat_box_frame, blur=14, offset_y=2)

        box_layout = QVBoxLayout(self.chat_box_frame)
        box_layout.setContentsMargins(14, 12, 14, 12)
        box_layout.setSpacing(8)

        # Badges de mentions actives du contexte
        self.mentions_layout = QHBoxLayout()
        self.mentions_layout.setContentsMargins(0, 0, 0, 0)
        self.mentions_layout.setSpacing(6)
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
        self.btn_attach = IconButton("ph.paperclip", tooltip="Joindre un fichier/contexte", size=22)
        self.btn_attach.clicked.connect(self._on_add_context)

        self.btn_mention = IconButton("ph.at", tooltip="Attacher un Paquet/Doc (@)", size=22)
        self.btn_mention.clicked.connect(self._on_add_context)

        self.btn_prompts_lib = IconButton("ph.books", tooltip="Bibliothèque de Prompts", size=22)
        self.btn_prompts_lib.clicked.connect(lambda: show_toast(self, "Bibliothèque de prompts en développement."))

        tools_layout.addWidget(self.btn_attach)
        tools_layout.addWidget(self.btn_mention)
        tools_layout.addWidget(self.btn_prompts_lib)

        box_footer.addLayout(tools_layout)
        box_footer.addStretch()

        self.tokens_badge = QLabel("0 tokens")
        self.tokens_badge.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; margin-right: 10px;")
        box_footer.addWidget(self.tokens_badge)

        # Bouton d'envoi circulaire 36x36px (Maquette concept_ide)
        self.btn_send = PrimaryButton("")
        self.btn_send.setIcon(load_phosphor_icon("ph.arrow-up", color="white"))
        self.btn_send.setFixedSize(36, 36)
        self.btn_send.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-radius: 18px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.ACCENT_HOVER};
            }}
        """)
        self.btn_send.clicked.connect(self._on_send_clicked)
        box_footer.addWidget(self.btn_send)

        box_layout.addLayout(box_footer)
        input_area_layout.addWidget(self.chat_box_frame)

        disclaimer_lbl = QLabel("L'IA peut faire des erreurs. Vérifiez toujours les cartes générées.")
        disclaimer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disclaimer_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; margin-top: 4px;")
        input_area_layout.addWidget(disclaimer_lbl)

        chat_layout.addWidget(input_area)

        self.chat_panel.add_tab("Chat", chat_container, "ph.chat-centered-text", closable=False)
        self.splitter.addWidget(self.chat_panel)

        # --- COL 2: Right Context Panel ---
        self.context_panel = IdePanel(detachable=True)
        self.context_panel.setMinimumWidth(280)

        context_container = QWidget()
        context_layout = QVBoxLayout(context_container)
        context_layout.setContentsMargins(14, 14, 14, 14)
        context_layout.setSpacing(16)

        # Section 1: Agent & Prompt Système
        lbl_agent_title = QLabel("INSTRUCTIONS SYSTÈME & AGENT")
        lbl_agent_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: 600; letter-spacing: 0.5px;")
        context_layout.addWidget(lbl_agent_title)

        self.agent_combo = StyledComboBox()
        self.agent_combo.currentIndexChanged.connect(self._on_agent_changed)
        context_layout.addWidget(self.agent_combo)

        self.sys_prompt_card = QFrame()
        self.sys_prompt_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 10px;
            }}
        """)
        sys_layout = QVBoxLayout(self.sys_prompt_card)
        sys_layout.setContentsMargins(4, 4, 4, 4)

        self.sys_prompt_lbl = QLabel('"Tu es un expert en mémorisation et création de cartes Anki..."')
        self.sys_prompt_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; line-height: 1.4;")
        self.sys_prompt_lbl.setWordWrap(True)
        sys_layout.addWidget(self.sys_prompt_lbl)
        context_layout.addWidget(self.sys_prompt_card)

        # Section 2: Sources Attachées (Maquette concept_ide)
        lbl_sources_title = QLabel("SOURCES ATTACHÉES")
        lbl_sources_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: 600; letter-spacing: 0.5px;")
        context_layout.addWidget(lbl_sources_title)

        self.sources_list = QListWidget()
        self.sources_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                outline: none;
                padding: 4px;
            }}
            QListWidget::item {{
                background: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                margin-bottom: 4px;
                padding: 6px;
            }}
        """)
        self.sources_list.setFixedHeight(120)
        context_layout.addWidget(self.sources_list)

        self.btn_add_context = SecondaryButton("Ajouter un contexte (@)")
        self.btn_add_context.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))
        self.btn_add_context.setStyleSheet(f"border-style: dashed; border-color: {DesignTokens.BORDER_COLOR}; padding: 6px;")
        self.btn_add_context.clicked.connect(self._on_add_context)
        context_layout.addWidget(self.btn_add_context)

        context_layout.addStretch()

        # Section 3: Mémoire de l'Agent (Maquette concept_ide)
        lbl_mem_title = QLabel("MÉMOIRE DE L'AGENT")
        lbl_mem_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: 600; letter-spacing: 0.5px;")
        context_layout.addWidget(lbl_mem_title)

        mem_box = QFrame()
        mem_box.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 10px;
            }}
        """)
        mem_layout = QVBoxLayout(mem_box)
        mem_layout.setContentsMargins(6, 6, 6, 6)
        mem_layout.setSpacing(8)

        row_tokens = QHBoxLayout()
        lbl_tok_title = QLabel("Tokens Utilisés")
        lbl_tok_title.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        self.lbl_tokens_usage = QLabel("0")
        self.lbl_tokens_usage.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; font-weight: bold;")
        row_tokens.addWidget(lbl_tok_title)
        row_tokens.addStretch()
        row_tokens.addWidget(self.lbl_tokens_usage)

        row_cards = QHBoxLayout()
        lbl_card_title = QLabel("Cartes Modifiées")
        lbl_card_title.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        self.lbl_cards_modified = QLabel("0")
        self.lbl_cards_modified.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; font-size: 11px; font-weight: bold;")
        row_cards.addWidget(lbl_card_title)
        row_cards.addStretch()
        row_cards.addWidget(self.lbl_cards_modified)

        mem_layout.addLayout(row_tokens)
        mem_layout.addLayout(row_cards)
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
        """Rafraîchit les modèles, decks, documents et agents depuis Peewee."""
        try:
            # 1. LLM Engines
            self.model_selector.blockSignals(True)
            self.model_selector.clear()
            engines = list(LLMConfigModel.select())
            if not engines:
                LLMConfigModel.create(
                    display_name="GPT-4o (OpenAI)",
                    provider="openai",
                    model_id="gpt-4o",
                    context_limit=128000,
                )
                LLMConfigModel.create(
                    display_name="Claude 3.5 Sonnet (Anthropic)",
                    provider="anthropic",
                    model_id="claude-3-5-sonnet-20240620",
                    context_limit=200000,
                )
                engines = list(LLMConfigModel.select())

            for eg in engines:
                display_name = getattr(eg, "display_name", getattr(eg, "name", str(eg)))
                self.model_selector.addItem(f"⚡ {display_name}", userData=eg)
            self.model_selector.blockSignals(False)

            # 2. Agents
            self.agent_combo.blockSignals(True)
            self.agent_combo.clear()
            agents = list(AgentModel.select())
            if agents:
                for ag in agents:
                    self.agent_combo.addItem(ag.name, userData=ag)
            else:
                ag_default = AgentModel.create(
                    name="Archiviste Pédagogue",
                    description="Expert en extraction atomique et mise en forme Anki.",
                    system_prompt="Tu es un expert en mémorisation, pédagogie et création de cartes Anki atomiques.",
                )
                self.agent_combo.addItem(ag_default.name, userData=ag_default)
            self.agent_combo.blockSignals(False)
            self._on_agent_changed()

            self.refresh_context_list()

        except Exception as e:
            logger.warning("Erreur refresh_data consultant_view: %s", e)

    def is_dirty(self) -> bool:
        return False

    @Slot()
    def _on_agent_changed(self) -> None:
        agent: Optional[AgentModel] = self.agent_combo.currentData()
        if agent and hasattr(agent, "system_prompt") and agent.system_prompt:
            prompt_snippet = agent.system_prompt[:150] + "..." if len(agent.system_prompt) > 150 else agent.system_prompt
            self.sys_prompt_lbl.setText(f'"{prompt_snippet}"')

    def refresh_context_list(self) -> None:
        """Met à jour l'affichage des éléments de contexte attachés."""
        self.sources_list.clear()

        # Update mentions badges in chat input box
        while self.mentions_layout.count() > 0:
            item = self.mentions_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        if not self.active_context:
            item = QListWidgetItem("Aucun contexte attaché (cliquez sur +)")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.sources_list.addItem(item)
            self.lbl_cards_modified.setText("0")
            return

        total_cards_in_context = 0

        for ctx_id in self.active_context:
            display_text = "Inconnu"
            if ctx_id.startswith("deck_"):
                try:
                    d_id = int(ctx_id.split("_")[1])
                    deck = DeckModel.get_or_none(DeckModel.id == d_id)
                    if deck:
                        card_count = CardModel.select().where(CardModel.deck == deck).count()
                        total_cards_in_context += card_count
                        display_text = f"🎴 Deck: {deck.name} ({card_count} cartes)"
                        badge = Badge(f"🎴 {deck.name}", variant="outline", color=DesignTokens.COLOR_GREEN)
                        self.mentions_layout.addWidget(badge)
                except Exception:
                    display_text = "Deck inconnu"
            elif ctx_id.startswith("doc_"):
                try:
                    d_id = int(ctx_id.split("_")[1])
                    doc = DocumentModel.get_or_none(DocumentModel.id == d_id)
                    if doc:
                        display_text = f"📄 Doc: {doc.title}"
                        badge = Badge(f"📄 {doc.title}", variant="outline", color=DesignTokens.COLOR_BLUE)
                        self.mentions_layout.addWidget(badge)
                except Exception:
                    display_text = "Doc inconnu"

            self.sources_list.addItem(display_text)

        self.mentions_layout.addStretch()
        self.lbl_cards_modified.setText(str(total_cards_in_context))

    def _insert_welcome_message(self) -> None:
        """Insère le message d'accueil initial de l'assistant IA."""
        msg_ai = (
            "Bonjour ! Je suis votre <b>Consultant IA AnkiForge</b>.<br><br>"
            "Je peux analyser vos cours, auditer la qualité de vos paquets Anki, détecter des doublons, "
            "ou suggérer des tags et des phrases à trous (Cloze).<br><br>"
            "💡 <i>Utilisez les raccourcis ci-dessous ou attachez vos paquets/documents via le bouton <b>+</b> ou <b>@</b>.</i>"
        )
        w = ChatMessageWidget("AnkiForge AI", msg_ai, is_user=False)
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, w)

    @Slot()
    def _on_input_text_changed(self) -> None:
        text = self.chat_input.toPlainText()
        tokens = int(len(text.split()) * 1.3)
        self.tokens_badge.setText(f"{tokens} tokens")

    @Slot(str)
    def _on_quick_prompt_clicked(self, prompt_text: str) -> None:
        # Enlève les émojis du bouton pour mettre une consigne propre
        clean_text = prompt_text.replace("💡 ", "").replace("🔍 ", "").replace("🧠 ", "").replace("🏷️ ", "")
        self.chat_input.setPlainText(clean_text)
        self.chat_input.setFocus()

    @Slot()
    def _on_add_context(self) -> None:
        """Affiche un menu permettant d'attacher un Deck ou un Document au contexte IA."""
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
        self.lbl_tokens_usage.setText("0")
        show_toast(self, "Contexte et mémoire réinitialisés avec succès.")

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

        # 2. Extraction des données contextuelles réelles
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
        self.lbl_chat_status.setText("⏳ Analyse contextuelle et génération de la réponse IA...")

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
        self.lbl_tokens_usage.setText(f"{self.used_tokens_count:,}")

    @Slot(str)
    def _on_ai_error(self, error: str) -> None:
        self.btn_send.setEnabled(True)
        self.lbl_chat_status.setText("")
        err_msg = ChatMessageWidget("AnkiForge AI", f"⚠️ <b>Information IA :</b> {error}", is_user=False)
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, err_msg)


ConsultantTab = ConsultantView
