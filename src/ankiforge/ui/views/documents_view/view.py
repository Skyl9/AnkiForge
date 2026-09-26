import logging
import pathlib
from typing import Any

from peewee import fn
from PySide6.QtCore import QPoint, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    DocumentPageModel,
    FolderModel,
    NoteChunkLinkModel,
)
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.services.ai.rag_service import RAGService
from ankiforge.services.markdown import FormatOptions, MarkdownFormatter, MarkdownStructurer
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.services.parsing.document_parser import DocumentParser
from ankiforge.services.parsing.marker_service import MarkerService
from ankiforge.services.reindex_service import mark_document_version
from ankiforge.services.workers.coverage_worker import CoverageWorker
from ankiforge.services.workers.document_worker import DocumentWorker
from ankiforge.ui.components import (
    Badge,
    GlowLineEdit,
    IconButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
)
from ankiforge.ui.dialogs.url_import_dialog import UrlImportDialog
from ankiforge.ui.dispatch import run_on_owner_thread
from ankiforge.ui.theme import DesignTokens, StyledMenu
from ankiforge.ui.views.documents_view.dialogs import (
    AIDocumentStructureDialog,
    AlbumImportDialog,
    DocumentDelimitationDialog,
    FolderCreateDialog,
    RAGTestDialog,
)
from ankiforge.ui.views.documents_view.dialogs.rag_test_dialog import _RAGResultWidget
from ankiforge.ui.views.documents_view.utils import apply_pill_style
from ankiforge.ui.views.documents_view.widgets import (
    AlbumViewerWidget,
    DocumentTreeWidget,
)
from ankiforge.ui.widgets.document_outline import DocumentOutlineWidget
from ankiforge.ui.widgets.katex_editor import KaTeXEditor
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.event_bus import CoverageSyncedEvent, event_bus
from ankiforge.utils.hierarchy import descendants_prefix, descends_from, join_hierarchy, leaf_name, split_hierarchy
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon
from ankiforge.utils.logger import log_and_notify_error

logger = logging.getLogger(__name__)


class MarkerInstallerWorker(QThread):
    """Installe Marker OCR dans le répertoire persistant de l'utilisateur."""

    progress = Signal(str)
    installed = Signal(str)
    failed = Signal(str)

    def run(self) -> None:
        try:
            executable = MarkerService.install(progress_callback=self.progress.emit)
            self.installed.emit(str(executable))
        except Exception as error:
            logger.exception("Installation de Marker OCR échouée : %s", error)
            self.failed.emit(str(error))


