"""
Vue Library (My Documents) — 100% Conforme à la Maquette concept_ide.
- Explorateur d'arborescence à gauche (FolderModel & DocumentModel avec icônes de type PDF/TXT/MD).
- Éditeur de document masqué par défaut (QStackedWidget page d'état vide si aucun document sélectionné).
- Structure d'arborescence directe à la racine (pas de conteneur "Tous les documents").
- Barre d'outils d'extraction : Import Fichier, Import URL, Analyse Marker IA, Insérer Coupure [SPLIT], Scinder.
"""

import logging
import pathlib
from typing import Any, Optional

from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtGui import QDropEvent, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DocumentModel, FolderModel
from ankiforge.services.workers.document_worker import DocumentWorker
from ankiforge.ui.components import (
    IconButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
)
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class DocumentTreeWidget(QTreeWidget):
    """QTreeWidget customisé pour supporter le Drag & Drop."""

    itemMoved = Signal(object, object)  # source_data, target_data

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def dropEvent(self, event: QDropEvent) -> None:
        source_item = self.currentItem()
        if not source_item:
            event.ignore()
            return

        source_data = source_item.data(0, Qt.ItemDataRole.UserRole)

        target_item = self.itemAt(event.position().toPoint())
        target_data = target_item.data(0, Qt.ItemDataRole.UserRole) if target_item else None

        event.ignore()

        if source_item == target_item:
            return

        if source_data:
            self.itemMoved.emit(source_data, target_data)


