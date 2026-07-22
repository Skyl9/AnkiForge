"""
Vue Édition / Analyse — 100% Conforme à la Maquette concept_ide + Raccordement Métier Avancé.
- Arborescence hiérarchique des sous-dossiers (QTreeWidget).
- Rendu ultra-rapide sans lag pour les grandes collections (>2000 cartes) via chargement virtuel par lots (Batching / Lazy Loading).
- Éditeur masqué par défaut si aucune carte n'est sélectionnée.
- Redimensionnement interactif libre de l'explorateur et de l'éditeur via QSplitter.
"""

import logging
import json
from typing import Optional, Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QLabel,
    QFrame,
    QListWidget,
    QListWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QFileDialog,
    QMessageBox,
    QProgressDialog,
    QInputDialog,
    QMenu,
)
from PySide6.QtCore import Qt, Signal, Slot, QSettings
from PySide6.QtGui import QFont, QAction

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.components.panels import IdePanel
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton, IconButton
from ankiforge.ui.components.inputs import GlowLineEdit, StyledTextEdit
from ankiforge.ui.components.badges import Badge
from ankiforge.utils.icon_loader import load_phosphor_icon

from ankiforge.database.models import NoteModel, NoteVersionModel, DeckModel, LLMConfigModel
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.cards.duplicate_manager import DuplicateManager
from ankiforge.services.cards.export_manager import ExportManager
from ankiforge.services.cards.store_manager import StoreManager
from ankiforge.services.workers.batch_edit_worker import BatchEditWorker
from ankiforge.services.workers.import_cards_worker import ImportCardsWorker

from ankiforge.ui.widgets.auto_tag_dialog import AutoTagDialog
from ankiforge.ui.widgets.batch_edit_dialog import BatchEditDialog
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.duplicate_resolver import DuplicateResolverDialog
from ankiforge.ui.widgets.linter_dialog import LinterDialog
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.ui.widgets.version_history_dialog import VersionHistoryDialog
from ankiforge.ui.dialogs.history_modal import HistoryModal
from ankiforge.ui.widgets.katex_editor import KaTeXHighlighter

logger = logging.getLogger(__name__)


class CardListItemWidget(QFrame):
    """Widget d'item de carte personnalisé conforme à la maquette concept_ide."""

    def __init__(self, note: NoteModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.note = note
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            CardListItemWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 0px;
            }}
            CardListItemWidget:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        # Rangée 1 : ID (tech font bleu) + Badge Carte n°1 / Status
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)

        id_lbl = QLabel(f"ID: {note.id}")
        id_font = QFont(DesignTokens.FONT_CODE, 11, QFont.Weight.Bold)
        id_lbl.setFont(id_font)
        id_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; border: none; background: transparent;")

        status = note.status or "new"
        variant_color = DesignTokens.COLOR_GREEN if status in ["new", "imported"] else DesignTokens.COLOR_YELLOW
        badge = Badge(f"Carte #{note.id}", variant="outline", color=variant_color)
        badge.setStyleSheet(f"""
            color: {variant_color};
            border: 1px solid rgba(16, 185, 129, 0.3);
            background-color: rgba(16, 185, 129, 0.15);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 600;
        """)

        row1.addWidget(id_lbl)
        row1.addStretch()
        row1.addWidget(badge)
        layout.addLayout(row1)

        # Rangée 2 : Type de note (icône swatches)
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(6)

        swatches_icon = QLabel()
        swatches_icon.setPixmap(load_phosphor_icon("swatches", color=DesignTokens.TEXT_MUTED).pixmap(14, 14))
        swatches_icon.setStyleSheet("border: none; background: transparent;")

        note_type_name = note.note_type.name if hasattr(note, "note_type") and note.note_type else "Informatique"
        type_lbl = QLabel(note_type_name)
        type_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 500; font-size: 12px; border: none; background: transparent;")

        row2.addWidget(swatches_icon)
        row2.addWidget(type_lbl)
        row2.addStretch()
        layout.addLayout(row2)

        # Rangée 3 : Dossier (icône folder)
        row3 = QHBoxLayout()
        row3.setContentsMargins(0, 0, 0, 0)
        row3.setSpacing(6)

        folder_icon = QLabel()
        folder_icon.setPixmap(load_phosphor_icon("folder", color=DesignTokens.TEXT_MUTED).pixmap(14, 14))
        folder_icon.setStyleSheet("border: none; background: transparent;")

        folder_name = "Par défaut"
        if hasattr(note, "cards") and note.cards.count() > 0:
            first_card = note.cards.first()
            if first_card and first_card.deck:
                folder_name = first_card.deck.name
        elif hasattr(note, "folder") and note.folder:
            folder_name = note.folder.name

        folder_lbl = QLabel(folder_name)
        folder_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")

        row3.addWidget(folder_icon)
        row3.addWidget(folder_lbl)
        row3.addStretch()
        layout.addLayout(row3)

        # Rangée 4 : Tags pills
        row4 = QHBoxLayout()
        row4.setContentsMargins(0, 4, 0, 0)
        row4.setSpacing(4)

        raw_tags = note.tags if hasattr(note, "tags") and note.tags else "Informatique"
        tags_list = [t.strip() for t in raw_tags.split(",") if t.strip()] if isinstance(raw_tags, str) else ["Informatique"]

        for tag in tags_list[:3]:
            tag_pill = QLabel(tag)
            tag_pill.setStyleSheet(f"""
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_SECONDARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            """)
            row4.addWidget(tag_pill)

        row4.addStretch()
        layout.addLayout(row4)


