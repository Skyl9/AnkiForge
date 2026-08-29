import json
import logging
from typing import Any

from PySide6.QtCore import QPoint, QSize, Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    LLMConfigModel,
    PersonaFolderModel,
    PersonaModel,
    db,
)
from ankiforge.services.ai.persona_version_service import PersonaVersionService
from ankiforge.services.tools.tool_service import ToolService
from ankiforge.ui.components import (
    Badge,
    FlowWidget,
    GlowLineEdit,
    IconButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
    StyledTextEdit,
)
from ankiforge.ui.dialogs.persona_history_dialog import PersonaHistoryDialog
from ankiforge.ui.theme import DesignTokens, StyledMenu
from ankiforge.ui.views.agents_view.constants import (
    JINJA2_SNIPPETS,
    MCP_BASE_TOOLS_SPEC,
    PERSONA_TYPE_SPECS,
)
from ankiforge.ui.views.agents_view.dialogs import (
    AgentPromptPreviewDialog,
    AgentTestDialog,
)
from ankiforge.ui.views.agents_view.widgets import (
    FolderHeaderWidget,
    PersonaItemWidget,
    ResponsiveAgentTopActionBar,
    SubTabButton,
    TagPillButton,
    ToolPermissionCard,
)
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class AgentsView(QWidget):
    """
    Vue Atelier d'Agents IA — Architecture Maître-Détail avec dossiers et sous-dossiers récursifs.
    """

    def __init__(
        self,
        ai_manager: Any | None = None,
        profile_name: str = "default",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.profile_name = profile_name
        self._current_agent: PersonaModel | None = None
        self._current_folder: PersonaFolderModel | None = None
        self._tool_cards: dict[str, ToolPermissionCard] = {}
        self._tool_checkboxes: dict[str, QCheckBox] = {}  # Rétrocompatibilité tests
        self._cached_personas: list[PersonaModel] = []
        self._cached_folders: list[PersonaFolderModel] = []
        self._current_scope_filter: str = "all"  # 'all', 'pipeline', 'mcp', 'universal'

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # ── 1. Panneau Gauche : Arborescence Dossiers & Personas ───────────────
        self.list_panel = IdePanel(detachable=True)
        self.list_panel.setMinimumWidth(320)

        list_content = QWidget()
        list_layout = QVBoxLayout(list_content)
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(8)

        # Ligne 1 : Titre + Compteur
        h_row = QHBoxLayout()
        h_row.setContentsMargins(0, 0, 0, 0)
        lbl_list_title = QLabel("AGENTS & DOSSIERS :")
        lbl_list_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        h_row.addWidget(lbl_list_title)
        h_row.addStretch()

        self.lbl_count_badge = Badge("0 agents", variant="neutral")
        self.lbl_count_badge.setFixedHeight(18)
        h_row.addWidget(self.lbl_count_badge)
        list_layout.addLayout(h_row)

        # Ligne 2 : Recherche + Bouton Nouvel Agent
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(6)

        self.edit_search = GlowLineEdit(placeholder="Filtrer par nom, rôle...")
        self.edit_search.setFixedHeight(28)
        self.edit_search.textChanged.connect(self._apply_filters)
        search_row.addWidget(self.edit_search, 1)

        self.btn_new = PrimaryButton("Nouvel Agent")
        self.btn_new.setIcon(load_phosphor_icon("ph.plus", color="white"))
        self.btn_new.setIconSize(QSize(14, 14))
        self.btn_new.setFixedHeight(30)
        search_row.addWidget(self.btn_new)
        list_layout.addLayout(search_row)

        # Ligne 3 : Filtres Segmented par Portée (Pills)
        filter_bar = QHBoxLayout()
        filter_bar.setContentsMargins(0, 0, 0, 0)
        filter_bar.setSpacing(4)

        self.btn_filter_all = QPushButton("Tous")
        self.btn_filter_pipe = QPushButton("⚡ Pipeline")
        self.btn_filter_mcp = QPushButton("🤝 MCP")
        self.btn_filter_univ = QPushButton("🌐 Universel")

        self._filter_buttons = [
            (self.btn_filter_all, "all"),
            (self.btn_filter_pipe, "pipeline"),
            (self.btn_filter_mcp, "mcp"),
            (self.btn_filter_univ, "universal"),
        ]

        for btn, scope in self._filter_buttons:
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 9999px;
                    color: {DesignTokens.TEXT_MUTED};
                    font-size: 10px;
                    font-weight: bold;
                    padding: 2px 7px;
                }}
                QPushButton:hover {{
                    color: {DesignTokens.TEXT_PRIMARY};
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                }}
                QPushButton:checked {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                    color: {DesignTokens.ACCENT_PRIMARY};
                }}
            """)
            btn.clicked.connect(lambda _, s=scope: self._set_scope_filter(s))
            filter_bar.addWidget(btn)

        filter_bar.addStretch()
        self.btn_filter_all.setChecked(True)
        list_layout.addLayout(filter_bar)

        # Arbre des dossiers et personas (QTreeWidget)
        self.persona_tree = QTreeWidget()
        self.persona_tree.setHeaderHidden(True)
        self.persona_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.persona_tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        self.persona_tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: transparent;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                outline: none;
                padding: 4px;
            }}
            QTreeWidget::item {{
                padding: 2px 2px;
                border-radius: 4px;
                margin-bottom: 2px;
            }}
            QTreeWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QTreeWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
                border-left: 2px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        list_layout.addWidget(self.persona_tree, 1)

        # Barre d'actions inférieure
        list_toolbar = QHBoxLayout()
        list_toolbar.setSpacing(6)

        self.btn_new_folder = SecondaryButton("Nouveau Dossier")
        self.btn_new_folder.setIcon(load_phosphor_icon("ph.folder-plus", color=DesignTokens.TEXT_PRIMARY))
        self.btn_new_folder.setIconSize(QSize(14, 14))
        self.btn_new_folder.setFixedHeight(30)

        self.btn_clone = IconButton("ph.copy", tooltip="Dupliquer l'agent sélectionné", size=30)
        self.btn_del = IconButton("ph.trash", tooltip="Supprimer l'élément sélectionné", size=30)

        list_toolbar.addWidget(self.btn_new_folder, 1)
        list_toolbar.addWidget(self.btn_clone)
        list_toolbar.addWidget(self.btn_del)
        list_layout.addLayout(list_toolbar)

        self.list_panel.add_tab("Arborescence d'Agents", list_content, "ph.folder-simple", closable=False)
        self.main_splitter.addWidget(self.list_panel)

        # ── 2. Panneau Droit : Éditeur Riche à Sous-Onglets IDE ────────────────
        self.editor_panel = IdePanel(detachable=True)

        editor_content = QWidget()
        editor_layout = QVBoxLayout(editor_content)
        editor_layout.setContentsMargins(10, 10, 10, 10)
        editor_layout.setSpacing(10)

        # ResponsiveTopActionBar
        self.top_action_bar = ResponsiveAgentTopActionBar()
        self.lbl_agent_icon = self.top_action_bar.lbl_agent_icon
        self.lbl_agent_title = self.top_action_bar.lbl_agent_title
        self.scope_badge = self.top_action_bar.scope_badge
        self.format_badge = self.top_action_bar.format_badge
        self.btn_history = self.top_action_bar.btn_history
        self.btn_test = self.top_action_bar.btn_test
        self.btn_save = self.top_action_bar.btn_save

        self.btn_history.clicked.connect(self._on_open_history)
        self.btn_test.clicked.connect(self._on_test_agent)

        editor_layout.addWidget(self.top_action_bar)

        # Barre de Sous-Onglets style IDE
        subtabs_bar = QHBoxLayout()
        subtabs_bar.setContentsMargins(0, 0, 0, 0)
        subtabs_bar.setSpacing(6)

        self.btn_subtab_identity = SubTabButton("Identité && Moteur IA", "ph.gear")
        self.btn_subtab_prompt = SubTabButton("Instructions && Prompt", "ph.sparkle")
        self.btn_subtab_tools = SubTabButton("Permissions d'Outils", "ph.wrench")

        self.btn_subtab_identity.clicked.connect(lambda: self._switch_subtab(0))
        self.btn_subtab_prompt.clicked.connect(lambda: self._switch_subtab(1))
        self.btn_subtab_tools.clicked.connect(lambda: self._switch_subtab(2))

        subtabs_bar.addWidget(self.btn_subtab_identity)
        subtabs_bar.addWidget(self.btn_subtab_prompt)
        subtabs_bar.addWidget(self.btn_subtab_tools)
        subtabs_bar.addStretch()

        editor_layout.addLayout(subtabs_bar)

        # Stack de contenu
        self.tabs = QStackedWidget()
        self.tabs.setObjectName("agentSubtabsStack")
        self.tabs.setStyleSheet(f"""
            QStackedWidget#agentSubtabsStack {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        editor_layout.addWidget(self.tabs, 1)

        # ── ONGLET 1 : Identité & Moteur IA ──
        tab_identity = QWidget()
        layout_identity = QVBoxLayout(tab_identity)
        layout_identity.setContentsMargins(14, 14, 14, 14)
        layout_identity.setSpacing(14)

        lbl_name = QLabel("NOM DU PERSONA :")
        lbl_name.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        layout_identity.addWidget(lbl_name)
        self.name_edit = StyledLineEdit()
        self.name_edit.setPlaceholderText("ex: Architecte de Cours, Linteur Wozniak, Consultant SRS...")
        layout_identity.addWidget(self.name_edit)

        lbl_desc = QLabel("DESCRIPTION & RÔLE :")
        lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        layout_identity.addWidget(lbl_desc)
        self.desc_edit = StyledLineEdit()
        self.desc_edit.setPlaceholderText("ex: Découpe le cours en concepts atomiques selon la règle de formulation minimale.")
        layout_identity.addWidget(self.desc_edit)

        row_props = QHBoxLayout()
        row_props.setSpacing(12)

        col_folder = QVBoxLayout()
        col_folder.setSpacing(4)
        lbl_folder_title = QLabel("DOSSIER D'APPARTENANCE :")
        lbl_folder_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        col_folder.addWidget(lbl_folder_title)
        self.folder_combo = StyledComboBox()
        self.folder_combo.currentIndexChanged.connect(self._on_folder_combo_changed)
        col_folder.addWidget(self.folder_combo)
        row_props.addLayout(col_folder, 1)

        col_scope = QVBoxLayout()
        col_scope.setSpacing(4)
        lbl_scope_title = QLabel("PORTÉE / USAGE DE L'AGENT :")
        lbl_scope_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        col_scope.addWidget(lbl_scope_title)
        self.scope_combo = StyledComboBox()
        for s_key, s_spec in PERSONA_TYPE_SPECS.items():
            self.scope_combo.addItem(s_spec["label"], userData=s_key)
        self.scope_combo.currentIndexChanged.connect(self._on_scope_changed)
        col_scope.addWidget(self.scope_combo)
        row_props.addLayout(col_scope, 1)

        col_fmt = QVBoxLayout()
        col_fmt.setSpacing(4)
        lbl_format = QLabel("FORMAT DE SORTIE :")
        lbl_format.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        col_fmt.addWidget(lbl_format)
        self.format_combo = StyledComboBox()
        self.format_combo.addItems(["json", "cloze", "markdown", "text"])
        col_fmt.addWidget(self.format_combo)
        row_props.addLayout(col_fmt, 1)

        layout_identity.addLayout(row_props)

        self.scope_info_card = QFrame()
        self.scope_info_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px;
            }}
        """)
        layout_scope_info = QHBoxLayout(self.scope_info_card)
        layout_scope_info.setContentsMargins(10, 8, 10, 8)
        self.lbl_scope_info = QLabel(PERSONA_TYPE_SPECS["pipeline"]["desc"])
        self.lbl_scope_info.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        self.lbl_scope_info.setWordWrap(True)
        layout_scope_info.addWidget(self.lbl_scope_info)
        layout_identity.addWidget(self.scope_info_card)

        lbl_engine = QLabel("MOTEUR IA DÉDIÉ (OPTIONNEL) :")
        lbl_engine.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        layout_identity.addWidget(lbl_engine)
        self.engine_combo = StyledComboBox()
        layout_identity.addWidget(self.engine_combo)

        self.engine_info_card = QFrame()
        self.engine_info_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px dashed {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px;
            }}
        """)
        layout_engine_info = QHBoxLayout(self.engine_info_card)
        layout_engine_info.setContentsMargins(10, 8, 10, 8)
        self.lbl_engine_info = QLabel("⚙️ Cet agent utilisera le modèle IA global par défaut défini dans les Paramètres.")
        self.lbl_engine_info.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; background: transparent;")
        layout_engine_info.addWidget(self.lbl_engine_info)
        layout_identity.addWidget(self.engine_info_card)

        layout_identity.addStretch()
        self.tabs.addWidget(tab_identity)

        # ── ONGLET 2 : Instructions & Prompt Jinja2 ──
        tab_prompt = QWidget()
        layout_prompt = QVBoxLayout(tab_prompt)
        layout_prompt.setContentsMargins(14, 14, 14, 14)
        layout_prompt.setSpacing(10)

        snippets_header = QHBoxLayout()
        lbl_prompt_title = QLabel("INSTRUCTIONS SYSTÈME (JINJA2 TEMPLATE) :")
        lbl_prompt_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        snippets_header.addWidget(lbl_prompt_title)
        snippets_header.addStretch()

        self.btn_preview_prompt = SecondaryButton("Aperçu Interpolé (Jinja2)")
        self.btn_preview_prompt.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_PRIMARY))
        self.btn_preview_prompt.setFixedHeight(28)
        self.btn_preview_prompt.clicked.connect(self._on_preview_prompt)
        snippets_header.addWidget(self.btn_preview_prompt)
        layout_prompt.addLayout(snippets_header)

        palette_box = QVBoxLayout()
        palette_box.setSpacing(4)
        lbl_snip = QLabel("Insérer au curseur :")
        lbl_snip.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        palette_box.addWidget(lbl_snip)

        self.snippets_flow = FlowWidget(margin=0, h_spacing=6, v_spacing=6)
        snippet_variants = ["field", "condition", "structure", "css", "cloze", "field", "condition"]
        for i, (template_code, display_name, tooltip) in enumerate(JINJA2_SNIPPETS):
            var_type = snippet_variants[i % len(snippet_variants)]
            btn_snip = TagPillButton(display_name, template_code=template_code, tooltip=tooltip, variant=var_type)
            btn_snip.clicked.connect(lambda _, code=template_code: self._insert_jinja_snippet(code))
            self.snippets_flow.addWidget(btn_snip)

        palette_box.addWidget(self.snippets_flow)
        layout_prompt.addLayout(palette_box)

        self.prompt_edit = StyledTextEdit()
        self.prompt_edit.setPlaceholderText("Tu es un agent expert en création de flashcards Anki...\nUtilisez {{ text_source }} et les variables Jinja2.")
        self.prompt_edit.setMinimumHeight(240)
        self.prompt_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                color: #a5b4fc;
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 12px;
                line-height: 1.5;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 12px;
            }}
            QPlainTextEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.prompt_edit.textChanged.connect(self._update_tokens_count)
        layout_prompt.addWidget(self.prompt_edit, 1)

        self.lbl_tokens = QLabel("Aa 0 caractères  |  ~0 Tokens estimés")
        self.lbl_tokens.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-family: monospace;")
        layout_prompt.addWidget(self.lbl_tokens)

        self.tabs.addWidget(tab_prompt)

        # ── ONGLET 3 : Permissions d'Outils MCP & Python ──
        tab_tools = QWidget()
        layout_tools = QVBoxLayout(tab_tools)
        layout_tools.setContentsMargins(14, 14, 14, 14)
        layout_tools.setSpacing(10)

        tools_header = QHBoxLayout()
        lbl_tools_title = QLabel("PERMISSIONS D'OUTILS (MCP & OUTILS PYTHON DÉTERMINISTES) :")
        lbl_tools_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        tools_header.addWidget(lbl_tools_title)
        tools_header.addStretch()

        btn_select_all = SecondaryButton("Tout Cocher")
        btn_select_all.setFixedHeight(26)
        btn_select_all.clicked.connect(lambda: self._set_all_tools(True))
        btn_deselect_all = SecondaryButton("Tout Décocher")
        btn_deselect_all.setFixedHeight(26)
        btn_deselect_all.clicked.connect(lambda: self._set_all_tools(False))
        tools_header.addWidget(btn_select_all)
        tools_header.addWidget(btn_deselect_all)
        layout_tools.addLayout(tools_header)

        tools_scroll = QScrollArea()
        tools_scroll.setWidgetResizable(True)
        tools_scroll.setFrameShape(QFrame.Shape.NoFrame)
        tools_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.tools_container = QWidget()
        self.tools_layout = QVBoxLayout(self.tools_container)
        self.tools_layout.setContentsMargins(0, 0, 0, 0)
        self.tools_layout.setSpacing(8)

        self._build_tools_cards()

        tools_scroll.setWidget(self.tools_container)
        layout_tools.addWidget(tools_scroll, 1)

        self.tabs.addWidget(tab_tools)

        self._switch_subtab(0)

        self.editor_panel.add_tab("Éditeur de Persona", editor_content, "ph.sparkle", closable=False)
        self.main_splitter.addWidget(self.editor_panel)
        self.main_splitter.setSizes([340, 660])

    def _switch_subtab(self, index: int) -> None:
        self.tabs.setCurrentIndex(index)
        self.btn_subtab_identity.set_active(index == 0)
        self.btn_subtab_prompt.set_active(index == 1)
        self.btn_subtab_tools.set_active(index == 2)

    def _build_tools_cards(self) -> None:
        while self.tools_layout.count() > 0:
            item = self.tools_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        self._tool_cards.clear()
        self._tool_checkboxes.clear()

        lbl_mcp = QLabel("OUTILS MCP CONSULTANT & SYSTÈME :")
        lbl_mcp.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px; margin-top: 4px;")
        self.tools_layout.addWidget(lbl_mcp)

        for key, spec in MCP_BASE_TOOLS_SPEC.items():
            card = ToolPermissionCard(
                tool_key=key,
                label=spec["label"],
                description=spec["desc"],
                category=spec["category"],
                category_color=spec["color"],
            )
            self._tool_cards[key] = card
            self._tool_checkboxes[key] = card.checkbox
            self.tools_layout.addWidget(card)

        lbl_py = QLabel("OUTILS PYTHON DÉTERMINISTES (MOTEUR DAG) :")
        lbl_py.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px; margin-top: 8px;")
        self.tools_layout.addWidget(lbl_py)

        try:
            tools = ToolService.list_tools()
            for t in tools:
                cat = "Natif" if t.is_builtin else "Script Custom"
                col = "#3b82f6" if t.is_builtin else "#f97316"
                card = ToolPermissionCard(
                    tool_key=t.name,
                    label=t.display_name,
                    description=t.description or "Script Python utilitaire.",
                    category=cat,
                    category_color=col,
                )
                self._tool_cards[t.name] = card
                self._tool_checkboxes[t.name] = card.checkbox
                self.tools_layout.addWidget(card)
        except Exception as e:
            logger.warning("Erreur chargement des outils Python : %s", e)

        self.tools_layout.addStretch()

    def _set_all_tools(self, state: bool) -> None:
        for card in self._tool_cards.values():
            card.setChecked(state)

    def _connect_signals(self) -> None:
        self.persona_tree.currentItemChanged.connect(self._on_tree_item_selected)
        self.btn_new.clicked.connect(self._on_new_agent)
        self.btn_new_folder.clicked.connect(self._on_new_folder)
        self.btn_clone.clicked.connect(self._on_clone_agent)
        self.btn_del.clicked.connect(self._on_delete_selected)
        self.btn_save.clicked.connect(self._on_save_agent)
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)

    def refresh_data(self) -> None:
        try:
            self.engine_combo.blockSignals(True)
            self.engine_combo.clear()
            self.engine_combo.addItem("⚙️ Hériter du réglage global de l'application", userData=None)

            llm_configs = list(LLMConfigModel.select())
            for cfg in llm_configs:
                display = cfg.display_name or f"{cfg.provider} ({cfg.model_id})"
                self.engine_combo.addItem(f"🤖 {display}", userData=cfg)
            self.engine_combo.blockSignals(False)

            self._cached_folders = list(PersonaFolderModel.select().order_by(PersonaFolderModel.name.asc()))
            self._populate_folder_combo()

            self._build_tools_cards()

            self._cached_personas = list(PersonaModel.select().order_by(PersonaModel.name.asc()))
            self._apply_filters()

            if self._cached_personas and not self._current_agent:
                self._select_first_persona_in_tree()

        except Exception as e:
            logger.warning("Erreur refresh_data agents_view: %s", e)

    def _populate_folder_combo(self) -> None:
        self.folder_combo.blockSignals(True)
        self.folder_combo.clear()
        self.folder_combo.addItem("📁 Aucun dossier (Racine)", userData=None)

        def _add_folders_recursive(parent_id: int | None, prefix: str = "") -> None:
            children = [f for f in self._cached_folders if (f.parent.id if f.parent else None) == parent_id]
            for child in children:
                icon_prefix = "📁 " if parent_id is None else "↳ 📁 "
                self.folder_combo.addItem(f"{prefix}{icon_prefix}{child.name}", userData=child.id)
                _add_folders_recursive(child.id, prefix=prefix + "   ")

        _add_folders_recursive(None)

        self.folder_combo.addItem("➕ Créer un nouveau dossier racine...", userData="__NEW_ROOT__")
        self.folder_combo.addItem("➕ Créer un sous-dossier ici...", userData="__NEW_SUB__")
        self.folder_combo.blockSignals(False)

    @Slot(int)
    def _on_folder_combo_changed(self, idx: int) -> None:
        val = self.folder_combo.currentData()
        if val in ("__NEW_ROOT__", "__NEW_SUB__"):
            parent_folder = self._current_folder if val == "__NEW_SUB__" else None
            prompt_title = f"Nouveau sous-dossier dans '{parent_folder.name}'" if parent_folder else "Nouveau Dossier Racine"
            name, ok = QInputDialog.getText(self, "Création de Dossier", f"{prompt_title} :")
            if ok and name.strip():
                try:
                    new_f = PersonaFolderModel.create(name=name.strip(), parent=parent_folder)
                    self._cached_folders = list(PersonaFolderModel.select().order_by(PersonaFolderModel.name.asc()))
                    self._populate_folder_combo()
                    idx_f = self.folder_combo.findData(new_f.id)
                    if idx_f != -1:
                        self.folder_combo.setCurrentIndex(idx_f)
                    self.refresh_data()
                    show_toast(self, f"Dossier '{name.strip()}' créé !")
                except Exception as e:
                    QMessageBox.critical(self, "Erreur", f"Impossible de créer le dossier : {e}")
                    self.folder_combo.setCurrentIndex(0)
            else:
                self.folder_combo.setCurrentIndex(0)

    def _set_scope_filter(self, scope: str) -> None:
        self._current_scope_filter = scope
        for btn, s in self._filter_buttons:
            btn.setChecked(s == scope)
        self._apply_filters()

    def _apply_filters(self) -> None:
        q = self.edit_search.text().strip().lower()
        scope = self._current_scope_filter

        filtered: list[PersonaModel] = []
        for ag in self._cached_personas:
            p_type = getattr(ag, "persona_type", "pipeline") or "pipeline"
            if scope != "all" and p_type != scope:
                continue
            folder_path = ag.folder.get_full_path().lower() if getattr(ag, "folder", None) else ""
            if q and (q not in str(ag.name).lower() and q not in str(ag.description or "").lower() and q not in folder_path):
                continue
            filtered.append(ag)

        self._render_tree(filtered)

    def _render_tree(self, personas: list[PersonaModel]) -> None:
        self.persona_tree.blockSignals(True)
        self.persona_tree.clear()

        self.lbl_count_badge.setText(f"{len(personas)} agent{'s' if len(personas) > 1 else ''}")

        personas_by_folder: dict[int | None, list[PersonaModel]] = {}
        for p in personas:
            f_id = p.folder.id if getattr(p, "folder", None) else None
            personas_by_folder.setdefault(f_id, []).append(p)

        active_filter = self._current_scope_filter != "all" or bool(self.edit_search.text().strip())

        def _count_total_personas_in_folder_subtree(folder: PersonaFolderModel) -> int:
            cnt = len(personas_by_folder.get(folder.id, []))
            subfolders = [f for f in self._cached_folders if (f.parent.id if f.parent else None) == folder.id]
            for sf in subfolders:
                cnt += _count_total_personas_in_folder_subtree(sf)
            return cnt

        def _render_folder_recursive(parent_id: int | None, parent_tree_item: QTreeWidgetItem | None) -> None:
            children_folders = [f for f in self._cached_folders if (f.parent.id if f.parent else None) == parent_id]
            for folder in children_folders:
                direct_personas = personas_by_folder.get(folder.id, [])
                total_cnt = _count_total_personas_in_folder_subtree(folder)

                if active_filter and total_cnt == 0:
                    continue

                folder_item = QTreeWidgetItem(self.persona_tree) if parent_tree_item is None else QTreeWidgetItem(parent_tree_item)

                folder_item.setData(0, Qt.ItemDataRole.UserRole, ("folder", folder))
                folder_item.setSizeHint(0, QSize(0, 32))
                is_sub = folder.parent is not None
                folder_widget = FolderHeaderWidget(folder.name, total_cnt, is_root=False, is_subfolder=is_sub)
                self.persona_tree.setItemWidget(folder_item, 0, folder_widget)
                folder_item.setExpanded(True)

                _render_folder_recursive(folder.id, folder_item)

                for p in direct_personas:
                    child_item = QTreeWidgetItem(folder_item)
                    child_item.setData(0, Qt.ItemDataRole.UserRole, ("persona", p))
                    child_item.setSizeHint(0, QSize(0, 36))
                    p_widget = PersonaItemWidget(p)
                    self.persona_tree.setItemWidget(child_item, 0, p_widget)

        _render_folder_recursive(None, None)

        unfiled_personas = personas_by_folder.get(None, [])
        if unfiled_personas:
            root_item = QTreeWidgetItem(self.persona_tree)
            root_item.setData(0, Qt.ItemDataRole.UserRole, ("folder", None))
            root_item.setSizeHint(0, QSize(0, 32))
            root_widget = FolderHeaderWidget("Sans dossier", len(unfiled_personas), is_root=True)
            self.persona_tree.setItemWidget(root_item, 0, root_widget)
            root_item.setExpanded(True)

            for p in unfiled_personas:
                child_item = QTreeWidgetItem(root_item)
                child_item.setData(0, Qt.ItemDataRole.UserRole, ("persona", p))
                child_item.setSizeHint(0, QSize(0, 36))
                p_widget = PersonaItemWidget(p)
                self.persona_tree.setItemWidget(child_item, 0, p_widget)

        self.persona_tree.blockSignals(False)

    def _select_first_persona_in_tree(self) -> None:
        def _find_first_persona(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == "persona":
                return item
            for i in range(item.childCount()):
                res = _find_first_persona(item.child(i))
                if res:
                    return res
            return None

        for i in range(self.persona_tree.topLevelItemCount()):
            top_item = self.persona_tree.topLevelItem(i)
            found = _find_first_persona(top_item)
            if found:
                self.persona_tree.setCurrentItem(found)
                return

    def is_dirty(self) -> bool:
        return False

    def _insert_jinja_snippet(self, snippet: str) -> None:
        cursor = self.prompt_edit.textCursor()
        cursor.insertText(snippet)
        self.prompt_edit.setTextCursor(cursor)
        self.prompt_edit.setFocus()

    def _update_tokens_count(self) -> None:
        text = self.prompt_edit.toPlainText()
        chars = len(text)
        tokens = int(chars / 4) if chars > 0 else 0
        self.lbl_tokens.setText(f"Aa {chars} caractères  |  ~{tokens} Tokens estimés")

    @Slot()
    def _on_scope_changed(self) -> None:
        scope_key = self.scope_combo.currentData() or "pipeline"
        spec = PERSONA_TYPE_SPECS.get(scope_key, PERSONA_TYPE_SPECS["pipeline"])
        self.lbl_scope_info.setText(spec["desc"])
        if hasattr(self, "scope_badge"):
            self.scope_badge.setText(spec["badge_text"])
            self.lbl_agent_icon.setPixmap(load_phosphor_icon("ph.sparkle", color=spec["badge_color"]).pixmap(18, 18))

    @Slot()
    def _on_engine_changed(self) -> None:
        cfg = self.engine_combo.currentData()
        if cfg:
            self.lbl_engine_info.setText(f"🤖 Moteur dédié : {cfg.provider.upper()} ({cfg.model_id}) avec configuration dédiée.")
        else:
            self.lbl_engine_info.setText("⚙️ Cet agent utilisera le modèle IA global par défaut défini dans les Paramètres.")

    @Slot()
    def _on_preview_prompt(self) -> None:
        prompt_text = self.prompt_edit.toPlainText()
        dlg = AgentPromptPreviewDialog(prompt_text, parent=self)
        dlg.exec()

    @Slot()
    def _on_test_agent(self) -> None:
        if not self._current_agent:
            show_toast(self, "Aucun agent sélectionné à tester.", is_error=True)
            return
        dlg = AgentTestDialog(self._current_agent, ai_manager=self.ai_manager, parent=self)
        dlg.exec()

    @Slot()
    def _on_tree_item_selected(self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None) -> None:
        if not current:
            return

        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, obj = data
        if item_type == "folder":
            self._current_folder = obj
            return

        if item_type == "persona" and isinstance(obj, PersonaModel):
            self._current_agent = obj
            self._load_persona_into_editor(obj)

    def _load_persona_into_editor(self, ag: PersonaModel) -> None:
        self.name_edit.setText(str(ag.name) if ag.name else "")
        self.desc_edit.setText(str(ag.description) if ag.description else "")
        self.prompt_edit.setPlainText(str(ag.system_prompt) if ag.system_prompt else "")
        self._update_tokens_count()

        if hasattr(self, "lbl_agent_title"):
            self.lbl_agent_title.setText(str(ag.name) if ag.name else "Agent sans nom")

        self.folder_combo.blockSignals(True)
        f_id = ag.folder.id if getattr(ag, "folder", None) else None
        idx_f = self.folder_combo.findData(f_id)
        if idx_f != -1:
            self.folder_combo.setCurrentIndex(idx_f)
        else:
            self.folder_combo.setCurrentIndex(0)
        self.folder_combo.blockSignals(False)

        p_type = getattr(ag, "persona_type", "pipeline") or "pipeline"
        idx_scope = self.scope_combo.findData(p_type)
        if idx_scope != -1:
            self.scope_combo.setCurrentIndex(idx_scope)
        else:
            self.scope_combo.setCurrentIndex(0)
        self._on_scope_changed()

        fmt = getattr(ag, "output_format", "json").lower()
        idx = self.format_combo.findText(fmt, Qt.MatchFlag.MatchFixedString)
        if idx != -1:
            self.format_combo.setCurrentIndex(idx)
        else:
            self.format_combo.setCurrentText("json")

        if hasattr(self, "format_badge"):
            self.format_badge.setText(fmt.upper())

        self.engine_combo.blockSignals(True)
        if getattr(ag, "llm_config", None):
            cfg_id = ag.llm_config.id
            idx_e = -1
            for i in range(self.engine_combo.count()):
                cfg_item = self.engine_combo.itemData(i)
                if cfg_item and getattr(cfg_item, "id", None) == cfg_id:
                    idx_e = i
                    break
            self.engine_combo.setCurrentIndex(idx_e if idx_e != -1 else 0)
        else:
            self.engine_combo.setCurrentIndex(0)
        self.engine_combo.blockSignals(False)
        self._on_engine_changed()

        allowed_list = []
        try:
            raw_tools = getattr(ag, "allowed_tools", "[]") or "[]"
            allowed_list = json.loads(raw_tools)
        except Exception:
            allowed_list = []

        for tool_key, card in self._tool_cards.items():
            card.setChecked(tool_key in allowed_list)

    @Slot(QPoint)
    def _on_tree_context_menu(self, pos: QPoint) -> None:
        item = self.persona_tree.itemAt(pos)
        if not item:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, obj = data
        menu = StyledMenu(self)

        if item_type == "folder" and obj is not None:
            action_subfolder = menu.addAction(load_phosphor_icon("ph.folder-plus"), "Nouveau sous-dossier")
            action_rename = menu.addAction(load_phosphor_icon("ph.pencil-simple"), "Renommer le dossier")
            action_delete = menu.addAction(load_phosphor_icon("ph.trash"), "Supprimer le dossier")

            action = menu.exec(self.persona_tree.viewport().mapToGlobal(pos))
            if action == action_subfolder:
                sub_name, ok = QInputDialog.getText(self, "Nouveau sous-dossier", f"Nom du sous-dossier dans '{obj.name}' :")
                if ok and sub_name.strip():
                    PersonaFolderModel.create(name=sub_name.strip(), parent=obj)
                    self.refresh_data()
            elif action == action_rename:
                new_name, ok = QInputDialog.getText(self, "Renommer le dossier", "Nouveau nom :", text=obj.name)
                if ok and new_name.strip():
                    obj.name = new_name.strip()
                    obj.save()
                    self.refresh_data()
            elif action == action_delete:
                confirm = QMessageBox.question(
                    self,
                    "Supprimer le dossier",
                    f"Supprimer le dossier '{obj.name}' et ses sous-dossiers ? (Les agents seront déplacés vers 'Sans dossier')",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if confirm == QMessageBox.StandardButton.Yes:
                    self._delete_folder_recursive(obj)
                    self.refresh_data()

        elif item_type == "persona":
            action_clone = menu.addAction(load_phosphor_icon("ph.copy"), "Dupliquer l'agent")
            action_del = menu.addAction(load_phosphor_icon("ph.trash"), "Supprimer l'agent")

            action = menu.exec(self.persona_tree.viewport().mapToGlobal(pos))
            if action == action_clone:
                self._current_agent = obj
                self._on_clone_agent()
            elif action == action_del:
                self._current_agent = obj
                self._on_delete_selected()

    def _delete_folder_recursive(self, folder: PersonaFolderModel) -> None:
        PersonaModel.update(folder=None).where(PersonaModel.folder == folder).execute()

        subfolders = list(PersonaFolderModel.select().where(PersonaFolderModel.parent == folder))
        for sf in subfolders:
            self._delete_folder_recursive(sf)

        folder.delete_instance()

    @Slot()
    def _on_new_folder(self) -> None:
        parent_folder = self._current_folder
        prompt_title = f"Nouveau sous-dossier dans '{parent_folder.name}'" if parent_folder else "Nouveau Dossier Racine"
        name, ok = QInputDialog.getText(self, "Nouveau Dossier", f"{prompt_title} :")
        if ok and name.strip():
            try:
                PersonaFolderModel.create(name=name.strip(), parent=parent_folder)
                self.refresh_data()
                show_toast(self, f"Dossier '{name.strip()}' créé !")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de créer le dossier : {e}")

    @Slot()
    def _on_new_agent(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouvel Agent IA", "Nom de l'agent :")
        if ok and name.strip():
            try:
                ag_name = name.strip()
                default_prompt = "Tu es un agent IA expert en création et optimisation de flashcards Anki selon la règle de formulation minimale."
                folder_id = self._current_folder.id if self._current_folder else None

                new_p = PersonaModel.create(
                    name=ag_name,
                    description="Nouvel agent IA configuré par l'utilisateur.",
                    system_prompt=default_prompt,
                    output_format="json",
                    persona_type=self._current_scope_filter if self._current_scope_filter in ("pipeline", "mcp", "universal") else "pipeline",
                    folder=folder_id,
                    allowed_tools="[]",
                )
                self.refresh_data()
                self._current_agent = new_p
                self._load_persona_into_editor(new_p)
                show_toast(self, f"Agent '{ag_name}' créé avec succès !")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de créer l'agent : {str(e)}")

    @Slot()
    def _on_clone_agent(self) -> None:
        if not self._current_agent:
            show_toast(self, "Aucun agent sélectionné à dupliquer.", is_error=True)
            return

        clone_name = f"{self._current_agent.name} (Copie)"
        try:
            cloned = PersonaModel.create(
                name=clone_name,
                description=self._current_agent.description,
                system_prompt=self._current_agent.system_prompt,
                output_format=self._current_agent.output_format,
                persona_type=getattr(self._current_agent, "persona_type", "pipeline"),
                folder=self._current_agent.folder,
                allowed_tools=self._current_agent.allowed_tools,
                llm_config=self._current_agent.llm_config,
            )
            self.refresh_data()
            self._current_agent = cloned
            self._load_persona_into_editor(cloned)
            show_toast(self, f"Agent dupliqué sous le nom '{clone_name}' !")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de dupliquer l'agent : {str(e)}")

    @Slot()
    def _on_delete_selected(self) -> None:
        current_item = self.persona_tree.currentItem()
        if not current_item:
            show_toast(self, "Rien n'est sélectionné.", is_error=True)
            return

        data = current_item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, obj = data
        if item_type == "folder" and obj is not None:
            confirm = QMessageBox.question(
                self,
                "Supprimer le dossier",
                f"Supprimer le dossier '{obj.name}' et ses sous-dossiers ? (Les agents seront déplacés vers 'Sans dossier')",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm == QMessageBox.StandardButton.Yes:
                self._delete_folder_recursive(obj)
                self._current_folder = None
                self.refresh_data()
                show_toast(self, "Dossier supprimé.")

        elif item_type == "persona" and isinstance(obj, PersonaModel):
            confirm = QMessageBox.question(
                self,
                "Supprimer l'agent",
                f"Voulez-vous vraiment supprimer l'agent '{obj.name}' ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm == QMessageBox.StandardButton.Yes:
                try:
                    obj.delete_instance()
                    self._current_agent = None
                    self.refresh_data()
                    show_toast(self, "Agent supprimé de la base de données.")
                except Exception as e:
                    QMessageBox.critical(self, "Erreur", f"Impossible de supprimer l'agent : {str(e)}")

    @Slot()
    def _on_save_agent(self) -> None:
        if not self._current_agent:
            show_toast(self, "Aucun agent sélectionné à sauvegarder.", is_error=True)
            return

        try:
            name = self.name_edit.text().strip()
            if not name:
                show_toast(self, "Le nom de l'agent ne peut pas être vide.", is_error=True)
                return

            selected_tools = [key for key, card in self._tool_cards.items() if card.isChecked()]
            selected_engine: LLMConfigModel | None = self.engine_combo.currentData()
            selected_scope: str = self.scope_combo.currentData() or "pipeline"
            selected_folder_id: int | None = self.folder_combo.currentData()
            if selected_folder_id in ("__NEW_ROOT__", "__NEW_SUB__"):
                selected_folder_id = None

            with db.atomic():
                self._current_agent.name = str(name)
                self._current_agent.description = str(self.desc_edit.text().strip())
                self._current_agent.system_prompt = str(self.prompt_edit.toPlainText())
                self._current_agent.output_format = str(self.format_combo.currentText().lower())
                self._current_agent.persona_type = str(selected_scope)
                self._current_agent.folder_id = selected_folder_id
                self._current_agent.allowed_tools = str(json.dumps(selected_tools))
                self._current_agent.llm_config_id = selected_engine.id if selected_engine else None
                self._current_agent.save()

                PersonaVersionService.create_snapshot(
                    self._current_agent,
                    commit_message=f"Mise à jour de '{name}'",
                )

            show_toast(self, f"Agent '{name}' enregistré avec succès !")
            self.refresh_data()
        except Exception as e:
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Échec de l'enregistrement de l'agent : {str(e)}")

    @Slot()
    def _on_open_history(self) -> None:
        if not self._current_agent or not self._current_agent.id:
            show_toast(self, "Sélectionnez un agent pour explorer son historique.", is_error=True)
            return

        dlg = PersonaHistoryDialog(self._current_agent.id, parent=self)
        dlg.version_restored.connect(self._on_version_restored)
        dlg.exec()

    @Slot(int)
    def _on_version_restored(self, persona_id: int) -> None:
        refreshed = PersonaModel.get_or_none(PersonaModel.id == persona_id)
        if refreshed:
            self._current_agent = refreshed
            self._load_persona_into_editor(refreshed)
            self.refresh_data()
            show_toast(self, f"Agent '{refreshed.name}' restauré avec succès !")


AgentsTab = AgentsView