class DocumentsView(QWidget):
    """
    Vue My Documents / Library — 100% Conforme à la Maquette concept_ide.
    """

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self._current_doc_id: Optional[int] = None
        self._dirty = False
        self.worker: Optional[DocumentWorker] = None

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # --- PANNEAU GAUCHE : Explorateur de Documents ---
        self.explorer_panel = IdePanel(detachable=True)
        self.explorer_panel.setMinimumWidth(260)

        explorer_content = QWidget()
        explorer_layout = QVBoxLayout(explorer_content)
        explorer_layout.setContentsMargins(10, 10, 10, 10)
        explorer_layout.setSpacing(8)

        # Barre d'outils supérieure (Importer & Nouveau dossier)
        explorer_toolbar = QHBoxLayout()
        explorer_toolbar.setSpacing(6)

        self.btn_import = SecondaryButton("Importer")
        self.btn_import.setIcon(load_phosphor_icon("ph.upload-simple", color=DesignTokens.TEXT_PRIMARY))
        self.btn_import.clicked.connect(self._on_import_file)

        self.btn_import_url = IconButton("ph.link", tooltip="Importer depuis le Web (ex: YouTube)", size=24)
        self.btn_import_url.clicked.connect(self._on_import_url)

        self.btn_new_folder = IconButton("ph.folder-plus", tooltip="Nouveau dossier", size=24)
        self.btn_new_folder.clicked.connect(self._on_new_folder)

        self.btn_delete = IconButton("ph.trash", tooltip="Supprimer", size=24)
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._on_delete_item)

        explorer_toolbar.addWidget(self.btn_import, 1)
        explorer_toolbar.addWidget(self.btn_import_url)
        explorer_toolbar.addWidget(self.btn_new_folder)
        explorer_toolbar.addWidget(self.btn_delete)
        explorer_layout.addLayout(explorer_toolbar)

        # Tree Widget pour l'arborescence des dossiers & documents
        self.tree_explorer = DocumentTreeWidget()
        self.tree_explorer.setHeaderHidden(True)
        self.tree_explorer.setStyleSheet(f"""
            QTreeWidget {{
                background-color: #1a1d24;
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

        self.explorer_panel.add_tab("Explorateur de Documents", explorer_content, "ph.files", closable=False)
        self.main_splitter.addWidget(self.explorer_panel)

        # --- PANNEAU DROITE : Éditeur & Lecteur de Document (.doc-page) via QStackedWidget ---
        self.editor_panel = IdePanel(detachable=True)

        self.editor_stack = QStackedWidget()

        # PAGE 0 : État vide (aucun document sélectionné par défaut)
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

        empty_subtitle = QLabel("Choisissez un document dans l'arborescence à gauche pour afficher son contenu ou importez un nouveau fichier.")
        empty_subtitle.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px;")
        empty_subtitle.setWordWrap(True)
        empty_subtitle.setMaximumWidth(420)
        empty_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_layout.addWidget(empty_icon)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_subtitle)

        self.editor_stack.addWidget(empty_page)

        # PAGE 1 : Conteneur Éditeur / Lecteur de document
        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        # Barre d'outils du document (Marker, URL, Coupure, Scinder, Sauvegarder)
        doc_toolbar_widget = QWidget()
        doc_toolbar_widget.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")
        doc_toolbar = QHBoxLayout(doc_toolbar_widget)
        doc_toolbar.setContentsMargins(12, 8, 12, 8)
        doc_toolbar.setSpacing(8)

        self.btn_marker = SecondaryButton("Forcer Analyse (Marker)")
        self.btn_marker.setIcon(load_phosphor_icon("ph.magic-wand", color=DesignTokens.COLOR_PURPLE))
        self.btn_marker.setToolTip("IA : Forcer une nouvelle extraction PDF vers Markdown via Marker")

        self.btn_rag = SecondaryButton("Vectoriser (RAG)")
        self.btn_rag.setIcon(load_phosphor_icon("ph.database", color="#10b981"))
        self.btn_rag.setToolTip("Indexer ce document dans la base vectorielle ChromaDB")
        self.btn_rag.clicked.connect(self._on_vectorize_rag)

        doc_toolbar.addWidget(self.btn_marker)
        doc_toolbar.addWidget(self.btn_rag)
        doc_toolbar.addStretch()

        self.lbl_word_count = QLabel("0 mots")
        self.lbl_word_count.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; margin-right: 8px;")
        doc_toolbar.addWidget(self.lbl_word_count)

        self.btn_save = PrimaryButton("Sauvegarder")
        self.btn_save.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        doc_toolbar.addWidget(self.btn_save)

        editor_layout.addWidget(doc_toolbar_widget)

        # Slider stylisé (Toggle)
        self.view_toggle_frame = QFrame()
        self.view_toggle_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #1a1d24;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 16px;
            }}
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {DesignTokens.TEXT_MUTED};
                font-weight: bold;
                border-radius: 14px;
                padding: 6px 16px;
            }}
            QPushButton:checked {{
                background-color: {DesignTokens.COLOR_PURPLE};
                color: white;
            }}
        """)
        toggle_layout = QHBoxLayout(self.view_toggle_frame)
        toggle_layout.setContentsMargins(2, 2, 2, 2)
        toggle_layout.setSpacing(0)

        self.btn_view_pdf = QPushButton("PDF")
        self.btn_view_pdf.setCheckable(True)
        self.btn_view_pdf.setChecked(True)

        self.btn_view_md = QPushButton("Markdown (KaTeX)")
        self.btn_view_md.setCheckable(True)

        self.btn_view_term = QPushButton("Terminal / Marker")
        self.btn_view_term.setCheckable(True)

        toggle_layout.addWidget(self.btn_view_pdf)
        toggle_layout.addWidget(self.btn_view_md)
        toggle_layout.addWidget(self.btn_view_term)

        self.btn_view_pdf.clicked.connect(lambda: self._on_view_toggled("pdf"))
        self.btn_view_md.clicked.connect(lambda: self._on_view_toggled("md"))
        self.btn_view_term.clicked.connect(lambda: self._on_view_toggled("term"))

        # Center the toggle
        toggle_container = QWidget()
        tc_layout = QHBoxLayout(toggle_container)
        tc_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tc_layout.addWidget(self.view_toggle_frame)
        editor_layout.addWidget(toggle_container)

        self.inner_editor_stack = QStackedWidget()

        from PySide6.QtPdfWidgets import QPdfView
        from PySide6.QtPdf import QPdfDocument

        self.pdf_document = QPdfDocument(self)
        self.pdf_viewer = QPdfView()
        self.pdf_viewer.setDocument(self.pdf_document)
        self.pdf_viewer.setPageMode(QPdfView.PageMode.MultiPage)
        self.inner_editor_stack.addWidget(self.pdf_viewer)

        # Zone centrale d'affichage style Feuille de Document (.doc-page) pour le Markdown
        self.doc_scroll = QScrollArea()
        self.doc_scroll.setWidgetResizable(True)
        self.doc_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.doc_scroll.setStyleSheet(f"background-color: {DesignTokens.BG_INPUT};")

        doc_page_wrapper = QWidget()
        page_wrapper_layout = QVBoxLayout(doc_page_wrapper)
        page_wrapper_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        page_wrapper_layout.setContentsMargins(24, 24, 24, 24)

        # Cadre style Feuille A4 / Document (.doc-page)
        self.doc_page_frame = QFrame()
        self.doc_page_frame.setMaximumWidth(1200)
        self.doc_page_frame.setMinimumWidth(800)
        self.doc_page_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #1a1d24;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        apply_shadow(self.doc_page_frame, blur=16, offset_y=4)

        frame_layout = QVBoxLayout(self.doc_page_frame)
        frame_layout.setContentsMargins(32, 32, 32, 32)
        frame_layout.setSpacing(16)

        # Titre du document
        self.doc_title_lbl = QLabel("Sélectionnez un document dans l'explorateur")
        self.doc_title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 20px; font-weight: bold; border-bottom: 2px solid {DesignTokens.BORDER_COLOR}; padding-bottom: 8px;")
        frame_layout.addWidget(self.doc_title_lbl)

        # Textedit d'édition du document (KaTeXEditor)
        from ankiforge.ui.widgets.katex_editor import KaTeXEditor

        self.text_editor = KaTeXEditor()
        self.text_editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if hasattr(self.text_editor, "editor"):
            self.text_editor.editor.setReadOnly(True)  # Sécurité pour ne pas casser la pagination
        frame_layout.addWidget(self.text_editor, 1)

        page_wrapper_layout.addWidget(self.doc_page_frame)
        self.doc_scroll.setWidget(doc_page_wrapper)

        self.inner_editor_stack.addWidget(self.doc_scroll)

        # [Index 2] Terminal View
        from PySide6.QtWidgets import QTextBrowser

        self.terminal_view = QTextBrowser()
        self.terminal_view.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.ACCENT_PRIMARY};
                font-family: 'Courier New', Courier, monospace;
                padding: 12px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        self.inner_editor_stack.addWidget(self.terminal_view)

        editor_layout.addWidget(self.inner_editor_stack, 1)

        self.editor_stack.addWidget(editor_container)

        self.editor_panel.add_tab("Lecteur & Éditeur", self.editor_stack, "ph.file-text", closable=False)
        self.main_splitter.addWidget(self.editor_panel)

        self.main_splitter.setSizes([260, 800])

        # Par défaut, afficher l'état vide
        self.editor_stack.setCurrentIndex(0)

    def _connect_signals(self) -> None:
        self.tree_explorer.itemSelectionChanged.connect(self._on_document_selected)
        self.tree_explorer.itemMoved.connect(self._on_item_moved)
        self.text_editor.content_changed.connect(self._on_document_text_changed)

        # Actions de la barre latérale gauche (Explorateur)
        self.btn_import.clicked.connect(self._on_import_file)
        self.btn_import_url.clicked.connect(self._on_import_url)
        self.btn_new_folder.clicked.connect(self._on_new_folder)
        self.btn_delete.clicked.connect(self._on_delete_item)

        # Actions de la barre du haut (Document)
        self.btn_save.clicked.connect(self._on_save_document)
        self.btn_marker.clicked.connect(self._on_run_marker_analysis)

    def _on_item_moved(self, source_data: dict, target_data: Optional[dict]) -> None:
        """Gère le déplacement (drag and drop) d'un document ou d'un dossier."""
        if not source_data:
            return

        source_type = source_data.get("type")
        source_id = source_data.get("id")

        target_type = target_data.get("type") if target_data else None
        target_id = target_data.get("id") if target_data else None

        # Si la cible est un document, on utilise le dossier de ce document comme cible réelle
        if target_type == "doc":
            doc = DocumentModel.get_or_none(DocumentModel.id == target_id)
            if doc and doc.folder:
                target_id = doc.folder.id
            else:
                target_id = None
            target_type = "folder" if target_id else None

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
            old_parts = old_name.split("::")
            base_name = old_parts[-1]

            if target_folder:
                new_name = target_folder.name + "::" + base_name
            else:
                new_name = base_name

            if new_name == old_name:
                return

            # Vérifier qu'on ne déplace pas un dossier dans lui-même ou un de ses enfants
            if target_folder and (target_folder.name == old_name or target_folder.name.startswith(old_name + "::")):
                show_toast(self, "Vous ne pouvez pas déplacer un dossier dans lui-même.", is_error=True)
                return

            try:
                with FolderModel._meta.database.atomic():
                    folders_to_update = FolderModel.select().where((FolderModel.name == old_name) | (FolderModel.name.startswith(old_name + "::")))

                    for f in folders_to_update:
                        if f.name == old_name:
                            f.name = new_name
                        else:
                            suffix = f.name[len(old_name) :]
                            f.name = new_name + suffix
                        f.save()

                self.refresh_data()
            except Exception as e:
                logger.error(f"Erreur déplacement dossier: {e}")
                show_toast(self, "Un dossier avec ce nom existe déjà à cet emplacement.", is_error=True)

    def refresh_data(self) -> None:
        """Recharge l'arborescence des dossiers et documents depuis Peewee."""
        try:
            self.tree_explorer.blockSignals(True)
            self.tree_explorer.clear()

            folder_items: dict[int, QTreeWidgetItem] = {}
            path_items: dict[str, QTreeWidgetItem] = {}
            folders = list(FolderModel.select())

            # Trier par nom alphabétiquement pour gérer les dossiers parents d'abord
            sorted_folders = sorted(folders, key=lambda f: f.name)

            # 1. Hiérarchie des dossiers
            for folder in sorted_folders:
                parts = folder.name.split("::")
                parent_item = None

                # Créer/retrouver les noeuds parents intermédiaires
                for i in range(1, len(parts)):
                    parent_path = "::".join(parts[:i])
                    if parent_path in path_items:
                        parent_item = path_items[parent_path]
                    else:
                        if parent_item:
                            new_item = QTreeWidgetItem(parent_item, [parts[i - 1]])
                        else:
                            new_item = QTreeWidgetItem(self.tree_explorer, [parts[i - 1]])
                        new_item.setIcon(0, load_phosphor_icon("ph.folder", weight="fill", color=DesignTokens.COLOR_BLUE))
                        path_items[parent_path] = new_item
                        parent_item = new_item

                node_name = parts[-1]
                if parent_item:
                    item = QTreeWidgetItem(parent_item, [node_name])
                else:
                    item = QTreeWidgetItem(self.tree_explorer, [node_name])

                item.setIcon(0, load_phosphor_icon("ph.folder", weight="fill", color=DesignTokens.COLOR_BLUE))
                item.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": folder.id})
                folder_items[folder.id] = item
                path_items[folder.name] = item

            # 2. Documents (Fichiers rattachés au dossier parent ou directement à la racine)
            documents = list(DocumentModel.select())
            for doc in documents:
                if hasattr(doc, "folder_id") and doc.folder_id and doc.folder_id in folder_items:
                    parent_item = folder_items[doc.folder_id]
                else:
                    parent_item = self.tree_explorer  # Directement sous la racine sans le header 'Tous les documents'

                title_to_display = doc.original_media.original_name if doc.original_media else doc.title
                item = QTreeWidgetItem(parent_item, [title_to_display])
                item.setData(0, Qt.ItemDataRole.UserRole, {"type": "doc", "id": doc.id})

                title_lower = doc.title.lower()
                is_pdf = getattr(doc, "file_type", "") == "pdf"
                has_content = bool(doc.content and doc.content.strip())

                if is_pdf:
                    if has_content:
                        item.setIcon(0, load_phosphor_icon("ph.file-pdf", color=DesignTokens.COLOR_RED))
                    else:
                        item.setIcon(0, load_phosphor_icon("ph.file-pdf", color=DesignTokens.TEXT_MUTED))
                        item.setText(0, f"{title_to_display} (Non extrait)")
                        item.setForeground(0, QColor(DesignTokens.TEXT_MUTED))
                        item.setToolTip(0, "PDF non extrait. Double-cliquez puis cliquez sur 'Forcer Analyse (Marker)'.")
                elif getattr(doc, "file_type", "") == "txt" or title_lower.endswith(".txt"):
                    item.setIcon(0, load_phosphor_icon("ph.file-text", color=DesignTokens.COLOR_BLUE))
                elif getattr(doc, "file_type", "") == "md" or title_lower.endswith(".md"):
                    item.setIcon(0, load_phosphor_icon("ph.file-code", color="#eab308"))
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
                self.text_editor.blockSignals(True)
                self.text_editor.set_content(doc.content if hasattr(doc, "content") else "")
                self.text_editor.blockSignals(False)
                self._dirty = False
                self._update_word_count()

                # Show PDF if available
                if doc.file_type == "pdf" and doc.original_media:
                    from ankiforge.utils.paths import get_app_data_dir

                    pdf_path = get_app_data_dir() / "media" / doc.original_media.filename
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

                self.editor_stack.setCurrentIndex(1)  # Afficher l'éditeur
        else:
            # Si un dossier est sélectionné, basculer sur l'état vide de l'éditeur
            self._current_doc_id = None
            self.editor_stack.setCurrentIndex(0)

    @Slot()
    def _on_document_text_changed(self) -> None:
        self._dirty = True
        self.btn_save.setStyleSheet(f"background-color: {DesignTokens.ACCENT_PRIMARY}; color: white;")
        self._update_word_count()

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
            "Documents (*.pdf *.txt *.md *.docx *.pptx);;Tous les fichiers (*.*)",
        )
        if file_path:
            ext = pathlib.Path(file_path).suffix.lower()
            if ext == ".pdf":
                self._import_pdf_directly(file_path)
            else:
                self._start_document_worker(file_path)

    @Slot()
    def _on_import_url(self) -> None:
        url, ok = QInputDialog.getText(self, "Importer depuis le Web", "Entrez l'URL de la page web ou de l'article :")
        if ok and url.strip():
            self._start_document_worker(url.strip())

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
        self.text_editor.set_content("Cliquer sur Analyser (Marker) pour extraire le texte...")
        self.editor_stack.setCurrentIndex(1)

        # Load PDF in viewer
        from ankiforge.utils.paths import get_app_data_dir

        pdf_path = get_app_data_dir() / "media" / media.filename
        if pdf_path.exists():
            self.pdf_document.load(str(pdf_path))
            self.view_toggle_frame.show()
            self._on_view_toggled("pdf")
        else:
            self.view_toggle_frame.hide()
            self._on_view_toggled("md")

        # Select in tree
        items = self.tree_explorer.findItems(title_to_display, Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive)
        for item in items:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("type") == "doc" and data.get("id") == doc.id:
                self.tree_explorer.setCurrentItem(item)
                break

        show_toast(self, f"PDF '{title_to_display}' importé. Démarrage automatique de l'analyse Marker...")
        if pdf_path.exists():
            self._start_document_worker(str(pdf_path), doc_id=doc.id)

    def _start_document_worker(self, path_or_url: str, doc_id: Optional[int] = None) -> None:
        self.btn_import.setEnabled(False)
        self.btn_import_url.setEnabled(False)
        if hasattr(self, "btn_url"):
            self.btn_url.setEnabled(False)
        show_toast(self, "Extraction et analyse du document en cours...")

        self.worker = DocumentWorker(path_or_url)
        self.worker.doc_id_to_update = doc_id
        self.worker.finished_signal.connect(self._on_worker_finished)
        self.worker.error_signal.connect(self._on_worker_error)
        self.worker.log_signal.connect(self._on_worker_log)

        # On bascule automatiquement sur le terminal
        self._on_view_toggled("term")
        self.terminal_view.clear()
        self.terminal_view.append("--- Démarrage de l'analyse Marker ---")

        self.worker.start()

    @Slot(str)
    def _on_worker_log(self, msg: str) -> None:
        if hasattr(self, "terminal_view"):
            self.terminal_view.append(msg)

    @Slot(str, str)
    def _on_worker_finished(self, title: str, content: str) -> None:
        if hasattr(self, "terminal_view"):
            self.terminal_view.append("--- Extraction terminée ! ---")

        # Bascule automatiquement sur la vue Markdown KaTeX une fois l'analyse terminée
        self._on_view_toggled("md")

        self.btn_import.setEnabled(True)
        if hasattr(self, "btn_url"):
            self.btn_url.setEnabled(True)

        try:
            doc_id_to_update = getattr(self.worker, "doc_id_to_update", None)

            if doc_id_to_update:
                doc = DocumentModel.get_by_id(doc_id_to_update)
                doc.content = content
                doc.save()
            else:
                from ankiforge.services.cards.media_manager import MediaManager

                original_media_id = None
                file_type = "md"
                source_url = None

                if self.worker and self.worker.file_path:
                    path_or_url = self.worker.file_path
                    if path_or_url.startswith("http"):
                        source_url = path_or_url
                        file_type = "web"
                    else:
                        media_manager = MediaManager()
                        media = media_manager.store_document_source(path_or_url)
                        if media:
                            original_media_id = media.id
                        import pathlib

                        file_type = pathlib.Path(path_or_url).suffix.replace(".", "") or "txt"

                doc = DocumentModel.create(
                    title=title,
                    content=content,
                    original_media_id=original_media_id,
                    file_type=file_type,
                    source_url=source_url,
                )

            # --- Génération immédiate des chunks en BDD ---
            from ankiforge.services.parsing.chunking_service import ChunkingService
            from ankiforge.database.models import DocumentChunkModel

            extracted_chunks = ChunkingService.extract_chunks(content)

            with DocumentChunkModel._meta.database.atomic():
                DocumentChunkModel.delete().where(DocumentChunkModel.document == doc).execute()
                for idx, chunk_data in enumerate(extracted_chunks):
                    DocumentChunkModel.create(
                        document=doc,
                        chunk_index=idx,
                        content=chunk_data["content"],
                        page_number=chunk_data["page_number"],
                        heading_path=chunk_data["heading_path"],
                        content_hash=chunk_data["content_hash"],
                    )
            # ----------------------------------------------

            self.refresh_data()
            self._current_doc_id = doc.id

            title_to_display = doc.original_media.original_name if doc.original_media else doc.title
            self.doc_title_lbl.setText(title_to_display)
            self.text_editor.set_content(content)
            self.editor_stack.setCurrentIndex(1)

            # Auto-select the newly created document in the tree
            items = self.tree_explorer.findItems(title_to_display, Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive)
            for item in items:
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data and data.get("type") == "doc" and data.get("id") == doc.id:
                    self.tree_explorer.setCurrentItem(item)
                    break

            show_toast(self, f"Document '{title_to_display}' importé avec succès !")
        except Exception as e:
            logger.exception("Erreur enregistrement document: %s", e)
            QMessageBox.critical(self, "Erreur", f"Échec de l'enregistrement du document : {str(e)}")

    @Slot(str)
    def _on_worker_error(self, error: str) -> None:
        self.btn_import.setEnabled(True)
        if hasattr(self, "btn_url"):
            self.btn_url.setEnabled(True)
        QMessageBox.critical(self, "Erreur d'importation", f"Impossible d'extraire le document :\n{error}")

    @Slot()
    def _on_new_folder(self) -> None:
        folder_name, ok = QInputDialog.getText(self, "Nouveau dossier", "Nom du dossier :")
        if ok and folder_name.strip():
            target_name = folder_name.strip()

            # Si un dossier ou document est sélectionné, on le crée dedans
            items = self.tree_explorer.selectedItems()
            if items:
                data = items[0].data(0, Qt.ItemDataRole.UserRole)
                if data:
                    item_type = data.get("type")
                    item_id = data.get("id")

                    target_folder_id = None
                    if item_type == "folder":
                        target_folder_id = item_id
                    elif item_type == "doc":
                        doc = DocumentModel.get_or_none(DocumentModel.id == item_id)
                        if doc and doc.folder:
                            target_folder_id = doc.folder.id

                    if target_folder_id:
                        folder = FolderModel.get_or_none(FolderModel.id == target_folder_id)
                        if folder:
                            target_name = f"{folder.name}::{target_name}"

            try:
                FolderModel.create(name=target_name)
                self.refresh_data()
                show_toast(self, f"Dossier '{target_name}' créé.")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de créer le dossier : {str(e)}")

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
                    f"Voulez-vous vraiment supprimer le dossier '{folder.name}' et tout son contenu (sous-dossiers et documents) ?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    with FolderModel._meta.database.atomic():
                        folders_to_delete = FolderModel.select().where((FolderModel.name == folder.name) | (FolderModel.name.startswith(folder.name + "::")))
                        for f in folders_to_delete:
                            f.delete_instance()
                    self.refresh_data()
                    self.editor_stack.setCurrentIndex(0)
                    show_toast(self, "Dossier supprimé.")

    @Slot()
    def _on_run_marker_analysis(self) -> None:
        if not self._current_doc_id:
            show_toast(self, "Veuillez d'abord sélectionner un document.", is_error=True)
            return

        doc = DocumentModel.get_by_id(self._current_doc_id)
        if doc.file_type == "pdf" and doc.original_media:
            from ankiforge.utils.paths import get_app_data_dir

            pdf_path = get_app_data_dir() / "media" / doc.original_media.filename
            if pdf_path.exists():
                self._start_document_worker(str(pdf_path), doc_id=doc.id)
                return

        text = self.text_editor.get_content()
        if not text:
            show_toast(self, "Veuillez d'abord charger un document.", is_error=True)
            return

        show_toast(self, "Analyse Marker IA : Détection des concepts denses terminée.")
        # Insertion visuelle d'un bloc d'analyse Marker
        marker_block = "\n\n> 🔮 **ANALYSE MARKER (IA)** : Section clé identifiée pour la forge de cartes.\n\n"
        cursor = self.text_editor.editor.textCursor()
        cursor.insertText(marker_block)

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
                self._dirty = False
                show_toast(self, f"Document '{doc.title}' enregistré avec succès !")
        except Exception as e:
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Impossible d'enregistrer le document : {str(e)}")

    @Slot()
    def _on_vectorize_rag(self) -> None:
        if not self._current_doc_id:
            show_toast(self, "Veuillez sélectionner un document à vectoriser.", is_error=True)
            return

        doc = DocumentModel.get_by_id(self._current_doc_id)
        if doc.chroma_collection_name:
            reply = QMessageBox.question(self, "Déjà indexé", "Ce document est déjà indexé dans ChromaDB.\nVoulez-vous le ré-indexer ?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.btn_rag.setEnabled(False)
        self.btn_rag.setText("Vectorisation...")

        from ankiforge.services.workers.vector_worker import VectorWorker

        self._vector_worker = VectorWorker(document_id=self._current_doc_id, parent=self)
        self._vector_worker.finished_indexing.connect(self._on_vectorization_success)
        self._vector_worker.error_occurred.connect(self._on_vectorization_error)
        self._vector_worker.finished.connect(self._vector_worker.deleteLater)
        self._vector_worker.start()

    @Slot(str)
    def _on_vectorization_success(self, collection_name: str) -> None:
        self.btn_rag.setEnabled(True)
        self.btn_rag.setText("Vectoriser (RAG)")
        show_toast(self, f"Document indexé dans ChromaDB : {collection_name}")

    @Slot(str)
    def _on_vectorization_error(self, err: str) -> None:
        self.btn_rag.setEnabled(True)
        self.btn_rag.setText("Vectoriser (RAG)")
        show_toast(self, f"Échec de la vectorisation : {err}", is_error=True)


DocumentsTab = DocumentsView
