from __future__ import annotations

import json
import logging
import re
from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QAction, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    CardModel,
    ConsultantMessageModel,
    ConsultantSessionModel,
    DeckModel,
    DocumentModel,
    LLMConfigModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    PersonaModel,
    db,
)
from ankiforge.repositories import PersonaRepository, SettingRepository
from ankiforge.services.ai.consultant_engine import robust_json_loads
from ankiforge.services.ai.context_compactor import ContextCompactor
from ankiforge.services.workers.consultant_worker import ConsultantWorker
from ankiforge.ui.components import (
    Badge,
    IconButton,
    IdePanel,
    PrimaryButton,
    StyledComboBox,
)
from ankiforge.ui.theme import DesignTokens, StyledMenu, apply_shadow
from ankiforge.ui.viewmodels import ConsultantViewModel
from ankiforge.ui.views.consultant_view.constants import apply_pill_style
from ankiforge.ui.views.consultant_view.widgets import (
    ChatMessageWidget,
    ConsultantChatInput,
    ConsultantSessionSidebar,
    ContextHubWidget,
    WorkspaceInspectorWidget,
)
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.event_bus import event_bus
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


def extract_card_proposal_from_text(response: str, user_query: str = "") -> dict[str, Any] | None:
    """
    Extrait une proposition de refactorisation ou scission de carte depuis le texte retourné par l'IA.
    Permet d'activer le diff et le Garde-Fou même si le LLM a renvoyé du JSON brut dans sa réponse.
    """

    def _fetch_original(nid: int | None) -> dict[str, Any]:
        if not nid:
            return {}
        try:
            n = NoteModel.get_or_none(NoteModel.id == nid)
            if n:
                act_v = n.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                if act_v and act_v.content:
                    return robust_json_loads(act_v.content)
        except Exception:
            pass
        return {}

    # 1. Chercher les blocs ```json ... ``` ou ``` ... ```
    json_matches = re.findall(r"```(?:json)?\s*([\{\[][\s\S]*?[\}\]])\s*```", response)
    for match in json_matches:
        try:
            parsed = robust_json_loads(match.strip())
            if isinstance(parsed, dict):
                if parsed.get("status") == "staged_diff":
                    if not parsed.get("original") and parsed.get("note_id"):
                        parsed["original"] = _fetch_original(parsed["note_id"])
                    return parsed
                explanation = parsed.get("explanation") or parsed.get("reasoning") or parsed.get("justification") or ""
                if "new_fields_json" in parsed or "new_fields" in parsed:
                    nf = parsed.get("new_fields_json") or parsed.get("new_fields")
                    nf_parsed = robust_json_loads(nf) if isinstance(nf, str) else nf
                    note_id = parsed.get("note_id")
                    orig = parsed.get("original") or _fetch_original(note_id)
                    return {
                        "status": "staged_diff",
                        "type": "card",
                        "note_id": note_id,
                        "title": f"Proposition de Refactorisation {f'— Note #{note_id}' if note_id else ''}",
                        "original": orig,
                        "modified": nf_parsed,
                        "explanation": explanation,
                    }
                if any(k in parsed for k in ["Front", "Back", "Recto", "Verso", "question", "reponse"]):
                    note_id = parsed.get("note_id")
                    if not note_id:
                        id_m = re.search(r"(?:Note|note|carte|Carte)\s*#?(\d+)", response + " " + user_query)
                        if id_m:
                            note_id = int(id_m.group(1))
                    orig = parsed.get("original") or _fetch_original(note_id)
                    return {
                        "status": "staged_diff",
                        "type": "card",
                        "note_id": note_id,
                        "title": f"Proposition de Refactorisation {f'— Note #{note_id}' if note_id else ''}",
                        "original": orig,
                        "modified": parsed,
                        "explanation": explanation,
                    }
            elif isinstance(parsed, list) and parsed:
                if all(isinstance(item, dict) for item in parsed):
                    id_m = re.search(r"(?:Note|note|carte|Carte)\s*#?(\d+)", response + " " + user_query)
                    note_id = int(id_m.group(1)) if id_m else None
                    orig = _fetch_original(note_id)
                    return {
                        "status": "staged_diff",
                        "type": "split",
                        "note_id": note_id,
                        "title": f"Proposition de Scission ({len(parsed)} cartes atomiques)",
                        "original": orig,
                        "modified": parsed,
                        "explanation": f"Scission en {len(parsed)} cartes atomiques.",
                    }
        except Exception:
            continue

    # 2. Chercher du JSON brut sans markdown
    try:
        raw_json_m = re.search(r'\{\s*"(?:Front|Recto|question|new_fields)"[\s\S]*?\}', response)
        if raw_json_m:
            parsed = json.loads(raw_json_m.group(0))
            id_m = re.search(r"(?:Note|note|carte|Carte)\s*#?(\d+)", response + " " + user_query)
            note_id = int(id_m.group(1)) if id_m else None
            orig = _fetch_original(note_id)
            explanation = parsed.get("explanation") or parsed.get("reasoning") or ""
            return {
                "status": "staged_diff",
                "type": "card",
                "note_id": note_id,
                "title": f"Proposition de Refactorisation {f'— Note #{note_id}' if note_id else ''}",
                "original": orig,
                "modified": parsed,
                "explanation": explanation,
            }
    except Exception:
        pass

    return None


