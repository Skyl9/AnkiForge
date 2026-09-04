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
    QPushButton,
    QScrollArea,
    QSizePolicy,
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
    Badge,
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
        icon_color: str = "",
        bg_tint: str = "",
        is_committed: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.ctx_id = ctx_id
        self.token_est = token_est
        self.is_committed = is_committed
        self._setup_ui(
            title=title,
            subtitle=subtitle,
            token_est=token_est,
            icon_name=icon_name,
            icon_color=icon_color or DesignTokens.ACCENT_PRIMARY,
            bg_tint=bg_tint or "rgba(99, 102, 241, 0.12)",
            is_committed=is_committed,
        )

    def _setup_ui(
        self,
        title: str,
        subtitle: str,
        token_est: int,
        icon_name: str,
        icon_color: str,
        bg_tint: str,
        is_committed: bool,
    ) -> None:
        self.setStyleSheet(f"""
            ContextAssetCard {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                margin-bottom: 2px;
            }}
            ContextAssetCard:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        # Conteneur d'icône teinté
        icon_box = QFrame()
        icon_box.setFixedSize(28, 28)
        icon_box.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_tint};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        ib_layout = QHBoxLayout(icon_box)
        ib_layout.setContentsMargins(0, 0, 0, 0)
        lbl_icon = QLabel()
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_icon.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(16, 16))
        ib_layout.addWidget(lbl_icon)
        layout.addWidget(icon_box)

        # Textes
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"font-weight: 600; font-size: 11px; color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
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
                font-family: '{DesignTokens.FONT_CODE}';
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
    add_deck_requested = Signal()
    add_doc_requested = Signal()
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
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(12, 12, 12, 14)
        container_layout.setSpacing(14)

        # ── 1. Section Persona & Directive Active ────────────────────────────
        sec_persona_header = QHBoxLayout()
        sec_persona_header.setContentsMargins(0, 0, 0, 0)
        sec_persona_header.setSpacing(6)

        lbl_persona_icon = QLabel()
        lbl_persona_icon.setPixmap(load_phosphor_icon("ph.brain", color=DesignTokens.ACCENT_PRIMARY).pixmap(14, 14))
        sec_persona_header.addWidget(lbl_persona_icon)

        lbl_persona_sec = QLabel("PERSONA & DIRECTIVE ACTIVE")
        lbl_persona_sec.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {DesignTokens.TEXT_MUTED}; letter-spacing: 0.5px;")
        sec_persona_header.addWidget(lbl_persona_sec)
        sec_persona_header.addStretch()
        container_layout.addLayout(sec_persona_header)

        persona_card = QFrame()
        persona_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        persona_layout = QVBoxLayout(persona_card)
        persona_layout.setContentsMargins(10, 10, 10, 10)
        persona_layout.setSpacing(8)

        # Ligne supérieure : Avatar de l'agent + Combo + Badge de portée
        persona_top_row = QHBoxLayout()
        persona_top_row.setContentsMargins(0, 0, 0, 0)
        persona_top_row.setSpacing(8)

        self.persona_avatar = QLabel()
        self.persona_avatar.setFixedSize(26, 26)
        self.persona_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.persona_avatar.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 13px;
            }}
        """)
        self.persona_avatar.setPixmap(load_phosphor_icon("ph.robot", color=DesignTokens.ACCENT_PRIMARY).pixmap(14, 14))
        persona_top_row.addWidget(self.persona_avatar)

        self.persona_combo = StyledComboBox()
        self.persona_combo.currentIndexChanged.connect(self._on_persona_combo_changed)
        persona_top_row.addWidget(self.persona_combo, 1)

        self.persona_badge = Badge("MCP", variant="neutral")
        persona_top_row.addWidget(self.persona_badge)
        persona_layout.addLayout(persona_top_row)

        # Encadré de citation pour la directive
        self.directive_frame = QFrame()
        self.directive_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-left: 3px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        dir_layout = QVBoxLayout(self.directive_frame)
        dir_layout.setContentsMargins(8, 6, 8, 6)
        dir_layout.setSpacing(2)

        self.lbl_system_directive = QLabel('"Directeur qualité : 20 règles de Piotr Wozniak, atomicité et clarté"')
        self.lbl_system_directive.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY}; font-style: italic; background: transparent; border: none; line-height: 1.4;")
        self.lbl_system_directive.setWordWrap(True)
        dir_layout.addWidget(self.lbl_system_directive)

        persona_layout.addWidget(self.directive_frame)
        container_layout.addWidget(persona_card)

        # ── 2. Espace de Travail Actif (Working Scope) ───────────────────────
        scope_header = QHBoxLayout()
        scope_header.setContentsMargins(0, 0, 0, 0)
        scope_header.setSpacing(6)

        lbl_scope_icon = QLabel()
        lbl_scope_icon.setPixmap(load_phosphor_icon("ph.stack", color=DesignTokens.ACCENT_PRIMARY).pixmap(14, 14))
        scope_header.addWidget(lbl_scope_icon)

        lbl_scope = QLabel("ESPACE DE TRAVAIL")
        lbl_scope.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {DesignTokens.TEXT_MUTED}; letter-spacing: 0.5px;")
        scope_header.addWidget(lbl_scope)

        self.lbl_scope_badge = Badge("0", variant="neutral")
        scope_header.addWidget(self.lbl_scope_badge)
        scope_header.addStretch()

        self.btn_add_source = SecondaryButton("+ Lier (@)")
        self.btn_add_source.setFixedHeight(24)
        self.btn_add_source.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
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
        self.sources_layout.setSpacing(3)
        container_layout.addWidget(self.sources_container)

        # État vide moderne et interactif (attribut conservé pour compatibilité des tests)
        self.empty_state_lbl = QFrame()
        self.empty_state_lbl.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px dashed {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        empty_layout = QVBoxLayout(self.empty_state_lbl)
        empty_layout.setContentsMargins(10, 12, 10, 12)
        empty_layout.setSpacing(6)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_icon = QLabel()
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon.setPixmap(load_phosphor_icon("ph.folder-dashed", color=DesignTokens.TEXT_MUTED).pixmap(24, 24))
        empty_layout.addWidget(empty_icon)

        empty_title = QLabel("Aucune source active")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        empty_layout.addWidget(empty_title)

        empty_sub = QLabel("Tapez @ ou liez un paquet pour contextualiser les analyses.")
        empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_sub.setStyleSheet(f"font-size: 10px; color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        empty_sub.setWordWrap(True)
        empty_layout.addWidget(empty_sub)

        # Puces d'ajout rapide
        quick_btns_layout = QHBoxLayout()
        quick_btns_layout.setSpacing(6)
        quick_btns_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_quick_deck = QPushButton("🎴 Paquet Anki")
        btn_quick_deck.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_quick_deck.setFixedHeight(22)
        btn_quick_deck.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_SECONDARY};
                font-size: 10px;
                font-weight: 600;
                padding: 2px 8px;
            }}
            QPushButton:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
                color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        btn_quick_deck.clicked.connect(self.add_deck_requested.emit)
        quick_btns_layout.addWidget(btn_quick_deck)

        btn_quick_doc = QPushButton("📄 Cours / PDF")
        btn_quick_doc.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_quick_doc.setFixedHeight(22)
        btn_quick_doc.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_SECONDARY};
                font-size: 10px;
                font-weight: 600;
                padding: 2px 8px;
            }}
            QPushButton:hover {{
                border-color: {DesignTokens.COLOR_BLUE};
                color: {DesignTokens.COLOR_BLUE};
            }}
        """)
        btn_quick_doc.clicked.connect(self.add_doc_requested.emit)
        quick_btns_layout.addWidget(btn_quick_doc)

        empty_layout.addLayout(quick_btns_layout)
        container_layout.addWidget(self.empty_state_lbl)

        # Stubs pour compatibilité ascendante
        self.actions_container = QWidget()
        self.actions_layout = QVBoxLayout(self.actions_container)

        # ── 3. Jauge et Décomposition de Mémoire (/context breakdown) ───────
        sec_mem_header = QHBoxLayout()
        sec_mem_header.setContentsMargins(0, 0, 0, 0)
        sec_mem_header.setSpacing(6)

        lbl_mem_icon = QLabel()
        lbl_mem_icon.setPixmap(load_phosphor_icon("ph.chart-pie-slice", color=DesignTokens.ACCENT_PRIMARY).pixmap(14, 14))
        sec_mem_header.addWidget(lbl_mem_icon)

        lbl_memory_sec = QLabel("FENÊTRE D'ATTENTION & TOKENS")
        lbl_memory_sec.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {DesignTokens.TEXT_MUTED}; letter-spacing: 0.5px;")
        sec_mem_header.addWidget(lbl_memory_sec)
        sec_mem_header.addStretch()

        self.btn_inspect_raw = IconButton("ph.magnifying-glass", tooltip="Inspecter le prompt brut complet (JSON)", size=20)
        self.btn_inspect_raw.clicked.connect(self._show_raw_dialog)
        sec_mem_header.addWidget(self.btn_inspect_raw)
        container_layout.addLayout(sec_mem_header)

        memory_card = QFrame()
        memory_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        memory_layout = QVBoxLayout(memory_card)
        memory_layout.setContentsMargins(10, 10, 10, 10)
        memory_layout.setSpacing(10)

        # En-tête métrique : 1,190 / 128k tokens + Badge pourcentage
        bar_header = QHBoxLayout()
        bar_header.setContentsMargins(0, 0, 0, 0)
        self.lbl_token_usage_total = QLabel("0 / 128k tokens (0%)")
        self.lbl_token_usage_total.setStyleSheet(f"font-size: 11px; font-family: '{DesignTokens.FONT_CODE}'; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        bar_header.addWidget(self.lbl_token_usage_total)
        bar_header.addStretch()

        self.badge_usage_pct = Badge("0%", variant="success")
        bar_header.addWidget(self.badge_usage_pct)
        memory_layout.addLayout(bar_header)

        # Jauge arrondie 8px
        self.progress_tokens = QProgressBar()
        self.progress_tokens.setRange(0, 100)
        self.progress_tokens.setValue(0)
        self.progress_tokens.setFixedHeight(8)
        self.progress_tokens.setTextVisible(False)
        self._update_progress_bar_style(0)
        memory_layout.addWidget(self.progress_tokens)

        # Tableau structuré de ventilation (Breakdown)
        breakdown_box = QFrame()
        breakdown_box.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        bd_layout = QVBoxLayout(breakdown_box)
        bd_layout.setContentsMargins(8, 8, 8, 8)
        bd_layout.setSpacing(6)

        # Ligne 1 : Persona
        row_sys = QHBoxLayout()
        row_sys.setContentsMargins(0, 0, 0, 0)
        dot_sys = QLabel("🟣")
        dot_sys.setStyleSheet("font-size: 9px;")
        row_sys.addWidget(dot_sys)
        lbl_sys_title = QLabel("Persona & Consignes")
        lbl_sys_title.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY};")
        row_sys.addWidget(lbl_sys_title)
        row_sys.addStretch()
        self.lbl_bd_system = QLabel("~250 tok")
        self.lbl_bd_system.setStyleSheet(f"font-size: 11px; font-family: '{DesignTokens.FONT_CODE}'; color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600;")
        row_sys.addWidget(self.lbl_bd_system)
        bd_layout.addLayout(row_sys)

        # Ligne 2 : Sources
        row_src = QHBoxLayout()
        row_src.setContentsMargins(0, 0, 0, 0)
        dot_src = QLabel("🔵")
        dot_src.setStyleSheet("font-size: 9px;")
        row_src.addWidget(dot_src)
        lbl_src_title = QLabel("Sources de travail")
        lbl_src_title.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY};")
        row_src.addWidget(lbl_src_title)
        row_src.addStretch()
        self.lbl_bd_sources = QLabel("0 tok")
        self.lbl_bd_sources.setStyleSheet(f"font-size: 11px; font-family: '{DesignTokens.FONT_CODE}'; color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600;")
        row_src.addWidget(self.lbl_bd_sources)
        bd_layout.addLayout(row_src)

        # Ligne 3 : Historique
        row_hist = QHBoxLayout()
        row_hist.setContentsMargins(0, 0, 0, 0)
        dot_hist = QLabel("🟢")
        dot_hist.setStyleSheet("font-size: 9px;")
        row_hist.addWidget(dot_hist)
        lbl_hist_title = QLabel("Historique de chat")
        lbl_hist_title.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY};")
        row_hist.addWidget(lbl_hist_title)
        row_hist.addStretch()
        self.lbl_bd_history = QLabel("0 tok")
        self.lbl_bd_history.setStyleSheet(f"font-size: 11px; font-family: '{DesignTokens.FONT_CODE}'; color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600;")
        row_hist.addWidget(self.lbl_bd_history)
        bd_layout.addLayout(row_hist)

        memory_layout.addWidget(breakdown_box)

        # Bouton compacter
        self.btn_compact = SecondaryButton("⚡ Compacter (/compact)")
        self.btn_compact.setToolTip("Résumer automatiquement l'historique pour libérer des tokens")
        self.btn_compact.setIcon(load_phosphor_icon("ph.arrows-in-line-vertical", color=DesignTokens.TEXT_PRIMARY))
        self.btn_compact.clicked.connect(self.compact_requested.emit)
        memory_layout.addWidget(self.btn_compact)

        container_layout.addWidget(memory_card)
        container_layout.addStretch()

        scroll_area.setWidget(container)
        main_layout.addWidget(scroll_area)

    def _update_progress_bar_style(self, pct: int) -> None:
        if pct < 60:
            chunk_color = DesignTokens.COLOR_GREEN
        elif pct < 85:
            chunk_color = DesignTokens.COLOR_YELLOW
        else:
            chunk_color = DesignTokens.COLOR_RED

        self.progress_tokens.setStyleSheet(f"""
            QProgressBar {{
                background-color: {DesignTokens.BG_PANEL};
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {chunk_color};
                border-radius: 4px;
            }}
        """)

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
        self.lbl_scope_badge.setText(str(len(self.active_context)))
        self.lbl_scope_badge.set_variant("info" if self.active_context else "neutral")

        total_sources_tok = 0

        for ctx_id in self.active_context:
            title = "Élément"
            subtitle = ""
            tok = 0
            icon = "ph.file"
            icon_color = DesignTokens.ACCENT_PRIMARY
            bg_tint = "rgba(99, 102, 241, 0.15)"
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
                        icon_color = DesignTokens.ACCENT_PRIMARY
                        bg_tint = "rgba(99, 102, 241, 0.15)"
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
                        icon_color = DesignTokens.COLOR_BLUE
                        bg_tint = "rgba(59, 130, 246, 0.15)"
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
                        icon_color = DesignTokens.COLOR_GREEN
                        bg_tint = "rgba(16, 185, 129, 0.15)"
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
                        icon_color = DesignTokens.COLOR_YELLOW
                        bg_tint = "rgba(245, 158, 11, 0.15)"
                except Exception:
                    pass

            total_sources_tok += tok
            card = ContextAssetCard(
                ctx_id,
                title,
                subtitle,
                tok,
                icon_name=icon,
                icon_color=icon_color,
                bg_tint=bg_tint,
                is_committed=is_comm,
            )
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
        self._update_progress_bar_style(pct)

        self.lbl_token_usage_total.setText(f"{total:,} / {self._max_context_limit // 1000}k tokens ({pct}%)")
        self.badge_usage_pct.setText(f"{pct}%")
        if pct < 60:
            self.badge_usage_pct.set_variant("success")
        elif pct < 85:
            self.badge_usage_pct.set_variant("warning")
        else:
            self.badge_usage_pct.set_variant("danger")

        self.lbl_bd_system.setText(f"~{self._persona_tokens:,} tok")
        self.lbl_bd_sources.setText(f"~{self._sources_tokens:,} tok ({len(self.active_context)} act.)" if self.active_context else "0 tok")
        self.lbl_bd_history.setText(f"~{self._history_tokens:,} tok")

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
            pr_text = str(p.system_prompt).strip()
            if len(pr_text) > 130:
                words = pr_text[:130].rsplit(" ", 1)[0]
                snip = f"{words}..."
            else:
                snip = pr_text
            self.lbl_system_directive.setText(f'"{snip}"')
            self._persona_tokens = ContextCompactor.estimate_tokens(pr_text) + 200
            p_type = getattr(p, "persona_type", "mcp")
            if p_type == "mcp":
                self.persona_badge.setText("MCP")
                self.persona_badge.set_variant("neutral")
            elif p_type == "pipeline":
                self.persona_badge.setText("Pipeline")
                self.persona_badge.set_variant("info")
            else:
                self.persona_badge.setText("Global")
                self.persona_badge.set_variant("success")
        self.update_token_breakdown()

    def _show_raw_dialog(self) -> None:
        dlg = RawContextDialog(self._last_context_payload, parent=self)
        dlg.exec()

    def refresh_theme(self, profile: Any) -> None:
        self.update_token_breakdown()
        self._update_persona_display()
