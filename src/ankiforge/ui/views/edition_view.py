"""
Vue Édition & Navigateur de Cartes avec Divulgation Progressive (Progressive Disclosure).
- Tableau pleine largeur en haut avec filtres (Dossier, Modèle, Tags) et texte épuré sans HTML brut.
- Mécanisme de repliement en 1-clic : le tableau se réduit en un ruban de navigation compact (30px)
  avec boutons Précédente / Suivante, offrant 100% de la hauteur à l'éditeur et au Live Preview.
- Éditeur de champs à gauche (50%) et Live Preview WebEngine à droite (50%) en bas.
- Machine à Remonter le Temps (Time Machine) et Linter IA intégrés.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QModelIndex, QSettings, Qt, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import LLMConfigModel, NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.cards.duplicate_manager import DuplicateManager
from ankiforge.services.cards.store_manager import StoreManager
from ankiforge.services.workers.batch_edit_worker import BatchEditWorker
from ankiforge.services.workers.import_cards_worker import ImportCardsWorker
from ankiforge.ui.components.buttons import IconButton, SecondaryButton
from ankiforge.ui.components.deck_select_window import DeckSelectWindow
from ankiforge.ui.components.panels import IdePanel
from ankiforge.ui.components.tables import VirtualTableView
from ankiforge.ui.components.tag_select_window import TagSelectWindow
from ankiforge.ui.models import (
    BadgeItemDelegate,
    CheckboxItemDelegate,
    NoteVirtualTableModel,
    TagItemDelegate,
    TextSnippetDelegate,
)
from ankiforge.ui.theme import DesignTokens, StyledMenu
from ankiforge.ui.widgets.auto_tag_dialog import AutoTagDialog
from ankiforge.ui.widgets.batch_edit_dialog import BatchEditDialog
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.duplicate_resolver import DuplicateResolverDialog
from ankiforge.ui.widgets.editor_toolbar_widget import EditorToolbarWidget
from ankiforge.ui.widgets.linter_dialog import LinterDialog
from ankiforge.ui.widgets.note_editor_widget import NoteFieldEditorWidget, NoteFieldTextEdit
from ankiforge.ui.widgets.time_machine_dialog import TimeMachineDialog
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.anki_renderer import get_max_cloze_index
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


def strip_html_tags(text: str) -> str:
    """Nettoie les balises HTML et décode les entités basiques pour un aperçu fluide dans le tableau."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = clean.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", clean).strip()


def format_tags_display(tags_raw: Any) -> str:
    """Formate les tags pour éviter l'affichage de chaînes Python brutes comme '[]'."""
    if not tags_raw:
        return ""
    if isinstance(tags_raw, str):
        try:
            parsed = json.loads(tags_raw)
            if isinstance(parsed, list):
                tags_raw = parsed
            elif tags_raw.strip() in ("[]", ""):
                return ""
        except Exception:
            if tags_raw.strip() in ("[]", ""):
                return ""
    if isinstance(tags_raw, list):
        clean_list = [str(t).strip() for t in tags_raw if str(t).strip()]
        return "  ".join(f"#{t}" for t in clean_list)
    return str(tags_raw).strip()


