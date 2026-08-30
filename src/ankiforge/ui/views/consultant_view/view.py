from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentModel,
    LLMConfigModel,
    NoteModel,
    NoteVersionModel,
    PersonaModel,
)
from ankiforge.repositories import PersonaRepository, SettingRepository
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
from ankiforge.ui.theme import DesignTokens, StyledMenu, apply_shadow
from ankiforge.ui.viewmodels import ConsultantViewModel
from ankiforge.ui.views.consultant_view.constants import apply_pill_style
from ankiforge.ui.views.consultant_view.widgets import (
    ChatMessageWidget,
)
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.event_bus import event_bus
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ConsultantView(QWidget):
    """
    AI Consultant Studio — Moteur ReAct, Intégration Outils Peewee/MCP et Visualisation Riche.
    """

    def __init__(self, ai_manager: Any | None = None, profile_name: str = "default", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.profile_name = profile_name
        self.persona_repo = PersonaRepository()
        self.setting_repo = SettingRepository()
        self.view_model = ConsultantViewModel(
            persona_repo=self.persona_repo,
            setting_repo=self.setting_repo,
            bus=event_bus,
            parent=self,
        )
        self.worker: ConsultantWorker | None = None
        self.used_tokens_count = 0
        self.modified_cards_count = 0
        self.active_context: list[str] = []

        self._current_thoughts: list[tuple[int, str]] = []
        self._current_tool_calls: list[tuple[str, str, str, bool]] = []

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()
        self._insert_welcome_message()

    def refresh_theme(self, profile: Any) -> None:
        if hasattr(self, "chat_panel") and hasattr(self.chat_panel, "refresh_theme"):
            self.chat_panel.refresh_theme(profile)
        if hasattr(self, "side_panel") and hasattr(self.side_panel, "refresh_theme"):
            self.side_panel.refresh_theme(profile)
        if hasattr(self, "lbl_chat_status"):
            self.lbl_chat_status.setStyleSheet(f"color: {profile.color_purple}; font-size: 11px; padding: 4px 16px; font-weight: bold;")
        if hasattr(self, "chat_messages_layout"):
            for i in range(self.chat_messages_layout.count()):
                item = self.chat_messages_layout.itemAt(i)
                if item and item.widget() and hasattr(item.widget(), "refresh_theme"):
                    item.widget().refresh_theme(profile)
        if hasattr(self, "btn_send") and hasattr(self.btn_send, "refresh_theme"):
            self.btn_send.refresh_theme(profile)

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)

        # ── 1. Panneau Principal de Chat ──────────────────────────────────────
        self.chat_panel = IdePanel(detachable=True)

        self.model_selector = StyledComboBox()
        self.model_selector.setMinimumWidth(180)
        self.chat_panel.add_header_widget(self.model_selector)
        self.chat_panel.add_header_separator()

        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        self.lbl_chat_status = QLabel("")
        self.lbl_chat_status.setStyleSheet(f"color: {DesignTokens.COLOR_PURPLE}; font-size: 11px; padding: 4px 16px; font-weight: bold;")
        chat_layout.addWidget(self.lbl_chat_status)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_scroll.setStyleSheet("background: transparent;")

        self.chat_scroll_widget = QWidget()
        self.chat_messages_layout = QVBoxLayout(self.chat_scroll_widget)
        self.chat_messages_layout.setContentsMargins(16, 16, 16, 16)
        self.chat_messages_layout.setSpacing(14)
        self.chat_messages_layout.addStretch()

        self.chat_scroll.setWidget(self.chat_scroll_widget)
        chat_layout.addWidget(self.chat_scroll, 1)

        input_area = QWidget()
        input_area_layout = QVBoxLayout(input_area)
        input_area_layout.setContentsMargins(16, 6, 16, 14)
        input_area_layout.setSpacing(8)

        quick_prompts_layout = QHBoxLayout()
        quick_prompts_layout.setContentsMargins(0, 0, 0, 0)
        quick_prompts_layout.setSpacing(6)

        prompts = [
            ("ph.chart-bar", "Rétention SRS", "Rétention SRS"),
            ("ph.magnifying-glass", "Cartes sangsues", "Cartes sangsues"),
            ("ph.palette", "Style CSS", "Style CSS"),
            ("ph.sparkle", "Audit Wozniak", "Audit Wozniak"),
            ("ph.wrench", "Outils MCP", "Outils MCP"),
        ]
        for icon, label, key in prompts:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIcon(load_phosphor_icon(icon, color=DesignTokens.ACCENT_PRIMARY))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 9999px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: 500;
                    color: {DesignTokens.TEXT_PRIMARY};
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                    color: #a5b4fc;
                }}
            """)
            btn.clicked.connect(lambda _, k=key: self._on_quick_prompt_clicked(k))
            quick_prompts_layout.addWidget(btn)

        quick_prompts_layout.addStretch()
        input_area_layout.addLayout(quick_prompts_layout)

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
        box_layout.setContentsMargins(14, 10, 14, 10)
        box_layout.setSpacing(6)

        self.mentions_layout = QHBoxLayout()
        self.mentions_layout.setContentsMargins(0, 0, 0, 0)
        self.mentions_layout.setSpacing(6)
        box_layout.addLayout(self.mentions_layout)

        self.chat_input = StyledTextEdit()
        self.chat_input.setFixedHeight(48)
        self.chat_input.setPlaceholderText("Posez une question, demandez un diagnostic de vos paquets ou tapez '@' pour attacher...")
        self.chat_input.setStyleSheet("border: none; background: transparent; font-size: 13px;")
        box_layout.addWidget(self.chat_input)

        box_footer = QHBoxLayout()
        box_footer.setContentsMargins(0, 0, 0, 0)

        tools_layout = QHBoxLayout()
        tools_layout.setSpacing(4)
        self.btn_attach = IconButton("ph.paperclip", tooltip="Attacher un Paquet ou Document (@)", size=22)
        self.btn_attach.clicked.connect(self._on_add_context)

        self.btn_mention = IconButton("ph.at", tooltip="Attacher un Paquet/Doc (@)", size=22)
        self.btn_mention.clicked.connect(self._on_add_context)

        tools_layout.addWidget(self.btn_attach)
        tools_layout.addWidget(self.btn_mention)
        box_footer.addLayout(tools_layout)
        box_footer.addStretch()

        self.tokens_badge = QLabel("0 tokens")
        self.tokens_badge.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; margin-right: 10px;")
        box_footer.addWidget(self.tokens_badge)

        self.btn_send = PrimaryButton("")
        self.btn_send.setIcon(load_phosphor_icon("ph.arrow-up", color="white"))
        self.btn_send.setFixedSize(34, 34)
        self.btn_send.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-radius: 17px;
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

        disclaimer_lbl = QLabel("Le Consultant IA interroge directement votre base de données locale AnkiForge de manière sécurisée.")
        disclaimer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disclaimer_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        input_area_layout.addWidget(disclaimer_lbl)

        chat_layout.addWidget(input_area)

        self.chat_panel.add_tab("Chat Consultant", chat_container, "ph.chat-centered-text", closable=False)
        self.splitter.addWidget(self.chat_panel)

        # ── 2. Panneau de Contexte Actif ──────────────────────────────────────
        self.context_panel = IdePanel(detachable=True)
        self.context_panel.setMinimumWidth(280)

        context_container = QWidget()
        context_layout = QVBoxLayout(context_container)
        context_layout.setContentsMargins(12, 12, 12, 12)
        context_layout.setSpacing(14)

        lbl_agent_title = QLabel("PERSONA & RÔLE DU CONSULTANT")
        lbl_agent_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        context_layout.addWidget(lbl_agent_title)

        self.persona_combo = StyledComboBox()
        self.persona_combo.currentIndexChanged.connect(self._on_agent_changed)
        context_layout.addWidget(self.persona_combo)

        self.sys_prompt_card = QFrame()
        self.sys_prompt_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px;
            }}
            QFrame QLabel {{
                background: transparent;
            }}
        """)
        sys_layout = QVBoxLayout(self.sys_prompt_card)
        sys_layout.setContentsMargins(4, 4, 4, 4)

        self.sys_prompt_lbl = QLabel('"Expert en analyse de rétention Anki et création de modèles de cartes."')
        self.sys_prompt_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; line-height: 1.4;")
        self.sys_prompt_lbl.setWordWrap(True)
        sys_layout.addWidget(self.sys_prompt_lbl)
        context_layout.addWidget(self.sys_prompt_card)

        lbl_sources_title = QLabel("PAQUETS & DOCUMENTS ATTACHÉS")
        lbl_sources_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
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
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self.sources_list.setFixedHeight(110)
        context_layout.addWidget(self.sources_list)

        self.btn_add_context = SecondaryButton("Ajouter un contexte (@)")
        self.btn_add_context.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))
        self.btn_add_context.setStyleSheet(f"border-style: dashed; border-color: {DesignTokens.BORDER_COLOR}; padding: 6px;")
        self.btn_add_context.clicked.connect(self._on_add_context)
        context_layout.addWidget(self.btn_add_context)

        context_layout.addStretch()

        lbl_mem_title = QLabel("MÉMOIRE DE LA SESSION")
        lbl_mem_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        context_layout.addWidget(lbl_mem_title)

        mem_box = QFrame()
        mem_box.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px;
            }}
            QFrame QLabel {{
                background: transparent;
            }}
        """)
        mem_layout = QVBoxLayout(mem_box)
        mem_layout.setContentsMargins(6, 6, 6, 6)
        mem_layout.setSpacing(6)

        row_tokens = QHBoxLayout()
        lbl_tok_title = QLabel("Tokens Estimés")
        lbl_tok_title.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        self.lbl_tokens_usage = QLabel("0")
        self.lbl_tokens_usage.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; font-weight: bold;")
        row_tokens.addWidget(lbl_tok_title)
        row_tokens.addStretch()
        row_tokens.addWidget(self.lbl_tokens_usage)

        row_cards = QHBoxLayout()
        lbl_card_title = QLabel("Cartes dans le Contexte")
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

        context_scroll = QScrollArea()
        context_scroll.setWidgetResizable(True)
        context_scroll.setFrameShape(QFrame.Shape.NoFrame)
        context_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        context_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; } QScrollBar { width: 0px; }")
        context_scroll.setWidget(context_container)

        self.context_panel.add_tab("Contexte Actif", context_scroll, "ph.bounding-box", closable=False)
        self.splitter.addWidget(self.context_panel)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setSizes([750, 280])

    def _connect_signals(self) -> None:
        self.chat_input.textChanged.connect(self._on_input_text_changed)

    def refresh_data(self) -> None:
        try:
            self.model_selector.blockSignals(True)
            self.model_selector.clear()
            engines = list(LLMConfigModel.select())
            for eg in engines:
                display_name = getattr(eg, "display_name", getattr(eg, "provider", str(eg)))
                self.model_selector.addItem(f"⚡ {display_name}", userData=eg)
            self.model_selector.blockSignals(False)

            self.persona_combo.blockSignals(True)
            self.persona_combo.clear()
            agents = list(PersonaModel.select().where(PersonaModel.persona_type.in_(["mcp", "universal"])).order_by(PersonaModel.name.asc()))
            if not agents:
                ag_default = PersonaModel.create(
                    name="Consultant Analytique",
                    description="Expert en diagnostic de collection, statistiques SRS et génération de styles.",
                    system_prompt="Tu es un Consultant IA expert en analyse de rétention Anki, diagnostic SRS et optimisation de modèles de cartes.",
                    persona_type="mcp",
                    output_format="text",
                )
                agents = [ag_default]

            for ag in agents:
                p_type = getattr(ag, "persona_type", "mcp")
                type_prefix = "🤝 " if p_type == "mcp" else "🌐 "
                self.persona_combo.addItem(f"{type_prefix}{ag.name}", userData=ag)

            self.persona_combo.blockSignals(False)
            self._on_agent_changed()
            self.refresh_context_list()

        except Exception as e:
            logger.warning("Erreur refresh_data consultant_view: %s", e)

    def is_dirty(self) -> bool:
        return False

    @Slot()
    def _on_agent_changed(self) -> None:
        agent: PersonaModel | None = self.persona_combo.currentData()
        if agent and hasattr(agent, "system_prompt") and agent.system_prompt:
            prompt_str = str(agent.system_prompt)
            prompt_snippet = prompt_str[:140] + "..." if len(prompt_str) > 140 else prompt_str
            self.sys_prompt_lbl.setText(f'"{prompt_snippet}"')

    def refresh_context_list(self) -> None:
        self.sources_list.clear()

        while self.mentions_layout.count() > 0:
            layout_item = self.mentions_layout.takeAt(0)
            if layout_item:
                w = layout_item.widget()
                if w:
                    w.deleteLater()

        if not self.active_context:
            empty_item = QListWidgetItem("Aucun contexte attaché (cliquez sur +)")
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.sources_list.addItem(empty_item)
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
                        badge = Badge(f"🎴 {deck.name}", variant="status")
                        apply_pill_style(badge, DesignTokens.COLOR_GREEN)
                        self.mentions_layout.addWidget(badge)
                except Exception:
                    display_text = "Deck inconnu"
            elif ctx_id.startswith("doc_"):
                try:
                    d_id = int(ctx_id.split("_")[1])
                    doc = DocumentModel.get_or_none(DocumentModel.id == d_id)
                    if doc:
                        display_text = f"📄 Doc: {doc.title}"
                        badge = Badge(f"📄 {doc.title}", variant="status")
                        apply_pill_style(badge, DesignTokens.COLOR_BLUE)
                        self.mentions_layout.addWidget(badge)
                except Exception:
                    display_text = "Doc inconnu"

            self.sources_list.addItem(display_text)

        self.mentions_layout.addStretch()
        self.lbl_cards_modified.setText(str(total_cards_in_context))

    def _insert_welcome_message(self) -> None:
        msg_ai = (
            "Bonjour ! Je suis votre <b>Consultant IA AnkiForge</b> raccordé à vos outils ReAct & MCP.<br><br>"
            "Je peux inspecter en direct vos métriques SRS (cartes sangsues, taux d'oubli), analyser la structure de vos cours, "
            "optimiser les modèles de cartes ou exécuter des scripts Python déterministes.<br><br>"
            "💡 <i>Cliquez sur les suggestions rapides ci-dessous ou attachez vos paquets via le bouton <b>+</b> ou <b>@</b>.</i>"
        )
        w = ChatMessageWidget("AnkiForge AI", msg_ai, is_user=False)
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, w)

    @Slot()
    def _on_input_text_changed(self) -> None:
        text = self.chat_input.toPlainText()
        tokens = int(len(text.split()) * 1.3)
        self.tokens_badge.setText(f"{tokens} tokens")

    @Slot(str)
    def _on_quick_prompt_clicked(self, key: str) -> None:
        prompt_presets = {
            "Rétention SRS": "Analyse en détail la rétention SRS et la stabilité FSRS-4.5 de mes paquets.",
            "Cartes sangsues": "Détecte les cartes sangsues (lapses élevés) et propose des reformulations atomiques.",
            "Style CSS": "Génère un style CSS moderne pour mon modèle de carte actuel.",
            "Audit Wozniak": "Effectue un audit de formulation minimale basé sur les 20 règles de Piotr Wozniak.",
            "Outils MCP": "Quels outils Python et requêtes Peewee sont disponibles pour le consultant ?",
        }
        if key in prompt_presets:
            resolved_text = prompt_presets[key]
        else:
            clean_text = key
            for prefix in ["📊 ", "🔍 ", "🎨 ", "⚡ ", "🛠️ "]:
                clean_text = clean_text.replace(prefix, "")
            resolved_text = clean_text
        self.chat_input.setPlainText(resolved_text)
        self.chat_input.setFocus()

    @Slot()
    def _on_add_context(self) -> None:
        menu = StyledMenu(self)

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
                            v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
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

        user_msg = ChatMessageWidget("Vous", user_text, is_user=True)
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, user_msg)
        self.chat_input.clear()

        QApplication.processEvents()
        self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum())

        context_data = self._build_context_data()
        selected_engine = self.model_selector.currentData()
        selected_persona = self.persona_combo.currentData()

        self.btn_send.setEnabled(False)
        self.lbl_chat_status.setText("⏳ Analyse ReAct et exécution d'outils en cours...")

        self._current_thoughts.clear()
        self._current_tool_calls.clear()

        ai_provider = None
        if self.ai_manager and hasattr(self.ai_manager, "create_provider_from_config") and selected_engine:
            try:
                ai_provider = self.ai_manager.create_provider_from_config(selected_engine)
            except Exception as e:
                logger.warning("Impossible de créer le provider : %s", e)

        self.worker = ConsultantWorker(
            llm_config=selected_engine,
            persona=selected_persona,
            context_data=context_data,
            instruction=user_text,
            ai_provider=ai_provider,
        )
        self.worker.thought_emitted.connect(self._on_thought_received)
        self.worker.tool_call_emitted.connect(self._on_tool_call_received)
        self.worker.progress.connect(self._on_ai_progress)
        self.worker.finished_signal.connect(self._on_ai_response)
        self.worker.error_signal.connect(self._on_ai_error)
        self.worker.start()

    @Slot(int, str)
    def _on_thought_received(self, step: int, thought: str) -> None:
        self._current_thoughts.append((step, thought))

    @Slot(str, str, str, bool)
    def _on_tool_call_received(self, tool_name: str, args_str: str, result_str: str, is_error: bool) -> None:
        self._current_tool_calls.append((tool_name, args_str, result_str, is_error))

    @Slot(str)
    def _on_ai_progress(self, msg: str) -> None:
        self.lbl_chat_status.setText(f"⏳ {msg}")

    @Slot(str)
    def _on_ai_response(self, response: str) -> None:
        self.btn_send.setEnabled(True)
        self.lbl_chat_status.setText("")

        ai_msg = ChatMessageWidget(
            sender="AnkiForge AI",
            text=response,
            is_user=False,
            thoughts=list(self._current_thoughts),
            tool_calls=list(self._current_tool_calls),
        )
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, ai_msg)

        QApplication.processEvents()
        self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum())

        self.used_tokens_count += int(len(response.split()) * 1.3) + 120
        self.lbl_tokens_usage.setText(f"{self.used_tokens_count:,}")

    @Slot(str)
    def _on_ai_error(self, error: str) -> None:
        self.btn_send.setEnabled(True)
        self.lbl_chat_status.setText("")
        err_msg = ChatMessageWidget(
            sender="AnkiForge AI",
            text=f"⚠️ <b>Erreur Consultant IA :</b> {error}",
            is_user=False,
            thoughts=list(self._current_thoughts),
            tool_calls=list(self._current_tool_calls),
        )
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, err_msg)


ConsultantTab = ConsultantView
