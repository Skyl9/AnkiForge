from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.services.cards.card_model_io import CardModelIO
from ankiforge.services.cards.snippet_library import CSSConflictResolver, SnippetItem
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
)
from ankiforge.ui.components.code_editor import CodeEditorWithGutter
from ankiforge.ui.components.snippet_drawer import SnippetLibraryDrawer
from ankiforge.ui.dialogs.css_conflict_dialog import CSSConflictDialog
from ankiforge.ui.dialogs.model_export_dialog import ModelExportDialog
from ankiforge.ui.dialogs.model_import_dialog import ModelImportDialog
from ankiforge.ui.dialogs.starter_pack_dialog import StarterPackDialog
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.card_models_view.utils import extract_css_classes
from ankiforge.ui.views.card_models_view.widgets import (
    ResponsiveTopActionBar,
    SubTabButton,
    TagPillButton,
)
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.cloze_manager import is_template_cloze
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class CardModelsView(QWidget):
    """
    Vue Card Models (Atelier de Modèles de Cartes) — Conforme Pilier 3 d'AnkiForge.
    """

    def __init__(self, ai_manager: Optional[Any] = None, profile_name: Optional[str] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.profile_name = profile_name
        self._current_model: Optional[NoteTypeModel] = None
        self._templates_list: List[Dict[str, Any]] = []
        self._current_template_idx: int = 0
        self._is_syncing_template: bool = False
        self._current_helper_cat: str = "Tous"
        self.helper_category_buttons: Dict[str, QPushButton] = {}
        self._last_active_editor: str = "front"

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # =========================================================================
        # 1. PANNEAU GAUCHE : Onglet 1 Modèles & Onglet 2 Snippets (260px)
        # =========================================================================
        self.left_panel = IdePanel(detachable=True)
        self.left_panel.setMinimumWidth(240)
        self.left_panel.setMaximumWidth(320)

        # --- Tab 1 : Modèles Disponibles ---
        list_content = QWidget()
        list_layout = QVBoxLayout(list_content)
        list_layout.setContentsMargins(8, 8, 8, 8)
        list_layout.setSpacing(8)

        search_row = QHBoxLayout()
        search_row.setSpacing(6)

        self.model_search_input = GlowLineEdit(placeholder="Rechercher...")
        self.model_search_input.setObjectName("modelSearchInput")
        self.model_search_input.setProperty("role", "search")
        self.model_search_input.textChanged.connect(self._filter_models_list)
        search_row.addWidget(self.model_search_input, 1)

        self.btn_new = PrimaryButton("Nouveau")
        self.btn_new.setIcon(load_phosphor_icon("ph.plus", color="white"))
        self.btn_new.setFixedHeight(28)
        self.btn_new.setToolTip("Créer un nouveau modèle de carte")
        search_row.addWidget(self.btn_new)

        list_layout.addLayout(search_row)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px 10px;
                margin-bottom: 2px;
                border: 1px solid transparent;
                border-radius: {DesignTokens.RADIUS_SM}px;
                font-weight: 500;
                font-size: 12px;
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                font-weight: bold;
            }}
        """)
        list_layout.addWidget(self.list_widget, 1)

        list_toolbar = QHBoxLayout()
        list_toolbar.setSpacing(6)

        self.btn_starter_pack = SecondaryButton("Pack IA")
        self.btn_starter_pack.setIcon(load_phosphor_icon("ph.sparkle", color=DesignTokens.ACCENT_PRIMARY))
        self.btn_starter_pack.setFixedHeight(28)
        self.btn_starter_pack.setToolTip("Explorer et installer les modèles communautaires (Starter Pack)")
        list_toolbar.addWidget(self.btn_starter_pack, 1)

        self.btn_duplicate = IconButton("ph.copy", tooltip="Dupliquer le modèle sélectionné", size=24)
        self.btn_import_json = IconButton("ph.download-simple", tooltip="Importer un modèle (.afmodel ou .json)", size=24)
        self.btn_del = IconButton("ph.trash", tooltip="Supprimer le modèle", size=24)

        list_toolbar.addWidget(self.btn_duplicate)
        list_toolbar.addWidget(self.btn_import_json)
        list_toolbar.addWidget(self.btn_del)

        list_layout.addLayout(list_toolbar)

        self.left_panel.add_tab("Modèles", list_content, "ph.swatches", closable=False)

        # --- Tab 2 : Bibliothèque de Snippets ---
        self.snippet_drawer = SnippetLibraryDrawer()
        self.snippet_drawer.snippet_selected.connect(self._on_insert_snippet)
        self.left_panel.add_tab("Snippets", self.snippet_drawer, "ph.sparkle", closable=False)

        self.main_splitter.addWidget(self.left_panel)

        # =========================================================================
        # 2. PANNEAU CENTRAL : Éditeur avec Top Action Bar Responsive & Splitter Vertical
        # =========================================================================
        self.editor_panel = IdePanel(detachable=True)

        editor_content = QWidget()
        editor_layout = QVBoxLayout(editor_content)
        editor_layout.setContentsMargins(8, 8, 8, 8)
        editor_layout.setSpacing(8)

        self.top_action_bar = ResponsiveTopActionBar()
        self.lbl_editor_icon = self.top_action_bar.lbl_editor_icon
        self.lbl_editor_title = self.top_action_bar.lbl_editor_title
        self.model_type_badge = self.top_action_bar.model_type_badge
        self.template_count_badge = self.top_action_bar.template_count_badge
        self.btn_export_json = self.top_action_bar.btn_export_json
        self.btn_refresh = self.top_action_bar.btn_refresh
        self.btn_save = self.top_action_bar.btn_save

        editor_layout.addWidget(self.top_action_bar)

        self.editor_vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.editor_vertical_splitter.setStyleSheet(f"""
            QSplitter::handle:vertical {{
                background-color: {DesignTokens.BORDER_COLOR};
                height: 4px;
                margin: 2px 0px;
                border-radius: 2px;
            }}
            QSplitter::handle:vertical:hover {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        # --- ZONE SUPÉRIEURE : Champs de données + Volet d'Aides Repliable ---
        top_resizable_container = QWidget()
        top_res_layout = QVBoxLayout(top_resizable_container)
        top_res_layout.setContentsMargins(0, 0, 0, 4)
        top_res_layout.setSpacing(6)

        fields_row = QHBoxLayout()
        fields_row.setSpacing(6)

        lbl_fields = QLabel("Champs :")
        lbl_fields.setFixedWidth(55)
        lbl_fields.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        fields_row.addWidget(lbl_fields)

        self.fields_input = StyledLineEdit()
        self.fields_input.setFixedHeight(26)
        self.fields_input.setText("Front, Back")
        self.fields_input.setPlaceholderText("ex: Front, Back, Audio...")
        fields_row.addWidget(self.fields_input, 1)

        top_res_layout.addLayout(fields_row)

        desc_row = QHBoxLayout()
        desc_row.setSpacing(6)

        lbl_desc = QLabel("Rôle IA :")
        lbl_desc.setFixedWidth(55)
        lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        desc_row.addWidget(lbl_desc)

        self.description_input = StyledLineEdit()
        self.description_input.setFixedHeight(26)
        self.description_input.setPlaceholderText("Directives sémantiques pour les agents IA...")
        desc_row.addWidget(self.description_input, 1)

        top_res_layout.addLayout(desc_row)

        self.helpers_frame = QFrame()
        self.helpers_frame.setObjectName("helpersFrame")
        self.helpers_frame.setStyleSheet(f"""
            QFrame#helpersFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        helpers_layout = QVBoxLayout(self.helpers_frame)
        helpers_layout.setContentsMargins(8, 6, 8, 6)
        helpers_layout.setSpacing(4)

        helpers_header = QHBoxLayout()
        helpers_header.setContentsMargins(0, 0, 0, 0)
        helpers_header.setSpacing(6)

        self.btn_collapse_helpers = IconButton("ph.caret-down", tooltip="Replier / Déplier le volet d'aides", size=18)
        self.btn_collapse_helpers.clicked.connect(self._toggle_helpers_collapsed)
        helpers_header.addWidget(self.btn_collapse_helpers)

        lbl_helpers_title = QLabel("Aides d'insertion")
        lbl_helpers_title.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        helpers_header.addWidget(lbl_helpers_title)

        self.lbl_helpers_count = Badge("0", variant="neutral")
        self.lbl_helpers_count.setFixedHeight(18)
        helpers_header.addWidget(self.lbl_helpers_count)
        helpers_header.addStretch()

        self.helper_category_combo = StyledComboBox()
        self.helper_category_combo.setFixedHeight(22)
        self.helper_category_combo.setFixedWidth(130)
        self.helper_category_combo.addItem("Toutes", userData="Tous")
        self.helper_category_combo.addItem("Champs", userData="Champs")
        self.helper_category_combo.addItem("Cloze", userData="Cloze")
        self.helper_category_combo.addItem("Classes CSS", userData="Classes CSS")
        self.helper_category_combo.addItem("Structure", userData="Structure")
        self.helper_category_combo.currentIndexChanged.connect(self._on_helper_combo_category_selected)
        helpers_header.addWidget(self.helper_category_combo)

        helpers_layout.addLayout(helpers_header)

        self.tags_scroll_area = QScrollArea()
        self.tags_scroll_area.setWidgetResizable(True)
        self.tags_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tags_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.tags_scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.tags_container = FlowWidget(margin=2, h_spacing=6, v_spacing=6)
        self.tags_container.setObjectName("tagsContainer")
        self.tags_container.setStyleSheet("QWidget#tagsContainer { background: transparent; border: none; }")
        self.tags_flow_layout = self.tags_container.flow_layout
        self.tags_scroll_area.setWidget(self.tags_container)

        helpers_layout.addWidget(self.tags_scroll_area, 1)
        top_res_layout.addWidget(self.helpers_frame, 1)

        self.editor_vertical_splitter.addWidget(top_resizable_container)

        # --- ZONE INFÉRIEURE : Multi-Templates + Onglets + Éditeurs de Code ---
        bottom_resizable_container = QWidget()
        bottom_res_layout = QVBoxLayout(bottom_resizable_container)
        bottom_res_layout.setContentsMargins(0, 4, 0, 0)
        bottom_res_layout.setSpacing(6)

        card_sel_widget = QWidget()
        card_sel_widget.setObjectName("cardSelWidget")
        card_sel_widget.setStyleSheet("QWidget#cardSelWidget { background: transparent; border: none; }")
        card_sel_row = QHBoxLayout(card_sel_widget)
        card_sel_row.setContentsMargins(0, 0, 0, 0)
        card_sel_row.setSpacing(6)

        lbl_card_sel = QLabel("Gabarit :")
        lbl_card_sel.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        card_sel_row.addWidget(lbl_card_sel)

        self.card_selector_combo = StyledComboBox()
        self.card_selector_combo.setFixedWidth(140)
        self.card_selector_combo.setFixedHeight(26)
        self.card_selector_combo.currentIndexChanged.connect(self._on_template_index_changed)
        card_sel_row.addWidget(self.card_selector_combo)

        self.btn_add_card_tmpl = IconButton("ph.plus", tooltip="Ajouter un nouveau gabarit", size=20)
        self.btn_dup_card_tmpl = IconButton("ph.copy", tooltip="Dupliquer le gabarit actuel", size=20)
        self.btn_rename_card_tmpl = IconButton("ph.pencil-simple", tooltip="Renommer le gabarit", size=20)
        self.btn_del_card_tmpl = IconButton("ph.trash", tooltip="Supprimer ce gabarit", size=20)

        card_sel_row.addWidget(self.btn_add_card_tmpl)
        card_sel_row.addWidget(self.btn_dup_card_tmpl)
        card_sel_row.addWidget(self.btn_rename_card_tmpl)
        card_sel_row.addWidget(self.btn_del_card_tmpl)
        card_sel_row.addStretch()

        bottom_res_layout.addWidget(card_sel_widget)

        subtabs_container = QFrame()
        subtabs_container.setObjectName("subtabsContainer")
        subtabs_container.setStyleSheet(f"""
            QFrame#subtabsContainer {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        subtabs_row = QHBoxLayout(subtabs_container)
        subtabs_row.setContentsMargins(4, 2, 4, 2)
        subtabs_row.setSpacing(6)

        self.btn_subtab_css = SubTabButton("Style CSS", "ph.file-css")
        self.btn_subtab_front = SubTabButton("HTML Recto", "ph.file-html")
        self.btn_subtab_back = SubTabButton("HTML Verso", "ph.file-html")

        subtabs_row.addWidget(self.btn_subtab_css)
        subtabs_row.addWidget(self.btn_subtab_front)
        subtabs_row.addWidget(self.btn_subtab_back)
        subtabs_row.addStretch()

        bottom_res_layout.addWidget(subtabs_container)

        self.editor_stack = QStackedWidget()

        self.css_editor_wrapper = CodeEditorWithGutter(
            placeholder=".card { font-family: arial; text-align: center; }",
            mode="css",
        )
        self.editor_stack.addWidget(self.css_editor_wrapper)

        self.front_html_wrapper = CodeEditorWithGutter(
            placeholder="{{Front}}",
            mode="html",
        )
        self.editor_stack.addWidget(self.front_html_wrapper)

        self.back_html_wrapper = CodeEditorWithGutter(
            placeholder='{{FrontSide}}\n<hr id="answer">\n{{Back}}',
            mode="html",
        )
        self.editor_stack.addWidget(self.back_html_wrapper)

        bottom_res_layout.addWidget(self.editor_stack, 1)
        self.editor_vertical_splitter.addWidget(bottom_resizable_container)

        self.editor_vertical_splitter.setSizes([90, 480])
        self.editor_vertical_splitter.setStretchFactor(0, 0)
        self.editor_vertical_splitter.setStretchFactor(1, 1)

        self.editor_horizontal_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.editor_horizontal_splitter.setChildrenCollapsible(False)

        code_container = QWidget()
        code_layout = QVBoxLayout(code_container)
        code_layout.setContentsMargins(0, 0, 0, 0)
        code_layout.setSpacing(0)
        code_layout.addWidget(self.editor_vertical_splitter)

        self.editor_horizontal_splitter.addWidget(code_container)

        self.preview_container = QFrame()
        self.preview_container.setObjectName("previewContainer")
        self.preview_container.setStyleSheet(f"""
            QFrame#previewContainer {{
                background-color: {DesignTokens.BG_PANEL};
                border-left: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        preview_layout = QVBoxLayout(self.preview_container)
        preview_layout.setContentsMargins(8, 6, 8, 8)
        preview_layout.setSpacing(6)

        preview_header = QHBoxLayout()
        preview_header.setContentsMargins(0, 0, 0, 0)
        preview_header.setSpacing(6)

        lbl_witness = QLabel("Témoin :")
        lbl_witness.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        preview_header.addWidget(lbl_witness)

        self.note_witness_combo = StyledComboBox()
        self.note_witness_combo.setFixedHeight(24)
        self.note_witness_combo.setMinimumWidth(180)
        self.note_witness_combo.addItem("Données d'exemple automatiques", userData=None)
        self.note_witness_combo.currentIndexChanged.connect(self._on_witness_note_changed)
        preview_header.addWidget(self.note_witness_combo, 1)

        self.btn_preview_refresh = IconButton("ph.arrows-clockwise", tooltip="Rafraîchir la prévisualisation", size=22)
        preview_header.addWidget(self.btn_preview_refresh)

        self.btn_close_preview = IconButton("ph.x", tooltip="Masquer l'aperçu en direct", size=22)
        preview_header.addWidget(self.btn_close_preview)

        preview_layout.addLayout(preview_header)

        self.card_preview_widget = CardPreviewWidget()
        preview_layout.addWidget(self.card_preview_widget, 1)

        self.editor_horizontal_splitter.addWidget(self.preview_container)
        self.editor_horizontal_splitter.setSizes([500, 420])
        self.editor_horizontal_splitter.setStretchFactor(0, 1)
        self.editor_horizontal_splitter.setStretchFactor(1, 1)

        editor_layout.addWidget(self.editor_horizontal_splitter, 1)

        self.editor_panel.add_tab("Éditeur de Modèle", editor_content, "ph.pencil-simple", closable=False)
        self.main_splitter.addWidget(self.editor_panel)

        self.main_splitter.setSizes([260, 820])
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self._switch_subtab(0)

    def _connect_signals(self) -> None:
        self.list_widget.currentItemChanged.connect(self._on_item_selected)
        self.btn_new.clicked.connect(self._on_new_model)
        self.btn_duplicate.clicked.connect(self._on_duplicate_model)
        self.btn_import_json.clicked.connect(self._on_import_json)
        self.btn_starter_pack.clicked.connect(self._on_open_starter_pack)
        self.btn_del.clicked.connect(self._on_delete_model)

        self.btn_export_json.clicked.connect(self._on_export_json)
        self.btn_refresh.clicked.connect(self._update_preview)
        self.btn_save.clicked.connect(self._on_save_model)
        self.top_action_bar.preview_toggle_requested.connect(self._toggle_preview_panel)

        self.btn_add_card_tmpl.clicked.connect(self._on_add_template)
        self.btn_dup_card_tmpl.clicked.connect(self._on_dup_template)
        self.btn_rename_card_tmpl.clicked.connect(self._on_rename_template)
        self.btn_del_card_tmpl.clicked.connect(self._on_del_template)

        self.fields_input.textChanged.connect(self._on_fields_changed)

        self.btn_subtab_css.clicked.connect(lambda: self._switch_subtab(0))
        self.btn_subtab_front.clicked.connect(lambda: self._switch_subtab(1))
        self.btn_subtab_back.clicked.connect(lambda: self._switch_subtab(2))

        self.btn_preview_refresh.clicked.connect(self._update_preview)
        self.btn_close_preview.clicked.connect(self._hide_preview_panel)

        self.front_html_wrapper.editor.cursorPositionChanged.connect(lambda: self._set_last_active_editor("front"))
        self.back_html_wrapper.editor.cursorPositionChanged.connect(lambda: self._set_last_active_editor("back"))
        self.css_editor_wrapper.editor.cursorPositionChanged.connect(lambda: self._set_last_active_editor("css"))

        self.css_editor_wrapper.editor.textChanged.connect(self._on_css_code_changed)
        self.front_html_wrapper.editor.textChanged.connect(self._on_code_changed)
        self.back_html_wrapper.editor.textChanged.connect(self._on_code_changed)

    def _set_last_active_editor(self, ed_type: str) -> None:
        self._last_active_editor = ed_type

    def _switch_subtab(self, index: int) -> None:
        if index in (0, 1, 2):
            self.editor_stack.setCurrentIndex(index)
            self.btn_subtab_css.set_active(index == 0)
            self.btn_subtab_front.set_active(index == 1)
            self.btn_subtab_back.set_active(index == 2)
            if index == 1:
                self._last_active_editor = "front"
            elif index == 2:
                self._last_active_editor = "back"
            elif index == 0:
                self._last_active_editor = "css"

    @Slot()
    def _toggle_preview_panel(self) -> None:
        is_visible = not self.preview_container.isVisible()
        self.preview_container.setVisible(is_visible)
        if is_visible:
            self._sync_current_template_from_editors()
            self._update_preview()
            self.editor_horizontal_splitter.setSizes([500, 420])
            self.top_action_bar.btn_toggle_preview.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_HOVER};
                    border: 1.5px solid {DesignTokens.ACCENT_PRIMARY};
                    color: {DesignTokens.TEXT_PRIMARY};
                    font-weight: 600;
                    border-radius: {DesignTokens.RADIUS_SM}px;
                }}
            """)
        else:
            self.top_action_bar.btn_toggle_preview.setStyleSheet("")

    @Slot()
    def _hide_preview_panel(self) -> None:
        self.preview_container.setVisible(False)
        self.top_action_bar.btn_toggle_preview.setStyleSheet("")

    def _on_code_changed(self) -> None:
        if self._is_syncing_template:
            return
        self._sync_current_template_from_editors()
        self._update_preview()

    def _on_css_code_changed(self) -> None:
        self._on_code_changed()
        self._update_tags_toolbar()

    def _sync_current_template_from_editors(self) -> None:
        if 0 <= self._current_template_idx < len(self._templates_list):
            self._templates_list[self._current_template_idx]["qfmt"] = self.front_html_wrapper.toPlainText()
            self._templates_list[self._current_template_idx]["afmt"] = self.back_html_wrapper.toPlainText()

    def _filter_models_list(self, query: str) -> None:
        q = query.lower().strip()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            model = item.data(Qt.ItemDataRole.UserRole)
            if not q or (model and q in model.name.lower()):
                item.setHidden(False)
            else:
                item.setHidden(True)

    def refresh_data(self) -> None:
        try:
            self.list_widget.blockSignals(True)
            self.list_widget.clear()

            models = list(NoteTypeModel.select())
            for m in models:
                is_m_cloze = False
                tmpl_count = 1
                if m.templates:
                    try:
                        t_list = json.loads(m.templates)
                        if isinstance(t_list, list):
                            tmpl_count = len(t_list)
                            if is_template_cloze(t_list):
                                is_m_cloze = True
                    except Exception:
                        pass  # nosec B110
                if not is_m_cloze and any(w in m.name.lower() for w in ("cloze", "trou", "texte à trou")):
                    is_m_cloze = True

                icon_str = "ph.eye-slash" if is_m_cloze else "ph.cards"
                type_label = "Cloze" if is_m_cloze else f"{tmpl_count} carte{'s' if tmpl_count > 1 else ''}"
                item = QListWidgetItem(f"{m.name}  ({type_label})")
                item.setIcon(load_phosphor_icon(icon_str, color=DesignTokens.ACCENT_PRIMARY))
                item.setToolTip(f"Modèle : {m.name}\nType : {'Texte à trous (Cloze)' if is_m_cloze else 'Standard'}\nGabarits : {tmpl_count}")
                item.setData(Qt.ItemDataRole.UserRole, m)
                self.list_widget.addItem(item)

            self.list_widget.blockSignals(False)

            if models and not self._current_model:
                self.list_widget.setCurrentRow(0)

        except Exception as e:
            logger.warning("Erreur refresh_data card_models_view: %s", e)

    def is_dirty(self) -> bool:
        return False

    def _is_cloze_active(self) -> bool:
        if is_template_cloze(self._templates_list):
            return True
        if self._current_model and any(w in self._current_model.name.lower() for w in ("cloze", "trou", "texte à trou")):
            return True
        raw_fields = [f.strip().lower() for f in self.fields_input.text().split(",") if f.strip()]
        return any("cloze" in f for f in raw_fields)

    @Slot()
    def _toggle_helpers_collapsed(self) -> None:
        is_hidden = self.tags_scroll_area.isHidden()
        if is_hidden:
            self.tags_scroll_area.show()
            self.btn_collapse_helpers.setIcon(load_phosphor_icon("ph.caret-down", color=DesignTokens.TEXT_PRIMARY))
            self.btn_collapse_helpers.setToolTip("Replier le volet d'aides")
            self.helpers_frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            self.helpers_frame.setMaximumHeight(16777215)
            self.helpers_frame.setMinimumHeight(0)
            self.editor_vertical_splitter.setSizes([140, 420])
        else:
            self.tags_scroll_area.hide()
            self.btn_collapse_helpers.setIcon(load_phosphor_icon("ph.caret-right", color=DesignTokens.TEXT_PRIMARY))
            self.btn_collapse_helpers.setToolTip("Déplier le volet d'aides")
            self.helpers_frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self.helpers_frame.setFixedHeight(34)
            self.editor_vertical_splitter.setSizes([70, 500])

    @Slot()
    def _on_item_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if not current:
            self._current_model = None
            self.lbl_editor_title.setText("Aucun modèle sélectionné")
            return

        model: Optional[NoteTypeModel] = current.data(Qt.ItemDataRole.UserRole)
        if not model:
            return

        self._current_model = model
        self.lbl_editor_title.setText(model.name)
        self.description_input.setText(getattr(model, "description", "") or "")

        if model.fields_schema:
            try:
                parsed_fields = json.loads(model.fields_schema)
                if isinstance(parsed_fields, list):
                    self.fields_input.setText(", ".join(parsed_fields))
                else:
                    self.fields_input.setText("Front, Back")
            except Exception:
                self.fields_input.setText("Front, Back")
        else:
            self.fields_input.setText("Front, Back")

        default_css = (
            ".card {\n  font-family: arial;\n  font-size: 20px;\n  text-align: center;\n  color: #1e293b;\n  background-color: #ffffff;\n}\n\n.cloze {\n  font-weight: bold;\n  color: #3b82f6;\n}"
        )
        self.css_editor_wrapper.setPlainText(model.css_style or default_css)

        self._templates_list = []
        if model.templates:
            try:
                parsed_tmpl = json.loads(model.templates)
                if isinstance(parsed_tmpl, list) and parsed_tmpl:
                    self._templates_list = parsed_tmpl
            except Exception:
                pass  # nosec B110

        if not self._templates_list:
            self._templates_list = [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": '{{FrontSide}}<br><hr id="answer"><br>{{Back}}'}]

        self._current_template_idx = 0
        self._populate_template_selector()
        self._load_current_template_to_editors()

        is_cloze = self._is_cloze_active()
        self.model_type_badge.setText("Cloze" if is_cloze else "Standard")
        cnt = len(self._templates_list)
        self.template_count_badge.setText(f"{cnt} gabarit{'s' if cnt > 1 else ''}")

        self._update_witness_notes_combo()
        self._update_tags_toolbar()
        self._update_preview()

    def _populate_template_selector(self) -> None:
        self.card_selector_combo.blockSignals(True)
        self.card_selector_combo.clear()
        for idx, tmpl in enumerate(self._templates_list):
            name = tmpl.get("name", f"Carte {idx + 1}")
            self.card_selector_combo.addItem(name, userData=idx)
        self.card_selector_combo.setCurrentIndex(self._current_template_idx)
        self.card_selector_combo.blockSignals(False)

    def _load_current_template_to_editors(self) -> None:
        if not (0 <= self._current_template_idx < len(self._templates_list)):
            return

        self._is_syncing_template = True
        tmpl = self._templates_list[self._current_template_idx]
        self.front_html_wrapper.setPlainText(tmpl.get("qfmt", ""))
        self.back_html_wrapper.setPlainText(tmpl.get("afmt", ""))
        self._is_syncing_template = False

    @Slot(int)
    def _on_template_index_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._templates_list):
            return
        self._sync_current_template_from_editors()
        self._current_template_idx = index
        self._load_current_template_to_editors()
        self._update_tags_toolbar()
        self._update_preview()

    @Slot()
    def _on_add_template(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau Gabarit", "Nom du gabarit de carte (ex: Carte 2) :")
        if ok and name.strip():
            self._sync_current_template_from_editors()
            new_tmpl = {
                "name": name.strip(),
                "qfmt": "{{Front}}",
                "afmt": '{{FrontSide}}<br><hr id="answer"><br>{{Back}}',
            }
            self._templates_list.append(new_tmpl)
            self._current_template_idx = len(self._templates_list) - 1
            self._populate_template_selector()
            self._load_current_template_to_editors()
            cnt = len(self._templates_list)
            self.template_count_badge.setText(f"{cnt} gabarit{'s' if cnt > 1 else ''}")
            self._update_tags_toolbar()
            self._update_preview()
            show_toast(self, f"Gabarit '{name.strip()}' ajouté.")

    @Slot()
    def _on_dup_template(self) -> None:
        if not (0 <= self._current_template_idx < len(self._templates_list)):
            return
        self._sync_current_template_from_editors()
        current = self._templates_list[self._current_template_idx]
        dup_name = f"{current.get('name', 'Carte')} (Copie)"
        new_tmpl = {
            "name": dup_name,
            "qfmt": current.get("qfmt", ""),
            "afmt": current.get("afmt", ""),
        }
        self._templates_list.append(new_tmpl)
        self._current_template_idx = len(self._templates_list) - 1
        self._populate_template_selector()
        self._load_current_template_to_editors()
        cnt = len(self._templates_list)
        self.template_count_badge.setText(f"{cnt} gabarit{'s' if cnt > 1 else ''}")
        self._update_tags_toolbar()
        self._update_preview()
        show_toast(self, f"Gabarit dupliqué sous '{dup_name}'.")

    @Slot()
    def _on_rename_template(self) -> None:
        if not (0 <= self._current_template_idx < len(self._templates_list)):
            return
        current_name = self._templates_list[self._current_template_idx].get("name", "")
        name, ok = QInputDialog.getText(self, "Renommer le Gabarit", "Nouveau nom :", text=current_name)
        if ok and name.strip():
            self._templates_list[self._current_template_idx]["name"] = name.strip()
            self._populate_template_selector()
            show_toast(self, "Gabarit renommé.")

    @Slot()
    def _on_del_template(self) -> None:
        if len(self._templates_list) <= 1:
            QMessageBox.warning(self, "Suppression impossible", "Un modèle doit comporter au moins un gabarit de carte.")
            return

        current_name = self._templates_list[self._current_template_idx].get("name", "")
        res = QMessageBox.question(
            self,
            "Supprimer le Gabarit",
            f"Voulez-vous vraiment supprimer le gabarit '{current_name}' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            self._templates_list.pop(self._current_template_idx)
            self._current_template_idx = max(0, self._current_template_idx - 1)
            self._populate_template_selector()
            self._load_current_template_to_editors()
            cnt = len(self._templates_list)
            self.template_count_badge.setText(f"{cnt} gabarit{'s' if cnt > 1 else ''}")
            self._update_tags_toolbar()
            self._update_preview()
            show_toast(self, "Gabarit supprimé.")

    def _update_witness_notes_combo(self) -> None:
        self.note_witness_combo.blockSignals(True)
        self.note_witness_combo.clear()
        self.note_witness_combo.addItem("Données d'exemple automatiques", userData=None)

        if self._current_model:
            notes = list(NoteModel.select().where(NoteModel.note_type == self._current_model).limit(15))
            for note in notes:
                version = NoteVersionModel.get_or_none(note=note, is_active=True)
                summary = f"Note #{note.id}"
                if version and version.content:
                    try:
                        content_dict = json.loads(version.content)
                        first_val = next(iter(content_dict.values()), "")
                        if first_val:
                            summary += f" : {first_val[:28]}..."
                    except Exception:
                        pass  # nosec B110
                self.note_witness_combo.addItem(summary, userData=note.id)

        self.note_witness_combo.blockSignals(False)

    @Slot(int)
    def _on_witness_note_changed(self, index: int) -> None:
        self._update_preview()

    @Slot(SnippetItem)
    def _on_insert_snippet(self, snippet: SnippetItem, target: Optional[str] = None) -> None:
        existing_css = self.css_editor_wrapper.toPlainText()
        conflicts = CSSConflictResolver.find_conflicts(existing_css, snippet.css_style)

        html_to_insert = snippet.html_template
        css_to_insert = snippet.css_style

        if conflicts:
            dialog = CSSConflictDialog(conflicting_classes=conflicts, snippet_name=snippet.name, parent=self)
            if dialog.exec() == CSSConflictDialog.DialogCode.Accepted:
                action = dialog.selected_action
                if action == "rename":
                    mapping = {cls_name: f"{cls_name}-v2" for cls_name in conflicts}
                    html_to_insert, css_to_insert = CSSConflictResolver.rename_classes(
                        html=snippet.html_template,
                        css=snippet.css_style,
                        class_mapping=mapping,
                    )
                    merged_css = CSSConflictResolver.merge_css(existing_css, css_to_insert, strategy="append")
                    self.css_editor_wrapper.setPlainText(merged_css)
                elif action == "replace":
                    merged_css = CSSConflictResolver.merge_css(existing_css, css_to_insert, strategy="replace", replace_classes=conflicts)
                    self.css_editor_wrapper.setPlainText(merged_css)
                elif action == "html_only":
                    pass
            else:
                return
        else:
            if snippet.css_style and snippet.css_style.strip() not in existing_css:
                merged_css = CSSConflictResolver.merge_css(existing_css, css_to_insert, strategy="append")
                self.css_editor_wrapper.setPlainText(merged_css)

        if target == "back" or (target is None and (self._last_active_editor == "back" or self.editor_stack.currentIndex() == 2)):
            target_wrapper = self.back_html_wrapper
            target_idx = 2
        else:
            target_wrapper = self.front_html_wrapper
            target_idx = 1

        cursor = target_wrapper.editor.textCursor()
        cursor.insertText(html_to_insert)
        target_wrapper.editor.setTextCursor(cursor)

        self._switch_subtab(target_idx)
        target_wrapper.editor.setFocus()

        show_toast(self, f"Snippet « {snippet.name} » inséré au curseur.")
        self._update_tags_toolbar()
        self._update_preview()

    @Slot(int)
    def _on_helper_combo_category_selected(self, index: int) -> None:
        cat_data = self.helper_category_combo.currentData()
        if cat_data:
            self._current_helper_cat = str(cat_data)
            self._update_tags_toolbar()

    @Slot(str)
    def _on_helper_category_selected(self, cat_name: str) -> None:
        self._current_helper_cat = cat_name
        self._update_tags_toolbar()

    @Slot()
    def _on_fields_changed(self) -> None:
        self._update_tags_toolbar()

    def _update_tags_toolbar(self) -> None:
        is_cloze = self._is_cloze_active()
        self.tags_container.clear()

        raw_fields = [f.strip() for f in self.fields_input.text().split(",") if f.strip()]
        if not raw_fields:
            raw_fields = ["Front", "Back"]

        self.front_html_wrapper.set_known_fields(raw_fields)
        self.back_html_wrapper.set_known_fields(raw_fields)
        css_text = self.css_editor_wrapper.toPlainText()
        detected_classes = extract_css_classes(css_text)
        self.front_html_wrapper.set_custom_classes(detected_classes)
        self.back_html_wrapper.set_custom_classes(detected_classes)
        self.css_editor_wrapper.set_custom_classes(detected_classes)

        active_cat = self._current_helper_cat

        if active_cat in ("Tous", "Champs"):
            for f in raw_fields:
                tag_str = f"{{{{{f}}}}}"
                btn = TagPillButton(tag_str, variant="field")
                btn.setToolTip(f"Insérer le champ {tag_str}")
                btn.clicked.connect(lambda _, t=tag_str: self._insert_tag_to_active_editor(t))
                self.tags_flow_layout.addWidget(btn)

        if is_cloze and active_cat in ("Tous", "Cloze"):
            for f in raw_fields:
                cloze_str = f"{{{{cloze:{f}}}}}"
                btn_c = TagPillButton(cloze_str, variant="cloze")
                btn_c.setToolTip(f"Insérer l'occlusion {cloze_str}")
                btn_c.clicked.connect(lambda _, t=cloze_str: self._insert_tag_to_active_editor(t))
                self.tags_flow_layout.addWidget(btn_c)

        if active_cat in ("Tous", "Classes CSS"):
            css_text = self.css_editor_wrapper.toPlainText()
            detected_classes = extract_css_classes(css_text)
            for cls_name in detected_classes:
                btn_cls = TagPillButton(f".{cls_name}", variant="css")
                btn_cls.setToolTip(f"Insérer le conteneur <div class='{cls_name}'></div> ou la règle CSS .{cls_name}")
                btn_cls.clicked.connect(lambda _, c=cls_name: self._insert_css_class_to_active_editor(c))
                self.tags_flow_layout.addWidget(btn_cls)

        if active_cat in ("Tous", "Structure"):
            btn_fs = TagPillButton("{{FrontSide}}", variant="structure")
            btn_fs.setToolTip("Insérer le rappel du recto au verso")
            btn_fs.clicked.connect(lambda: self._insert_tag_to_active_editor("{{FrontSide}}"))
            self.tags_flow_layout.addWidget(btn_fs)

            btn_hr = TagPillButton('<hr id="answer">', variant="structure")
            btn_hr.setToolTip("Insérer la ligne séparatrice de réponse Anki")
            btn_hr.clicked.connect(lambda: self._insert_tag_to_active_editor('<hr id="answer">'))
            self.tags_flow_layout.addWidget(btn_hr)

            for f in raw_fields:
                cond_tag = f"{{{{#{f}}}}}"
                btn_cond = TagPillButton(cond_tag, variant="condition")
                btn_cond.setToolTip(f"Insérer le bloc conditionnel si '{f}' n'est pas vide")
                cond_snippet = f"{{{{#{f}}}}}\n  {{{{{f}}}}}\n{{{{/{f}}}}}"
                btn_cond.clicked.connect(lambda _, s=cond_snippet: self._insert_tag_to_active_editor(s))
                self.tags_flow_layout.addWidget(btn_cond)

        total_pills = self.tags_flow_layout.count()
        self.lbl_helpers_count.setText(f"{total_pills}")
        self.tags_container.updateGeometry()

    def _insert_tag_to_active_editor(self, tag_str: str) -> None:
        active_idx = self.editor_stack.currentIndex()
        if active_idx == 1:
            self.front_html_wrapper.insertPlainText(tag_str)
        elif active_idx == 2:
            self.back_html_wrapper.insertPlainText(tag_str)
        elif active_idx == 0:
            self.css_editor_wrapper.insertPlainText(tag_str)

    def _insert_css_class_to_active_editor(self, class_name: str) -> None:
        active_idx = self.editor_stack.currentIndex()
        if active_idx in (1, 2):
            tag = f'<div class="{class_name}">\n  \n</div>'
            if active_idx == 1:
                self.front_html_wrapper.insertPlainText(tag)
            else:
                self.back_html_wrapper.insertPlainText(tag)
        elif active_idx == 0:
            rule = f"\n.{class_name} {{\n  \n}}\n"
            self.css_editor_wrapper.insertPlainText(rule)

    @Slot()
    def _update_preview(self) -> None:
        raw_fields = [f.strip() for f in self.fields_input.text().split(",") if f.strip()]
        if not raw_fields:
            raw_fields = ["Front", "Back"]

        selected_note_id = self.note_witness_combo.currentData()
        mock_fields: Dict[str, str] = {}

        if selected_note_id:
            version = NoteVersionModel.get_or_none(NoteVersionModel.note_id == selected_note_id, is_active=True)
            if version and version.content:
                try:
                    mock_fields = json.loads(version.content)
                except Exception:
                    mock_fields = {}

        if not mock_fields:
            for f in raw_fields:
                f_lower = f.lower()
                if "cloze" in f_lower or "texte" in f_lower:
                    mock_fields[f] = "La capitale de la France est {{c1::Paris::Ville}}."
                elif "front" in f_lower or "recto" in f_lower:
                    mock_fields[f] = "Quelle est la capitale de la France ?"
                elif "back" in f_lower or "verso" in f_lower or "extra" in f_lower:
                    mock_fields[f] = "Paris est la capitale et la plus grande ville de France."
                else:
                    mock_fields[f] = f"Valeur de test pour {f}"

        self._sync_current_template_from_editors()
        css = self.css_editor_wrapper.toPlainText()

        self.card_preview_widget.update_preview(
            note_type=self._current_model,
            fields_dict=mock_fields,
            override_templates=self._templates_list,
            override_css=css,
        )

    @Slot()
    def _on_new_model(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau modèle de carte", "Nom du modèle :")
        if ok and name.strip():
            try:
                default_tmpl = [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": '{{FrontSide}}<br><hr id="answer"><br>{{Back}}'}]
                new_model = NoteTypeModel.create(
                    name=name.strip(),
                    fields_schema=json.dumps(["Front", "Back"], ensure_ascii=False),
                    templates=json.dumps(default_tmpl, ensure_ascii=False),
                    css_style=(
                        ".card {\n  font-family: arial;\n  font-size: 20px;\n  text-align: center;\n"
                        "  color: #1e293b;\n  background-color: #ffffff;\n}\n\n.cloze {\n"
                        "  font-weight: bold;\n  color: #3b82f6;\n}"
                    ),
                )
                logger.info("Nouveau modèle de carte créé : '%s' (ID: %s)", new_model.name, new_model.id)
                self.refresh_data()
                for i in range(self.list_widget.count()):
                    item = self.list_widget.item(i)
                    if item.data(Qt.ItemDataRole.UserRole).id == new_model.id:
                        self.list_widget.setCurrentItem(item)
                        break
                show_toast(self, f"Modèle '{name.strip()}' créé avec succès.")
            except Exception as e:
                logger.error("Impossible de créer le modèle : %s", e)
                QMessageBox.critical(self, "Erreur", f"Impossible de créer le modèle : {str(e)}")

    @Slot()
    def _on_duplicate_model(self) -> None:
        if not self._current_model:
            return

        dup_name = f"{self._current_model.name} (Copie)"
        idx = 2
        while NoteTypeModel.get_or_none(NoteTypeModel.name == dup_name):
            dup_name = f"{self._current_model.name} (Copie {idx})"
            idx += 1

        try:
            created = NoteTypeModel.create(
                name=dup_name,
                fields_schema=self._current_model.fields_schema,
                templates=self._current_model.templates,
                css_style=self._current_model.css_style,
            )
            logger.info("Modèle de carte '%s' dupliqué sous '%s'", self._current_model.name, dup_name)
            self.refresh_data()
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item.data(Qt.ItemDataRole.UserRole).id == created.id:
                    self.list_widget.setCurrentItem(item)
                    break
                show_toast(self, f"Modèle dupliqué sous '{dup_name}'.")
        except Exception as e:
            logger.error("Impossible de dupliquer le modèle : %s", e)
            QMessageBox.critical(self, "Erreur", f"Impossible de dupliquer le modèle : {str(e)}")

    @Slot()
    def _on_export_json(self) -> None:
        if not self._current_model:
            show_toast(self, "Aucun modèle sélectionné à exporter.", is_error=True)
            return

        self._sync_current_template_from_editors()
        dialog = ModelExportDialog(model=self._current_model, parent=self)
        dialog.exec()

    @Slot()
    def _on_import_json(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Importer un modèle de carte",
            "",
            "Paquets & Modèles AnkiForge (*.afmodel *.json);;Paquet .afmodel (*.afmodel);;Fichier JSON (*.json)",
        )
        if file_path:
            try:
                is_valid, parsed_data, err_msg = CardModelIO.read_model_file(file_path)
                if not is_valid or not parsed_data:
                    QMessageBox.critical(self, "Fichier Invalide", f"Le fichier de modèle est invalide :\n{err_msg}")
                    return

                dialog = ModelImportDialog(model_data=parsed_data, parent=self)
                if dialog.exec() == ModelImportDialog.DialogCode.Accepted and dialog.imported_model:
                    self.refresh_data()
                    for i in range(self.list_widget.count()):
                        item = self.list_widget.item(i)
                        if item.data(Qt.ItemDataRole.UserRole).id == dialog.imported_model.id:
                            self.list_widget.setCurrentItem(item)
                            break
                    show_toast(self, f"Modèle '{dialog.imported_model.name}' importé avec succès.")
            except Exception as e:
                logger.error("Échec de l'import de modèle : %s", e)
                QMessageBox.critical(self, "Erreur d'importation", f"Échec de l'import : {str(e)}")

    @Slot()
    def _on_open_starter_pack(self) -> None:
        dialog = StarterPackDialog(parent=self)
        dialog.model_installed.connect(self._on_starter_model_installed)
        dialog.exec()

    def _on_starter_model_installed(self, model_id: int) -> None:
        self.refresh_data()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole).id == model_id:
                self.list_widget.setCurrentItem(item)
                break

    @Slot()
    def _on_delete_model(self) -> None:
        if not self._current_model:
            return

        model_name = self._current_model.name
        res = QMessageBox.question(
            self,
            "Supprimer le modèle",
            f"Voulez-vous vraiment supprimer le modèle '{model_name}' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            try:
                self._current_model.delete_instance()
                self._current_model = None
                logger.info("Modèle de carte '%s' supprimé.", model_name)
                self.refresh_data()
                show_toast(self, "Modèle supprimé.")
            except Exception as e:
                logger.error("Impossible de supprimer le modèle : %s", e)
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer le modèle : {str(e)}")

    @Slot()
    def _on_save_model(self) -> None:
        if not self._current_model:
            show_toast(self, "Aucun modèle sélectionné à sauvegarder.", is_error=True)
            return

        try:
            fields_list = [f.strip() for f in self.fields_input.text().split(",") if f.strip()]
            if not fields_list:
                fields_list = ["Front", "Back"]

            self._sync_current_template_from_editors()
            css = self.css_editor_wrapper.toPlainText()

            self._current_model.fields_schema = json.dumps(fields_list, ensure_ascii=False)
            self._current_model.description = self.description_input.text().strip()
            self._current_model.templates = json.dumps(self._templates_list, ensure_ascii=False)
            self._current_model.css_style = css
            self._current_model.save()

            logger.info("Modèle de carte '%s' sauvegardé avec succès.", self._current_model.name)
            show_toast(self, f"Modèle '{self._current_model.name}' sauvegardé avec succès.")
            self._update_preview()
        except Exception as e:
            logger.error("Impossible de sauvegarder le modèle : %s", e)
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Impossible de sauvegarder le modèle : {str(e)}")

    def refresh_theme(self, profile: Any) -> None:
        if hasattr(self, "card_preview_widget") and hasattr(self.card_preview_widget, "refresh_theme"):
            self.card_preview_widget.refresh_theme(profile)
        if hasattr(self, "snippet_drawer") and hasattr(self.snippet_drawer, "refresh_theme"):
            self.snippet_drawer.refresh_theme(profile)
        self._update_tags_toolbar()
        self._switch_subtab(self.editor_stack.currentIndex())


CardModelsTab = CardModelsView