class ExplorateurDossiersTagsWidget(QWidget):
    """Panneau d'explorateur dossiers (QTreeWidget hiérarchique) et filtres par tags."""

    folder_selected = Signal(object)
    tag_selected = Signal(object)
    import_requested = Signal()
    export_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Actions de Collection (Import / Export) au-dessus des dossiers
        coll_toolbar = QHBoxLayout()
        coll_toolbar.setContentsMargins(0, 0, 0, 0)
        coll_toolbar.setSpacing(6)

        self.btn_import_collection = SecondaryButton("Importer")
        self.btn_import_collection.setIcon(load_phosphor_icon("download-simple", color=DesignTokens.TEXT_PRIMARY))
        self.btn_import_collection.setToolTip("Importer un paquet ou une collection (.apkg, .colpkg, .txt)")
        self.btn_import_collection.clicked.connect(self.import_requested.emit)

        self.btn_export_collection = SecondaryButton("Exporter")
        self.btn_export_collection.setIcon(load_phosphor_icon("export", color=DesignTokens.TEXT_PRIMARY))
        self.btn_export_collection.setToolTip("Exporter le paquet au format Anki (.apkg)")
        self.btn_export_collection.clicked.connect(self.export_requested.emit)

        coll_toolbar.addWidget(self.btn_import_collection, 1)
        coll_toolbar.addWidget(self.btn_export_collection, 1)
        layout.addLayout(coll_toolbar)

        # Section Dossiers Hiérarchique (QTreeWidget)
        self.folder_area = QWidget()
        folder_layout = QVBoxLayout(self.folder_area)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(4)

        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.setFrameShape(QFrame.Shape.NoFrame)
        self.folder_tree.setStyleSheet(f"""
            QTreeWidget {{
                background: transparent;
                border: none;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QTreeWidget::item {{
                padding: 4px 6px;
                border-radius: 4px;
            }}
            QTreeWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QTreeWidget::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
                font-weight: bold;
            }}
        """)
        self.folder_tree.itemClicked.connect(self._on_tree_item_clicked)

        folder_layout.addWidget(self.folder_tree)
        layout.addWidget(self.folder_area, 1)

        # Séparateur / En-tête Filtres Tags
        tags_header_layout = QHBoxLayout()
        tags_header_layout.setContentsMargins(0, 4, 0, 0)
        tags_header_layout.setSpacing(6)

        tag_icon = QLabel()
        tag_icon.setPixmap(load_phosphor_icon("tag", color=DesignTokens.COLOR_YELLOW).pixmap(14, 14))

        tags_hdr_lbl = QLabel("FILTRES (TAGS)")
        tags_hdr_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; border: none;")

        tags_header_layout.addWidget(tag_icon)
        tags_header_layout.addWidget(tags_hdr_lbl)
        tags_header_layout.addStretch()
        layout.addLayout(tags_header_layout)

        # Section Tags
        self.tag_list = QListWidget()
        self.tag_list.setFrameShape(QFrame.Shape.NoFrame)
        self.tag_list.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-radius: 6px;
                color: #94a3b8;
            }
            QListWidget::item:hover {
                background-color: #2d313a;
                color: #f8fafc;
            }
            QListWidget::item:selected {
                background-color: #2d313a;
                color: #f8fafc;
                font-weight: bold;
            }
        """)
        self.tag_list.itemClicked.connect(self._on_tag_clicked)
        layout.addWidget(self.tag_list, 1)

    def populate_folders(self, folders: list) -> None:
        """Construit l'arborescence hiérarchique des dossiers et sous-dossiers (::)."""
        self.folder_tree.clear()

        root_item = QTreeWidgetItem(self.folder_tree, ["Tous les dossiers"])
        root_item.setIcon(0, load_phosphor_icon("folder", color=DesignTokens.COLOR_BLUE))
        root_item.setData(0, Qt.ItemDataRole.UserRole, None)
        root_item.setExpanded(True)

        node_map: dict[str, QTreeWidgetItem] = {}

        for f in folders:
            full_name = getattr(f, "name", str(f))
            parts = [p.strip() for p in full_name.split("::") if p.strip()]
            current_parent = root_item
            path_accum = ""

            for idx, part in enumerate(parts):
                path_accum = f"{path_accum}::{part}" if path_accum else part
                if path_accum in node_map:
                    current_parent = node_map[path_accum]
                else:
                    item = QTreeWidgetItem(current_parent, [part])
                    item.setIcon(0, load_phosphor_icon("folder", color=DesignTokens.COLOR_BLUE))
                    # Storing folder ID on leaf / node
                    folder_id = getattr(f, "id", None) if idx == len(parts) - 1 else None
                    item.setData(0, Qt.ItemDataRole.UserRole, folder_id)
                    item.setExpanded(True)
                    node_map[path_accum] = item
                    current_parent = item

    def populate_tags(self, tags: list) -> None:
        self.tag_list.clear()
        all_item = QListWidgetItem("Tous les tags")
        all_item.setIcon(load_phosphor_icon("tag", color=DesignTokens.COLOR_YELLOW))
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        self.tag_list.addItem(all_item)

        for t in tags:
            item = QListWidgetItem(str(t))
            item.setIcon(load_phosphor_icon("tag", color=DesignTokens.COLOR_YELLOW))
            item.setData(Qt.ItemDataRole.UserRole, t)
            self.tag_list.addItem(item)

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        folder_id = item.data(0, Qt.ItemDataRole.UserRole)
        self.folder_selected.emit(folder_id)

    def _on_tag_clicked(self, item: QListWidgetItem) -> None:
        tag_name = item.data(Qt.ItemDataRole.UserRole)
        self.tag_selected.emit(tag_name)