class ContextPillBadge(Badge):
    """Badge de contexte au-dessus de l'input avec suppression sécurisée par clic sur ✕."""

    def __init__(self, text: str, context_id: str, on_remove: Any, is_committed: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(text, variant="status", parent=parent)
        self.context_id = context_id
        self.on_remove = on_remove
        self.is_committed = is_committed
        if not is_committed:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip("Cliquer pour retirer du contexte")
        else:
            self.setToolTip("Source ancrée dans l'historique de cette discussion")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            if not self.is_committed and self.on_remove:
                from PySide6.QtCore import QTimer

                ctx = self.context_id
                cb = self.on_remove
                QTimer.singleShot(0, lambda: cb(ctx))
            return
        super().mousePressEvent(event)


class ConsultantView(QWidget):
    """
    AI Consultant Studio — Streaming Live, Stop Button, Sessions Persistées, Garde-Fous et Diff Viewer.
    """

    request_navigation = Signal(str, object)

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
        self._active_ai_message: ChatMessageWidget | None = None
        self._active_staged_diff: dict[str, Any] | None = None
        self.used_tokens_count = 0
        self.modified_cards_count = 0
        self.active_context: list[str] = []
        self.committed_context: set[str] = set()

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()
        if not self.view_model.messages:
            self._insert_welcome_message()

    def refresh_theme(self, profile: Any) -> None:
        if hasattr(self, "session_sidebar") and hasattr(self.session_sidebar, "refresh_theme"):
            self.session_sidebar.refresh_theme(profile)
        if hasattr(self, "chat_panel") and hasattr(self.chat_panel, "refresh_theme"):
            self.chat_panel.refresh_theme(profile)
        if hasattr(self, "context_panel") and hasattr(self.context_panel, "refresh_theme"):
            self.context_panel.refresh_theme(profile)
        if hasattr(self, "context_hub") and hasattr(self.context_hub, "refresh_theme"):
            self.context_hub.refresh_theme(profile)
        if hasattr(self, "workspace_inspector") and hasattr(self.workspace_inspector, "refresh_theme"):
            self.workspace_inspector.refresh_theme(profile)
        if hasattr(self, "lbl_chat_status"):
            self.lbl_chat_status.setStyleSheet(f"color: {profile.color_purple}; font-size: 11px; padding: 4px 16px; font-weight: bold;")
        if hasattr(self, "chat_messages_layout"):
            for i in range(self.chat_messages_layout.count()):
                item = self.chat_messages_layout.itemAt(i)
                if item and item.widget() and hasattr(item.widget(), "refresh_theme"):
                    item.widget().refresh_theme(profile)
        if hasattr(self, "btn_send") and hasattr(self.btn_send, "refresh_theme"):
            self.btn_send.refresh_theme(profile)
        if hasattr(self, "chat_inner_splitter"):
            self.chat_inner_splitter.setStyleSheet(f"""
                QSplitter::handle {{
                    background-color: {profile.border_color};
                    width: 1px;
                }}
            """)

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)

        # ── 1. Panneau Principal Central : Chat & Discussions ────────────────
        self.chat_panel = IdePanel(detachable=True)

        # Bouton toggle de la sidebar (intégré dans l'en-tête de l'onglet)
        self.btn_toggle_sidebar = IconButton("ph.sidebar-simple", tooltip="Afficher/Masquer l'historique des discussions", size=22)
        self.btn_toggle_sidebar.clicked.connect(self._toggle_sidebar)
        self.chat_panel.add_header_widget(self.btn_toggle_sidebar)
        self.chat_panel.add_header_separator()

        self.model_selector = StyledComboBox()
        self.model_selector.setMinimumWidth(160)
        self.chat_panel.add_header_widget(self.model_selector)
        self.chat_panel.add_header_separator()

        # Bouton toggle de l'inspecteur
        self.btn_toggle_inspector = IconButton("ph.brain", tooltip="Afficher/Masquer le Hub de Contexte", size=22)
        self.btn_toggle_inspector.clicked.connect(self._toggle_inspector)
        self.chat_panel.add_header_widget(self.btn_toggle_inspector)

        # Attributs préservés pour compatibilité ascendante
        self.session_selector = StyledComboBox()
        self.session_selector.setVisible(False)
        self.session_selector.currentIndexChanged.connect(self._on_session_selected)
        self.btn_new_chat = IconButton("ph.plus", size=22)
        self.btn_new_chat.setVisible(False)
        self.btn_new_chat.clicked.connect(self._on_new_chat_clicked)
        self.btn_session_menu = IconButton("ph.dots-three-vertical", size=22)
        self.btn_session_menu.setVisible(False)
        self.btn_session_menu.clicked.connect(self._on_session_menu_clicked)

        # Conteneur global de l'onglet comprenant la sidebar ET le flux conversationnel
        tab_container = QWidget()
        tab_layout = QHBoxLayout(tab_container)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        self.chat_inner_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.chat_inner_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {DesignTokens.BORDER_COLOR};
                width: 1px;
            }}
        """)
        tab_layout.addWidget(self.chat_inner_splitter)

        # ── 1.1 Sidebar des discussions intégrée dans l'onglet ──────────────
        self.session_sidebar = ConsultantSessionSidebar(self)
        self.chat_inner_splitter.addWidget(self.session_sidebar)

        # ── 1.2 Zone de discussion centrale ─────────────────────────────────
        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        self.lbl_chat_status = QLabel("")
        self.lbl_chat_status.setStyleSheet(f"color: {DesignTokens.COLOR_PURPLE}; font-size: 11px; padding: 4px 16px; font-weight: bold;")
        chat_layout.addWidget(self.lbl_chat_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(2)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"QProgressBar {{ background: transparent; border: none; }} QProgressBar::chunk {{ background-color: {DesignTokens.ACCENT_PRIMARY}; }}")
        self.progress_bar.hide()
        chat_layout.addWidget(self.progress_bar)

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
        input_area_layout.setContentsMargins(16, 4, 16, 8)
        input_area_layout.setSpacing(8)

        self.chat_box_frame = QFrame()
        self.chat_box_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_LG}px;
                background-clip: padding-box;
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

        # Zone de saisie riche avec gestion sécurisée de l'autocomplétion
        self.chat_input = ConsultantChatInput(self)
        self.chat_input.send_requested.connect(self._on_send_or_stop_clicked)
        self.chat_input.mention_completed.connect(self._on_mention_completed)
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
        self._set_send_button_mode(is_running=False)
        self.btn_send.clicked.connect(self._on_send_or_stop_clicked)
        box_footer.addWidget(self.btn_send)

        box_layout.addLayout(box_footer)
        input_area_layout.addWidget(self.chat_box_frame)

        disclaimer_lbl = QLabel("Le Consultant IA propose des refactorisations sous forme de diffs validables avant écriture en BDD.")
        disclaimer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disclaimer_lbl.setWordWrap(True)
        disclaimer_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; margin-top: 2px;")
        input_area_layout.addWidget(disclaimer_lbl)

        chat_layout.addWidget(input_area)

        self.chat_inner_splitter.addWidget(chat_container)
        self.chat_inner_splitter.setCollapsible(0, True)
        self.chat_inner_splitter.setCollapsible(1, False)
        self.chat_inner_splitter.setSizes([220, 780])

        self.chat_panel.add_tab("Consultant IA", tab_container, "ph.chat-centered-text", closable=False)
        self.splitter.addWidget(self.chat_panel)

        # ── 2. Panneau de Contexte & Cerveau de l'Agent IA (Droite) ─────────
        self.context_panel = IdePanel(detachable=True)
        self.context_panel.setMinimumWidth(340)

        self.context_hub = ContextHubWidget(self)
        self.context_hub.add_context_requested.connect(self._on_add_context)
        self.context_hub.context_removed.connect(self._remove_context)
        self.context_hub.compact_requested.connect(self._on_compact_requested)
        self.context_hub.action_triggered.connect(self._on_proactive_action_triggered)
        self.context_hub.persona_changed.connect(self._on_hub_persona_changed)

        self.persona_combo = self.context_hub.persona_combo
        self.sys_prompt_lbl = self.context_hub.lbl_system_directive

        # Stubs pour la compatibilité avec les tests unitaires existants
        self.sources_list = QListWidget()
        self.sources_list.hide()
        self.sources_list.itemDoubleClicked.connect(self._on_source_item_double_clicked)
        self.lbl_tokens_usage = QLabel("0")
        self.lbl_cards_in_context = QLabel("0")
        self.lbl_cards_modified = QLabel("0")
        self.workspace_inspector = WorkspaceInspectorWidget()
        self.workspace_inspector.next_step_requested.connect(self._on_next_step_clicked)
        self.workspace_inspector.action_applied.connect(self._on_workspace_action_applied)
        self.workspace_inspector.action_reverted.connect(self._on_workspace_action_reverted)

        self.context_panel.add_tab("Cerveau && Contexte", self.context_hub, "ph.brain", closable=False)

        self.splitter.addWidget(self.context_panel)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, True)
        self.splitter.setSizes([960, 360])
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)

    def _connect_signals(self) -> None:
        self.chat_input.textChanged.connect(self._on_input_text_changed)
        self.session_sidebar.session_selected.connect(self._on_sidebar_session_selected)
        self.session_sidebar.new_chat_requested.connect(self._on_new_chat_clicked)
        self.session_sidebar.session_renamed.connect(self._on_sidebar_session_renamed)
        self.session_sidebar.session_deleted.connect(self._on_sidebar_session_deleted)
        self.session_sidebar.session_exported.connect(self._on_sidebar_session_exported)
        self.view_model.sessions_list_updated.connect(self._on_sessions_list_updated)
        self.view_model.session_changed.connect(self._on_active_session_reloaded)
        self.view_model.stats_updated.connect(self._on_stats_updated)

    def _toggle_sidebar(self) -> None:
        """Bascule l'affichage de la barre latérale des discussions."""
        self.session_sidebar.setHidden(not self.session_sidebar.isHidden())

    def _toggle_inspector(self) -> None:
        """Bascule l'affichage du panneau d'inspection et diff."""
        self.context_panel.setHidden(not self.context_panel.isHidden())

    @Slot(int)
    def _on_sidebar_session_selected(self, session_id: int) -> None:
        self.view_model.switch_session(session_id)

    @Slot(int, str)
    def _on_sidebar_session_renamed(self, session_id: int, new_title: str) -> None:
        s = ConsultantSessionModel.get_or_none(ConsultantSessionModel.id == session_id)
        if s:
            s.title = new_title
            s.save()
            self.view_model.load_sessions()
            show_toast(self, "Discussion renommée.")

    @Slot(int)
    def _on_sidebar_session_deleted(self, session_id: int) -> None:
        s = ConsultantSessionModel.get_or_none(ConsultantSessionModel.id == session_id)
        if s:
            s.delete_instance(recursive=True)
            self.view_model.load_sessions()
            if self.view_model.sessions:
                self.view_model.switch_session(self.view_model.sessions[0].id)
            else:
                self.view_model.create_new_session()
            show_toast(self, "Discussion supprimée.")

    @Slot(int)
    def _on_sidebar_session_exported(self, session_id: int) -> None:
        s = ConsultantSessionModel.get_or_none(ConsultantSessionModel.id == session_id)
        if not s:
            return
        msgs = list(ConsultantMessageModel.select().where(ConsultantMessageModel.session == s).order_by(ConsultantMessageModel.created_at.asc()))
        export_lines = [f"# Discussion AnkiForge AI — {s.title}\n"]
        for m in msgs:
            r = "**Vous**" if m.role == "user" else "**AnkiForge AI**"
            export_lines.append(f"### {r}\n{m.content}\n")
        markdown_content = "\n".join(export_lines)
        QApplication.clipboard().setText(markdown_content)
        show_toast(self, "Discussion copiée dans le presse-papier en Markdown !")

    @Slot(int, int)
    def _on_stats_updated(self, tokens: int, cards: int) -> None:
        self.lbl_tokens_usage.setText(f"{tokens:,}")
        self.lbl_cards_modified.setText(str(cards))
        self.session_sidebar.update_metrics(tokens, cards)

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
                    name="Consultant Qualité & Wozniak",
                    description="Expert en diagnostic de collection, audit ergonomique Wozniak et refactorisation chirurgicale.",
                    system_prompt="Tu es un Consultant IA expert en analyse de rétention Anki, diagnostic SRS et formulation de cartes ergonomiques (20 règles de Piotr Wozniak).",
                    persona_type="mcp",
                    output_format="text",
                )
                agents = [ag_default]

            for ag in agents:
                p_type = getattr(ag, "persona_type", "mcp")
                type_prefix = "🤝 " if p_type == "mcp" else "🌐 "
                self.persona_combo.addItem(f"{type_prefix}{ag.name}", userData=ag)

            self.persona_combo.blockSignals(False)
            if hasattr(self, "context_hub"):
                self.context_hub.set_personas(agents, active_persona=self.persona_combo.currentData())
            self._on_agent_changed()

            self.view_model.load_sessions()
            self.refresh_context_list()

        except Exception as e:
            logger.warning("Erreur refresh_data consultant_view: %s", e)

    def is_dirty(self) -> bool:
        return False

    @Slot(list)
    def _on_sessions_list_updated(self, sessions: list[ConsultantSessionModel]) -> None:
        active_id = self.view_model.current_session.id if self.view_model.current_session else None
        self.session_sidebar.set_sessions(sessions, active_id=active_id)
        self.session_selector.blockSignals(True)
        self.session_selector.clear()
        for s in sessions:
            self.session_selector.addItem(f"💬 {s.title}", userData=s.id)
        if self.view_model.current_session:
            idx = self.session_selector.findData(self.view_model.current_session.id)
            if idx != -1:
                self.session_selector.setCurrentIndex(idx)
        self.session_selector.blockSignals(False)

    @Slot()
    def _on_session_selected(self) -> None:
        s_id = self.session_selector.currentData()
        if s_id:
            self.view_model.switch_session(s_id)

    @Slot()
    def _on_new_chat_clicked(self) -> None:
        self.view_model.create_new_session()
        self.active_context.clear()
        self.refresh_context_list()
        self._clear_messages_ui()
        self._insert_welcome_message()
        show_toast(self, "Nouvelle discussion démarrée.")

    @Slot()
    def _on_compact_requested(self) -> None:
        """Lance la compaction intelligente de l'historique sans altérer le scope."""
        self._handle_slash_command("/compact")

    @Slot(str)
    def _on_proactive_action_triggered(self, action_text: str) -> None:
        """Déclenche une action proactive suggérée par l'agent."""
        self._on_next_step_clicked(action_text)

    @Slot(object)
    def _on_hub_persona_changed(self, persona: PersonaModel) -> None:
        """Met à jour le persona sélectionné."""
        self._on_agent_changed()

    def _display_context_breakdown_message(self) -> None:
        """Affiche le diagnostic complet de la fenêtre de contexte (/context style CLI)."""
        selected_engine = self.model_selector.currentData()
        model_name = getattr(selected_engine, "display_name", "Modèle IA") if selected_engine else "Modèle IA"
        max_limit = getattr(selected_engine, "context_limit", 128000) or 128000

        p_tokens = self.context_hub._persona_tokens
        s_tokens = self.context_hub._sources_tokens
        h_tokens = self.view_model.used_tokens_count
        total = p_tokens + s_tokens + h_tokens
        pct = min(100.0, (total / max(1, max_limit)) * 100)

        sources_lines = []
        for ctx_id in self.active_context:
            sources_lines.append(f"  • <code>{ctx_id}</code>")

        sources_str = "<br>".join(sources_lines) if sources_lines else "  • <i>Aucune source connectée au scope actif</i>"

        breakdown_html = (
            f"<b>📊 Diagnostic de la Fenêtre d'Attention (Context Window Breakdown)</b><br><br>"
            f"<b>Moteur actif :</b> {model_name}<br>"
            f"<b>Utilisation globale :</b> <b>{total:,}</b> / {max_limit:,} tokens (<b>{pct:.1f}%</b>)<br><br>"
            f"<b>Ventilation détaillée :</b><br>"
            f"• 🧠 <b>Directive Système & Persona :</b> ~{p_tokens:,} tokens ({p_tokens / max(1, total) * 100:.1f}%)<br>"
            f"• 📚 <b>Sources & Scope Actif :</b> ~{s_tokens:,} tokens ({s_tokens / max(1, total) * 100:.1f}%)<br>"
            f"{sources_str}<br>"
            f"• 💬 <b>Historique de Discussion :</b> ~{h_tokens:,} tokens ({len(self.view_model.messages)} messages)<br><br>"
            f"💡 <i>Conseil : Tapez <code>/compact</code> pour résumer l'historique de discussion sans perdre vos sources connectées.</i>"
        )
        w = ChatMessageWidget("AnkiForge AI", breakdown_html, is_user=False)
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, w)
        self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum())

    @Slot()
    def _on_session_menu_clicked(self) -> None:
        """Affiche le menu contextuel de gestion de session (Renommer, Supprimer, Exporter)."""
        curr_session = self.view_model.current_session
        if not curr_session:
            return

        menu = StyledMenu(self)
        act_rename = menu.addAction(load_phosphor_icon("ph.pencil", color=DesignTokens.TEXT_PRIMARY), "Renommer la discussion...")
        act_export = menu.addAction(load_phosphor_icon("ph.share-network", color=DesignTokens.TEXT_PRIMARY), "Copier la discussion en Markdown")
        menu.addSeparator()
        act_delete = menu.addAction(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED), "Supprimer cette discussion")

        pos = self.btn_session_menu.mapToGlobal(self.btn_session_menu.rect().bottomLeft())
        action = menu.exec(pos)

        if action == act_rename:
            new_title, ok = QInputDialog.getText(self, "Renommer la discussion", "Nouveau titre :", text=curr_session.title)
            if ok and new_title.strip():
                curr_session.title = new_title.strip()
                curr_session.save()
                self.view_model.load_sessions()
                show_toast(self, "Discussion renommée.")

        elif action == act_export:
            export_lines = [f"# Discussion AnkiForge AI — {curr_session.title}\n"]
            for m in self.view_model.messages:
                r = "**Vous**" if m.get("role") == "user" else "**AnkiForge AI**"
                export_lines.append(f"### {r}\n{m.get('text', '')}\n")
            markdown_content = "\n".join(export_lines)
            QApplication.clipboard().setText(markdown_content)
            show_toast(self, "Discussion copiée dans le presse-papier en Markdown !")

        elif action == act_delete:
            ret = QMessageBox.question(
                self,
                "Confirmer la suppression",
                f"Voulez-vous vraiment supprimer la discussion '{curr_session.title}' ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ret == QMessageBox.StandardButton.Yes:
                curr_session.delete_instance(recursive=True)
                self.view_model.load_sessions()
                if self.view_model.sessions:
                    self.view_model.switch_session(self.view_model.sessions[0].id)
                else:
                    self.view_model.create_new_session()
                show_toast(self, "Discussion supprimée.")

    @Slot(object)
    def _on_active_session_reloaded(self, session: ConsultantSessionModel) -> None:
        self._clear_messages_ui()
        self.session_sidebar.set_active_session_id(session.id)
        if not self.view_model.messages:
            self.committed_context.clear()
            self.refresh_context_list()
            self._insert_welcome_message()
            return

        # Discussion existante : les sources actives sont ancrées
        self.committed_context.update(self.active_context)
        self.refresh_context_list()

        for msg in self.view_model.messages:
            is_user = msg.get("role") == "user"
            sender = "Vous" if is_user else "AnkiForge AI"
            w = ChatMessageWidget(
                sender,
                msg.get("text", ""),
                is_user=is_user,
                thoughts=msg.get("thoughts"),
                tool_calls=msg.get("tool_calls"),
            )
            self._connect_chat_message_signals(w)
            self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, w)

            staged = msg.get("staged_diff")
            if staged and not is_user:
                w.add_inline_diff(staged)

        self.lbl_tokens_usage.setText(f"{self.view_model.used_tokens_count:,}")
        self.session_sidebar.update_metrics(self.view_model.used_tokens_count, self.modified_cards_count)

    def _connect_chat_message_signals(self, w: ChatMessageWidget) -> None:
        """Connecte les signaux de diffs et d'inspection sur une bulle de message."""
        w.diff_inspect_requested.connect(self._on_diff_inspect_requested)
        w.diff_applied.connect(self._on_workspace_action_applied)
        w.diff_rejected.connect(self._on_workspace_action_rejected)
        w.diff_reverted.connect(self._on_workspace_action_reverted)
        w.open_editor_requested.connect(self._on_open_in_editor_requested)

    @Slot(int)
    def _on_open_in_editor_requested(self, note_id: int) -> None:
        """Navigue directement vers la carte correspondante dans l'onglet Édition."""
        logger.info("Navigation vers l'Édition demandée pour la note #%d", note_id)
        self.request_navigation.emit("edition", {"note_id": note_id})

    @Slot(str)
    def _on_workspace_action_reverted(self, message: str) -> None:
        """Décrémente le compteur et met à jour l'affichage lors d'une annulation."""
        if self.modified_cards_count > 0:
            self.modified_cards_count -= 1
            self.lbl_cards_modified.setText(str(self.modified_cards_count))
        self.refresh_context_list()
        show_toast(self, "Action annulée en BDD.")

    @Slot(dict)
    def _on_diff_inspect_requested(self, patch_data: dict[str, Any]) -> None:
        """Bascule immédiatement sur l'Inspecteur de droite et charge la proposition."""
        if hasattr(self.context_panel, "set_active_tab"):
            self.context_panel.set_active_tab(1)

        self.workspace_inspector.update_diff_view(
            title=patch_data.get("title", "Proposition de modification"),
            original_text=patch_data.get("original", ""),
            modified_text=patch_data.get("modified", ""),
            patch_type=patch_data.get("type", "card"),
            metadata=patch_data.get("metadata", {"note_id": patch_data.get("note_id")}),
        )

    @Slot(str)
    def _on_workspace_action_rejected(self, message: str) -> None:
        """Notification suite au rejet d'une proposition."""
        self.refresh_context_list()

    @Slot(QListWidgetItem)
    def _on_source_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Supprime une source spécifique du contexte actif lors d'un double-clic."""
        idx = self.sources_list.row(item)
        if 0 <= idx < len(self.active_context):
            ctx_id = self.active_context[idx]
            self._remove_context(ctx_id)
            show_toast(self, "Élément retiré du contexte.")

    def _clear_messages_ui(self) -> None:
        while self.chat_messages_layout.count() > 1:
            item = self.chat_messages_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _set_send_button_mode(self, is_running: bool) -> None:
        if hasattr(self, "progress_bar"):
            self.progress_bar.setVisible(is_running)

        if is_running:
            self.btn_send.setIcon(load_phosphor_icon("ph.stop", color="white"))
            self.btn_send.setToolTip("Interrompre la génération (Stop)")
            self.btn_send.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.COLOR_RED};
                    border-radius: 17px;
                    border: none;
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.COLOR_RED};
                    opacity: 0.9;
                }}
            """)
        else:
            self.btn_send.setIcon(load_phosphor_icon("ph.arrow-up", color="white"))
            self.btn_send.setToolTip("Envoyer la requête")
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

    @Slot()
    def _on_agent_changed(self) -> None:
        agent: PersonaModel | None = self.persona_combo.currentData()
        if agent and hasattr(agent, "system_prompt") and agent.system_prompt:
            prompt_str = str(agent.system_prompt)
            prompt_snippet = prompt_str[:140] + "..." if len(prompt_str) > 140 else prompt_str
            self.sys_prompt_lbl.setText(f'"{prompt_snippet}"')

    def _remove_context(self, ctx_id: str) -> None:
        """Supprime une source du contexte si elle n'a pas encore été engagée dans un message envoyé."""
        if ctx_id in self.committed_context:
            show_toast(self, "Cette source est ancrée dans l'historique de cette discussion.")
            return

        if ctx_id in self.active_context:
            self.active_context.remove(ctx_id)
            self.refresh_context_list()
            show_toast(self, "Source retirée du contexte.")

    def refresh_context_list(self) -> None:
        self.sources_list.clear()

        while self.mentions_layout.count() > 0:
            layout_item = self.mentions_layout.takeAt(0)
            if layout_item:
                w = layout_item.widget()
                if w:
                    w.deleteLater()

        if not self.active_context:
            empty_item = QListWidgetItem("Aucun contexte attaché (cliquez sur + ou tapez @)")
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.sources_list.addItem(empty_item)
            self.lbl_cards_in_context.setText("0")
        else:
            total_cards_in_context = 0

            for ctx_id in self.active_context:
                display_text = "Inconnu"
                is_comm = ctx_id in self.committed_context
                suffix = " 🔒" if is_comm else " ✕"

                if ctx_id.startswith("deck_"):
                    try:
                        d_id = int(ctx_id.split("_")[1])
                        deck = DeckModel.get_or_none(DeckModel.id == d_id)
                        if deck:
                            card_count = CardModel.select().where(CardModel.deck == deck).count()
                            total_cards_in_context += card_count
                            display_text = f"🎴 Deck: {deck.name} ({card_count} cartes)"
                            badge = ContextPillBadge(f"🎴 {deck.name}{suffix}", ctx_id, on_remove=self._remove_context, is_committed=is_comm)
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
                            badge = ContextPillBadge(f"📄 {doc.title}{suffix}", ctx_id, on_remove=self._remove_context, is_committed=is_comm)
                            apply_pill_style(badge, DesignTokens.COLOR_BLUE)
                            self.mentions_layout.addWidget(badge)
                    except Exception:
                        display_text = "Doc inconnu"
                elif ctx_id.startswith("card_"):
                    try:
                        n_id = int(ctx_id.split("_")[1])
                        note = NoteModel.get_or_none(NoteModel.id == n_id)
                        if note:
                            active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                            snippet = ""
                            if active_v and active_v.content:
                                try:
                                    d_c = json.loads(active_v.content)
                                    snippet = d_c.get("Front", d_c.get("Recto", active_v.content))
                                except Exception:
                                    snippet = active_v.content
                            short_snip = str(snippet).replace("\n", " ")[:24] + ("..." if len(str(snippet)) > 24 else "")
                            display_text = f"🗂️ Note #{note.id} ({short_snip})"
                            badge = ContextPillBadge(f"🗂️ #{note.id}: {short_snip}{suffix}", ctx_id, on_remove=self._remove_context, is_committed=is_comm)
                            apply_pill_style(badge, DesignTokens.COLOR_YELLOW)
                            self.mentions_layout.addWidget(badge)
                            total_cards_in_context += 1
                    except Exception:
                        display_text = "Note inconnue"
                elif ctx_id.startswith("model_"):
                    try:
                        m_val = ctx_id.split("_")[1]
                        nt = NoteTypeModel.get_or_none(NoteTypeModel.id == int(m_val)) if m_val.isdigit() else NoteTypeModel.get_or_none(NoteTypeModel.name == m_val)
                        if nt:
                            display_text = f"🎨 Modèle: {nt.name}"
                            badge = ContextPillBadge(f"🎨 {nt.name}{suffix}", ctx_id, on_remove=self._remove_context, is_committed=is_comm)
                            apply_pill_style(badge, DesignTokens.COLOR_PURPLE)
                            self.mentions_layout.addWidget(badge)
                    except Exception:
                        display_text = "Modèle inconnu"

                self.sources_list.addItem(display_text)

            self.mentions_layout.addStretch()
            self.lbl_cards_in_context.setText(str(total_cards_in_context))

        if hasattr(self, "context_hub"):
            self.context_hub.set_context_sources(
                self.active_context,
                self._build_context_data(),
                committed_context=self.committed_context,
            )
            self.context_hub.set_history_tokens(self.view_model.used_tokens_count)

    def _insert_welcome_message(self) -> None:
        msg_ai = (
            "Bonjour ! Je suis votre <b>Consultant IA AnkiForge</b>.<br><br>"
            "Je dispose d'outils d'audit Wozniak, de recherche de doublons Levenshtein, de RAG documentaire, "
            "d'inspection/évolution des <b>Modèles de cartes</b> et de propositions de refactorisation sous forme de <b>Diffs avec Garde-Fou</b>.<br><br>"
            "💡 <i>Tapez <b>@</b> pour lier un paquet, une carte, un modèle ou un document, <b>/</b> pour les raccourcis.</i>"
        )
        w = ChatMessageWidget("AnkiForge AI", msg_ai, is_user=False)
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, w)

    @Slot()
    def _on_input_text_changed(self) -> None:
        text = self.chat_input.toPlainText()
        tokens = int(len(text.split()) * 1.3)
        self.tokens_badge.setText(f"{tokens} tokens")

    @Slot(str, str)
    def _on_mention_completed(self, m_type: str, m_id: str) -> None:
        """Gère la sélection d'une mention ou commande dans la popup."""
        if m_type == "slash":
            self._handle_slash_command(m_id)
        elif m_type == "deck":
            self._attach_context(f"deck_{m_id}")
        elif m_type == "doc":
            self._attach_context(f"doc_{m_id}")
        elif m_type == "card":
            self._attach_context(f"card_{m_id}")
            self.chat_input.insertPlainText(f" [Note #{m_id}]")
        elif m_type == "model":
            self._attach_context(f"model_{m_id}")
            self.chat_input.insertPlainText(f" [Modèle: {m_id}]")

    def _handle_slash_command(self, cmd: str) -> bool:
        """Exécute une commande Slash locale si applicable. Renvoie True si traitée."""
        cmd_clean = cmd.strip().lower()
        if cmd_clean == "/clear":
            self._on_clear_memory()
            self.chat_input.clear()
            return True
        elif cmd_clean == "/context":
            self._display_context_breakdown_message()
            self.chat_input.clear()
            return True
        elif cmd_clean == "/compact":
            recap, steps = ContextCompactor.compact_post_task(self.view_model.conversation_history)
            self.workspace_inspector.set_next_steps(steps)
            if hasattr(self, "context_hub"):
                self.context_hub._update_proactive_actions(has_deck=any("deck_" in c for c in self.active_context), has_doc=any("doc_" in c for c in self.active_context))
            show_toast(self, "Contexte compacté avec succès !")
            self.chat_input.clear()
            return True
        elif cmd_clean == "/help":
            help_msg = (
                "<b>Commandes Slash disponibles :</b><br>"
                "• <code>/context</code> : Afficher le diagnostic complet et ventilation des tokens<br>"
                "• <code>/compact</code> : Compacter la mémoire et libérer des tokens<br>"
                "• <code>/clear</code> : Effacer l'historique et démarrer une nouvelle session<br>"
                "• <code>/panorama</code> : Lancer une analyse panoramique 360° globale<br>"
                "• <code>/deepscan</code> : Scanner en profondeur le paquet principal<br>"
                "• <code>/undo</code> : Restaurer la version précédente de la dernière note modifiée<br><br>"
                "<b>Mentions rapides :</b> Tapez <code>@</code> pour lier un paquet ou document."
            )
            w = ChatMessageWidget("AnkiForge AI", help_msg, is_user=False)
            self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, w)
            self.chat_input.clear()
            return True
        elif cmd_clean == "/undo":
            self._undo_last_card_modification()
            self.chat_input.clear()
            return True
        elif cmd_clean == "/panorama":
            self.chat_input.setPlainText("Donne-moi un panorama 360° complet de ma collection.")
            self._on_send_clicked()
            return True
        elif cmd_clean == "/deepscan":
            self.chat_input.setPlainText("Effectue un deep scan approfondi de la distribution de mon paquet.")
            self._on_send_clicked()
            return True
        return False

    def _undo_last_card_modification(self) -> None:
        try:
            sources = ["consultant_refactor", "consultant_split", "consultant_workspace", "consultant_inline", "consultant_split_inline"]
            last_version = NoteVersionModel.select().where(NoteVersionModel.source.in_(sources)).order_by(NoteVersionModel.id.desc()).first()
            if not last_version:
                show_toast(self, "Aucune version récente du consultant à annuler.", is_error=True)
                return

            note = last_version.note
            prev_version = note.versions.where(NoteVersionModel.version_number < last_version.version_number).order_by(NoteVersionModel.version_number.desc()).first()
            if prev_version:
                with db.atomic():
                    last_version.is_active = False
                    last_version.save()
                    prev_version.is_active = True
                    prev_version.save()
                show_toast(self, f"Note #{note.id} restaurée à la version {prev_version.version_number} !")
                undo_msg = f"↩️ <b>Time Machine :</b> Note #{note.id} restaurée avec succès à la version précédente {prev_version.version_number}."
                w = ChatMessageWidget("AnkiForge AI", undo_msg, is_user=False)
                self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, w)
            else:
                show_toast(self, "Pas de version antérieure disponible pour cette note.", is_error=True)
        except Exception as e:
            logger.error("Erreur undo Time Machine : %s", e)
            show_toast(self, f"Erreur Time Machine : {e}", is_error=True)

    @Slot(str)
    def _on_quick_prompt_clicked(self, key: str) -> None:
        prompt_presets = {
            "Audit Wozniak": "Effectue un audit de formulation basé sur les 20 règles de Piotr Wozniak sur mon paquet principal.",
            "Recherche Doublons": "Détecte les cartes doublons ou formulées de façon similaire dans ma collection.",
            "Panorama 360°": "Donne-moi un panorama 360° complet de ma collection (paquets, cartes, sangsues, documents).",
            "Rétention SRS": "Analyse en détail la rétention SRS et la stabilité FSRS-4.5 de mes paquets.",
            "Deep Scan Deck": "Effectue un scan approfondi (deep scan) de la distribution des intervalles et des sangsues de mon paquet principal.",
            "Scission cartes": "Identifie une carte surchargée et propose une scission atomique avec diff.",
        }
        if key in prompt_presets:
            resolved_text = prompt_presets[key]
        else:
            clean_text = key
            for prefix in ["📊 ", "🔍 ", "🎨 ", "⚡ ", "🛠️ ", "🌐 ", "🔬 ", "💡 ", "✂️ ", "🛡️ "]:
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

        menu_models = menu.addMenu("🎨 Attacher un Modèle de carte")
        models = list(NoteTypeModel.select())
        if models:
            for m in models:
                action = QAction(m.name, self)
                action.triggered.connect(lambda _, model_id=m.id: self._attach_context(f"model_{model_id}"))
                menu_models.addAction(action)
        else:
            no_model = QAction("Aucun modèle disponible", self)
            no_model.setEnabled(False)
            menu_models.addAction(no_model)

        menu_cards = menu.addMenu("🗂️ Attacher une Carte (Note)")
        recent_notes = list(NoteModel.select().order_by(NoteModel.id.desc()).limit(20))
        if recent_notes:
            for n in recent_notes:
                active_v = n.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                snippet = f"Note #{n.id}"
                if active_v and active_v.content:
                    try:
                        d_c = json.loads(active_v.content)
                        front_text = d_c.get("Front", d_c.get("Recto", active_v.content))
                        snippet = f"#{n.id} : {str(front_text)[:30]}"
                    except Exception:
                        snippet = f"#{n.id} : {active_v.content[:30]}"
                action = QAction(snippet, self)
                action.triggered.connect(lambda _, note_id=n.id: self._attach_context(f"card_{note_id}"))
                menu_cards.addAction(action)
        else:
            no_card = QAction("Aucune carte disponible", self)
            no_card.setEnabled(False)
            menu_cards.addAction(no_card)

        menu.exec(self.btn_add_context.mapToGlobal(self.btn_add_context.rect().bottomLeft()))

    def _attach_context(self, ctx_id: str) -> None:
        if ctx_id not in self.active_context:
            self.active_context.append(ctx_id)
            self.refresh_context_list()
            show_toast(self, "Contexte attaché !")

    def attach_and_prompt(self, context_item: str, prompt: str = "") -> None:
        """Attache un élément de contexte et pré-remplit le champ de saisie du chat."""
        if context_item:
            self._attach_context(context_item)
        if prompt:
            self.chat_input.setPlainText(prompt)
            self.chat_input.setFocus()

    @Slot()
    def _on_clear_memory(self) -> None:
        self.committed_context.clear()
        self.active_context.clear()
        self.refresh_context_list()
        self.used_tokens_count = 0
        self.lbl_tokens_usage.setText("0")
        self.view_model.create_new_session()
        self.workspace_inspector.set_empty_state()

        self._clear_messages_ui()
        self._insert_welcome_message()
        show_toast(self, "Session réinitialisée.")

    @Slot(str)
    def _on_next_step_clicked(self, step_text: str) -> None:
        """Gère le clic sur une suggestion d'action proactive post-tâche."""
        clean_text = step_text
        for icon_prefix in ["🔍 ", "🎨 ", "📦 ", "⚡ ", "✂️ ", "🛡️ "]:
            clean_text = clean_text.replace(icon_prefix, "")
        self.chat_input.setPlainText(clean_text)
        self.chat_input.setFocus()

    @Slot(str)
    def _on_workspace_action_applied(self, message: str) -> None:
        """Notification suite à une action validée et enregistrée en BDD depuis le garde-fou."""
        self.modified_cards_count += 1
        self.lbl_cards_modified.setText(str(self.modified_cards_count))
        self.refresh_context_list()

    def _build_context_data(self) -> dict[str, list[dict[str, Any]]]:
        data: dict[str, list[dict[str, Any]]] = {"documents": [], "paquets": [], "modeles": [], "cartes_ciblees": []}

        for ctx_id in self.active_context:
            if ctx_id.startswith("doc_"):
                try:
                    d_id = int(ctx_id.split("_")[1])
                    doc = DocumentModel.get_or_none(DocumentModel.id == d_id)
                    if doc:
                        data["documents"].append({"titre": doc.title, "contenu": getattr(doc, "content", "")})
                except Exception:
                    pass  # nosec B110

            elif ctx_id.startswith("model_"):
                try:
                    m_val = ctx_id.split("_")[1]
                    nt = NoteTypeModel.get_or_none(NoteTypeModel.id == int(m_val)) if m_val.isdigit() else NoteTypeModel.get_or_none(NoteTypeModel.name == m_val)
                    if nt:
                        fields_val = robust_json_loads(nt.fields_schema) if nt.fields_schema else ["Front", "Back"]
                        tpl_val = robust_json_loads(nt.templates) if nt.templates else []
                        data["modeles"].append(
                            {
                                "nom": nt.name,
                                "description": nt.description or "",
                                "schema_champs": fields_val,
                                "templates": tpl_val,
                                "css_style": nt.css_style or "",
                            }
                        )
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
                                    fields_dict = robust_json_loads(v.content)
                                except Exception:
                                    fields_dict = {"Front": v.content}
                                notes_data.append(
                                    {
                                        "note_id": note.id,
                                        "modele": note.note_type.name if note.note_type else "Inconnu",
                                        "tags": note.tags,
                                        "fields": fields_dict,
                                    }
                                )
                        data["paquets"].append({"nom": deck.name, "cartes": notes_data})
                except Exception:
                    pass  # nosec B110

            elif ctx_id.startswith("card_"):
                try:
                    n_id = int(ctx_id.split("_")[1])
                    note = NoteModel.get_or_none(NoteModel.id == n_id)
                    if note:
                        v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                        c_dict = {}
                        if v and v.content:
                            try:
                                c_dict = robust_json_loads(v.content)
                            except Exception:
                                c_dict = {"Front": v.content}
                        data["cartes_ciblees"].append(
                            {
                                "note_id": note.id,
                                "modele": note.note_type.name if note.note_type else "Inconnu",
                                "tags": note.tags,
                                "fields": c_dict,
                            }
                        )
                except Exception:
                    pass  # nosec B110

        return data

    @Slot()
    def _on_send_or_stop_clicked(self) -> None:
        if self.worker and self.worker.isRunning():
            self.lbl_chat_status.setText("⏹ Interruption en cours...")
            self.worker.cancel()
            return

        self._on_send_clicked()

    @Slot()
    def _on_send_clicked(self) -> None:
        user_text = self.chat_input.toPlainText().strip()
        if not user_text:
            return

        if user_text.startswith("/") and self._handle_slash_command(user_text):
            return

        user_msg = ChatMessageWidget("Vous", user_text, is_user=True)
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, user_msg)
        self.view_model.add_user_message(user_text)
        self.chat_input.clear()

        self._active_ai_message = ChatMessageWidget("AnkiForge AI", text="", is_user=False)
        self._connect_chat_message_signals(self._active_ai_message)
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, self._active_ai_message)

        QApplication.processEvents()
        self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum())

        context_data = self._build_context_data()
        selected_engine = self.model_selector.currentData()
        selected_persona = self.persona_combo.currentData()

        # Note Agent Aidant IA : Le Working Scope (paquets, documents, modèles)
        # est ancré (committed) dans l'historique de cette discussion dès l'envoi du message.
        self.committed_context.update(self.active_context)
        self.refresh_context_list()

        self._set_send_button_mode(is_running=True)
        self.lbl_chat_status.setText("⏳ Analyse et streaming en direct...")

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
            conversation_history=list(self.view_model.conversation_history),
        )
        self.worker.thought_emitted.connect(self._on_thought_received)
        self.worker.tool_started_signal.connect(self._on_tool_started)
        self.worker.tool_finished_signal.connect(self._on_tool_finished)
        self.worker.text_delta_signal.connect(self._on_text_delta)
        self.worker.progress.connect(self._on_ai_progress)
        self.worker.next_steps_signal.connect(self._on_next_steps_received)
        self.worker.finished_signal.connect(self._on_ai_response)
        self.worker.cancelled_signal.connect(self._on_ai_cancelled)
        self.worker.error_signal.connect(self._on_ai_error)
        self.worker.start()

    @Slot(int, str, bool)
    def _on_thought_received(self, step: int, thought: str, is_running: bool) -> None:
        self.view_model.record_thought(step, thought, is_running=is_running)
        if self._active_ai_message:
            self._active_ai_message.add_or_update_thought(step, thought, is_running=is_running)
            self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum())

    @Slot(str, str)
    def _on_tool_started(self, tool_name: str, args_str: str) -> None:
        self.view_model.record_tool_call(tool_name, args_str, "", is_done=False)
        if self._active_ai_message:
            self._active_ai_message.add_tool_start(tool_name, args_str)
            self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum())

    @Slot(str, str, str, bool)
    def _on_tool_finished(self, tool_name: str, args_str: str, result_str: str, is_error: bool) -> None:
        self.view_model.record_tool_call(tool_name, args_str, result_str, is_done=True, is_error=is_error)
        if self._active_ai_message:
            self._active_ai_message.update_tool_result(tool_name, result_str, is_error=is_error)
            self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum())

        # Traitement des diffs avec affichage INLINE dans le chat et dans le Workspace
        try:
            parsed_res = json.loads(result_str) if isinstance(result_str, str) and result_str.strip().startswith("{") else {}
            if isinstance(parsed_res, dict) and parsed_res.get("status") == "staged_diff":
                self._active_staged_diff = parsed_res
                # 1. Ajout dans le message chat (Inline Diff)
                if self._active_ai_message:
                    self._active_ai_message.add_inline_diff(parsed_res)

                # 2. Ajout dans le Workspace Inspector
                self.workspace_inspector.update_diff_view(
                    title=parsed_res.get("title", "Proposition de modification"),
                    original_text=parsed_res.get("original", ""),
                    modified_text=parsed_res.get("modified", ""),
                    patch_type=parsed_res.get("type", "card"),
                    metadata=parsed_res.get("metadata", {"note_id": parsed_res.get("note_id")}),
                )
                if hasattr(self.context_panel, "set_active_tab"):
                    self.context_panel.set_active_tab(1)
        except Exception as err:
            logger.debug("Remarque mise à jour workspace inspector : %s", err)

    @Slot(str)
    def _on_text_delta(self, delta: str) -> None:
        if self._active_ai_message:
            self._active_ai_message.append_text_chunk(delta)
            self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum())

    @Slot(str)
    def _on_ai_progress(self, msg: str) -> None:
        self.lbl_chat_status.setText(f"⏳ {msg}")

    @Slot(list)
    def _on_next_steps_received(self, next_steps: list[str]) -> None:
        self.workspace_inspector.set_next_steps(next_steps)

    @Slot(str)
    def _on_ai_response(self, response: str) -> None:
        self._set_send_button_mode(is_running=False)
        self.lbl_chat_status.setText("")

        if self._active_ai_message:
            self._active_ai_message.mark_as_finished(response)

        # 1. Détection automatique des propositions de modification en JSON
        last_user_q = ""
        if self.view_model.conversation_history:
            for msg in reversed(self.view_model.conversation_history):
                if msg.get("role") == "user":
                    last_user_q = msg.get("content", "")
                    break

        card_prop = extract_card_proposal_from_text(response, user_query=last_user_q)
        if card_prop:
            note_id = card_prop.get("note_id")
            orig_content: Any = {"Front": "/* Contenu existant */"}
            if note_id:
                note = NoteModel.get_or_none(NoteModel.id == int(note_id))
                if note:
                    active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                    if active_v and active_v.content:
                        try:
                            orig_content = json.loads(active_v.content)
                        except Exception:
                            orig_content = {"Front": active_v.content}

            patch_payload = {
                "title": card_prop.get("title", f"Proposition de Refactorisation {f'— Note #{note_id}' if note_id else ''}"),
                "type": card_prop.get("type", "card"),
                "note_id": note_id,
                "original": orig_content,
                "modified": card_prop.get("modified"),
                "metadata": {"note_id": note_id},
            }

            if self._active_ai_message:
                self._active_ai_message.add_inline_diff(patch_payload)

            self.workspace_inspector.update_diff_view(
                title=patch_payload["title"],
                original_text=patch_payload["original"],
                modified_text=patch_payload["modified"],
                patch_type=patch_payload["type"],
                metadata=patch_payload["metadata"],
            )
            if hasattr(self.context_panel, "set_active_tab"):
                self.context_panel.set_active_tab(1)

        # 2. Détection CSS pour le workspace
        css_match = re.search(r"```(?:css)?\s*(\.[\s\S]+?)\s*```", response)
        if css_match and not card_prop:
            css_payload: dict[str, Any] = {
                "title": "Proposition de Style CSS IA",
                "type": "css",
                "original": "/* Style actuel */",
                "modified": css_match.group(1).strip(),
                "metadata": {},
            }
            if self._active_ai_message:
                self._active_ai_message.add_inline_diff(css_payload)

            self.workspace_inspector.update_diff_view(
                title=css_payload["title"],
                original_text=css_payload["original"],
                modified_text=css_payload["modified"],
                patch_type=css_payload["type"],
            )
            if hasattr(self.context_panel, "set_active_tab"):
                self.context_panel.set_active_tab(1)

        diff_to_save = card_prop or self._active_staged_diff
        self.view_model.add_assistant_message(response, staged_diff=diff_to_save)
        self._active_staged_diff = None

        QApplication.processEvents()
        self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum())

        self.used_tokens_count += int(len(response.split()) * 1.3) + 120
        self.lbl_tokens_usage.setText(f"{self.used_tokens_count:,}")

    @Slot()
    def _on_ai_cancelled(self) -> None:
        self._set_send_button_mode(is_running=False)
        self.lbl_chat_status.setText("")
        if self._active_ai_message:
            self._active_ai_message.mark_as_cancelled()
        show_toast(self, "Génération interrompue.")

    @Slot(str)
    def _on_ai_error(self, error: str) -> None:
        self._set_send_button_mode(is_running=False)
        self.lbl_chat_status.setText("")
        if self._active_ai_message:
            self._active_ai_message.append_text_chunk(f"\n\n⚠️ <b>Erreur :</b> {error}")
            self._active_ai_message.mark_as_finished()

    def closeEvent(self, event: Any) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(1000)
        super().closeEvent(event)


ConsultantTab = ConsultantView