class DocumentsView(QWidget):
    """
    Vue My Documents / Library — 100% Conforme au Design System AnkiForge.
    """

    request_navigation = Signal(str, object)

    def __init__(
        self,
        ai_manager: Any | None = None,
        profile_name: str | None = None,
        parent: QWidget | None = None,
        doc_repo: DocumentRepository | None = None,
    ) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.profile_name = profile_name
        self.doc_repo = doc_repo or DocumentRepository()
        self._current_doc_id: int | None = None
        self._dirty = False
        self.worker: DocumentWorker | None = None
        self._coverage_worker: CoverageWorker | None = None
        self._outline_debounce_timer = QTimer(self)
        self._outline_debounce_timer.setSingleShot(True)
        self._outline_debounce_timer.setInterval(400)
        self._outline_debounce_timer.timeout.connect(self._update_outline)

        self._cursor_spy_timer = QTimer(self)
        self._cursor_spy_timer.setSingleShot(True)
        self._cursor_spy_timer.setInterval(100)
        self._cursor_spy_timer.timeout.connect(self._sync_active_line_to_outline)

        self._coverage_refresh_timer = QTimer(self)
        self._coverage_refresh_timer.setSingleShot(True)
        self._coverage_refresh_timer.setInterval(250)
        self._coverage_refresh_timer.timeout.connect(self._on_coverage_refresh_trigger)
        self._coverage_fingerprint: tuple[int, int] | None = None

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # ── 1. Panneau Gauche : Explorateur de Documents ──────────────────────
        self.explorer_panel = IdePanel(detachable=True)
        self.explorer_panel.setMinimumWidth(300)
        self.explorer_panel.setMaximumWidth(360)

        explorer_content = QWidget()
        explorer_layout = QVBoxLayout(explorer_content)
        explorer_layout.setContentsMargins(8, 8, 8, 8)
        explorer_layout.setSpacing(8)

        # Barre d'outils supérieure
        explorer_toolbar = QHBoxLayout()
        explorer_toolbar.setSpacing(6)

        self.btn_import = SecondaryButton("Importer", tooltip="Importer un fichier local (PDF, Markdown, Texte, .apkg)")
        self.btn_import.setIcon(load_phosphor_icon("ph.upload-simple", color=DesignTokens.TEXT_PRIMARY))
        self.btn_import.setMinimumWidth(96)
        self.btn_import.setFixedHeight(30)
        self.btn_import.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.btn_import.clicked.connect(self._on_import_file)

        self.btn_import_url = IconButton("ph.link", tooltip="Importer depuis le Web / YouTube", size=24)
        self.btn_import_url.clicked.connect(self._on_import_url)

        self.btn_new_album = IconButton("ph.images", tooltip="Créer un Album d'images", size=24)
        self.btn_new_album.clicked.connect(self._on_new_album)

        self.btn_new_folder = IconButton("ph.folder-plus", tooltip="Nouveau dossier", size=24)
        self.btn_new_folder.clicked.connect(self._on_new_folder)

        self.btn_delete = IconButton("ph.trash", tooltip="Supprimer", size=24)
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._on_delete_item)

        self.btn_copy_profile = IconButton("ph.arrows-left-right", tooltip="Importer des documents depuis un autre profil", size=24)
        self.btn_copy_profile.clicked.connect(self._on_import_from_other_profile)

        explorer_toolbar.addWidget(self.btn_import, 1)
        explorer_toolbar.addWidget(self.btn_import_url)
        explorer_toolbar.addWidget(self.btn_copy_profile)
        explorer_toolbar.addWidget(self.btn_new_album)
        explorer_toolbar.addWidget(self.btn_new_folder)
        explorer_toolbar.addWidget(self.btn_delete)
        explorer_layout.addLayout(explorer_toolbar)

        # Champ de recherche dynamique
        self.doc_search_input = GlowLineEdit()
        self.doc_search_input.setPlaceholderText("Rechercher un document...")
        self.doc_search_input.textChanged.connect(self._on_search_filter_changed)
        explorer_layout.addWidget(self.doc_search_input)

        # Tree Widget
        self.tree_explorer = DocumentTreeWidget()
        self.tree_explorer.setHeaderHidden(True)
        self.tree_explorer.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_explorer.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 4px;
            }}
            QTreeWidget::item {{
                padding: 6px;
                border-radius: 4px;
            }}
            QTreeWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QTreeWidget::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        explorer_layout.addWidget(self.tree_explorer, 1)

        self.explorer_panel.add_tab("Documents", explorer_content, "ph.files", closable=False)
        self.main_splitter.addWidget(self.explorer_panel)

        # ── 2. Panneau Central : Éditeur & Lecteur de Document ────────────────
        self.editor_panel = IdePanel(detachable=True)
        self.editor_stack = QStackedWidget()

        # PAGE 0 : État vide
        empty_page = QWidget()
        empty_layout = QVBoxLayout(empty_page)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(12)

        empty_icon = QLabel()
        empty_icon.setPixmap(load_phosphor_icon("ph.files", color=DesignTokens.TEXT_MUTED).pixmap(56, 56))
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_title = QLabel("Aucun document sélectionné")
        empty_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 16px; font-weight: bold;")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_subtitle = QLabel("Choisissez un document dans l'explorateur à gauche ou importez un nouveau support de cours (PDF, Markdown, Word, Page Web).")
        empty_subtitle.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px;")
        empty_subtitle.setWordWrap(True)
        empty_subtitle.setMaximumWidth(440)
        empty_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_layout.addWidget(empty_icon)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_subtitle)

        empty_actions = QHBoxLayout()
        empty_actions.setSpacing(10)
        btn_quick_import = PrimaryButton("Importer un fichier", tooltip="Parcourir vos fichiers locaux pour importer un document")
        btn_quick_import.setIcon(load_on_accent_icon("ph.upload-simple"))
        btn_quick_import.clicked.connect(self._on_import_file)

        btn_quick_url = SecondaryButton("Importer depuis le Web", tooltip="Importer du contenu depuis une URL Web ou une vidéo YouTube")
        btn_quick_url.setIcon(load_phosphor_icon("ph.link", color=DesignTokens.TEXT_PRIMARY))
        btn_quick_url.clicked.connect(self._on_import_url)

        btn_quick_album = SecondaryButton("Créer un album", tooltip="Créer un album d'images à annoter ou occlure")
        btn_quick_album.setIcon(load_phosphor_icon("ph.images", color=DesignTokens.COLOR_PURPLE))
        btn_quick_album.clicked.connect(self._on_new_album)

        empty_actions.addWidget(btn_quick_import)
        empty_actions.addWidget(btn_quick_url)
        empty_actions.addWidget(btn_quick_album)
        empty_layout.addLayout(empty_actions)

        self.editor_stack.addWidget(empty_page)

        # PAGE 1 : Conteneur Éditeur
        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        # Toolbar du document
        doc_header_card = QFrame()
        doc_header_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        header_main_layout = QVBoxLayout(doc_header_card)
        header_main_layout.setContentsMargins(10, 8, 10, 8)
        header_main_layout.setSpacing(6)

        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(8)

        self.doc_title_lbl = QLabel("Sélectionnez un document")
        self.doc_title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 15px; font-weight: bold;")
        row1.addWidget(self.doc_title_lbl, 1)

        self.lbl_word_count = QLabel("0 mots")
        self.lbl_word_count.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px;")
        row1.addWidget(self.lbl_word_count)

        self.rag_status_pill = Badge("Non indexé", variant="status")
        apply_pill_style(self.rag_status_pill, DesignTokens.TEXT_MUTED)
        row1.addWidget(self.rag_status_pill)

        self.btn_save = PrimaryButton("Sauvegarder", tooltip="Enregistrer les modifications textuelles du document (Ctrl+S)")
        self.btn_save.setIcon(load_on_accent_icon("ph.floppy-disk"))
        self.btn_save.setFixedHeight(28)
        self.btn_save.setStyleSheet("font-size: 11px; padding: 4px 10px;")
        self.btn_save.clicked.connect(self._on_save_document)
        row1.addWidget(self.btn_save)

        header_main_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(6)

        self.view_toggle_frame = QFrame()
        self.view_toggle_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 12px;
            }}
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {DesignTokens.TEXT_MUTED};
                font-weight: 600;
                border-radius: 10px;
                padding: 3px 8px;
                font-size: 11px;
            }}
            QPushButton:checked {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                color: white;
            }}
        """)
        toggle_layout = QHBoxLayout(self.view_toggle_frame)
        toggle_layout.setContentsMargins(2, 2, 2, 2)
        toggle_layout.setSpacing(1)

        self.btn_view_pdf = QPushButton("PDF")
        self.btn_view_pdf.setToolTip("Afficher le visualiseur PDF haute définition")
        self.btn_view_pdf.setIcon(load_phosphor_icon("ph.file-pdf", color=DesignTokens.COLOR_RED))
        self.btn_view_pdf.setCheckable(True)
        self.btn_view_pdf.setChecked(True)

        self.btn_view_md = QPushButton("MD")
        self.btn_view_md.setToolTip("Afficher et éditer le texte Markdown extrait")
        self.btn_view_md.setIcon(load_phosphor_icon("ph.markdown-logo", color=DesignTokens.COLOR_YELLOW))
        self.btn_view_md.setCheckable(True)

        self.btn_view_term = QPushButton("Logs")
        self.btn_view_term.setToolTip("Afficher la console des journaux d'extraction")
        self.btn_view_term.setIcon(load_phosphor_icon("ph.terminal-window", color=DesignTokens.COLOR_BLUE))
        self.btn_view_term.setCheckable(True)

        toggle_layout.addWidget(self.btn_view_pdf)
        toggle_layout.addWidget(self.btn_view_md)
        toggle_layout.addWidget(self.btn_view_term)

        self.btn_view_pdf.clicked.connect(lambda: self._on_view_toggled("pdf"))
        self.btn_view_md.clicked.connect(lambda: self._on_view_toggled("md"))
        self.btn_view_term.clicked.connect(lambda: self._on_view_toggled("term"))

        row2.addWidget(self.view_toggle_frame)
        row2.addStretch()

        self.btn_format_md = SecondaryButton("🪄 Formater")
        self.btn_format_md.setIcon(load_phosphor_icon("ph.sparkle", color=DesignTokens.ACCENT_PRIMARY))
        self.btn_format_md.setToolTip("Nettoyer, normaliser et formater le Markdown (césures OCR, KaTeX, tables GFM)")
        self.btn_format_md.setFixedHeight(26)
        self.btn_format_md.setStyleSheet(f"font-size: 11px; padding: 2px 8px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self._setup_format_menu()
        row2.addWidget(self.btn_format_md)

        self.btn_ai_structure = SecondaryButton("🤖 Structurer IA")
        self.btn_ai_structure.setIcon(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_PURPLE))
        self.btn_ai_structure.setToolTip("Transformer cette retranscription ou ce texte brut en cours structuré par IA")
        self.btn_ai_structure.setFixedHeight(26)
        self.btn_ai_structure.setStyleSheet(f"font-size: 11px; padding: 2px 8px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_ai_structure.clicked.connect(self._on_open_ai_structure_dialog)
        row2.addWidget(self.btn_ai_structure)

        self.btn_delimit = SecondaryButton("Délimiter les pages")
        self.btn_delimit.setIcon(load_phosphor_icon("ph.scissors", color=DesignTokens.SYNTAX_TAG))
        self.btn_delimit.setToolTip("Sélectionner les pages et chapitres utiles avant la forge et le RAG")
        self.btn_delimit.setFixedHeight(26)
        self.btn_delimit.setStyleSheet(f"font-size: 11px; padding: 2px 8px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_delimit.clicked.connect(self._on_open_delimitation_dialog)
        row2.addWidget(self.btn_delimit)

        self.btn_marker = SecondaryButton("Marker OCR")
        self.btn_marker.setIcon(load_phosphor_icon("ph.magic-wand", color=DesignTokens.COLOR_PURPLE))
        self.btn_marker.setToolTip("Extraction Deep Learning PDF vers Markdown KaTeX via Marker")
        self.btn_marker.setFixedHeight(26)
        self.btn_marker.setStyleSheet(f"font-size: 11px; padding: 2px 8px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_marker.clicked.connect(self._on_run_marker_analysis)
        self.btn_marker.hide()
        row2.addWidget(self.btn_marker)

        self.btn_rag = SecondaryButton("Indexer (RAG)")
        self.btn_rag.setIcon(load_phosphor_icon("ph.database", color=DesignTokens.COLOR_GREEN))
        self.btn_rag.setToolTip("Indexer ce document pour la recherche sémantique IA (FAISS & BM25)")
        self.btn_rag.setFixedHeight(26)
        self.btn_rag.setStyleSheet(f"font-size: 11px; padding: 2px 8px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_rag.clicked.connect(self._on_vectorize_rag)
        row2.addWidget(self.btn_rag)

        self.btn_test_rag = IconButton("ph.magnifying-glass", tooltip="Recherche sémantique instantanée", size=22)
        self.btn_test_rag.clicked.connect(self._on_open_rag_test_dialog)
        row2.addWidget(self.btn_test_rag)

        header_main_layout.addLayout(row2)
        editor_layout.addWidget(doc_header_card)

        from ankiforge.ui.views.documents_view.widgets.audio_player import AudioPlayerWidget

        self.audio_player = AudioPlayerWidget()
        self.audio_player.hide()
        editor_layout.addWidget(self.audio_player)

        self.inner_editor_stack = QStackedWidget()

        try:
            from PySide6.QtPdf import QPdfDocument
            from PySide6.QtPdfWidgets import QPdfView

            self.pdf_document = QPdfDocument(self)
            self.pdf_viewer = QPdfView()
            self.pdf_viewer.setDocument(self.pdf_document)
            self.pdf_viewer.setPageMode(QPdfView.PageMode.MultiPage)
            self.inner_editor_stack.addWidget(self.pdf_viewer)
        except ImportError:
            self.pdf_viewer = QWidget()
            self.inner_editor_stack.addWidget(self.pdf_viewer)

        self.text_editor = KaTeXEditor()
        self.text_editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if hasattr(self.text_editor, "editor"):
            self.text_editor.editor.setReadOnly(False)
        self.inner_editor_stack.addWidget(self.text_editor)

        self.terminal_view = QTextBrowser()
        self.terminal_view.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.ACCENT_PRIMARY};
                font-family: '{DesignTokens.FONT_CODE}';
                padding: 12px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        self.inner_editor_stack.addWidget(self.terminal_view)
        editor_layout.addWidget(self.inner_editor_stack, 1)

        self.editor_stack.addWidget(editor_container)

        # PAGE 2 : Album Viewer
        self.album_viewer = AlbumViewerWidget()
        self.album_viewer.album_modified.connect(self._on_album_modified)
        self.album_viewer.forge_requested.connect(self._on_album_forge_requested)
        self.album_viewer.visual_rag_requested.connect(self._on_vectorize_rag)
        self.album_viewer.search_rag_requested.connect(self._on_open_rag_test_dialog)
        self.editor_stack.addWidget(self.album_viewer)

        self.editor_panel.add_tab("Éditeur", self.editor_stack, "ph.file-text", closable=False)
        self.main_splitter.addWidget(self.editor_panel)

        # ── 3. Panneau Droit : Sommaire, Couverture & Sandbox RAG ──────────────
        self.coverage_panel = IdePanel(detachable=True)
        self.coverage_panel.setMinimumWidth(250)
        self.coverage_panel.setMaximumWidth(320)

        # --- TAB 1: Sommaire & Couverture SRS ---
        coverage_content = QWidget()
        cov_layout = QVBoxLayout(coverage_content)
        cov_layout.setContentsMargins(10, 10, 10, 10)
        cov_layout.setSpacing(10)

        self.coverage_card = QFrame()
        self.coverage_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        cov_card_layout = QVBoxLayout(self.coverage_card)
        cov_card_layout.setContentsMargins(12, 10, 12, 10)
        cov_card_layout.setSpacing(6)

        self.lbl_coverage_summary = QLabel("📊 Couverture : 0%")
        self.lbl_coverage_summary.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 13px;")
        cov_card_layout.addWidget(self.lbl_coverage_summary)

        self.coverage_bar = QProgressBar()
        self.coverage_bar.setRange(0, 100)
        self.coverage_bar.setValue(0)
        self.coverage_bar.setTextVisible(False)
        self.coverage_bar.setFixedHeight(8)
        self.coverage_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {DesignTokens.COLOR_GREEN};
                border-radius: 3px;
            }}
        """)
        cov_card_layout.addWidget(self.coverage_bar)

        self.lbl_coverage_details = QLabel("0 sections analysées • 0 cartes liées")
        self.lbl_coverage_details.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px;")
        cov_card_layout.addWidget(self.lbl_coverage_details)

        self.btn_align_cards = SecondaryButton("Synchroniser les cartes")
        self.btn_align_cards.setIcon(load_phosphor_icon("ph.link", color=DesignTokens.COLOR_BLUE))
        self.btn_align_cards.setToolTip("Associer les fiches portant les tags de traçabilité (doc:/source:/page:/section:) aux sections de ce document")
        self.btn_align_cards.setFixedHeight(24)
        self.btn_align_cards.setStyleSheet(f"font-size: 10px; padding: 2px 6px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_align_cards.clicked.connect(self._on_smart_align_document)
        cov_card_layout.addWidget(self.btn_align_cards)

        cov_layout.addWidget(self.coverage_card)

        self.chapters_filter = QComboBox()
        self.chapters_filter.addItems(["Toutes les sections", "Couvertes", "Non couvertes"])
        self.chapters_filter.setFixedHeight(24)
        self.chapters_filter.setToolTip("Filtrer les sections selon leur état de couverture")
        self.chapters_filter.setStyleSheet(f"""
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 2px 8px;
                font-size: 10px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 18px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                selection-background-color: {DesignTokens.BG_HOVER};
                selection-color: {DesignTokens.TEXT_PRIMARY};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self.chapters_filter.currentIndexChanged.connect(self._apply_chapters_filter)
        cov_layout.addWidget(self.chapters_filter)

        self.chapters_list = QListWidget()
        self.chapters_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                font-size: 11px;
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        cov_layout.addWidget(self.chapters_list, 1)
        self.chapters_list.itemClicked.connect(self._on_chapter_clicked)

        self.btn_forge_chapter = PrimaryButton("⚡ Forger la section", tooltip="Envoyer cette section dans le Studio de Création pour générer des cartes")
        self.btn_forge_chapter.clicked.connect(self._on_forge_selected_chapter)
        cov_layout.addWidget(self.btn_forge_chapter)

        self.coverage_panel.add_tab("Sommaire", coverage_content, "ph.list-checks", closable=False)

        # --- TAB 2: Bac à Sable RAG ---
        rag_sandbox_content = QWidget()
        rag_layout = QVBoxLayout(rag_sandbox_content)
        rag_layout.setContentsMargins(10, 10, 10, 10)
        rag_layout.setSpacing(8)

        lbl_rag_desc = QLabel("Recherche Sémantique FAISS")
        lbl_rag_desc.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: bold; font-size: 11px; letter-spacing: 0.5px;")
        rag_layout.addWidget(lbl_rag_desc)

        rag_search_row = QHBoxLayout()
        self.rag_sandbox_input = GlowLineEdit()
        self.rag_sandbox_input.setPlaceholderText("Poser une question au document...")
        self.rag_sandbox_input.returnPressed.connect(self._on_sandbox_search)

        self.btn_sandbox_search = PrimaryButton("", tooltip="Lancer la recherche sémantique multimodale dans FAISS")
        self.btn_sandbox_search.setIcon(load_on_accent_icon("ph.magnifying-glass"))
        self.btn_sandbox_search.setFixedWidth(36)
        self.btn_sandbox_search.clicked.connect(self._on_sandbox_search)

        rag_search_row.addWidget(self.rag_sandbox_input, 1)
        rag_search_row.addWidget(self.btn_sandbox_search)
        rag_layout.addLayout(rag_search_row)

        self.rag_sandbox_results = QListWidget()
        self.rag_sandbox_results.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QListWidget::item {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                margin-bottom: 6px;
                padding: 8px;
                font-size: 11px;
            }}
            QListWidget::item:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        rag_layout.addWidget(self.rag_sandbox_results, 1)

        self.coverage_panel.add_tab("RAG", rag_sandbox_content, "ph.database", closable=False)

        # --- TAB 3: Plan & Arborescence (Outline) ---
        self.outline_widget = DocumentOutlineWidget()
        self.coverage_panel.add_tab("Plan", self.outline_widget, "ph.tree-structure", closable=False)

        self.main_splitter.addWidget(self.coverage_panel)

        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.setCollapsible(2, False)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        self.main_splitter.setSizes([230, 600, 270])
        self.coverage_panel.hide()
        self.editor_stack.setCurrentIndex(0)

    def _connect_signals(self) -> None:
        self.tree_explorer.itemSelectionChanged.connect(self._on_document_selected)
        self.tree_explorer.itemMoved.connect(self._on_item_moved)
        self.tree_explorer.customContextMenuRequested.connect(self._on_tree_context_menu)
        self.editor_stack.currentChanged.connect(self._on_editor_page_changed)
        self.text_editor.content_changed.connect(self._on_document_text_changed)
        self.outline_widget.heading_selected.connect(self._on_outline_heading_selected)
        self.outline_widget.forge_section_requested.connect(self._on_forge_outline_section)
        self.outline_widget.repair_requested.connect(self._on_repair_document_headings)
        self.outline_widget.toc_requested.connect(self._on_insert_document_toc)
        if hasattr(self.text_editor, "editor") and self.text_editor.editor:
            self.text_editor.editor.cursorPositionChanged.connect(self._cursor_spy_timer.start)
        self._on_coverage_synced = self._handle_coverage_synced
        event_bus.subscribe(CoverageSyncedEvent, self._on_coverage_synced)
        self.destroyed.connect(lambda: event_bus.unsubscribe(CoverageSyncedEvent, self._on_coverage_synced))

    def _handle_coverage_synced(self, event: CoverageSyncedEvent) -> None:
        if event.doc_id is not None and event.doc_id != self._current_doc_id:
            return
        run_on_owner_thread(self, self._coverage_refresh_timer.start)

    @Slot()
    def _on_coverage_refresh_trigger(self) -> None:
        """Rafraîchit silencieusement la couverture après un évènement réactif (debounce)."""
        if self.coverage_panel.isHidden() or not self._current_doc_id:
            return
        fingerprint = self._calc_coverage_fingerprint(self._current_doc_id)
        if fingerprint == self._coverage_fingerprint:
            return
        self._refresh_chapters_list(allow_synthesis=False)

    @staticmethod
    def _calc_coverage_fingerprint(doc_id: int) -> tuple[int, int]:
        chunk_count = DocumentChunkModel.select().where(DocumentChunkModel.document_id == doc_id).count()
        link_count = NoteChunkLinkModel.select().join(DocumentChunkModel).where(DocumentChunkModel.document_id == doc_id).count()
        return (chunk_count, link_count)

    @Slot(int)
    def _on_editor_page_changed(self, index: int) -> None:
        if index > 0:
            self.coverage_panel.show()
            sizes = self.main_splitter.sizes()
            sizes[2] = max(sizes[2] or 270, self.coverage_panel.minimumWidth())
            self.main_splitter.setSizes(sizes)
        else:
            self.coverage_panel.hide()

    def _on_search_filter_changed(self, text: str) -> None:
        self.tree_explorer.filter_text(text)

    def _on_item_moved(self, source_data: dict, target_data: dict | None) -> None:
        if not source_data:
            return

        source_type = source_data.get("type")
        source_id = source_data.get("id")
        target_type = target_data.get("type") if target_data else None
        target_id = target_data.get("id") if target_data else None

        if target_type == "doc":
            doc = DocumentModel.get_or_none(DocumentModel.id == target_id)
            target_id = doc.folder.id if doc and doc.folder else None

        if source_type == "doc":
            doc = DocumentModel.get_or_none(DocumentModel.id == source_id)
            if doc:
                current_folder_id = doc.folder.id if doc.folder else None
                if current_folder_id == target_id:
                    return
                doc.folder = target_id
                doc.save()
                self.refresh_data()

        elif source_type == "folder":
            folder = FolderModel.get_or_none(FolderModel.id == source_id)
            if not folder:
                return

            target_folder = FolderModel.get_or_none(FolderModel.id == target_id) if target_id else None
            old_name = folder.name
            base_name = leaf_name(old_name)
            new_name = join_hierarchy((target_folder.name, base_name)) if target_folder else base_name

            if new_name == old_name:
                return

            if target_folder and descends_from(target_folder.name, old_name):
                show_toast(self, "Vous ne pouvez pas déplacer un dossier dans lui-même.", is_error=True)
                return

            try:
                with FolderModel._meta.database.atomic():
                    folders_to_update = FolderModel.select().where((FolderModel.name == old_name) | (FolderModel.name.startswith(descendants_prefix(old_name))))
                    for f in folders_to_update:
                        if f.name == old_name:
                            f.name = new_name
                        else:
                            suffix = f.name[len(old_name) :]
                            f.name = new_name + suffix
                        f.save()
                self.refresh_data()
            except Exception as e:
                logger.error("Erreur déplacement dossier : %s", e)
                show_toast(self, "Un dossier avec ce nom existe déjà à cet emplacement.", is_error=True)

    def refresh_data(self) -> None:
        try:
            self.tree_explorer.blockSignals(True)
            self.tree_explorer.clear()

            DocumentRepository().heal_folder_hierarchies()

            folder_items: dict[int, QTreeWidgetItem] = {}
            path_items: dict[str, QTreeWidgetItem] = {}
            folders = list(FolderModel.select())
            sorted_folders = sorted(folders, key=lambda f: f.name)

            for folder in sorted_folders:
                parts = split_hierarchy(folder.name)
                parent_item = None
                for i in range(1, len(parts)):
                    parent_path = join_hierarchy(parts[:i])
                    if parent_path in path_items:
                        parent_item = path_items[parent_path]
                    else:
                        new_item = QTreeWidgetItem(parent_item or self.tree_explorer, [parts[i - 1]])
                        new_item.setIcon(0, load_phosphor_icon("ph.folder", weight="fill", color=DesignTokens.COLOR_BLUE))
                        p_model = FolderModel.get_or_none(FolderModel.name == parent_path)
                        if p_model:
                            new_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": p_model.id})
                            folder_items[p_model.id] = new_item
                        path_items[parent_path] = new_item
                        parent_item = new_item

                node_name = parts[-1]
                item = QTreeWidgetItem(parent_item or self.tree_explorer, [node_name])
                item.setIcon(0, load_phosphor_icon("ph.folder", weight="fill", color=DesignTokens.COLOR_BLUE))
                item.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": folder.id})
                folder_items[folder.id] = item
                path_items[folder.name] = item

            documents = list(DocumentModel.select())
            for doc in documents:
                parent_item = folder_items[doc.folder_id] if hasattr(doc, "folder_id") and doc.folder_id and doc.folder_id in folder_items else self.tree_explorer
                title_to_display = doc.original_media.original_name if doc.original_media else doc.title
                item = QTreeWidgetItem(parent_item, [title_to_display])
                item.setData(0, Qt.ItemDataRole.UserRole, {"type": "doc", "id": doc.id})

                title_lower = doc.title.lower()
                is_album = getattr(doc, "file_type", "") == "album"
                is_pdf = getattr(doc, "file_type", "") == "pdf"
                has_content = bool(doc.content and doc.content.strip())

                if is_album:
                    item.setIcon(0, load_phosphor_icon("ph.images", color=DesignTokens.COLOR_PURPLE))
                    p_count = getattr(doc, "total_pages", 0) or 0
                    item.setText(0, f"{title_to_display} ({p_count}p)")
                elif is_pdf:
                    if has_content:
                        item.setIcon(0, load_phosphor_icon("ph.file-pdf", color=DesignTokens.COLOR_RED))
                    else:
                        item.setIcon(0, load_phosphor_icon("ph.file-pdf", color=DesignTokens.TEXT_MUTED))
                        item.setText(0, f"{title_to_display} (Non extrait)")
                        item.setForeground(0, QColor(DesignTokens.TEXT_MUTED))
                elif getattr(doc, "file_type", "") == "txt" or title_lower.endswith(".txt"):
                    item.setIcon(0, load_phosphor_icon("ph.file-text", color=DesignTokens.COLOR_BLUE))
                elif getattr(doc, "file_type", "") == "epub" or title_lower.endswith(".epub"):
                    item.setIcon(0, load_phosphor_icon("ph.book-open", color=DesignTokens.COLOR_PURPLE))
                elif getattr(doc, "file_type", "") == "pptx" or title_lower.endswith(".pptx"):
                    item.setIcon(0, load_phosphor_icon("ph.presentation", color=DesignTokens.COLOR_YELLOW))
                elif getattr(doc, "file_type", "") in ("audio", "mp3", "m4a", "wav", "ogg", "flac", "aac") or title_lower.endswith((".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac")):
                    item.setIcon(0, load_phosphor_icon("ph.waveform", color=DesignTokens.COLOR_GREEN))
                elif getattr(doc, "file_type", "") == "md" or title_lower.endswith(".md"):
                    item.setIcon(0, load_phosphor_icon("ph.file-code", color=DesignTokens.COLOR_YELLOW))
                elif getattr(doc, "file_type", "") == "ipynb" or title_lower.endswith(".ipynb"):
                    item.setIcon(0, load_phosphor_icon("ph.notebook", color=DesignTokens.COLOR_PURPLE))
                elif getattr(doc, "file_type", "") == "py" or title_lower.endswith(".py"):
                    item.setIcon(0, load_phosphor_icon("ph.file-py", color=DesignTokens.COLOR_BLUE))
                elif getattr(doc, "file_type", "") == "web":
                    item.setIcon(0, load_phosphor_icon("ph.globe", color=DesignTokens.ACCENT_PRIMARY))
                elif getattr(doc, "file_type", "") == "youtube":
                    item.setIcon(0, load_phosphor_icon("ph.youtube-logo", color=DesignTokens.COLOR_RED))
                else:
                    item.setIcon(0, load_phosphor_icon("ph.file-text", color=DesignTokens.COLOR_BLUE))

            self.tree_explorer.expandAll()
            self.tree_explorer.blockSignals(False)

            if not self._current_doc_id:
                self.editor_stack.setCurrentIndex(0)

        except Exception as e:
            logger.warning("Erreur refresh_data documents_view: %s", e)

    def is_dirty(self) -> bool:
        return self._dirty

    @Slot()
    def _on_document_selected(self) -> None:
        self._coverage_refresh_timer.stop()
        self._coverage_fingerprint = None
        items = self.tree_explorer.selectedItems()
        if not items:
            self.btn_delete.setEnabled(False)
            self._current_doc_id = None
            self.editor_stack.setCurrentIndex(0)
            return

        self.btn_delete.setEnabled(True)
        item = items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("type") == "doc":
            doc = DocumentModel.get_or_none(DocumentModel.id == data["id"])
            if doc:
                self._current_doc_id = doc.id
                title_to_display = doc.original_media.original_name if doc.original_media else doc.title
                self.doc_title_lbl.setText(title_to_display)

                if getattr(doc, "file_type", "") == "album":
                    self.btn_marker.hide()
                    self.album_viewer.load_album(doc)
                    self.editor_stack.setCurrentIndex(2)
                    self._update_rag_status_pill()
                    self._refresh_chapters_list()
                    return

                self.text_editor.blockSignals(True)
                doc_content = doc.content if hasattr(doc, "content") else ""
                self.text_editor.set_content(doc_content)
                self.outline_widget.set_document_content(doc_content)
                self.text_editor.blockSignals(False)
                self._dirty = False
                self._update_word_count()
                self._update_rag_status_pill()

                is_audio = getattr(doc, "file_type", "") in ("audio", "mp3", "m4a", "wav", "ogg", "flac", "aac")
                if is_audio and doc.original_media:
                    from ankiforge.utils.paths import resolve_media_path

                    audio_path = resolve_media_path(doc.original_media.filename)
                    if audio_path.exists():
                        self.audio_player.load_audio(str(audio_path))
                        self.audio_player.show()
                    else:
                        self.audio_player.hide()
                else:
                    if hasattr(self, "audio_player"):
                        self.audio_player.stop()
                        self.audio_player.hide()

                if doc.file_type == "pdf":
                    self.btn_marker.show()
                else:
                    self.btn_marker.hide()

                if doc.file_type == "pdf" and doc.original_media:
                    from ankiforge.utils.paths import resolve_media_path

                    pdf_path = resolve_media_path(doc.original_media.filename)
                    if pdf_path.exists():
                        self.pdf_document.load(str(pdf_path))
                        self.view_toggle_frame.show()
                        self._on_view_toggled("pdf")
                    else:
                        self.view_toggle_frame.hide()
                        self._on_view_toggled("md")
                else:
                    self.view_toggle_frame.hide()
                    self._on_view_toggled("md")

                self.editor_stack.setCurrentIndex(1)
                self._refresh_chapters_list()
        else:
            self.btn_marker.hide()
            if hasattr(self, "audio_player"):
                self.audio_player.stop()
                self.audio_player.hide()
            self._current_doc_id = None
            self.outline_widget.set_document_content("")
            self.editor_stack.setCurrentIndex(0)
            self._refresh_chapters_list()

    def _update_rag_status_pill(self) -> None:
        if not self._current_doc_id:
            self.rag_status_pill.setText("Non indexé")
            apply_pill_style(self.rag_status_pill, DesignTokens.TEXT_MUTED)
            return

        rag = RAGService()
        is_rag_ready = rag.is_indexed(self._current_doc_id)
        chunk_count = DocumentChunkModel.select().where(DocumentChunkModel.document_id == self._current_doc_id).count()

        if is_rag_ready:
            self.rag_status_pill.setText(f"RAG Prêt ({chunk_count} chunks)")
            apply_pill_style(self.rag_status_pill, DesignTokens.COLOR_GREEN)
        elif chunk_count > 0:
            self.rag_status_pill.setText(f"Structuré ({chunk_count} chunks)")
            apply_pill_style(self.rag_status_pill, DesignTokens.COLOR_YELLOW)
        else:
            self.rag_status_pill.setText("Non structuré")
            apply_pill_style(self.rag_status_pill, DesignTokens.TEXT_MUTED)

    @Slot()
    def _on_document_text_changed(self) -> None:
        self._dirty = True
        self.btn_save.setEnabled(True)
        self._update_word_count()
        self._outline_debounce_timer.start()

    def _setup_format_menu(self) -> None:
        """Configure le menu déroulant d'options de formatage Markdown."""
        menu = QMenu(self.btn_format_md)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 16px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        act_all = menu.addAction("🪄 Tout formater (Auto)")
        act_all.triggered.connect(lambda: self._format_current_document())

        menu.addSeparator()

        act_ocr = menu.addAction("✂️ Dé-césurer les coupures OCR")
        act_ocr.triggered.connect(
            lambda: self._format_current_document(
                FormatOptions(
                    dehyphenate_ocr=True,
                    normalize_katex=False,
                    align_tables=False,
                    normalize_headings=False,
                    clean_whitespace=False,
                    normalize_code_fences=False,
                )
            )
        )

        act_katex = menu.addAction("🧮 Harmoniser KaTeX ($ / $$)")
        act_katex.triggered.connect(
            lambda: self._format_current_document(
                FormatOptions(
                    dehyphenate_ocr=False,
                    normalize_katex=True,
                    align_tables=False,
                    normalize_headings=False,
                    clean_whitespace=False,
                    normalize_code_fences=False,
                )
            )
        )

        act_tables = menu.addAction("📊 Aligner les tableaux GFM")
        act_tables.triggered.connect(
            lambda: self._format_current_document(
                FormatOptions(
                    dehyphenate_ocr=False,
                    normalize_katex=False,
                    align_tables=True,
                    normalize_headings=False,
                    clean_whitespace=False,
                    normalize_code_fences=False,
                )
            )
        )

        act_space = menu.addAction("🧹 Nettoyer les espaces superflus")
        act_space.triggered.connect(
            lambda: self._format_current_document(
                FormatOptions(
                    dehyphenate_ocr=False,
                    normalize_katex=False,
                    align_tables=False,
                    normalize_headings=False,
                    clean_whitespace=True,
                    normalize_code_fences=False,
                )
            )
        )

        menu.addSeparator()
        act_ai = menu.addAction("🤖 Structurer avec l'IA...")
        act_ai.triggered.connect(self._on_open_ai_structure_dialog)

        self.btn_format_md.setMenu(menu)

    @Slot()
    def _on_open_ai_structure_dialog(self) -> None:
        """Ouvre la boîte de dialogue de structuration IA pour le document actif."""
        if not self._current_doc_id:
            show_toast(self, "Veuillez sélectionner un document à structurer", level="warning")
            return

        doc = DocumentModel.get_or_none(DocumentModel.id == self._current_doc_id)
        if not doc:
            return

        content = self.text_editor.get_content()
        if not content.strip():
            show_toast(self, "Le document actif est vide", level="warning")
            return

        dialog = AIDocumentStructureDialog(
            doc_title=doc.title,
            content=content,
            ai_manager=self.ai_manager,
            parent=self,
        )
        dialog.structure_applied.connect(self._on_structure_applied_to_editor)
        dialog.structure_saved_as_copy.connect(self._on_structure_saved_as_copy)
        dialog.exec()

    @Slot(str)
    def _on_structure_applied_to_editor(self, new_text: str) -> None:
        """Remplace le contenu de l'éditeur par le résultat structuré par l'IA."""
        self.text_editor.set_content(new_text)
        self._dirty = True
        self.btn_save.setEnabled(True)
        self.outline_widget.set_document_content(new_text)
        show_toast(self, "Document restructuré avec succès dans l'éditeur", level="success")

    @Slot(str)
    def _on_structure_saved_as_copy(self, new_text: str) -> None:
        """Enregistre le document structuré sous forme d'une nouvelle copie."""
        if not self._current_doc_id:
            return

        doc = DocumentModel.get_or_none(DocumentModel.id == self._current_doc_id)
        orig_title = doc.title if doc else "Document"
        folder = doc.folder if doc else None

        new_doc = DocumentModel.create(
            title=f"{orig_title} (Structuré IA)",
            content=new_text,
            file_type="md",
            folder=folder,
        )
        self.refresh_data()
        self._select_doc_id_in_tree(new_doc.id)
        show_toast(self, f"Copie structurée '{new_doc.title}' créée avec succès", level="success")

    def _format_current_document(self, options: FormatOptions | None = None) -> None:
        """Applique les règles de formatage au document actif et actualise l'éditeur."""
        if not self._current_doc_id:
            show_toast(self, "Veuillez sélectionner un document à formater", level="warning")
            return
        content = self.text_editor.get_content()
        if not content.strip():
            return
        result = MarkdownFormatter.format(content, options)
        if result.changed:
            self.text_editor.set_content(result.formatted_text)
            self._dirty = True
            self.btn_save.setEnabled(True)
            self.outline_widget.set_document_content(result.formatted_text)
            summary = ", ".join(result.changes_summary) if result.changes_summary else "Formatage appliqué"
            show_toast(self, f"Formatage réussi : {summary}", level="success")
        else:
            show_toast(self, "Le document est déjà parfaitement formaté", level="info")

    @Slot(int)
    def _on_outline_heading_selected(self, line_number: int) -> None:
        """Déplace le curseur dans l'éditeur vers la ligne sélectionnée et active visuellement la section."""
        if hasattr(self.text_editor, "editor") and self.text_editor.editor:
            editor = self.text_editor.editor
            doc = editor.document()
            block = doc.findBlockByLineNumber(line_number - 1)
            if block.isValid():
                cursor = editor.textCursor()
                cursor.setPosition(block.position())
                cursor.select(QTextCursor.SelectionType.LineUnderCursor)
                editor.setTextCursor(cursor)
                editor.centerCursor()
                editor.setFocus()
                if hasattr(self, "outline_widget"):
                    self.outline_widget.set_active_line(line_number)

    def _sync_active_line_to_outline(self) -> None:
        """Transmet la position courante du curseur au plan pour mise en valeur (Scroll Spy)."""
        if hasattr(self, "outline_widget") and hasattr(self.text_editor, "editor") and self.text_editor.editor:
            cursor = self.text_editor.editor.textCursor()
            line_number = cursor.blockNumber() + 1
            self.outline_widget.set_active_line(line_number)

    @Slot(str, str, int, int)
    def _on_forge_outline_section(self, title: str, content: str, start_line: int, end_line: int) -> None:
        """Envoie directement le contenu d'une section du plan vers le Studio de Création de cartes."""
        if not content.strip():
            show_toast(self, "La section sélectionnée est vide.", is_error=True)
            return

        doc = DocumentModel.get_or_none(DocumentModel.id == self._current_doc_id)
        doc_title = doc.title if doc else "Document"

        self.request_navigation.emit(
            "creation",
            {
                "doc_id": self._current_doc_id,
                "text_source": content,
                "source_title": f"{doc_title} - {title}",
            },
        )
        show_toast(self, f"Section '{title}' envoyée au Studio de Création", level="success")

    @Slot()
    def _on_repair_document_headings(self) -> None:
        """Harmonise la hiérarchie des titres après validation interactive de l'utilisateur."""
        content = self.text_editor.get_content()
        if not content.strip():
            return

        repairs = MarkdownStructurer.detect_heading_hierarchy_issues(content)
        if not repairs:
            show_toast(self, "La hiérarchie des titres est déjà optimale", level="info")
            return

        from ankiforge.ui.dialogs.repair_headings_dialog import RepairHeadingsDialog

        dialog = RepairHeadingsDialog(repairs, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = dialog.get_selected_repairs()
            if not selected:
                show_toast(self, "Aucune correction sélectionnée", level="info")
                return

            repaired = MarkdownStructurer.apply_heading_repairs(content, selected)
            self.text_editor.replace_all_text_with_undo(repaired)
            self._dirty = True
            self.btn_save.setEnabled(True)
            self.outline_widget.set_document_content(repaired)
            show_toast(self, f"Hiérarchie réparée : {len(selected)} titre(s) ajusté(s) (Ctrl+Z pour annuler)", level="success")

    @Slot()
    def _on_insert_document_toc(self) -> None:
        """Génère et insère ou met à jour in-place une Table des Matières propre."""
        content = self.text_editor.get_content()
        if not content.strip():
            return

        new_content, changed = MarkdownStructurer.insert_or_update_toc(content)
        if not changed:
            show_toast(self, "Aucun titre trouvé pour générer le sommaire", level="warning")
            return

        self.text_editor.replace_all_text_with_undo(new_content)
        self._dirty = True
        self.btn_save.setEnabled(True)
        self.outline_widget.set_document_content(new_content)
        show_toast(self, "Table des matières mise à jour (Ctrl+Z pour annuler)", level="success")

    def _update_outline(self) -> None:
        """Met à jour l'arborescence suite à une modification du texte."""
        if hasattr(self, "outline_widget") and self._current_doc_id:
            content = self.text_editor.get_content()
            self.outline_widget.set_document_content(content)

    def _update_word_count(self) -> None:
        text = self.text_editor.get_content()
        words = len(text.split())
        self.lbl_word_count.setText(f"{words:,} mots")

    @Slot()
    def _on_import_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Importer un document",
            "",
            "Documents (*.pdf *.epub *.txt *.md *.docx *.pptx *.ipynb *.py *.mp3 *.m4a *.wav *.ogg *.flac *.aac);;Tous les fichiers (*.*)",
        )
        if file_path:
            ext = pathlib.Path(file_path).suffix.lower()
            if ext == ".pdf":
                self._import_pdf_directly(file_path)
            else:
                self._start_document_worker(file_path)

    @Slot()
    def _on_import_url(self) -> None:
        dialog = UrlImportDialog(self)
        dialog.import_completed.connect(self._on_web_import_completed)
        dialog.cards_requested.connect(self._on_web_import_cards_requested)
        dialog.exec()

    @Slot(list)
    def _on_web_import_completed(self, doc_ids: list[int]) -> None:
        self.refresh_data()
        if doc_ids:
            self._select_doc_id_in_tree(doc_ids[0])

    @Slot(int)
    def _on_web_import_cards_requested(self, doc_id: int) -> None:
        self.request_navigation.emit("creation", {"doc_id": doc_id})

    @Slot()
    def _on_new_album(self) -> None:
        dialog = AlbumImportDialog(self)
        dialog.album_created.connect(self._on_album_created)
        dialog.exec()

    @Slot(int)
    def _on_album_created(self, doc_id: int) -> None:
        self.refresh_data()
        self._select_doc_id_in_tree(doc_id)

    @Slot(int)
    def _on_album_modified(self, doc_id: int) -> None:
        self.refresh_data()

    @Slot(int)
    def _on_album_forge_requested(self, doc_id: int) -> None:
        self.request_navigation.emit("creation", {"doc_id": doc_id})

    def _select_doc_id_in_tree(self, doc_id: int) -> None:
        def find_item(parent: QTreeWidgetItem | DocumentTreeWidget) -> QTreeWidgetItem | None:
            count = parent.childCount() if isinstance(parent, QTreeWidgetItem) else parent.topLevelItemCount()
            for i in range(count):
                child = parent.child(i) if isinstance(parent, QTreeWidgetItem) else parent.topLevelItem(i)
                if not child:
                    continue
                d = child.data(0, Qt.ItemDataRole.UserRole)
                if d and d.get("type") == "doc" and d.get("id") == doc_id:
                    return child
                found = find_item(child)
                if found:
                    return found
            return None

        it = find_item(self.tree_explorer)
        if it:
            self.tree_explorer.setCurrentItem(it)

    @Slot(str)
    def _on_view_toggled(self, mode: str) -> None:
        self.btn_view_pdf.setChecked(mode == "pdf")
        self.btn_view_md.setChecked(mode == "md")
        self.btn_view_term.setChecked(mode == "term")

        if mode == "pdf":
            self.inner_editor_stack.setCurrentIndex(0)
        elif mode == "md":
            self.inner_editor_stack.setCurrentIndex(1)
        else:
            self.inner_editor_stack.setCurrentIndex(2)

    def _import_pdf_directly(self, file_path: str) -> None:
        from ankiforge.services.cards.media_manager import MediaManager

        media_manager = MediaManager()
        media = media_manager.store_document_source(file_path)
        if not media:
            show_toast(self, "Erreur lors de l'import du PDF.", is_error=True)
            return

        file_path_obj = pathlib.Path(file_path)
        doc = DocumentModel.create(
            title=file_path_obj.stem,
            content="",
            original_media_id=media.id,
            file_type="pdf",
            source_url=None,
        )

        self.refresh_data()
        self._current_doc_id = doc.id
        title_to_display = media.original_name
        self.doc_title_lbl.setText(title_to_display)
        self.text_editor.set_content("Cliquer sur 'Marker OCR' pour extraire le texte et les formules en KaTeX...")
        self.editor_stack.setCurrentIndex(1)

        from ankiforge.utils.paths import resolve_media_path

        pdf_path = resolve_media_path(media.filename)
        if pdf_path.exists():
            self.pdf_document.load(str(pdf_path))
            self.view_toggle_frame.show()
            self._on_view_toggled("pdf")
        else:
            self.view_toggle_frame.hide()
            self._on_view_toggled("md")

        show_toast(self, f"PDF '{title_to_display}' importé. Démarrage de l'analyse Marker OCR...")
        if pdf_path.exists():
            self._start_document_worker(str(pdf_path), doc_id=doc.id)

    def _start_document_worker(self, path_or_url: str, doc_id: int | None = None) -> None:
        self.btn_import.setEnabled(False)
        self.btn_import_url.setEnabled(False)
        show_toast(self, "Extraction et analyse du document en cours...")

        self.worker = DocumentWorker(path_or_url, doc_id_to_update=doc_id)
        self.worker.finished_signal.connect(self._on_worker_finished)
        self.worker.error_signal.connect(self._on_worker_error)
        self.worker.log_signal.connect(self._on_worker_log)

        self._on_view_toggled("term")
        self.terminal_view.clear()
        self.terminal_view.append("--- Démarrage de l'extraction documentaire ---")
        self.worker.start()

    @Slot(str)
    def _on_worker_log(self, msg: str) -> None:
        if hasattr(self, "terminal_view"):
            self.terminal_view.append(msg)
            scrollbar = self.terminal_view.verticalScrollBar()
            if scrollbar is not None:
                scrollbar.setValue(scrollbar.maximum())

    @Slot(str, str)
    def _on_worker_finished(self, title: str, content: str) -> None:
        if hasattr(self, "terminal_view"):
            self.terminal_view.append("--- Extraction terminée avec succès ! ---")

        self._on_view_toggled("md")
        self.btn_import.setEnabled(True)
        self.btn_import_url.setEnabled(True)

        try:
            doc_id_to_update = getattr(self.worker, "doc_id_to_update", None)
            file_type = "md"
            original_media = None
            source_url = None

            if doc_id_to_update:
                existing_doc = self.doc_repo.get_document_by_id(doc_id_to_update)
                file_type = (existing_doc.file_type if existing_doc else None) or "md"
            elif self.worker and self.worker.file_path:
                path_or_url = self.worker.file_path
                if path_or_url.startswith("http"):
                    source_url = path_or_url
                    file_type = "web"
                else:
                    from ankiforge.services.cards.media_manager import MediaManager

                    original_media = MediaManager().store_document_source(path_or_url)
                    ext_clean = pathlib.Path(path_or_url).suffix.replace(".", "").lower()
                    file_type = "audio" if ext_clean in ("mp3", "m4a", "wav", "ogg", "flac", "aac", "wma") else ext_clean or "txt"

            doc = self.doc_repo.save_imported_document(
                title=title,
                content=content,
                file_type=file_type,
                source_url=source_url,
                doc_id_to_update=doc_id_to_update,
                original_media=original_media,
            )

            self.refresh_data()
            self._current_doc_id = doc.id
            self._select_doc_id_in_tree(doc.id)
            title_to_display = doc.original_media.original_name if doc.original_media else doc.title
            self.doc_title_lbl.setText(title_to_display)
            self.text_editor.set_content(content)
            self.editor_stack.setCurrentIndex(1)
            self._update_rag_status_pill()

            show_toast(self, f"Document '{title_to_display}' importé avec succès !")
        except Exception as e:
            log_and_notify_error(e, context="Enregistrement du document", parent=self, title="Erreur")

    @Slot(str)
    def _on_worker_error(self, error: str) -> None:
        self.btn_import.setEnabled(True)
        self.btn_import_url.setEnabled(True)
        log_and_notify_error(error, context="Extraction du document", parent=self, title="Erreur d'importation")

    @Slot()
    def _on_new_folder(self) -> None:
        items = self.tree_explorer.selectedItems()
        target_folder_id: int | None = None
        if items:
            data = items[0].data(0, Qt.ItemDataRole.UserRole)
            if data:
                item_type = data.get("type")
                item_id = data.get("id")
                if item_type == "folder":
                    target_folder_id = item_id
                elif item_type == "doc":
                    doc = DocumentModel.get_or_none(DocumentModel.id == item_id)
                    if doc and doc.folder:
                        target_folder_id = doc.folder.id
        self._on_new_subfolder(parent_folder_id=target_folder_id)

    def _on_new_subfolder(self, parent_folder_id: int | None = None) -> None:
        dlg = FolderCreateDialog(parent_folder_id=parent_folder_id, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            created = dlg.get_created_folder()
            self.refresh_data()
            if created:
                self._select_folder_id_in_tree(created.id)
            show_toast(self, f"Dossier '{dlg.get_full_path()}' créé.")

    def _select_folder_id_in_tree(self, folder_id: int) -> None:
        def find_item(parent: QTreeWidgetItem | DocumentTreeWidget) -> QTreeWidgetItem | None:
            count = parent.childCount() if isinstance(parent, QTreeWidgetItem) else parent.topLevelItemCount()
            for i in range(count):
                child = parent.child(i) if isinstance(parent, QTreeWidgetItem) else parent.topLevelItem(i)
                if not child:
                    continue
                d = child.data(0, Qt.ItemDataRole.UserRole)
                if d and d.get("type") == "folder" and d.get("id") == folder_id:
                    return child
                found = find_item(child)
                if found:
                    return found
            return None

        it = find_item(self.tree_explorer)
        if it:
            self.tree_explorer.setCurrentItem(it)
            it.setSelected(True)

    def _on_rename_folder(self, folder_id: int) -> None:
        folder = FolderModel.get_or_none(FolderModel.id == folder_id)
        if not folder:
            return
        parts = split_hierarchy(folder.name)
        leaf = parts[-1]
        new_name, ok = QInputDialog.getText(
            self,
            "Renommer le dossier",
            f"Nouveau nom pour '{leaf}' :",
            text=leaf,
        )
        if not ok or not new_name.strip():
            return

        new_name = new_name.strip()
        if new_name == leaf:
            return

        try:
            repo = DocumentRepository()
            renamed = repo.rename_folder(folder_id, new_name)
            self.refresh_data()
            self._select_folder_id_in_tree(renamed.id)
            show_toast(self, f"Dossier renommé en '{new_name}'.")
        except Exception as e:
            logger.error("Erreur renommage dossier : %s", e)
            from ankiforge.ui.widgets.toast import log_and_notify_error

            log_and_notify_error(e, context="Renommage de dossier", parent=self, title="Erreur")

    @Slot(QPoint)
    def _on_tree_context_menu(self, pos: QPoint) -> None:
        item = self.tree_explorer.itemAt(pos)
        menu = StyledMenu(self)

        if item is None:
            act_new_root = menu.addAction(load_phosphor_icon("ph.folder-plus", color=DesignTokens.COLOR_BLUE), "📁 Nouveau dossier racine...")
            act_new_root.triggered.connect(lambda: self._on_new_subfolder(parent_folder_id=None))
        else:
            self.tree_explorer.setCurrentItem(item)
            item.setSelected(True)
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if not data or data.get("type") == "folder":
                folder_id = data.get("id") if data else None
                act_new_sub = menu.addAction(load_phosphor_icon("ph.folder-plus", color=DesignTokens.COLOR_BLUE), "📁 Nouveau sous-dossier...")
                act_new_sub.triggered.connect(lambda: self._on_new_subfolder(parent_folder_id=folder_id))

                if folder_id is not None:
                    act_rename = menu.addAction(load_phosphor_icon("ph.pencil", color=DesignTokens.COLOR_YELLOW), "✏️ Renommer...")
                    act_rename.triggered.connect(lambda: self._on_rename_folder(folder_id=folder_id))

                    menu.addSeparator()

                    act_del = menu.addAction(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED), "🗑️ Supprimer le dossier")
                    act_del.triggered.connect(self._on_delete_item)
            elif data.get("type") == "doc":
                act_open = menu.addAction(load_phosphor_icon("ph.folder-open", color=DesignTokens.COLOR_BLUE), "📂 Ouvrir")
                act_open.triggered.connect(self._on_document_selected)

                menu.addSeparator()

                act_del = menu.addAction(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED), "🗑️ Supprimer")
                act_del.triggered.connect(self._on_delete_item)

        menu.exec(self.tree_explorer.viewport().mapToGlobal(pos))

    @Slot()
    def _on_delete_item(self) -> None:
        items = self.tree_explorer.selectedItems()
        if not items:
            return

        item = items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type = data.get("type")
        item_id = data.get("id")

        if item_type == "doc":
            doc = DocumentModel.get_or_none(DocumentModel.id == item_id)
            if doc:
                reply = QMessageBox.question(
                    self,
                    "Confirmer la suppression",
                    f"Voulez-vous vraiment supprimer le document '{doc.title}' ?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    doc.delete_instance()
                    self.refresh_data()
                    self.editor_stack.setCurrentIndex(0)
                    show_toast(self, "Document supprimé.")
        elif item_type == "folder":
            folder = FolderModel.get_or_none(FolderModel.id == item_id)
            if folder:
                reply = QMessageBox.question(
                    self,
                    "Confirmer la suppression",
                    f"Voulez-vous vraiment supprimer le dossier '{folder.name}' et son contenu ?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    with FolderModel._meta.database.atomic():
                        folders_to_delete = FolderModel.select().where((FolderModel.name == folder.name) | (FolderModel.name.startswith(descendants_prefix(folder.name))))
                        for f in folders_to_delete:
                            f.delete_instance()
                    self.refresh_data()
                    self.editor_stack.setCurrentIndex(0)
                    show_toast(self, "Dossier supprimé.")

    @Slot()
    def _on_open_delimitation_dialog(self) -> None:
        if not self._current_doc_id:
            show_toast(self, "Veuillez sélectionner un document.", is_error=True)
            return

        doc = DocumentModel.get_by_id(self._current_doc_id)
        dlg = DocumentDelimitationDialog(doc, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            show_toast(self, "Délimitation et sections appliquées avec succès !")
            self._refresh_chapters_list()
            self._update_rag_status_pill()

    @Slot()
    def _on_open_rag_test_dialog(self) -> None:
        if not self._current_doc_id:
            show_toast(self, "Veuillez sélectionner un document.", is_error=True)
            return

        doc = DocumentModel.get_by_id(self._current_doc_id)
        dlg = RAGTestDialog(doc, parent=self)
        dlg.exec()

    @Slot()
    def _on_run_marker_analysis(self) -> None:
        if not self._current_doc_id:
            show_toast(self, "Veuillez d'abord sélectionner un document.", is_error=True)
            return

        doc = DocumentModel.get_by_id(self._current_doc_id)
        if doc.file_type != "pdf":
            show_toast(self, "L'analyse Marker OCR est disponible uniquement pour les fichiers PDF.", is_error=True)
            self.btn_marker.hide()
            return

        pdf_path = None
        if doc.original_media:
            from ankiforge.utils.paths import resolve_media_path

            candidate = resolve_media_path(doc.original_media.filename)
            if candidate.exists():
                pdf_path = candidate

        marker_exec = DocumentParser.get_marker_executable()
        if not marker_exec:
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Installer Marker OCR")
            dialog.setText("Marker OCR n'est pas installé dans cette application packagée.")
            dialog.setInformativeText("AnkiForge va créer un environnement Python séparé dans ~/.ankiforge/tools/marker et y installer marker-pdf.")
            install_button = dialog.addButton("Installer Marker OCR", QMessageBox.ButtonRole.AcceptRole)
            fallback_button = dialog.addButton("Extraction standard", QMessageBox.ButtonRole.DestructiveRole)
            dialog.addButton(QMessageBox.StandardButton.Cancel)
            dialog.exec()
            clicked = dialog.clickedButton()
            if clicked is install_button:
                self._install_marker_and_start(str(pdf_path) if pdf_path else "")
                return
            if clicked is not fallback_button:
                return

        if pdf_path:
            self._start_document_worker(str(pdf_path), doc_id=doc.id)
            return

        show_toast(self, "Analyse Marker : Document déjà textuel.")

    def _install_marker_and_start(self, pdf_path: str) -> None:
        if not pdf_path:
            show_toast(self, "Le fichier PDF source est introuvable.", is_error=True)
            return
        self.btn_marker.setEnabled(False)
        show_toast(self, "Installation de Marker OCR en cours. Suivez les étapes dans la console...")

        # Basculer automatiquement sur la console de logs pour rassurer l'utilisateur
        self.editor_stack.setCurrentIndex(1)
        self.view_toggle_frame.show()
        self._on_view_toggled("term")
        self.terminal_view.clear()
        self.terminal_view.append("==================================================")
        self.terminal_view.append("🚀 Installation de Marker OCR & Dépendances")
        self.terminal_view.append("==================================================")
        self.terminal_view.append("Création de l'environnement virtuel dédié et téléchargement des paquets...")
        self.terminal_view.append("Cette opération peut nécessiter quelques minutes selon votre connexion réseau.\n")

        self._marker_installer = MarkerInstallerWorker()
        self._marker_installer.progress.connect(self._on_worker_log)
        self._marker_installer.installed.connect(lambda _: self._on_marker_installed(pdf_path))
        self._marker_installer.failed.connect(self._on_marker_install_failed)
        self._marker_installer.start()

    def _on_marker_installed(self, pdf_path: str) -> None:
        self.btn_marker.setEnabled(True)
        if hasattr(self, "terminal_view"):
            self.terminal_view.append("\n✅ Marker OCR a été installé avec succès !")
            self.terminal_view.append("--- Démarrage de l'analyse documentaire avec Marker OCR ---\n")
        show_toast(self, "Marker OCR installé avec succès.")
        self._start_document_worker(pdf_path, doc_id=self._current_doc_id)

    def _on_marker_install_failed(self, error: str) -> None:
        self.btn_marker.setEnabled(True)
        if hasattr(self, "terminal_view"):
            self.terminal_view.append(f"\n❌ Échec de l'installation de Marker OCR :\n{error}\n")
        show_toast(self, f"Installation de Marker OCR échouée : {error}", is_error=True)

    @Slot()
    def _on_save_document(self) -> None:
        if not self._current_doc_id:
            show_toast(self, "Aucun document sélectionné à sauvegarder.", is_error=True)
            return

        try:
            doc = DocumentModel.get_or_none(DocumentModel.id == self._current_doc_id)
            if doc:
                doc.title = self.doc_title_lbl.text()
                content = self.text_editor.get_content()
                doc.content = content
                doc.word_count = len(content.split())
                doc.save()

                if getattr(doc, "file_type", "") != "album" and not DocumentPageModel.select().where(DocumentPageModel.document == doc).exists():
                    extracted = ChunkingService.extract_chunks(content, file_type=doc.file_type, strategy=ChunkingService.preferred_strategy(doc.file_type))
                    if extracted:
                        start_p = getattr(doc, "start_page", None)
                        end_p = getattr(doc, "end_page", None)
                        raw_excl = getattr(doc, "excluded_headings", None)
                        excl_headings: list[str] = []
                        if raw_excl:
                            try:
                                import json

                                parsed = json.loads(raw_excl)
                                if isinstance(parsed, list):
                                    excl_headings = [str(x).lower() for x in parsed]
                            except Exception as err:
                                logger.debug("Parsing des titres exclus ignoré : %s", err)

                        retained = []
                        for c in extracted:
                            pn = c.get("page_number")
                            if pn is not None:
                                if start_p is not None and pn < start_p:
                                    continue
                                if end_p is not None and pn > end_p:
                                    continue
                            hp = (c.get("heading_path") or "").lower()
                            if excl_headings and any(eh in hp for eh in excl_headings):
                                continue
                            retained.append(c)

                        with DocumentChunkModel._meta.database.atomic():
                            DocumentChunkModel.delete().where(DocumentChunkModel.document == doc).execute()
                            for idx, chunk_data in enumerate(retained):
                                DocumentChunkModel.create(
                                    document=doc,
                                    chunk_index=idx,
                                    content=chunk_data["content"],
                                    page_number=chunk_data.get("page_number"),
                                    heading_path=chunk_data.get("heading_path"),
                                    start_time=chunk_data.get("start_time"),
                                    end_time=chunk_data.get("end_time"),
                                    content_hash=chunk_data.get("content_hash") or ChunkingService.hash_content(chunk_data["content"]),
                                )
                        mark_document_version(doc)
                        from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService

                        CoverageAlignmentService.sync_coverage_from_tags(doc.id)

                self._dirty = False
                self.btn_save.setStyleSheet("")
                self._update_rag_status_pill()
                self._refresh_chapters_list()
                show_toast(self, f"Document '{doc.title}' enregistré avec succès !")
        except Exception as e:
            log_and_notify_error(e, context="Sauvegarde du document", parent=self, title="Erreur de sauvegarde")

    def _refresh_chapters_list(self, allow_synthesis: bool = True) -> None:
        selected_key = self._current_selected_chapter_key()
        self.chapters_list.clear()
        if not self._current_doc_id:
            self._coverage_fingerprint = None
            self.lbl_coverage_summary.setText("📊 Couverture : 0%")
            self.coverage_bar.setValue(0)
            self._set_coverage_bar_color(0)
            self.lbl_coverage_details.setText("0 sections analysées • 0 cartes liées")
            return

        self._coverage_fingerprint = self._calc_coverage_fingerprint(self._current_doc_id)

        chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document_id == self._current_doc_id).order_by(DocumentChunkModel.chunk_index))
        if not chunks and allow_synthesis:
            chunks = self._ensure_document_chunks(self._current_doc_id)

        if not chunks:
            item = QListWidgetItem("Aucun fragment structuré (document vide)")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.chapters_list.addItem(item)
            self.lbl_coverage_summary.setText("📊 Couverture : 0%")
            self.coverage_bar.setValue(0)
            self._set_coverage_bar_color(0)
            self.lbl_coverage_details.setText("0 sections analysées • 0 cartes liées")
            self._apply_chapters_filter()
            return

        stats = self.doc_repo.get_coverage_stats(self._current_doc_id)
        chunk_card_counts = self._query_chunk_card_counts(self._current_doc_id)

        unit_type = stats.get("unit_type", "sections")
        groups = self._group_chunks_by_unit(chunks, unit_type)

        coverage_by_heading: dict[str, int] = {}
        restore_item: QListWidgetItem | None = None
        for label, chunk_ids in groups:
            card_count = sum(chunk_card_counts.get(cid, 0) for cid in chunk_ids)
            covered = card_count > 0
            if covered:
                badge = "🟢"
                status_text = f"Couvert ({card_count} carte{'s' if card_count > 1 else ''})"
            else:
                badge = "⚠️"
                status_text = "Non couvert (0 carte)"
            frag_text = f", {len(chunk_ids)} fragment{'s' if len(chunk_ids) > 1 else ''}" if len(chunk_ids) > 1 else ""
            item_text = f"{badge} {label} — {status_text}{frag_text}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, chunk_ids)
            item.setData(Qt.ItemDataRole.UserRole + 1, covered)
            self.chapters_list.addItem(item)
            if chunk_ids == selected_key:
                restore_item = item
            if unit_type != "pages":
                for key in self._heading_coverage_keys(label):
                    coverage_by_heading[key] = max(coverage_by_heading.get(key, 0), card_count)

        if hasattr(self, "outline_widget"):
            self.outline_widget.set_coverage_data(coverage_by_heading)

        percent = int(stats.get("coverage_pct", 0))
        unit_label = "pages" if unit_type == "pages" else "sections"
        covered_units = stats.get("covered_units", 0)
        total_units = stats.get("total_units", len(groups))
        total_cards = stats.get("total_cards", 0)
        excluded_units = stats.get("excluded_units", 0)

        excl_suffix = f" • {excluded_units} exclu(e)s" if excluded_units > 0 else ""
        self.lbl_coverage_summary.setText(f"📊 Couverture : {percent}% ({covered_units}/{total_units} {unit_label}{excl_suffix})")
        self.coverage_bar.setValue(percent)
        self._set_coverage_bar_color(percent)
        self.lbl_coverage_details.setText(f"{total_units} {unit_label} utiles • {covered_units} couvertes • {total_cards} cartes liées")

        self._apply_chapters_filter()
        if restore_item is not None:
            self.chapters_list.setCurrentItem(restore_item)
            self.chapters_list.scrollToItem(restore_item, QAbstractItemView.ScrollHint.EnsureVisible)

    def _ensure_document_chunks(self, doc_id: int) -> list[Any]:
        """Synthétise les fragments d'un document s'il n'en possède aucun (idempotent)."""
        existing = list(DocumentChunkModel.select().where(DocumentChunkModel.document_id == doc_id).order_by(DocumentChunkModel.chunk_index))
        if existing:
            return existing
        doc = DocumentModel.get_or_none(DocumentModel.id == doc_id)
        if not doc:
            return []
        created: list[DocumentChunkModel] = []
        pages = list(DocumentPageModel.select().where(DocumentPageModel.document == doc).order_by(DocumentPageModel.page_number))
        if pages:
            with DocumentChunkModel._meta.database.atomic():
                for p in pages:
                    created.append(
                        DocumentChunkModel.create(
                            document=doc,
                            chunk_index=p.page_number - 1,
                            content=p.ocr_text or f"Page {p.page_number}",
                            page_number=p.page_number,
                            heading_path=f"Page {p.page_number}",
                            content_hash=ChunkingService.hash_content(p.ocr_text or f"Page {p.page_number}"),
                        )
                    )
            mark_document_version(doc)
            return created
        if doc.content and doc.content.strip():
            extracted = ChunkingService.extract_chunks(doc.content, file_type=doc.file_type, strategy=ChunkingService.preferred_strategy(doc.file_type))
            if extracted:
                with DocumentChunkModel._meta.database.atomic():
                    for chunk_data in extracted:
                        created.append(
                            DocumentChunkModel.create(
                                document=doc,
                                chunk_index=chunk_data["index"],
                                content=chunk_data["content"],
                                page_number=chunk_data.get("page_number"),
                                heading_path=chunk_data.get("heading_path"),
                                start_time=chunk_data.get("start_time"),
                                end_time=chunk_data.get("end_time"),
                                content_hash=chunk_data.get("content_hash") or ChunkingService.hash_content(chunk_data["content"]),
                            )
                        )
                mark_document_version(doc)
                return created
        return []

    @staticmethod
    def _query_chunk_card_counts(doc_id: int) -> dict[int, int]:
        """Compte les cartes liées par fragment en une seule requête GROUP BY."""
        rows = (
            NoteChunkLinkModel.select(
                NoteChunkLinkModel.chunk_id,
                fn.COUNT(NoteChunkLinkModel.id).alias("card_count"),
            )
            .join(DocumentChunkModel)
            .where(DocumentChunkModel.document_id == doc_id)
            .group_by(NoteChunkLinkModel.chunk_id)
        )
        return {int(r.chunk_id): int(r.card_count) for r in rows}

    @staticmethod
    def _group_chunks_by_unit(chunks: list[Any], unit_type: str) -> list[tuple[str, list[int]]]:
        """Regroupe les fragments par unité réelle de couverture (section ou page)."""
        groups: list[tuple[str, list[int]]] = []
        index: dict[tuple[str, str | int | None], int] = {}
        for chunk in chunks:
            if unit_type == "pages":
                key = ("page", chunk.page_number)
                label = f"Page {chunk.page_number}" if chunk.page_number else f"Section #{chunk.chunk_index + 1}"
            else:
                raw_heading = chunk.heading_path or (f"Page {chunk.page_number}" if chunk.page_number else f"Section #{chunk.chunk_index + 1}")
                # La version en base peut contenir des balises HTML résiduelles (<span page Marker>…)
                heading = MarkdownStructurer.clean_heading_title(raw_heading) or raw_heading
                key = ("heading", heading)
                label = heading
            if key in index:
                groups[index[key]][1].append(chunk.id)
            else:
                index[key] = len(groups)
                groups.append((label, [chunk.id]))
        return groups

    @staticmethod
    def _heading_coverage_keys(heading_path: str) -> list[str]:
        """Génère les clés (chemin brut, slugs) indexant la couverture d'une section."""
        parts = [p.strip() for p in heading_path.split(" > ") if p.strip()]
        if not parts:
            return []
        full_slug = " > ".join(MarkdownStructurer.slugify(p) for p in parts)
        leaf_raw = parts[-1]
        leaf_slug = MarkdownStructurer.slugify(leaf_raw)
        keys = [heading_path, full_slug, leaf_raw, leaf_slug]
        return list(dict.fromkeys(keys))

    def _current_selected_chapter_key(self) -> list[int] | None:
        item = self.chapters_list.currentItem()
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, list) else None

    def _apply_chapters_filter(self) -> None:
        mode = self.chapters_filter.currentIndex() if hasattr(self, "chapters_filter") else 0
        for i in range(self.chapters_list.count()):
            item = self.chapters_list.item(i)
            covered = item.data(Qt.ItemDataRole.UserRole + 1)
            if covered is None:
                item.setHidden(False)
                continue
            if mode == 1:
                item.setHidden(not covered)
            elif mode == 2:
                item.setHidden(covered)
            else:
                item.setHidden(False)

    def _set_coverage_bar_color(self, percent: int) -> None:
        if percent >= 100:
            color = DesignTokens.COLOR_GREEN
        elif percent >= 50:
            color = DesignTokens.COLOR_YELLOW
        else:
            color = DesignTokens.COLOR_RED
        self.coverage_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 3px;
            }}
        """)

    @Slot(QListWidgetItem)
    def _on_chapter_clicked(self, item: QListWidgetItem) -> None:
        chunk_ids = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(chunk_ids, list) or not chunk_ids:
            return
        chunk = DocumentChunkModel.get_or_none(DocumentChunkModel.id == chunk_ids[0])
        if chunk and chunk.start_time is not None and hasattr(self, "audio_player") and not self.audio_player.isHidden():
            self.audio_player.seek_seconds(chunk.start_time)
            return
        doc = DocumentModel.get_or_none(DocumentModel.id == self._current_doc_id)
        if chunk and chunk.heading_path and doc and (doc.file_type or "").lower() in ("md", "markdown", "txt", "text", "web"):
            self._navigate_editor_to_heading(chunk.heading_path)
            return
        if chunk and chunk.page_number and doc and doc.content:
            self._scroll_editor_to_page(chunk.page_number)

    def _navigate_editor_to_heading(self, heading_path: str) -> None:
        """Déplace le curseur de l'éditeur vers le titre correspondant à la section cliquée."""
        if not hasattr(self.text_editor, "editor") or not self.text_editor.editor:
            return
        content = self.text_editor.get_content() or ""
        outline = MarkdownStructurer.get_outline(content)
        target_parts = [MarkdownStructurer.slugify(p.strip()) for p in heading_path.split(" > ")]
        line_number: int | None = None
        for oi in outline:
            oi_parts = [MarkdownStructurer.slugify(p.strip()) for p in oi.breadcrumb.split(" > ")]
            if oi_parts == target_parts or (len(target_parts) == 1 and oi_parts and oi_parts[-1] == target_parts[0]):
                line_number = oi.line_number
                break
        if line_number is not None:
            self._on_outline_heading_selected(line_number)

    def _scroll_editor_to_page(self, page_number: int) -> None:
        """Fait défiler l'éditeur jusqu'au marqueur de page {N} correspondant."""
        if not hasattr(self.text_editor, "editor") or not self.text_editor.editor:
            return
        editor = self.text_editor.editor
        content = self.text_editor.get_content() or ""
        if not content:
            return
        explicit_pages = [int(m.group(1)) for m in ChunkingService._MARKER_PAGE_RE.finditer(content)]
        offset = 1 if explicit_pages and min(explicit_pages) == 0 else 0
        target = page_number - offset
        doc = editor.document()
        for i, line in enumerate(content.split("\n")):
            hit = ChunkingService._MARKER_PAGE_RE.search(line)
            if hit and int(hit.group(1)) == target:
                block = doc.findBlockByNumber(i)
                if block.isValid():
                    cursor = editor.textCursor()
                    cursor.setPosition(block.position())
                    editor.setTextCursor(cursor)
                    editor.centerCursor()
                    editor.setFocus()
                return

    @Slot()
    def _on_forge_selected_chapter(self) -> None:
        items = self.chapters_list.selectedItems()
        if not items:
            show_toast(self, "Veuillez sélectionner un chapitre dans le sommaire.", is_error=True)
            return

        chunk_ids = items[0].data(Qt.ItemDataRole.UserRole)
        if not isinstance(chunk_ids, list) or not chunk_ids:
            return

        chunk = DocumentChunkModel.get_or_none(DocumentChunkModel.id == chunk_ids[0])
        if not chunk:
            return

        doc = DocumentModel.get_or_none(DocumentModel.id == self._current_doc_id)
        doc_title = doc.title if doc else "Document"
        section_name = chunk.heading_path or (f"Page {chunk.page_number}" if chunk.page_number else f"Section #{chunk.chunk_index + 1}")

        self.request_navigation.emit(
            "creation",
            {
                "doc_id": self._current_doc_id,
                "text_source": chunk.content,
                "source_title": f"{doc_title} - {section_name}",
                "chunk_id": chunk.id,
                "page_number": chunk.page_number,
            },
        )

    @Slot()
    def _on_smart_align_document(self) -> None:
        if not self._current_doc_id:
            show_toast(self, "Veuillez sélectionner un document d'abord.", is_error=True)
            return

        from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService

        show_toast(self, "Synchronisation des fiches Anki via les tags en cours...")
        res = CoverageAlignmentService.align_document(self._current_doc_id)
        matched = res.get("matched_notes", 0)
        cov_pct = res.get("coverage_pct", 0.0)
        self._refresh_chapters_list()
        show_toast(self, f"✅ {matched} cartes synchronisées via les tags ! Couverture : {cov_pct:.0f}%")

    @Slot()
    def _on_import_from_other_profile(self) -> None:
        import sqlite3

        from ankiforge.services.profile_manager import ProfileManager
        from ankiforge.utils.paths import get_active_profile

        pm = ProfileManager()
        current_prof = get_active_profile()
        other_profiles = [p for p in pm.list_profiles() if p != current_prof]

        if not other_profiles:
            show_toast(self, "Aucun autre profil disponible pour importer des documents.", is_error=True)
            return

        src_prof, ok = QInputDialog.getItem(
            self,
            "Importer depuis un profil",
            "Sélectionnez le profil source :",
            other_profiles,
            0,
            False,
        )
        if not ok or not src_prof:
            return

        src_db = pm.get_db_path(src_prof)
        if not src_db.exists():
            show_toast(self, f"Base introuvable pour le profil {src_prof}.", is_error=True)
            return

        con = sqlite3.connect(src_db)
        cur = con.cursor()
        docs = cur.execute("SELECT id, title, file_type FROM documentmodel ORDER BY title").fetchall()
        con.close()

        if not docs:
            show_toast(self, f"Aucun document trouvé dans le profil '{src_prof}'.", is_error=True)
            return

        doc_choices = ["Tous les documents"] + [f"#{d[0]} : {d[1]} ({d[2]})" for d in docs]
        chosen_doc, ok_doc = QInputDialog.getItem(
            self,
            "Choisir le document",
            f"Documents disponibles dans '{src_prof}' :",
            doc_choices,
            0,
            False,
        )
        if not ok_doc or not chosen_doc:
            return

        from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService

        imported_count = 0
        if chosen_doc == "Tous les documents":
            for d in docs:
                new_doc = CoverageAlignmentService.copy_document_from_profile(src_prof, current_prof, d[0])
                if new_doc:
                    CoverageAlignmentService.align_document(new_doc.id)
                    imported_count += 1
        else:
            doc_id = int(chosen_doc.split(":")[0].replace("#", "").strip())
            new_doc = CoverageAlignmentService.copy_document_from_profile(src_prof, current_prof, doc_id)
            if new_doc:
                CoverageAlignmentService.align_document(new_doc.id)
                imported_count += 1

        self.refresh_data()
        show_toast(self, f"✅ {imported_count} document(s) importé(s) et aligné(s) avec succès !")

    @Slot()
    def _on_vectorize_rag(self) -> None:
        if not self._current_doc_id:
            show_toast(self, "Veuillez sélectionner un document à indexer.", is_error=True)
            return

        self.btn_rag.setEnabled(False)
        self.btn_rag.setText("Indexation RAG...")

        self._coverage_worker = CoverageWorker(document_id=self._current_doc_id, parent=self)
        self._coverage_worker.finished_processing.connect(self._on_vectorization_success)
        self._coverage_worker.error_occurred.connect(self._on_vectorization_error)
        self._coverage_worker.finished.connect(self._coverage_worker.deleteLater)
        self._coverage_worker.start()

    @Slot()
    def _on_vectorization_success(self) -> None:
        self.btn_rag.setEnabled(True)
        self.btn_rag.setText("Indexer (RAG)")
        show_toast(self, "Document indexé avec succès pour la recherche IA (RAG) !")
        self._refresh_chapters_list()
        self._update_rag_status_pill()
        if hasattr(self, "album_viewer"):
            self.album_viewer.refresh_pages()

    @Slot(str)
    def _on_vectorization_error(self, err: str) -> None:
        self.btn_rag.setEnabled(True)
        self.btn_rag.setText("Indexer (RAG)")
        show_toast(self, f"Échec de l'indexation RAG : {err}", is_error=True)

    @Slot()
    def _on_sandbox_search(self) -> None:
        if not self._current_doc_id:
            show_toast(self, "Veuillez d'abord sélectionner un document.", is_error=True)
            return

        query = self.rag_sandbox_input.text().strip()
        if not query:
            return

        self.rag_sandbox_results.clear()
        try:
            rag = RAGService()
            results = rag.search(self._current_doc_id, query, top_k=4)
            if not results:
                self.rag_sandbox_results.addItem(QListWidgetItem("Aucun fragment pertinent trouvé."))
                return

            for r in results:
                loc = r.get("heading_path") or (f"Page {r.get('page_number')}" if r.get("page_number") else f"Section #{r.get('chunk_index', 0) + 1}")
                rel_pct = r.get("relevance_pct", 0)
                if rel_pct == 0:
                    score_val = r.get("score", 1.0)
                    rel_pct = max(0, min(100, int((1.0 - min(score_val, 1.0)) * 100))) if score_val <= 1.0 else int(100 / (1.0 + score_val))

                content_snippet = r.get("content", "")[:160] + "..." if len(r.get("content", "")) > 160 else r.get("content", "")
                item_txt = f"📍 {loc} (Pertinence: {rel_pct}%)\n{content_snippet}"
                item = QListWidgetItem(item_txt)
                item.setData(Qt.ItemDataRole.UserRole, r)
                self.rag_sandbox_results.addItem(item)
                self.rag_sandbox_results.setItemWidget(item, _RAGResultWidget(r, query))

        except Exception as e:
            self.rag_sandbox_results.addItem(QListWidgetItem(f"Erreur recherche RAG : {e}"))

    def refresh_theme(self, profile: Any) -> None:
        if hasattr(self, "tree_explorer"):
            self.tree_explorer.setStyleSheet(f"""
                QTreeWidget {{
                    background-color: {profile.bg_panel};
                    border: 1px solid {profile.border_color};
                    border-radius: {profile.radius_sm}px;
                    color: {profile.text_primary};
                    padding: 4px;
                }}
                QTreeWidget::item {{
                    padding: 6px;
                    border-radius: 4px;
                }}
                QTreeWidget::item:hover {{
                    background-color: {profile.bg_hover};
                }}
                QTreeWidget::item:selected {{
                    background-color: {profile.bg_hover};
                    color: {profile.text_primary};
                }}
            """)

        if hasattr(self, "doc_page_frame"):
            self.doc_page_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {profile.bg_panel};
                    border: 1px solid {profile.border_color};
                    border-radius: {profile.radius_md}px;
                }}
            """)

        if hasattr(self, "doc_title_lbl"):
            self.doc_title_lbl.setStyleSheet(f"color: {profile.text_primary}; font-size: 18px; font-weight: bold; border-bottom: 1px solid {profile.border_color}; padding-bottom: 8px;")

        if hasattr(self, "coverage_card"):
            self.coverage_card.setStyleSheet(f"""
                QFrame {{
                    background-color: {profile.bg_panel};
                    border: 1px solid {profile.border_color};
                    border-radius: {profile.radius_md}px;
                }}
            """)

        if hasattr(self, "lbl_coverage_summary"):
            self.lbl_coverage_summary.setStyleSheet(f"color: {profile.text_primary}; font-weight: bold; font-size: 13px;")

        if hasattr(self, "coverage_bar"):
            self.coverage_bar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: {profile.bg_input};
                    border: 1px solid {profile.border_color};
                    border-radius: 4px;
                }}
                QProgressBar::chunk {{
                    background-color: {profile.color_green};
                    border-radius: 3px;
                }}
            """)

        if hasattr(self, "chapters_list"):
            self.chapters_list.setStyleSheet(f"""
                QListWidget {{
                    background-color: {profile.bg_panel};
                    border: 1px solid {profile.border_color};
                    border-radius: {profile.radius_sm}px;
                    color: {profile.text_primary};
                    padding: 4px;
                }}
                QListWidget::item {{
                    padding: 8px;
                    border-bottom: 1px solid {profile.border_color};
                    border-radius: 4px;
                    font-size: 11px;
                }}
                QListWidget::item:hover {{
                    background-color: {profile.bg_hover};
                }}
                QListWidget::item:selected {{
                    background-color: {profile.bg_hover};
                    color: {profile.text_primary};
                }}
            """)

        if hasattr(self, "rag_sandbox_results"):
            self.rag_sandbox_results.setStyleSheet(f"""
                QListWidget {{
                    background-color: {profile.bg_input};
                    border: 1px solid {profile.border_color};
                    border-radius: {profile.radius_sm}px;
                    padding: 4px;
                    color: {profile.text_primary};
                }}
                QListWidget::item {{
                    background-color: {profile.bg_panel};
                    border: 1px solid {profile.border_color};
                    border-radius: 6px;
                    margin-bottom: 6px;
                    padding: 8px;
                    font-size: 11px;
                }}
                QListWidget::item:hover {{
                    border-color: {profile.accent_primary};
                }}
            """)


DocumentsTab = DocumentsView