class EditionView(QWidget):
    """
    Vue Édition / Analyse conformité 100% avec maquette concept_ide/index.html.
    Orchestration complète des opérations métiers Anki (Linter IA, Auto-Tag, Doublons, Édition par Lot, Versionnage).
    Optimisation pour >2000 cartes via chargement virtuel dynamique et fenêtre de prévisualisation rétractable.
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
        self._preview_device = "desktop"
        self._active_folder_id: Optional[int] = None
        self._active_tag: Optional[str] = None

        # Optimization state for large collections (>2000 cards)
        self._all_notes: list[NoteModel] = []
        self._displayed_count: int = 0

        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # QSplitter principal (Explorateur principal | Éditeur secondaire rétractable)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setStyleSheet("QSplitter::handle { background: transparent; }")
        main_layout.addWidget(self.main_splitter)

        # ==========================================
        # FENÊTRE PRINCIPALE : Explorateur & Liste des Cartes
        # ==========================================
        self.left_panel = IdePanel(detachable=True)
        self.left_panel.setMinimumWidth(320)

        left_content = QWidget()
        left_layout = QVBoxLayout(left_content)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Splitter vertical dans la colonne de gauche (Arborescence Dossiers 35% | Liste cartes Flex-1)
        self.col1_splitter = QSplitter(Qt.Orientation.Vertical)
        self.col1_splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {DesignTokens.BORDER_COLOR}; height: 1px; }}")

        # Haut : Explorateur hiérarchique dossiers & tags
        self.explorer_widget = ExplorateurDossiersTagsWidget()
        self.explorer_widget.import_requested.connect(self._on_import_collection)
        self.explorer_widget.export_requested.connect(self._on_export_collection)
        self.explorer_widget.folder_selected.connect(self._on_filter_folder)
        self.explorer_widget.tag_selected.connect(self._on_filter_tag)
        self.col1_splitter.addWidget(self.explorer_widget)

        # Bas : Recherche + Liste de cartes
        card_list_container = QWidget()
        card_list_layout = QVBoxLayout(card_list_container)
        card_list_layout.setContentsMargins(0, 0, 0, 0)
        card_list_layout.setSpacing(0)

        # Toolbar recherche
        search_toolbar = QWidget()
        search_toolbar.setStyleSheet(f"background-color: {DesignTokens.BG_SIDEBAR}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")
        search_layout = QHBoxLayout(search_toolbar)
        search_layout.setContentsMargins(10, 8, 10, 8)
        search_layout.setSpacing(8)

        self.search_input = GlowLineEdit()
        self.search_input.setPlaceholderText("Rechercher...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        search_layout.addWidget(self.search_input, 1)

        self.btn_filter = IconButton("funnel", tooltip="Filtres avancés", size=24)
        search_layout.addWidget(self.btn_filter)

        card_list_layout.addWidget(search_toolbar)

        # QListWidget pour les cartes avec chargement virtuel asynchrone par défilement
        self.card_list = QListWidget()
        self.card_list.setFrameShape(QFrame.Shape.NoFrame)
        self.card_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.card_list.customContextMenuRequested.connect(self._show_card_context_menu)
        self.card_list.verticalScrollBar().valueChanged.connect(self._on_card_list_scrolled)
        self.card_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_MAIN};
                border: none;
            }}
            QListWidget::item {{
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                padding: 0px;
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        self.card_list.itemClicked.connect(self._on_card_selected)
        card_list_layout.addWidget(self.card_list, 1)

        self.col1_splitter.addWidget(card_list_container)
        self.col1_splitter.setSizes([220, 480])
        self.col1_splitter.setCollapsible(0, True)
        self.col1_splitter.setCollapsible(1, False)

        left_layout.addWidget(self.col1_splitter)
        self.left_panel.add_tab("Explorateur", left_content, icon_name="ph.compass", closable=False)
        self.main_splitter.addWidget(self.left_panel)

        # ==========================================
        # FENÊTRE SECONDAIRE : Éditeur & Prévisualisation (Caché par défaut si pas de sélection)
        # ==========================================
        self.right_panel = IdePanel(detachable=True)
        self.right_panel.setMinimumWidth(380)

        # Boutons d'en-tête (Outillage Métier + Sauvegarder)
        self.btn_history = SecondaryButton("Historique")
        self.btn_history.setIcon(load_phosphor_icon("clock-counter-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_history.setToolTip("Machine à remonter le temps — Comparateur de versions")
        self.btn_history.clicked.connect(self._open_history_modal)

        self.btn_save = PrimaryButton("Sauvegarder")
        self.btn_save.setIcon(load_phosphor_icon("floppy-disk", color="white"))
        self.btn_save.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10b981, stop:1 #059669);
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: 600;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #059669, stop:1 #047857);
            }
        """)
        self.btn_save.clicked.connect(self._save_card)

        self.right_panel.add_header_widget(self.btn_history)
        self.right_panel.add_header_widget(self.btn_save)
        self.right_panel.add_header_separator()

        editor_content = QWidget()
        editor_content_layout = QVBoxLayout(editor_content)
        editor_content_layout.setContentsMargins(0, 0, 0, 0)
        editor_content_layout.setSpacing(0)

        # Splitter vertical entre Éditeur (Haut) et Prévisualisation (Bas)
        self.col2_splitter = QSplitter(Qt.Orientation.Vertical)
        self.col2_splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {DesignTokens.BORDER_COLOR}; height: 1px; }}")

        # --- Haut : Zone de saisie (Recto & Verso) ---
        fields_container = QWidget()
        fields_layout = QVBoxLayout(fields_container)
        fields_layout.setContentsMargins(16, 16, 16, 16)
        fields_layout.setSpacing(14)

        # Champ Recto
        recto_hdr = QHBoxLayout()
        recto_lbl = QLabel("RECTO")
        recto_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; border: none;")
        recto_hdr.addWidget(recto_lbl)
        recto_hdr.addStretch()

        self.btn_bold = IconButton("text-b", tooltip="Gras", size=24)
        self.btn_bold.clicked.connect(lambda: self._insert_format("**", "**"))
        self.btn_italic = IconButton("text-italic", tooltip="Italique", size=24)
        self.btn_italic.clicked.connect(lambda: self._insert_format("*", "*"))
        self.btn_code = IconButton("code", tooltip="Code", size=24)
        self.btn_code.clicked.connect(lambda: self._insert_format("`", "`"))

        recto_hdr.addWidget(self.btn_bold)
        recto_hdr.addWidget(self.btn_italic)
        recto_hdr.addWidget(self.btn_code)
        fields_layout.addLayout(recto_hdr)

        self.editor_recto = StyledTextEdit()
        self.editor_recto.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 12px;
                padding: 10px;
            }}
            QTextEdit:focus {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.editor_recto.setPlaceholderText("Entrez le recto de la carte (support Markdown, LaTeX & Cloze {{c1::...}})...")
        self.editor_recto.textChanged.connect(self._on_text_changed)
        self.recto_highlighter = KaTeXHighlighter(self.editor_recto.document())
        fields_layout.addWidget(self.editor_recto, 1)

        # Champ Verso
        verso_hdr = QHBoxLayout()
        verso_lbl = QLabel("VERSO")
        verso_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; border: none;")
        verso_hdr.addWidget(verso_lbl)
        verso_hdr.addStretch()
        fields_layout.addLayout(verso_hdr)

        self.editor_verso = StyledTextEdit()
        self.editor_verso.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 12px;
                padding: 10px;
            }}
            QTextEdit:focus {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.editor_verso.setPlaceholderText("Entrez le verso de la carte...")
        self.editor_verso.textChanged.connect(self._on_text_changed)
        self.verso_highlighter = KaTeXHighlighter(self.editor_verso.document())
        fields_layout.addWidget(self.editor_verso, 1)

        # Ligne de Tags
        tags_row = QHBoxLayout()
        tags_row.setContentsMargins(0, 4, 0, 0)
        tags_row.setSpacing(8)

        self.tag_pill = QLabel("Informatique")
        self.tag_pill.setStyleSheet(f"""
            background-color: {DesignTokens.BG_INPUT};
            color: {DesignTokens.TEXT_SECONDARY};
            border: 1px solid {DesignTokens.BORDER_COLOR};
            border-radius: 4px;
            padding: 4px 10px;
            font-size: 11px;
        """)
        tags_row.addWidget(self.tag_pill)

        self.btn_add_tag = IconButton("plus", tooltip="Ajouter un tag", size=24)
        self.btn_add_tag.clicked.connect(self._on_add_tag)
        tags_row.addWidget(self.btn_add_tag)
        tags_row.addStretch()

        fields_layout.addLayout(tags_row)
        self.col2_splitter.addWidget(fields_container)

        # --- Bas : Zone de prévisualisation live Anki WebEngine + MathJax ---
        preview_container = QWidget()
        preview_container.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; border-top: 1px solid {DesignTokens.BORDER_COLOR};")
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(12, 8, 12, 12)
        preview_layout.setSpacing(8)

        self.card_preview = CardPreviewWidget(show_header=True)
        preview_layout.addWidget(self.card_preview)

        self.col2_splitter.addWidget(preview_container)
        self.col2_splitter.setSizes([350, 350])
        self.col2_splitter.setCollapsible(0, False)
        self.col2_splitter.setCollapsible(1, False)

        editor_content_layout.addWidget(self.col2_splitter)

        self.right_panel.add_tab("Éditeur", editor_content, icon_name="ph.pencil-simple", closable=False)
        self.main_splitter.addWidget(self.right_panel)

        # 1. Éditeur masqué par défaut si aucune carte n'est sélectionnée
        self.right_panel.setVisible(False)

        # 2. Séparateurs entièrement redimensionnables par l'utilisateur
        self.main_splitter.setSizes([800, 0])
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, True)

    def _show_card_context_menu(self, pos) -> None:
        item = self.card_list.itemAt(pos)
        if not item:
            return
        note: Optional[NoteModel] = item.data(Qt.ItemDataRole.UserRole)
        if not note:
            return

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QMenu::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)

        act_approve = QAction("Approuver la note", self)
        act_approve.triggered.connect(lambda: self.approve_selected_notes([note.id]))
        menu.addAction(act_approve)

        act_reject = QAction("Rejeter / Supprimer la note", self)
        act_reject.triggered.connect(lambda: self.reject_selected_notes([note.id]))
        menu.addAction(act_reject)

        menu.addSeparator()

        act_linter = QAction("Linter IA", self)
        act_linter.triggered.connect(lambda: self.open_linter_dialog([note.id]))
        menu.addAction(act_linter)

        act_autotag = QAction("Auto-Tag IA", self)
        act_autotag.triggered.connect(lambda: self.open_auto_tag_dialog([note.id]))
        menu.addAction(act_autotag)

        act_batch = QAction("Édition IA par Lot", self)
        act_batch.triggered.connect(lambda: self.open_batch_edit_dialog([note.id]))
        menu.addAction(act_batch)

        act_history = QAction("Historique des versions", self)
        act_history.triggered.connect(lambda: self.show_version_history(note.id))
        menu.addAction(act_history)

        menu.exec(self.card_list.mapToGlobal(pos))

    def _on_filter_folder(self, folder_id: Optional[int]) -> None:
        self._active_folder_id = folder_id
        self.refresh_data()

    def _on_filter_tag(self, tag_name: Optional[str]) -> None:
        self._active_tag = tag_name
        self.refresh_data()

    def _on_add_tag(self) -> None:
        if not self._current_note:
            return
        tag_name, ok = QInputDialog.getText(self, "Nouveau Tag", "Entrez le nom du tag:")
        if ok and tag_name.strip():
            t = tag_name.strip()
            existing = [x.strip() for x in (self._current_note.tags or "").split(",") if x.strip()]
            if t not in existing:
                existing.append(t)
                self._current_note.tags = ", ".join(existing)
                self._current_note.save()
                self.tag_pill.setText(self._current_note.tags)
                self.refresh_data()

    def _on_card_selected(self, item: QListWidgetItem) -> None:
        note: Optional[NoteModel] = item.data(Qt.ItemDataRole.UserRole)
        if not note:
            return
        self._current_note = note

        # Afficher le panneau d'édition lors de la sélection
        if not self.right_panel.isVisible():
            self.right_panel.setVisible(True)
            self.main_splitter.setSizes([450, 750])

        # Update tab title
        self.right_panel.set_tab_text(0, f"Éditeur (ID: {note.id})")
        self.tag_pill.setText(note.tags if note.tags else "Informatique")

        recto = ""
        verso = ""

        # Query active version or most recent version
        version = NoteVersionModel.get_or_none(note=note, is_active=True)
        if not version:
            version = NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.desc()).first()

        if version and version.content:
            try:
                data = json.loads(version.content)
                if isinstance(data, dict):
                    # Flexible lookup matching any field schema (Front, Back, Question, Answer, Text, Extra, Field_1, etc.)
                    for k, v in data.items():
                        k_lower = str(k).lower()
                        if k_lower in ["front", "recto", "question", "text", "texte", "field_1"] and not recto:
                            recto = str(v)
                        elif k_lower in ["back", "verso", "answer", "réponse", "reponse", "extra", "field_2"] and not verso:
                            verso = str(v)

                    # Fallback: 1st field = Recto, 2nd field = Verso
                    if not recto and len(data) > 0:
                        vals = list(data.values())
                        recto = str(vals[0]) if len(vals) > 0 else ""
                        verso = str(vals[1]) if len(vals) > 1 else ""
                else:
                    recto = str(data)
            except Exception:
                recto = version.content

        if not recto and not verso:
            recto = f"Carte #{note.id}"
            verso = ""

        self.editor_recto.setPlainText(recto)
        self.editor_verso.setPlainText(verso)
        self._update_preview()
        self._dirty = False

    def _on_text_changed(self) -> None:
        self._dirty = True
        self._update_preview()

    def _update_preview(self) -> None:
        recto_text = self.editor_recto.toPlainText()
        verso_text = self.editor_verso.toPlainText()

        note_type = getattr(self._current_note, "note_type", None) if self._current_note else None
        fields_dict: dict[str, str] = {
            "Front": recto_text,
            "Back": verso_text,
            "front": recto_text,
            "back": verso_text,
            "Question": recto_text,
            "Answer": verso_text,
            "Text": recto_text,
            "Extra": verso_text,
            "Field_1": recto_text,
            "Field_2": verso_text,
        }

        if self._current_note:
            version = NoteVersionModel.get_or_none(note=self._current_note, is_active=True)
            if version and version.content:
                try:
                    v_data = json.loads(version.content)
                    if isinstance(v_data, dict):
                        for k, v in v_data.items():
                            fields_dict[str(k)] = str(v)
                except Exception:
                    pass  # nosec B110

        # Override with current live editor changes
        fields_dict["Front"] = recto_text
        fields_dict["Back"] = verso_text
        fields_dict["front"] = recto_text
        fields_dict["back"] = verso_text

        override_templates = None
        if not note_type or not getattr(note_type, "templates", None):
            override_templates = [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}]

        self.card_preview.update_preview(
            note_type=note_type,
            fields_dict=fields_dict,
            override_templates=override_templates,
        )

    def _insert_format(self, prefix: str, suffix: str) -> None:
        cursor = self.editor_recto.textCursor()
        selected = cursor.selectedText()
        cursor.insertText(f"{prefix}{selected}{suffix}")

    def _on_search_text_changed(self, text: str) -> None:
        text = text.lower()
        for i in range(self.card_list.count()):
            item = self.card_list.item(i)
            note = item.data(Qt.ItemDataRole.UserRole)
            if note:
                match = text in str(note.id).lower() or text in (note.tags or "").lower()
                item.setHidden(not match)

    def _open_history_modal(self) -> None:
        if self._current_note:
            modal = HistoryModal(self._current_note, self)
            modal.exec()

    @Slot()
    def _run_linter(self) -> None:
        if self._current_note:
            self.open_linter_dialog([self._current_note.id])

    @Slot()
    def _save_card(self) -> None:
        if not self._current_note:
            return

        try:
            new_content = {"front": self.editor_recto.toPlainText(), "back": self.editor_verso.toPlainText()}
            self._current_note.add_version(new_content, source="manual")
            self._dirty = False
            self.refresh_data()
            show_toast(self, f"Carte #{self._current_note.id} sauvegardée avec succès.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Impossible de sauvegarder la carte : {str(e)}")

    @Slot(list)
    def open_linter_dialog(self, note_ids: list[int]) -> None:
        if not note_ids:
            return
        dialog = LinterDialog(note_ids, self)
        dialog.exec()
        self.refresh_data()

    @Slot(list)
    def open_auto_tag_dialog(self, note_ids: list[int]) -> None:
        if not note_ids:
            return
        if AutoTagDialog(self, note_ids).exec():
            show_toast(self, "Auto-Tagging terminé avec succès !")
            self.refresh_data()

    @Slot(list)
    def open_batch_edit_dialog(self, note_ids: list[int]) -> None:
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

    @Slot(int)
    def show_version_history(self, note_id: int) -> None:
        try:
            note = NoteModel.get_by_id(note_id)
            if VersionHistoryDialog(note, self).exec():
                self.refresh_data()
        except Exception:
            self._open_history_modal()

    @Slot(list)
    def approve_selected_notes(self, note_ids: list[int]) -> None:
        try:
            self.store.approve_notes(note_ids)
            show_toast(self, f"{len(note_ids)} note(s) approuvée(s) !")
            self.refresh_data()
        except Exception as e:
            logger.exception("Erreur lors de l'approbation des notes")
            QMessageBox.critical(self, "Erreur", str(e))

    @Slot(list)
    def reject_selected_notes(self, note_ids: list[int]) -> None:
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

    def _on_import_collection(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Importer une collection ou paquet Anki", "", "Fichiers Anki (*.apkg *.colpkg *.txt);;Tous les fichiers (*)")
        if not file_path:
            return

        self.progress_dialog = QProgressDialog("Importation en cours...", "Annuler", 0, 0, self)
        self.progress_dialog.show()

        self.import_thread = ImportCardsWorker(self.store, file_path)
        self.import_thread.progress.connect(self.progress_dialog.setLabelText)
        self.import_thread.finished_signal.connect(self._on_import_success)
        self.import_thread.error_signal.connect(self._on_import_error)
        self.import_thread.start()

    def _on_import_success(self) -> None:
        if self.progress_dialog:
            self.progress_dialog.close()
        show_toast(self, "Paquet importé avec succès !")
        self.refresh_data()

    def _on_import_error(self, error_msg: str) -> None:
        if self.progress_dialog:
            self.progress_dialog.close()
        QMessageBox.critical(self, "Erreur d'import", error_msg)

    def _on_export_collection(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(self, "Exporter la collection Anki", "AnkiForge_Collection.apkg", "Paquet Anki (*.apkg)")
        if not file_path:
            return
        try:
            decks = list(DeckModel.select())
            if not decks:
                QMessageBox.warning(self, "Export impossible", "Aucun paquet trouvé dans la collection.")
                return
            ExportManager().export_deck(decks[0].id, file_path)
            show_toast(self, "Export terminé avec succès !")
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'export", f"Erreur lors de l'export : {str(e)}")

    def _on_card_list_scrolled(self, value: int) -> None:
        scrollbar = self.card_list.verticalScrollBar()
        if scrollbar.maximum() > 0 and value >= int(scrollbar.maximum() * 0.85):
            self._load_next_card_batch()

    def _load_next_card_batch(self) -> None:
        if self._displayed_count >= len(self._all_notes):
            return

        next_batch = self._all_notes[self._displayed_count : self._displayed_count + self.BATCH_SIZE]
        for note in next_batch:
            item = QListWidgetItem()
            widget = CardListItemWidget(note)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, note)
            self.card_list.addItem(item)
            self.card_list.setItemWidget(item, widget)

        self._displayed_count += len(next_batch)

    def refresh_data(self) -> None:
        self.card_list.clear()
        self._all_notes = []
        self._displayed_count = 0

        # Masquer l'éditeur par défaut s'il n'y a pas de sélection active
        self._current_note = None
        self.right_panel.setVisible(False)

        try:
            # Populate explorer decks/folders (Hierarchical Tree from DeckModel)
            decks = list(DeckModel.select())
            self.explorer_widget.populate_folders(decks)

            # Collect unique tags
            notes_sample = list(NoteModel.select())
            tags_set = set()
            for n in notes_sample:
                if n.tags:
                    for t in n.tags.split(","):
                        if t.strip():
                            tags_set.add(t.strip())
            self.explorer_widget.populate_tags(sorted(list(tags_set)))

            # Query notes according to filters
            query = NoteModel.select()
            if self._active_folder_id is not None:
                from ankiforge.database.models import CardModel

                matching_note_ids = [c.note_id for c in CardModel.select(CardModel.note).where(CardModel.deck == self._active_folder_id)]
                query = query.where(NoteModel.id.in_(matching_note_ids))
            if self._active_tag is not None:
                query = query.where(NoteModel.tags.contains(self._active_tag))

            self._all_notes = list(query)
            self._load_next_card_batch()

        except Exception:
            pass  # nosec B110

    def is_dirty(self) -> bool:
        return self._dirty


# Alias pour la rétrocompatibilité
EditionTab = EditionView