class EditionView(QWidget):
    """
    Vue Principale d'Édition et de Navigation des Cartes avec Divulgation Progressive.
    """

    BATCH_SIZE = 50

    def __init__(self, ai_manager: Any = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.store = StoreManager()
        self.settings = QSettings("AnkiForgeOrg", "ankiforge_obsidian")

        self.batch_thread: Optional[BatchEditWorker] = None
        self.import_thread: Optional[ImportCardsWorker] = None
        self.progress_dialog: Optional[QProgressDialog] = None

        self._dirty = False
        self._current_note: Optional[NoteModel] = None
        self._active_folder_id: Optional[int] = None
        self._active_tags: List[str] = []
        self._active_model_id: Optional[int] = None
        self._current_table_fields: Optional[List[str]] = None
        self._original_content: Dict[str, str] = {}

        self.dynamic_field_widgets: Dict[str, NoteFieldEditorWidget] = {}
        self._active_editor: Optional[NoteFieldTextEdit] = None

        self._table_collapsed: bool = False
        self._saved_table_height: int = 260
        self._preview_visible: bool = True
        self._saved_preview_width: int = 400

        self._deck_modal: Optional[DeckSelectWindow] = None
        self._tag_modal: Optional[TagSelectWindow] = None
        self._import_dialog: Optional[QWidget] = None
        self._export_dialog: Optional[QWidget] = None

        self._all_notes: List[NoteModel] = []
        self._displayed_count: int = 0

        self._setup_ui()
        self._setup_shortcuts()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # Panneau unifié (IdePanel)
        self.main_panel = IdePanel(detachable=True)

        panel_content = QWidget()
        panel_layout = QVBoxLayout(panel_content)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # =====================================================================
        # SPLITTER VERTICAL PRINCIPAL (Tableau Haut / Éditeur & Preview Bas)
        # =====================================================================
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {DesignTokens.BORDER_COLOR};
                height: 4px;
            }}
            QSplitter::handle:hover {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        # ---------------------------------------------------------------------
        # VOLET SUPÉRIEUR : TABLEAU PLEINE LARGEUR & RUBAN PROGRESSIF
        # ---------------------------------------------------------------------
        self.table_container = QWidget()
        self.table_container_layout = QVBoxLayout(self.table_container)
        self.table_container_layout.setContentsMargins(0, 0, 0, 0)
        self.table_container_layout.setSpacing(0)

        # A. Boîte complète du Tableau (Déplié)
        self.table_box = QWidget()
        table_box_layout = QVBoxLayout(self.table_box)
        table_box_layout.setContentsMargins(0, 0, 0, 0)
        table_box_layout.setSpacing(0)

        # Barre de filtres
        filter_bar = QWidget()
        filter_bar.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(8, 6, 8, 6)
        filter_layout.setSpacing(8)

        self.btn_open_folder = QPushButton("Dossier : Tous ▾")
        self.btn_open_folder.setIcon(load_phosphor_icon("folders", color=DesignTokens.TEXT_SECONDARY))
        self.btn_open_folder.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
                color: {DesignTokens.TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        self.btn_open_folder.clicked.connect(self._show_folder_modal)
        filter_layout.addWidget(self.btn_open_folder)

        self.btn_open_model = QPushButton("Modèle : Tous ▾")
        self.btn_open_model.setIcon(load_phosphor_icon("cards", color=DesignTokens.ACCENT_PRIMARY))
        self.btn_open_model.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
                color: {DesignTokens.TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        self.btn_open_model.clicked.connect(self._show_model_menu)
        filter_layout.addWidget(self.btn_open_model)

        separator = QFrame()
        separator.setFixedSize(1, 14)
        separator.setStyleSheet(f"background-color: {DesignTokens.BORDER_COLOR}; border: none;")
        filter_layout.addWidget(separator)

        tags_lbl = QLabel("TAGS :")
        tags_lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {DesignTokens.TEXT_MUTED}; text-transform: uppercase;")
        filter_layout.addWidget(tags_lbl)

        self.tags_container = QWidget()
        self.tags_layout = QHBoxLayout(self.tags_container)
        self.tags_layout.setContentsMargins(0, 0, 0, 0)
        self.tags_layout.setSpacing(4)
        filter_layout.addWidget(self.tags_container)

        self.btn_open_tag = QPushButton("+ Tag")
        self.btn_open_tag.setIcon(load_phosphor_icon("plus", color=DesignTokens.TEXT_SECONDARY))
        self.btn_open_tag.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px dashed {DesignTokens.BORDER_COLOR};
                border-radius: 12px;
                padding: 2px 8px;
                min-height: 20px;
                font-size: 10px;
                color: {DesignTokens.TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        self.btn_open_tag.clicked.connect(self._show_tag_modal)
        filter_layout.addWidget(self.btn_open_tag)
        filter_layout.addStretch()

        self.btn_import_apkg = IconButton("download-simple", tooltip="Importer un paquet Anki (.apkg)", size=22)
        self.btn_import_apkg.clicked.connect(self._open_import_dialog)
        filter_layout.addWidget(self.btn_import_apkg)

        self.btn_export_apkg = IconButton("upload-simple", tooltip="Exporter des cartes Anki (.apkg)", size=22)
        self.btn_export_apkg.clicked.connect(self._open_export_dialog)
        filter_layout.addWidget(self.btn_export_apkg)

        table_box_layout.addWidget(filter_bar)

        # Tableau des cartes virtualisé (Pleine largeur 60 FPS)
        self.card_table = VirtualTableView()
        self.note_table_model = NoteVirtualTableModel(parent=self)
        self.card_table.setModel(self.note_table_model)

        self.checkbox_delegate = CheckboxItemDelegate(self.card_table)
        self.text_code_delegate = TextSnippetDelegate(is_code_font=True, parent=self.card_table)
        self.text_regular_delegate = TextSnippetDelegate(is_code_font=False, parent=self.card_table)
        self.badge_delegate = BadgeItemDelegate(parent=self.card_table)
        self.tag_delegate = TagItemDelegate(parent=self.card_table)

        self._update_table_headers()

        self.card_table.clicked.connect(self._on_card_selected)
        selection_model = self.card_table.selectionModel()
        if selection_model is not None:
            selection_model.currentRowChanged.connect(self._on_table_row_changed)
        self.card_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.card_table.customContextMenuRequested.connect(self._show_card_context_menu)

        table_box_layout.addWidget(self.card_table)
        self.table_container_layout.addWidget(self.table_box)

        # B. Ruban de Navigation Compact (Progressive Disclosure quand replié)
        self.nav_ribbon = QWidget()
        self.nav_ribbon.setFixedHeight(32)
        self.nav_ribbon.setStyleSheet(f"""
            QWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        ribbon_layout = QHBoxLayout(self.nav_ribbon)
        ribbon_layout.setContentsMargins(8, 2, 8, 2)
        ribbon_layout.setSpacing(8)

        self.btn_prev_card = IconButton("caret-left", tooltip="Carte précédente (Alt+Up)", size=22)
        self.btn_prev_card.clicked.connect(self._select_previous_card)
        ribbon_layout.addWidget(self.btn_prev_card)

        self.lbl_card_ribbon_info = QLabel("Aucune carte sélectionnée")
        self.lbl_card_ribbon_info.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; border: none;")
        ribbon_layout.addWidget(self.lbl_card_ribbon_info)

        self.btn_next_card = IconButton("caret-right", tooltip="Carte suivante (Alt+Down)", size=22)
        self.btn_next_card.clicked.connect(self._select_next_card)
        ribbon_layout.addWidget(self.btn_next_card)

        ribbon_layout.addStretch()

        self.btn_expand_table = SecondaryButton("Déplier la liste")
        self.btn_expand_table.setIcon(load_phosphor_icon("caret-down", color=DesignTokens.TEXT_PRIMARY))
        self.btn_expand_table.setFixedHeight(24)
        self.btn_expand_table.setStyleSheet("""
            QPushButton {
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 600;
            }
        """)
        self.btn_expand_table.clicked.connect(self._toggle_table_collapsed)
        ribbon_layout.addWidget(self.btn_expand_table)

        self.nav_ribbon.hide()
        self.table_container_layout.addWidget(self.nav_ribbon)

        self.main_splitter.addWidget(self.table_container)

        # ---------------------------------------------------------------------
        # VOLET INFÉRIEUR : ÉDITEUR DE CHAMPS (GAUCHE) & LIVE PREVIEW (DROITE)
        # ---------------------------------------------------------------------
        self.editor_stack = QStackedWidget()

        # Page 0: Placeholder élégant
        self.editor_placeholder = QWidget()
        self.editor_placeholder.setStyleSheet(f"background-color: {DesignTokens.BG_SIDEBAR};")
        placeholder_layout = QVBoxLayout(self.editor_placeholder)
        placeholder_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_layout.setSpacing(10)

        self.placeholder_icon = QLabel()
        self.placeholder_icon.setPixmap(load_phosphor_icon("cards", color=DesignTokens.TEXT_MUTED).pixmap(44, 44))
        self.placeholder_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_icon.setStyleSheet("border: none; background: transparent;")

        self.placeholder_title = QLabel("Aucune note sélectionnée")
        self.placeholder_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: bold; border: none; background: transparent;")
        self.placeholder_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.placeholder_sub = QLabel("Sélectionnez une carte dans le tableau ci-dessus pour afficher l'éditeur et l'aperçu live.")
        self.placeholder_sub.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px; border: none; background: transparent;")
        self.placeholder_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        placeholder_layout.addWidget(self.placeholder_icon)
        placeholder_layout.addWidget(self.placeholder_title)
        placeholder_layout.addWidget(self.placeholder_sub)

        self.editor_stack.addWidget(self.editor_placeholder)  # Index 0

        # Page 1: Conteneur d'édition complet
        self.editor_container = QWidget()
        self.editor_container.setStyleSheet(f"background-color: {DesignTokens.BG_SIDEBAR};")
        editor_layout = QVBoxLayout(self.editor_container)
        editor_layout.setContentsMargins(6, 6, 6, 6)
        editor_layout.setSpacing(6)

        # Toolbar compacte au sommet (32px)
        self.editor_toolbar = EditorToolbarWidget(self)
        self.editor_toolbar.action_triggered.connect(self._handle_editor_action)
        self.editor_toolbar.save_requested.connect(self._save_card)
        self.editor_toolbar.history_requested.connect(self._open_history_modal)
        self.editor_toolbar.toggle_preview_requested.connect(self._toggle_preview_pane)
        self.editor_toolbar.toggle_table_requested.connect(self._toggle_table_collapsed)
        editor_layout.addWidget(self.editor_toolbar)

        # Splitter Horizontal (Champs à gauche 50% / Live Preview à droite 50%)
        self.fields_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.fields_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {DesignTokens.BORDER_COLOR};
                width: 3px;
            }}
            QSplitter::handle:hover {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        # Gauche : ScrollArea pour champs dynamiques
        self.fields_scroll_area = QScrollArea()
        self.fields_scroll_area.setWidgetResizable(True)
        self.fields_scroll_area.setStyleSheet(f"QScrollArea {{ border: none; background-color: {DesignTokens.BG_SIDEBAR}; }}")

        self.fields_container = QWidget()
        self.fields_container.setStyleSheet(f"background-color: {DesignTokens.BG_SIDEBAR};")
        self.fields_layout = QVBoxLayout(self.fields_container)
        self.fields_layout.setContentsMargins(0, 0, 0, 0)
        self.fields_layout.setSpacing(6)
        self.fields_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.fields_scroll_area.setWidget(self.fields_container)
        self.fields_splitter.addWidget(self.fields_scroll_area)

        # Droite : Live Preview
        self.preview_container = QWidget()
        preview_layout = QVBoxLayout(self.preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)

        self.card_preview = CardPreviewWidget(show_header=True)
        preview_layout.addWidget(self.card_preview)

        self.fields_splitter.addWidget(self.preview_container)
        self.fields_splitter.setSizes([500, 500])

        editor_layout.addWidget(self.fields_splitter, 1)

        self.editor_stack.addWidget(self.editor_container)  # Index 1

        self.main_splitter.addWidget(self.editor_stack)

        # Répartition initiale du Splitter Vertical : Tableau 280px / Éditeur 450px
        self.main_splitter.setSizes([280, 450])
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)

        panel_layout.addWidget(self.main_splitter)

        self.main_panel.add_tab("Navigateur & Éditeur de Cartes", panel_content, icon_name="ph.cards", closable=False)
        main_layout.addWidget(self.main_panel)

        self.editor_stack.setCurrentIndex(0)

    def _setup_shortcuts(self) -> None:
        """Enregistre les raccourcis clavier universels pour la vue."""
        QShortcut(QKeySequence.StandardKey.Save, self, self._save_card)
        QShortcut(QKeySequence("Ctrl+H"), self, self._open_history_modal)
        QShortcut(QKeySequence("Ctrl+P"), self, self._toggle_preview_pane)
        QShortcut(QKeySequence("Ctrl+Shift+T"), self, self._toggle_table_collapsed)
        QShortcut(QKeySequence("Alt+Up"), self, self._select_previous_card)
        QShortcut(QKeySequence("Alt+Down"), self, self._select_next_card)
        QShortcut(QKeySequence("Ctrl+B"), self, lambda: self._handle_editor_action("bold"))
        QShortcut(QKeySequence("Ctrl+I"), self, lambda: self._handle_editor_action("italic"))
        QShortcut(QKeySequence("Ctrl+U"), self, lambda: self._handle_editor_action("underline"))
        QShortcut(QKeySequence("Ctrl+K"), self, lambda: self._handle_editor_action("link"))
        QShortcut(QKeySequence("Ctrl+M"), self, lambda: self._handle_editor_action("math"))
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, lambda: self._handle_editor_action("cloze"))

    # --- Gestion de la Divulgation Progressive (Tableau / Ruban) ---

    @Slot()
    def _toggle_table_collapsed(self) -> None:
        """Bascule entre le tableau complet et le ruban de navigation compact."""
        self._table_collapsed = not self._table_collapsed

        if self._table_collapsed:
            sizes = self.main_splitter.sizes()
            self._saved_table_height = max(180, sizes[0])
            self.table_box.hide()
            self.nav_ribbon.show()
            self.editor_toolbar.btn_toggle_table.setIcon(load_phosphor_icon("caret-down", color=DesignTokens.TEXT_PRIMARY))
            self.editor_toolbar.btn_toggle_table.setToolTip("Déplier la liste des cartes (Ctrl+Shift+T)")
            self.main_splitter.setSizes([32, sizes[0] + sizes[1] - 32])
        else:
            sizes = self.main_splitter.sizes()
            self.table_box.show()
            self.nav_ribbon.hide()
            self.editor_toolbar.btn_toggle_table.setIcon(load_phosphor_icon("caret-up", color=DesignTokens.TEXT_PRIMARY))
            self.editor_toolbar.btn_toggle_table.setToolTip("Replier la liste des cartes (Ctrl+Shift+T)")
            self.main_splitter.setSizes([self._saved_table_height, max(300, sizes[0] + sizes[1] - self._saved_table_height)])

    def _update_nav_ribbon_info(self) -> None:
        """Met à jour le texte d'information du ruban compact."""
        if not self._current_note:
            self.lbl_card_ribbon_info.setText("Aucune carte sélectionnée")
            return

        selected_rows = self.card_table.get_selected_rows()
        current_row = selected_rows[0] if selected_rows else self.card_table.currentIndex().row()
        total_rows = self.note_table_model.rowCount()
        recto_text = ""
        for widget in self.dynamic_field_widgets.values():
            recto_text = strip_html_tags(widget.get_text())
            break

        row_info = f"({current_row + 1}/{total_rows})" if current_row >= 0 else ""
        preview = f"{recto_text[:60]}..." if len(recto_text) > 60 else recto_text
        self.lbl_card_ribbon_info.setText(f"Carte #{self._current_note.id} {row_info} : {preview}")

    @Slot()
    def _select_previous_card(self) -> None:
        """Sélectionne la carte précédente dans la liste."""
        selected_rows = self.card_table.get_selected_rows()
        current_row = selected_rows[0] if selected_rows else self.card_table.currentIndex().row()
        if current_row > 0:
            target_row = current_row - 1
            self.card_table.select_row(target_row)
            self._on_card_selected()

    @Slot()
    def _select_next_card(self) -> None:
        """Sélectionne la carte suivante dans la liste."""
        selected_rows = self.card_table.get_selected_rows()
        current_row = selected_rows[0] if selected_rows else self.card_table.currentIndex().row()
        if current_row >= 0 and current_row < self.note_table_model.rowCount() - 1:
            target_row = current_row + 1
            self.card_table.select_row(target_row)
            self._on_card_selected()

    # --- Gestion du Volet de Prévisualisation ---

    @Slot()
    def _toggle_preview_pane(self) -> None:
        """Affiche ou masque le volet d'aperçu latéral."""
        self._preview_visible = not self._preview_visible
        self.preview_container.setVisible(self._preview_visible)

        sizes = self.fields_splitter.sizes()
        if self._preview_visible:
            self.fields_splitter.setSizes([sizes[0], max(250, sizes[1] - self._saved_preview_width), self._saved_preview_width])
        else:
            self._saved_preview_width = max(260, sizes[1])
            self.fields_splitter.setSizes([sizes[0] + sizes[1], 0])

    @Slot(str)
    def set_view_mode(self, mode: str) -> None:
        """Gère les modes de compatibilité ('fields_only', 'split', 'preview_only')."""
        if mode == "fields_only":
            self._preview_visible = False
            self.preview_container.hide()
            self.fields_scroll_area.show()
            self.fields_splitter.setSizes([1000, 0])
        elif mode == "preview_only":
            self._preview_visible = True
            self.preview_container.show()
            self.fields_scroll_area.hide()
            self.fields_splitter.setSizes([0, 1000])
        else:  # split
            self._preview_visible = True
            self.preview_container.show()
            self.fields_scroll_area.show()
            self.fields_splitter.setSizes([500, 500])

    # --- Actions d'Édition & Formatage ---

    def _get_target_editor(self) -> Optional[NoteFieldTextEdit]:
        """Retourne l'éditeur actuellement actif ou le premier champ par défaut."""
        if self._active_editor and not self._active_editor.isHidden():
            return self._active_editor

        for widget in self.dynamic_field_widgets.values():
            if not widget.editor.isHidden():
                return widget.editor
        return None

    @Slot(str)
    def _handle_editor_action(self, action_id: str) -> None:
        editor = self._get_target_editor()
        if not editor:
            return

        if action_id == "bold":
            editor.wrap_selection("<b>", "</b>")
        elif action_id == "italic":
            editor.wrap_selection("<i>", "</i>")
        elif action_id == "underline":
            editor.wrap_selection("<u>", "</u>")
        elif action_id == "strikethrough":
            editor.wrap_selection("<s>", "</s>")
        elif action_id == "code_inline":
            editor.wrap_selection("<code>", "</code>")
        elif action_id == "code_block":
            editor.wrap_selection("<pre><code>\n", "\n</code></pre>")
        elif action_id == "math":
            editor.wrap_selection("$", "$")
        elif action_id == "cloze":
            current_dict = {name: w.get_text() for name, w in self.dynamic_field_widgets.items()}
            max_c = get_max_cloze_index(current_dict)
            next_c = max(1, max_c + 1)
            editor.wrap_selection(f"{{{{c{next_c}::", "}}")
        elif action_id == "link":
            editor.wrap_selection('<a href="https://">', "</a>")
        elif action_id == "image":
            editor.insert_at_cursor('<img src="">')
        elif action_id == "bullet_list":
            editor.wrap_selection("<ul>\n  <li>", "</li>\n</ul>")
        elif action_id == "ordered_list":
            editor.wrap_selection("<ol>\n  <li>", "</li>\n</ol>")
        elif action_id == "hr":
            editor.insert_at_cursor("<hr>\n")
        elif action_id == "quote":
            editor.wrap_selection("<blockquote>", "</blockquote>")

    # --- Construction Dynamique des Champs ---

    def _build_dynamic_editors(self, note: NoteModel, data: Dict[str, str]) -> None:
        while self.fields_layout.count():
            item = self.fields_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget:
                    widget.deleteLater()

        self.dynamic_field_widgets.clear()
        self._original_content.clear()
        self._active_editor = None

        fields = ["Front", "Back"]
        if note.note_type and note.note_type.fields_schema:
            try:
                fields = json.loads(str(note.note_type.fields_schema)) if note.note_type and note.note_type.fields_schema else []
            except Exception as e:
                logger.warning("Échec du chargement du schéma des champs : %s", e)
                fields = []

        for i, field_name in enumerate(fields):
            val = data.get(field_name, data.get(field_name.lower(), ""))

            field_widget = NoteFieldEditorWidget(
                field_name=field_name,
                initial_value=val,
                is_first=(i == 0),
                parent=self.fields_container,
            )
            field_widget.set_known_fields(fields)
            field_widget.content_changed.connect(self._on_field_content_changed)
            field_widget.focus_received.connect(self._on_field_focus_received)
            field_widget.save_requested.connect(self._save_card)
            field_widget.history_requested.connect(self._open_history_modal)
            field_widget.editor.shortcut_action_triggered.connect(self._handle_editor_action)

            self.dynamic_field_widgets[field_name] = field_widget
            self._original_content[field_name] = val
            self.fields_layout.addWidget(field_widget)

        if self.dynamic_field_widgets:
            first_widget = list(self.dynamic_field_widgets.values())[0]
            self._active_editor = first_widget.editor

    def _on_field_focus_received(self, field_widget: NoteFieldEditorWidget) -> None:
        self._active_editor = field_widget.editor

    def _on_field_content_changed(self, field_name: str) -> None:
        is_modified = False
        for name, widget in self.dynamic_field_widgets.items():
            if widget.get_text() != self._original_content.get(name, ""):
                is_modified = True
                break

        self._dirty = is_modified
        self._update_preview()
        self._update_nav_ribbon_info()

    def _on_table_row_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        """Gère le changement de sélection de ligne au clavier ou à la souris."""
        if not current.isValid():
            return
        self._on_card_selected(current)

    def _on_card_selected(self, item_or_index: Any = None) -> None:
        """Charge et affiche la carte sélectionnée dans l'éditeur et l'aperçu."""
        if isinstance(item_or_index, QModelIndex):
            row = item_or_index.row()
        elif hasattr(item_or_index, "row"):
            row = item_or_index.row()
        else:
            selected_rows = self.card_table.get_selected_rows()
            row = selected_rows[0] if selected_rows else self.card_table.currentIndex().row()

        if row < 0:
            return

        note = self.note_table_model.get_note_at(row)
        if not note:
            return

        if self._dirty and self._current_note and self._current_note.id != note.id:
            reply = QMessageBox.question(
                self,
                "Modifications non enregistrées",
                f"La carte #{self._current_note.id} contient des modifications non sauvegardées.\nVoulez-vous la sauvegarder avant de continuer ?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if reply == QMessageBox.StandardButton.Save:
                self._save_card()
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        self._current_note = note
        self.editor_stack.setCurrentIndex(1)
        data = self._get_note_content_dynamic(note)
        self._build_dynamic_editors(note, data)

        self._update_preview()
        self._update_nav_ribbon_info()
        self._dirty = False

    def _update_preview(self) -> None:
        fields_dict: Dict[str, str] = {}
        for field_name, widget in self.dynamic_field_widgets.items():
            fields_dict[field_name] = widget.get_text()

        note_type = getattr(self._current_note, "note_type", None) if self._current_note else None

        if "Front" not in fields_dict and len(fields_dict) > 0:
            fields_dict["Front"] = list(fields_dict.values())[0]
        if "Back" not in fields_dict and len(fields_dict) > 1:
            fields_dict["Back"] = list(fields_dict.values())[1]

        override_templates = None
        if not note_type or not getattr(note_type, "templates", None):
            override_templates = [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}]

        self.card_preview.update_preview(
            note_type=note_type,
            fields_dict=fields_dict,
            override_templates=override_templates,
        )

    # --- Sauvegarde & Time Machine ---

    @Slot()
    def _save_card(self) -> None:
        if not self._current_note:
            return

        try:
            note_id = self._current_note.id
            new_content = {field: widget.get_text() for field, widget in self.dynamic_field_widgets.items()}
            self._current_note.add_version(new_content, source="manual")
            self._original_content = new_content.copy()
            self._dirty = False

            # Mise à jour instantanée du modèle virtuel en O(1)
            self.note_table_model.update_note_content(note_id, new_content)
            self._update_nav_ribbon_info()
            show_toast(self, f"Carte #{note_id} sauvegardée avec succès.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Impossible de sauvegarder la carte : {str(e)}")

    @Slot()
    def _open_history_modal(self) -> None:
        if not self._current_note:
            return

        dialog = TimeMachineDialog(note=self._current_note, parent=self)
        dialog.version_restored.connect(self._on_version_restored)
        dialog.exec()

    def _on_version_restored(self, note_id: int, restored_dict: Dict[str, str]) -> None:
        """Met à jour immédiatement l'éditeur et la table suite à la restauration."""
        for field, widget in self.dynamic_field_widgets.items():
            if field in restored_dict:
                widget.set_text(restored_dict[field])

        self._original_content = restored_dict.copy()
        self._dirty = False
        self._update_preview()
        self._update_nav_ribbon_info()

        self.refresh_data()
        self.select_note_by_id(note_id)

    # --- Menus & Filtres ---

    @Slot()
    def _show_folder_modal(self) -> None:
        try:
            if self._deck_modal and self._deck_modal.isVisible():
                self._deck_modal.raise_()
                self._deck_modal.activateWindow()
                return
        except RuntimeError:
            self._deck_modal = None

        self._deck_modal = DeckSelectWindow(parent=self)
        self._deck_modal.deck_selected.connect(self._on_deck_selected_from_modal)
        self._deck_modal.show()

    @Slot(int, str)
    def _on_deck_selected_from_modal(self, deck_id: int, deck_name: str) -> None:
        if deck_id == -1:
            self.btn_open_folder.setText("Dossier : Tous ▾")
            self.btn_open_folder.setIcon(load_phosphor_icon("folders", color=DesignTokens.TEXT_SECONDARY))
            self.btn_open_folder.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: bold;
                    color: {DesignTokens.TEXT_SECONDARY};
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                }}
            """)
            self._active_folder_id = None
        else:
            self.btn_open_folder.setText(f"Dossier : {deck_name} ▾")
            self.btn_open_folder.setIcon(load_phosphor_icon("folder", color=DesignTokens.ACCENT_PRIMARY))
            self.btn_open_folder.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(99, 102, 241, 0.15);
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: bold;
                    color: {DesignTokens.ACCENT_PRIMARY};
                }}
            """)
            self._active_folder_id = deck_id

        self.refresh_data()

    @Slot()
    def _show_tag_modal(self) -> None:
        try:
            if self._tag_modal and self._tag_modal.isVisible():
                self._tag_modal.raise_()
                self._tag_modal.activateWindow()
                return
        except RuntimeError:
            self._tag_modal = None

        current_tags = set()
        for note in NoteModel.select(NoteModel.tags).where(NoteModel.tags.is_null(False)).limit(500):
            if note.tags:
                try:
                    tags = json.loads(str(note.tags))
                    if isinstance(tags, list):
                        for t in tags:
                            if t.strip():
                                current_tags.add(t.strip())
                    elif isinstance(tags, str) and tags.strip():
                        current_tags.add(tags.strip())
                except Exception as e:
                    logger.warning("Échec du parsing des tags : %s", e)

        self._tag_modal = TagSelectWindow(allowed_tags=current_tags, parent=self)
        self._tag_modal.tag_selected.connect(self._on_tag_selected_from_modal)
        self._tag_modal.show()

    @Slot(str)
    def _on_tag_selected_from_modal(self, tag: str) -> None:
        if tag not in self._active_tags:
            self._active_tags.append(tag)
            self._rebuild_tag_chips()
            show_toast(self, f"Tag {tag} ajouté au filtre")
            self.refresh_data()

    def _rebuild_tag_chips(self) -> None:
        while self.tags_layout.count():
            item = self.tags_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

        for tag in self._active_tags:
            chip = QPushButton(f"{tag}")
            chip.setIcon(load_phosphor_icon("x", color=DesignTokens.ACCENT_PRIMARY))
            chip.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: 12px;
                    padding: 2px 8px;
                    min-height: 20px;
                    font-size: 11px;
                    font-weight: bold;
                    color: {DesignTokens.TEXT_PRIMARY};
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                }}
            """)
            chip.clicked.connect(lambda checked=False, t=tag: self._remove_tag_filter(t))
            self.tags_layout.addWidget(chip)

    def _remove_tag_filter(self, tag: str) -> None:
        if tag in self._active_tags:
            self._active_tags.remove(tag)
            self._rebuild_tag_chips()
            self.refresh_data()

    @Slot()
    def _show_model_menu(self) -> None:
        menu = StyledMenu(self)

        all_action = menu.addAction("Tous les modèles")
        all_action.triggered.connect(lambda: self._on_model_selected(None, "Tous les modèles"))

        menu.addSeparator()

        try:
            for m in NoteTypeModel.select():
                action = menu.addAction(m.name)
                action.triggered.connect(lambda checked=False, mid=m.id, mname=m.name: self._on_model_selected(mid, mname))
        except Exception as e:
            logger.warning("Erreur chargement modèles : %s", e)

        menu.exec(self.btn_open_model.mapToGlobal(self.btn_open_model.rect().bottomLeft()))

    def _on_model_selected(self, model_id: Optional[int], model_name: str) -> None:
        self._active_model_id = model_id
        if model_id is None:
            self.btn_open_model.setText("Modèle : Tous ▾")
            self.btn_open_model.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: bold;
                    color: {DesignTokens.TEXT_SECONDARY};
                }}
            """)
        else:
            self.btn_open_model.setText(f"Modèle : {model_name} ▾")
            self.btn_open_model.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(99, 102, 241, 0.15);
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: bold;
                    color: {DesignTokens.ACCENT_PRIMARY};
                }}
            """)
        self._update_table_headers()
        self.refresh_data()

    def _update_table_headers(self) -> None:
        if self._active_model_id:
            try:
                model = NoteTypeModel.get_or_none(NoteTypeModel.id == self._active_model_id)
                if model and model.fields_schema:
                    fields = json.loads(model.fields_schema)
                    current_fields = fields[:3]
                    self._current_table_fields = current_fields
                    self.note_table_model.set_active_model_fields(current_fields)

                    self.card_table.setColumnWidth(0, 36)
                    self.card_table.setItemDelegateForColumn(0, self.checkbox_delegate)
                    for i in range(1, len(current_fields) + 1):
                        self.card_table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
                        if i == 1:
                            self.card_table.setItemDelegateForColumn(i, self.text_code_delegate)
                        else:
                            self.card_table.setItemDelegateForColumn(i, self.text_regular_delegate)

                    deck_col = len(current_fields) + 1
                    tags_col = deck_col + 1
                    self.card_table.setColumnWidth(deck_col, 140)
                    self.card_table.setColumnWidth(tags_col, 140)
                    self.card_table.setItemDelegateForColumn(deck_col, self.badge_delegate)
                    self.card_table.setItemDelegateForColumn(tags_col, self.tag_delegate)
                    return
            except Exception as e:
                logger.warning("Erreur lors de la mise à jour des en-têtes du tableau : %s", e)

        # Default (Mixed / All Models) : Tableau Spacieux
        self._current_table_fields = None
        self.note_table_model.set_active_model_fields(None)
        self.card_table.setColumnWidth(0, 36)
        self.card_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.card_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.card_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.card_table.setColumnWidth(3, 110)  # Modèle
        self.card_table.setColumnWidth(4, 140)  # Deck
        self.card_table.setColumnWidth(5, 140)  # Tags
        self.card_table.setItemDelegateForColumn(0, self.checkbox_delegate)
        self.card_table.setItemDelegateForColumn(1, self.text_code_delegate)
        self.card_table.setItemDelegateForColumn(2, self.text_regular_delegate)
        self.card_table.setItemDelegateForColumn(3, self.badge_delegate)
        self.card_table.setItemDelegateForColumn(4, self.badge_delegate)
        self.card_table.setItemDelegateForColumn(5, self.tag_delegate)

    # --- Menu Contextuel & Opérations de Masse ---

    def _show_card_context_menu(self, pos: Any) -> None:
        index = self.card_table.indexAt(pos)
        if not index.isValid():
            return

        row = index.row()
        note = self.note_table_model.get_note_at(row)
        if not note:
            return

        menu = StyledMenu(self)

        action_edit = menu.addAction(load_phosphor_icon("pencil-simple", color=DesignTokens.TEXT_PRIMARY), "Éditer cette carte")
        action_edit.triggered.connect(lambda: self.select_note_by_id(note.id))

        action_history = menu.addAction(load_phosphor_icon("clock-counter-clockwise", color=DesignTokens.TEXT_PRIMARY), "Historique des versions")
        action_history.triggered.connect(lambda: self.show_version_history(note.id))

        menu.addSeparator()

        action_lint = menu.addAction(load_phosphor_icon("first-aid-kit", color=DesignTokens.ACCENT_PRIMARY), "Linter IA (Wozniak)")
        action_lint.triggered.connect(lambda: self.open_linter_dialog([note.id]))

        action_tag = menu.addAction(load_phosphor_icon("tag", color=DesignTokens.COLOR_PURPLE), "Auto-Tagging IA")
        action_tag.triggered.connect(lambda: self.open_auto_tag_dialog([note.id]))

        menu.addSeparator()

        action_delete = menu.addAction(load_phosphor_icon("trash", color=DesignTokens.COLOR_RED), "Supprimer la carte")
        action_delete.triggered.connect(lambda: self.reject_selected_notes([note.id]))

        menu.exec(self.card_table.mapToGlobal(pos))

    @Slot(int)
    def show_version_history(self, note_id: int) -> None:
        try:
            note = NoteModel.get_by_id(note_id)
            dialog = TimeMachineDialog(note=note, parent=self)
            dialog.version_restored.connect(self._on_version_restored)
            dialog.exec()
        except Exception as e:
            logger.warning("Erreur ouverture TimeMachine : %s", e)

    @Slot(list)
    def open_linter_dialog(self, note_ids: List[int]) -> None:
        if not note_ids:
            return
        dialog = LinterDialog(note_ids, self)
        dialog.exec()
        self.refresh_data()

    @Slot(list)
    def open_auto_tag_dialog(self, note_ids: List[int]) -> None:
        if not note_ids:
            return
        if AutoTagDialog(self, note_ids).exec():
            show_toast(self, "Auto-Tagging terminé avec succès !")
            self.refresh_data()

    @Slot(list)
    def open_batch_edit_dialog(self, note_ids: List[int]) -> None:
        if not note_ids:
            return
        dialog = BatchEditDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            try:
                llm_config = LLMConfigModel.get_by_id(data["llm_id"])
                provider = AIManager.create_provider_from_config(llm_config)
            except Exception:
                provider = None

            if not provider:
                QMessageBox.warning(self, "Configuration IA", "Aucun provider IA disponible pour l'édition par lot.")
                return

            self.progress_dialog = QProgressDialog("Modification IA en cours...", "Annuler", 0, 0, self)
            self.batch_thread = BatchEditWorker(provider, note_ids, data["prompt"], data["chunk_size"])
            self.batch_thread.progress.connect(self.progress_dialog.setLabelText)
            self.batch_thread.finished_signal.connect(self._on_batch_edit_success)
            self.batch_thread.error_signal.connect(self._on_batch_edit_error)
            self.progress_dialog.canceled.connect(self.batch_thread.cancel)
            self.batch_thread.start()
            self.progress_dialog.show()

    def _on_batch_edit_success(self, count: int) -> None:
        if self.progress_dialog:
            self.progress_dialog.close()
        show_toast(self, f"{count} notes traitées par l'IA !")
        self.refresh_data()

    def _on_batch_edit_error(self, msg: str) -> None:
        if self.progress_dialog:
            self.progress_dialog.close()
        QMessageBox.critical(self, "Erreur IA", msg)

    @Slot()
    def scan_for_duplicates(self) -> None:
        try:
            deck_id = self._active_folder_id or 1
            conflicts = DuplicateManager.find_duplicates(deck_id)
            if not conflicts:
                show_toast(self, "Aucun doublon trouvé !")
            else:
                DuplicateResolverDialog(conflicts, self).exec()
                self.refresh_data()
        except Exception as e:
            logger.exception("Erreur lors du scan des doublons")
            QMessageBox.critical(self, "Erreur", str(e))

    @Slot(list)
    def approve_selected_notes(self, note_ids: List[int]) -> None:
        try:
            self.store.approve_notes(note_ids)
            show_toast(self, f"{len(note_ids)} note(s) approuvée(s) !")
            self.refresh_data()
        except Exception as e:
            logger.exception("Erreur lors de l'approbation des notes")
            QMessageBox.critical(self, "Erreur", str(e))

    @Slot(list)
    def reject_selected_notes(self, note_ids: List[int]) -> None:
        reply = QMessageBox.question(
            self,
            "Confirmation",
            f"Supprimer définitivement {len(note_ids)} note(s) ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.store.delete_notes(note_ids)
                show_toast(self, "Notes supprimées.")
                self.refresh_data()
            except Exception as e:
                logger.exception("Erreur lors de la suppression des notes")
                QMessageBox.critical(self, "Erreur", str(e))

    # --- Défilement Virtuel & Chargement des Cartes ---

    def _on_card_list_scrolled(self, value: int) -> None:
        scrollbar = self.card_table.verticalScrollBar()
        if scrollbar.maximum() > 0 and value >= int(scrollbar.maximum() * 0.85):
            self._load_next_card_batch()

    def _get_note_content_dynamic(self, note: NoteModel) -> Dict[str, str]:
        data = {}
        version = NoteVersionModel.get_or_none(note=note, is_active=True)
        if not version:
            version = NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.desc()).first()

        if version and version.content:
            try:
                parsed = json.loads(version.content)
                if isinstance(parsed, dict):
                    data = {str(k): str(v) for k, v in parsed.items()}
            except Exception as e:
                logger.warning("Erreur parsing contenu note pour rendu dynamique : %s", e)
        return data

    def _load_next_card_batch(self) -> None:
        """Alias de compatibilité (la virtualisation Qt gère le défilement et le fetchMore nativement)."""
        if self.note_table_model.canFetchMore():
            self.note_table_model.fetchMore()

    def refresh_data(self) -> None:
        self._current_note = None
        if hasattr(self, "editor_stack"):
            self.editor_stack.setCurrentIndex(0)
        if hasattr(self, "lbl_card_ribbon_info"):
            self.lbl_card_ribbon_info.setText("Aucune carte sélectionnée")

        try:
            query = NoteModel.select().order_by(NoteModel.id.asc())
            if self._active_folder_id is not None:
                from ankiforge.database.models import CardModel, DeckModel

                active_deck = DeckModel.get_or_none(DeckModel.id == self._active_folder_id)
                if active_deck:
                    deck_name = active_deck.name
                    descendant_decks = DeckModel.select(DeckModel.id).where((DeckModel.id == active_deck.id) | (DeckModel.name.startswith(f"{deck_name}::")))
                    deck_ids = [d.id for d in descendant_decks]
                    matching_note_ids = [c.note_id for c in CardModel.select(CardModel.note).where(CardModel.deck.in_(deck_ids))]
                    query = query.where(NoteModel.id.in_(matching_note_ids))
            for tag in self._active_tags:
                query = query.where(NoteModel.tags.contains(tag))
            if self._active_model_id is not None:
                query = query.where(NoteModel.note_type == self._active_model_id)

            self.note_table_model.set_filter_query(query, active_model_fields=self._current_table_fields)
            self._update_table_headers()

        except Exception as e:
            logger.warning("Erreur lors du rafraîchissement d'EditionView: %s", e)

    def select_note_by_id(self, note_id: int) -> None:
        try:
            row = self.note_table_model.find_row_by_note_id(note_id)
            if row >= 0:
                self.card_table.select_row(row)
                self._on_card_selected()
                return

            target_note = NoteModel.get_or_none(NoteModel.id == note_id)
            if target_note:
                self.note_table_model.prepend_note(target_note)
                self.card_table.select_row(0)
                self._on_card_selected()
        except Exception as e:
            logger.warning("Impossible de sélectionner la note %s: %s", note_id, e)

    def is_dirty(self) -> bool:
        return self._dirty

    def refresh_theme(self, profile: Any) -> None:
        """Rafraîchit à chaud les composants d'EditionView."""
        if hasattr(self, "card_preview") and hasattr(self.card_preview, "refresh_theme"):
            self.card_preview.refresh_theme(profile)

        if hasattr(self, "editor_placeholder"):
            self.editor_placeholder.setStyleSheet(f"background-color: {profile.bg_sidebar};")
        if hasattr(self, "placeholder_icon"):
            self.placeholder_icon.setPixmap(load_phosphor_icon("cards", color=profile.text_muted).pixmap(44, 44))
        if hasattr(self, "placeholder_title"):
            self.placeholder_title.setStyleSheet(f"color: {profile.text_primary}; font-size: 14px; font-weight: bold; border: none; background: transparent;")
        if hasattr(self, "placeholder_sub"):
            self.placeholder_sub.setStyleSheet(f"color: {profile.text_muted}; font-size: 12px; border: none; background: transparent;")

        if hasattr(self, "editor_container"):
            self.editor_container.setStyleSheet(f"background-color: {profile.bg_sidebar};")
        if hasattr(self, "fields_container"):
            self.fields_container.setStyleSheet(f"background-color: {profile.bg_sidebar};")

        # Rafraîchir les boutons de filtre dossiers & modèles
        if hasattr(self, "btn_open_folder"):
            is_active = self._active_folder_id is not None
            self.btn_open_folder.setIcon(load_phosphor_icon("folder" if is_active else "folders", color=profile.accent_primary if is_active else profile.text_secondary))
            if not is_active:
                self.btn_open_folder.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {profile.bg_panel};
                        border: 1px solid {profile.border_color};
                        border-radius: {profile.radius_sm}px;
                        padding: 4px 10px;
                        font-size: 11px;
                        font-weight: bold;
                        color: {profile.text_secondary};
                    }}
                    QPushButton:hover {{
                        background-color: {profile.bg_hover};
                    }}
                """)
            else:
                self.btn_open_folder.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {profile.bg_active};
                        border: 1px solid {profile.accent_primary};
                        border-radius: {profile.radius_sm}px;
                        padding: 4px 10px;
                        font-size: 11px;
                        font-weight: bold;
                        color: {profile.accent_primary};
                    }}
                """)

        if hasattr(self, "btn_open_model"):
            is_active = self._active_model_id is not None
            if not is_active:
                self.btn_open_model.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {profile.bg_panel};
                        border: 1px solid {profile.border_color};
                        border-radius: {profile.radius_sm}px;
                        padding: 4px 10px;
                        font-size: 11px;
                        font-weight: bold;
                        color: {profile.text_secondary};
                    }}
                    QPushButton:hover {{
                        background-color: {profile.bg_hover};
                    }}
                """)
            else:
                self.btn_open_model.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {profile.bg_active};
                        border: 1px solid {profile.accent_primary};
                        border-radius: {profile.radius_sm}px;
                        padding: 4px 10px;
                        font-size: 11px;
                        font-weight: bold;
                        color: {profile.accent_primary};
                    }}
                """)

        if hasattr(self, "_rebuild_tag_chips"):
            self._rebuild_tag_chips()

        for panel in self.findChildren(IdePanel):
            if hasattr(panel, "refresh_theme"):
                panel.refresh_theme(profile)

    def _open_import_dialog(self) -> None:
        """Ouvre le dialogue d'importation depuis la vue Édition."""
        from ankiforge.ui.dialogs.import_dialog import ImportDialog

        if hasattr(self, "_import_dialog") and self._import_dialog is not None and self._import_dialog.isVisible():
            self._import_dialog.raise_()
            self._import_dialog.activateWindow()
            return

        self._import_dialog = ImportDialog(parent=self)
        self._import_dialog.import_finished.connect(lambda _: self.refresh_data())
        self._import_dialog.show()
        self._import_dialog.raise_()
        self._import_dialog.activateWindow()

    def _open_export_dialog(self) -> None:
        """Ouvre le dialogue d'exportation depuis la vue Édition."""
        from ankiforge.ui.dialogs.export_dialog import ExportDialog

        if hasattr(self, "_export_dialog") and self._export_dialog is not None and self._export_dialog.isVisible():
            self._export_dialog.raise_()
            self._export_dialog.activateWindow()
            return

        self._export_dialog = ExportDialog(default_deck_id=self.current_folder_id, parent=self)
        self._export_dialog.show()
        self._export_dialog.raise_()
        self._export_dialog.activateWindow()


# Alias pour la rétrocompatibilité
EditionTab = EditionView
