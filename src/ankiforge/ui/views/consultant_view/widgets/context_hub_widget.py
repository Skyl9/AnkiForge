"""
Hub de Contexte et Mémoire de Travail pour l'Agent Aidant IA.

Remplace l'ancien inspecteur de diff par un cockpit d'analyse contextuelle complet :
- Directive et Persona actifs.
- Espace de travail persistant (Working Scope : Paquets, Documents RAG, Cartes ciblées).
- Estimation précise des tokens par source et décomposition globale (style /context CLI).
- Boîte à outils proactive (Intent Actions) adaptée aux sources connectées.
- Dialogue d'inspection du contexte brut (Raw Prompt Viewer).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    PersonaModel,
)
from ankiforge.services.ai.context_compactor import ContextCompactor
from ankiforge.ui.components import (
    IconButton,
    SecondaryButton,
    StyledComboBox,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class RawContextDialog(QDialog):
    """Modale d'inspection du contexte brut et des prompts envoyés à l'IA."""

    def __init__(self, raw_data_dict: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Inspection du Contexte Brut (Prompt Augmenté)")
        self.resize(750, 550)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel("🔍 Payload JSON et Scope injectés dans la fenêtre d'attention")
        header.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {DesignTokens.TEXT_PRIMARY};")
        layout.addWidget(header)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        formatted_json = json.dumps(raw_data_dict, ensure_ascii=False, indent=2)
        self.text_edit.setPlainText(formatted_json)
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: {DesignTokens.FONT_CODE};
                font-size: 11px;
                padding: 10px;
            }}
        """)
        layout.addWidget(self.text_edit, 1)

        btn_close = SecondaryButton("Fermer")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)


class ContextAssetCard(QFrame):
    """Carte d'affichage d'un actif contextuel connecté (Deck, Document, Carte, Modèle)."""

    remove_requested = Signal(str)

    def __init__(
        self,
        ctx_id: str,
        title: str,
        subtitle: str,
        token_est: int,
        icon_name: str = "ph.file",
        is_committed: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.ctx_id = ctx_id
        self.token_est = token_est
        self.is_committed = is_committed
        self._setup_ui(title, subtitle, token_est, icon_name, is_committed)

    def _setup_ui(self, title: str, subtitle: str, token_est: int, icon_name: str, is_committed: bool) -> None:
        self.setStyleSheet(f"""
            ContextAssetCard {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                margin-bottom: 4px;
            }}
            ContextAssetCard:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 8, 8)
        layout.setSpacing(10)

        # Icône Phosphor
        lbl_icon = QLabel()
        lbl_icon.setPixmap(load_phosphor_icon(icon_name, color=DesignTokens.ACCENT_PRIMARY).pixmap(18, 18))
        layout.addWidget(lbl_icon)

        # Textes
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"font-weight: 600; font-size: 12px; color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        lbl_title.setWordWrap(True)
        text_layout.addWidget(lbl_title)

        status_text = "🔒 Ancré dans la discussion" if is_committed else subtitle
        lbl_sub = QLabel(status_text)
        lbl_sub.setStyleSheet(f"font-size: 10px; color: {DesignTokens.COLOR_GREEN if is_committed else DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        text_layout.addWidget(lbl_sub)
        layout.addLayout(text_layout, 1)

        # Badge de tokens
        lbl_tokens = QLabel(f"~{token_est:,} tok")
        lbl_tokens.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_SECONDARY};
                font-family: {DesignTokens.FONT_CODE};
                font-size: 10px;
                padding: 2px 6px;
                border-radius: 4px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        layout.addWidget(lbl_tokens)

        # Si engagé (un message a déjà été envoyé), la source est conservée dans l'historique
        if is_committed:
            lbl_lock = QLabel()
            lbl_lock.setPixmap(load_phosphor_icon("ph.lock-simple", color=DesignTokens.TEXT_MUTED).pixmap(16, 16))
            lbl_lock.setToolTip("Cette source est ancrée dans l'historique de cette discussion")
            layout.addWidget(lbl_lock)
        else:
            # Source non encore envoyée : retirable librement
            btn_del = IconButton("ph.x", tooltip="Retirer du contexte de travail", size=18)
            from PySide6.QtCore import QTimer

            btn_del.clicked.connect(lambda: QTimer.singleShot(0, lambda: self.remove_requested.emit(self.ctx_id)))
            layout.addWidget(btn_del)


class ContextHubWidget(QWidget):
    """
    Cockpit de gestion de contexte intelligent et de mémoire de travail pour l'Agent Aidant.
    Remplace l'ancien inspecteur de diffs redondant.
    """

    add_context_requested = Signal()
    context_removed = Signal(str)
    compact_requested = Signal()
    action_triggered = Signal(str)
    persona_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.active_context: list[str] = []
        self._persona_tokens: int = 250
        self._sources_tokens: int = 0
        self._history_tokens: int = 0
        self._max_context_limit: int = 128000
        self._last_context_payload: dict[str, Any] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(12, 10, 12, 12)
        container_layout.setSpacing(10)

        # ── 1. Carte Persona & Consigne Active ──────────────────────────────
        lbl_persona_sec = QLabel("PERSONA & DIRECTIVE ACTIVE")
        lbl_persona_sec.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {DesignTokens.TEXT_MUTED}; letter-spacing: 0.5px;")
        container_layout.addWidget(lbl_persona_sec)

        persona_card = QFrame()
        persona_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        persona_layout = QVBoxLayout(persona_card)
        persona_layout.setContentsMargins(8, 8, 8, 8)
        persona_layout.setSpacing(6)

        self.persona_combo = StyledComboBox()
        self.persona_combo.currentIndexChanged.connect(self._on_persona_combo_changed)
        persona_layout.addWidget(self.persona_combo)

        self.lbl_system_directive = QLabel('"Directeur qualité : 20 règles de Piotr Wozniak, atomicité et clarté"')
        self.lbl_system_directive.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY}; font-style: italic; background: transparent;")
        self.lbl_system_directive.setWordWrap(True)
        persona_layout.addWidget(self.lbl_system_directive)

        container_layout.addWidget(persona_card)

        # ── 2. Espace de Travail Actif (Working Scope) ───────────────────────
        scope_header = QHBoxLayout()
        lbl_scope = QLabel("ESPACE DE TRAVAIL (WORKING SCOPE)")
        lbl_scope.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {DesignTokens.TEXT_MUTED}; letter-spacing: 0.5px;")
        scope_header.addWidget(lbl_scope)
        scope_header.addStretch()

        self.btn_add_source = SecondaryButton("+ Lier (@)")
        self.btn_add_source.setFixedHeight(24)
        self.btn_add_source.setStyleSheet("""
            QPushButton {
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 600;
            }
        """)
        self.btn_add_source.clicked.connect(self.add_context_requested.emit)
        scope_header.addWidget(self.btn_add_source)
        container_layout.addLayout(scope_header)

        self.sources_container = QWidget()
        self.sources_layout = QVBoxLayout(self.sources_container)
        self.sources_layout.setContentsMargins(0, 0, 0, 0)
        self.sources_layout.setSpacing(4)
        container_layout.addWidget(self.sources_container)

        self.empty_state_lbl = QLabel("Aucune source connectée.\nTapez @ ou cliquez sur + Lier pour connecter un paquet ou un cours PDF.")
        self.empty_state_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state_lbl.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px dashed {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_MUTED};
                font-size: 11px;
                padding: 14px;
            }}
        """)
        container_layout.addWidget(self.empty_state_lbl)

        # ── 3. Autonomie & Outils MCP de l'Agent IA ─────────────────────────
        lbl_mcp_sec = QLabel("AUTONOMIE & OUTILS MCP DE L'AGENT")
        lbl_mcp_sec.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {DesignTokens.TEXT_MUTED}; letter-spacing: 0.5px;")
        container_layout.addWidget(lbl_mcp_sec)

        mcp_card = QFrame()
        mcp_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        mcp_layout = QVBoxLayout(mcp_card)
        mcp_layout.setContentsMargins(8, 8, 8, 8)
        mcp_layout.setSpacing(4)

        lbl_mcp_title = QLabel("🤖 Mode ReAct Autonome Actif")
        lbl_mcp_title.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        mcp_layout.addWidget(lbl_mcp_title)

        lbl_mcp_desc = QLabel("L'IA examine vos sources et déclenche de façon proactive ses outils (Audit Wozniak, Levenshtein, RAG, Retouches) selon les besoins.")
        lbl_mcp_desc.setStyleSheet(f"font-size: 10px; color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent; line-height: 1.3;")
        lbl_mcp_desc.setWordWrap(True)
        mcp_layout.addWidget(lbl_mcp_desc)

        container_layout.addWidget(mcp_card)

        # Container stub pour compatibilité avec tests si nécessaire
        self.actions_container = QWidget()
        self.actions_layout = QVBoxLayout(self.actions_container)

        # ── 4. Jauge et Décomposition de Mémoire (/context breakdown) ───────
        lbl_memory_sec = QLabel("FENÊTRE D'ATTENTION & TOKENS (/context)")
        lbl_memory_sec.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {DesignTokens.TEXT_MUTED}; letter-spacing: 0.5px;")
        container_layout.addWidget(lbl_memory_sec)

        memory_card = QFrame()
        memory_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        memory_layout = QVBoxLayout(memory_card)
        memory_layout.setContentsMargins(8, 8, 8, 8)
        memory_layout.setSpacing(8)

        # Jauge globale
        bar_header = QHBoxLayout()
        self.lbl_token_usage_total = QLabel("0 / 128k tokens (0%)")
        self.lbl_token_usage_total.setStyleSheet(f"font-size: 11px; font-family: {DesignTokens.FONT_CODE}; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        bar_header.addWidget(self.lbl_token_usage_total)
        bar_header.addStretch()

        self.btn_inspect_raw = IconButton("ph.magnifying-glass", tooltip="Inspecter le prompt brut", size=18)
        self.btn_inspect_raw.clicked.connect(self._show_raw_dialog)
        bar_header.addWidget(self.btn_inspect_raw)
        memory_layout.addLayout(bar_header)

        self.progress_tokens = QProgressBar()
        self.progress_tokens.setRange(0, 100)
        self.progress_tokens.setValue(0)
        self.progress_tokens.setFixedHeight(6)
        self.progress_tokens.setTextVisible(False)
        self.progress_tokens.setStyleSheet(f"""
            QProgressBar {{
                background-color: {DesignTokens.BG_PANEL};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-radius: 3px;
            }}
        """)
        memory_layout.addWidget(self.progress_tokens)

        # Décomposition détaillée (/context breakdown)
        self.lbl_bd_system = QLabel("• 🧠 Persona & Outils : 250 tokens")
        self.lbl_bd_system.setStyleSheet(f"font-size: 10px; color: {DesignTokens.TEXT_SECONDARY};")
        memory_layout.addWidget(self.lbl_bd_system)

        self.lbl_bd_sources = QLabel("• 📚 Sources connectées : 0 tokens")
        self.lbl_bd_sources.setStyleSheet(f"font-size: 10px; color: {DesignTokens.COLOR_BLUE};")
        memory_layout.addWidget(self.lbl_bd_sources)

        self.lbl_bd_history = QLabel("• 💬 Historique de chat : 0 tokens")
        self.lbl_bd_history.setStyleSheet(f"font-size: 10px; color: {DesignTokens.COLOR_GREEN};")
        memory_layout.addWidget(self.lbl_bd_history)

        # Bouton compacter
        self.btn_compact = SecondaryButton("⚡ Compacter la mémoire (/compact)")
        self.btn_compact.setIcon(load_phosphor_icon("ph.arrows-in-line-vertical", color=DesignTokens.TEXT_PRIMARY))
        self.btn_compact.clicked.connect(self.compact_requested.emit)
        memory_layout.addWidget(self.btn_compact)

        container_layout.addWidget(memory_card)
        container_layout.addStretch()

        scroll_area.setWidget(container)
        main_layout.addWidget(scroll_area)

    def set_personas(self, personas: list[PersonaModel], active_persona: PersonaModel | None = None) -> None:
        self.persona_combo.blockSignals(True)
        self.persona_combo.clear()
        for p in personas:
            p_type = getattr(p, "persona_type", "mcp")
            type_prefix = "🤝 " if p_type == "mcp" else "🌐 "
            self.persona_combo.addItem(f"{type_prefix}{p.name}", userData=p)

        if active_persona:
            idx = self.persona_combo.findText(f"🤝 {active_persona.name}")
            if idx == -1:
                idx = self.persona_combo.findText(f"🌐 {active_persona.name}")
            if idx != -1:
                self.persona_combo.setCurrentIndex(idx)

        self.persona_combo.blockSignals(False)
        self._update_persona_display()

    def set_context_sources(
        self,
        context_ids: list[str],
        raw_payload: dict[str, Any] | None = None,
        committed_context: set[str] | None = None,
    ) -> None:
        """Met à jour les sources de travail et recalcule les estimations de tokens."""
        self.active_context = list(context_ids)
        self._last_context_payload = raw_payload or {}
        committed_set = committed_context or set()

        # Nettoyer les cartes existantes
        while self.sources_layout.count() > 0:
            item = self.sources_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        self.empty_state_lbl.setVisible(len(self.active_context) == 0)

        total_sources_tok = 0

        for ctx_id in self.active_context:
            title = "Élément"
            subtitle = ""
            tok = 0
            icon = "ph.file"
            is_comm = ctx_id in committed_set

            if ctx_id.startswith("deck_"):
                try:
                    d_id = int(ctx_id.split("_")[1])
                    deck = DeckModel.get_or_none(DeckModel.id == d_id)
                    if deck:
                        card_cnt = CardModel.select().where(CardModel.deck == deck).count()
                        title = f"🎴 Paquet : {deck.name}"
                        subtitle = f"{card_cnt} cartes"
                        tok = card_cnt * 25
                        icon = "ph.cards"
                except Exception:
                    pass

            elif ctx_id.startswith("doc_"):
                try:
                    d_id = int(ctx_id.split("_")[1])
                    doc = DocumentModel.get_or_none(DocumentModel.id == d_id)
                    if doc:
                        title = f"📄 Document : {doc.title}"
                        doc_len = len(getattr(doc, "content", "") or "")
                        tok = ContextCompactor.estimate_tokens(getattr(doc, "content", "") or "")
                        subtitle = f"{doc_len:,} caractères • 🟢 Index RAG"
                        icon = "ph.file-text"
                except Exception:
                    pass

            elif ctx_id.startswith("card_"):
                try:
                    n_id = int(ctx_id.split("_")[1])
                    note = NoteModel.get_or_none(NoteModel.id == n_id)
                    if note:
                        active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                        snip = ""
                        if active_v and active_v.content:
                            try:
                                d_c = json.loads(active_v.content)
                                snip = d_c.get("Front", d_c.get("Recto", active_v.content))
                            except Exception:
                                snip = active_v.content
                        title = f"🗂️ Carte ciblée #{note.id}"
                        subtitle = f"{str(snip)[:30]}..."
                        tok = 60
                        icon = "ph.cardholder"
                except Exception:
                    pass

            elif ctx_id.startswith("model_"):
                try:
                    m_val = ctx_id.split("_")[1]
                    nt = NoteTypeModel.get_or_none(NoteTypeModel.id == int(m_val)) if m_val.isdigit() else NoteTypeModel.get_or_none(NoteTypeModel.name == m_val)
                    if nt:
                        title = f"🎨 Modèle : {nt.name}"
                        subtitle = "Gabarit de carte & CSS"
                        tok = 150
                        icon = "ph.paint-brush"
                except Exception:
                    pass

            total_sources_tok += tok
            card = ContextAssetCard(ctx_id, title, subtitle, tok, icon_name=icon, is_committed=is_comm)
            card.remove_requested.connect(self.context_removed.emit)
            self.sources_layout.addWidget(card)

        self._sources_tokens = total_sources_tok
        self.update_token_breakdown()

    def set_history_tokens(self, tokens: int) -> None:
        self._history_tokens = tokens
        self.update_token_breakdown()

    def update_token_breakdown(self) -> None:
        total = self._persona_tokens + self._sources_tokens + self._history_tokens
        pct = min(100, int((total / max(1, self._max_context_limit)) * 100))
        self.progress_tokens.setValue(pct)

        self.lbl_token_usage_total.setText(f"{total:,} / {self._max_context_limit // 1000}k tokens ({pct}%)")
        self.lbl_bd_system.setText(f"• 🧠 Persona & Outils : ~{self._persona_tokens:,} tokens")
        self.lbl_bd_sources.setText(f"• 📚 Sources connectées : ~{self._sources_tokens:,} tokens ({len(self.active_context)} act.)")
        self.lbl_bd_history.setText(f"• 💬 Historique de chat : ~{self._history_tokens:,} tokens")

    def _update_proactive_actions(self, has_deck: bool, has_doc: bool) -> None:
        """Méthode de compatibilité conservée sans boutons manuels superflus."""
        pass

    def _on_persona_combo_changed(self) -> None:
        self._update_persona_display()
        persona = self.persona_combo.currentData()
        if persona:
            self.persona_changed.emit(persona)

    def _update_persona_display(self) -> None:
        p: PersonaModel | None = self.persona_combo.currentData()
        if p and hasattr(p, "system_prompt") and p.system_prompt:
            pr_text = str(p.system_prompt)
            snip = pr_text[:130] + "..." if len(pr_text) > 130 else pr_text
            self.lbl_system_directive.setText(f'"{snip}"')
            self._persona_tokens = ContextCompactor.estimate_tokens(pr_text) + 200
        self.update_token_breakdown()

    def _show_raw_dialog(self) -> None:
        dlg = RawContextDialog(self._last_context_payload, parent=self)
        dlg.exec()

    def refresh_theme(self, profile: Any) -> None:
        self.update_token_breakdown()
