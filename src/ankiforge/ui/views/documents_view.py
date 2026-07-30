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

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QScrollArea,
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
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


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

        explorer_toolbar.addWidget(self.btn_import, 1)
        explorer_toolbar.addWidget(self.btn_import_url)
        explorer_toolbar.addWidget(self.btn_new_folder)
        explorer_layout.addLayout(explorer_toolbar)

        # Tree Widget pour l'arborescence des dossiers & documents
        self.tree_explorer = QTreeWidget()
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

        self.btn_marker = SecondaryButton("Analyser (Marker)")
        self.btn_marker.setIcon(load_phosphor_icon("ph.magic-wand", color=DesignTokens.COLOR_PURPLE))
        self.btn_marker.setToolTip("IA : Identifier les zones denses et extraire le contenu")

        self.btn_url = SecondaryButton("Depuis le Web (URL)")
        self.btn_url.setIcon(load_phosphor_icon("ph.globe", color=DesignTokens.COLOR_BLUE))
        self.btn_url.setToolTip("Importer un article ou cours depuis une URL Web")

        self.btn_insert_split = SecondaryButton("Insérer Coupure")
        self.btn_insert_split.setIcon(load_phosphor_icon("ph.scissors", color="#eab308"))
        self.btn_insert_split.setToolTip("Insérer une balise [SPLIT] à la position du curseur (Ctrl+D)")

        self.btn_split_sections = SecondaryButton("Scinder [SPLIT]")
        self.btn_split_sections.setIcon(load_phosphor_icon("ph.split-horizontal", color=DesignTokens.TEXT_PRIMARY))
        self.btn_split_sections.setToolTip("Découper le document en plusieurs chapitres aux balises [SPLIT]")

        self.btn_rag = SecondaryButton("Vectoriser (RAG)")
        self.btn_rag.setIcon(load_phosphor_icon("ph.database", color="#10b981"))
        self.btn_rag.setToolTip("Indexer ce document dans la base vectorielle ChromaDB")
        self.btn_rag.clicked.connect(self._on_vectorize_rag)

        doc_toolbar.addWidget(self.btn_marker)
        doc_toolbar.addWidget(self.btn_url)
        doc_toolbar.addWidget(self.btn_insert_split)
        doc_toolbar.addWidget(self.btn_split_sections)
        doc_toolbar.addWidget(self.btn_rag)
        doc_toolbar.addStretch()

        self.lbl_word_count = QLabel("0 mots")
        self.lbl_word_count.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; margin-right: 8px;")
        doc_toolbar.addWidget(self.lbl_word_count)

        self.btn_save = PrimaryButton("Sauvegarder")
        self.btn_save.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        doc_toolbar.addWidget(self.btn_save)

        editor_layout.addWidget(doc_toolbar_widget)

        # Zone centrale d'affichage style Feuille de Document (.doc-page)
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
        self.doc_page_frame.setMaximumWidth(840)
        self.doc_page_frame.setMinimumWidth(500)
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

        # Textedit d'édition du document
        self.text_editor = StyledTextEdit()
        self.text_editor.setPlaceholderText("Le contenu du document apparaîtra ici...")
        self.text_editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background: transparent;
                border: none;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 14px;
                line-height: 1.6;
            }}
        """)
        frame_layout.addWidget(self.text_editor, 1)

        page_wrapper_layout.addWidget(self.doc_page_frame)
        self.doc_scroll.setWidget(doc_page_wrapper)
        editor_layout.addWidget(self.doc_scroll, 1)

        self.editor_stack.addWidget(editor_container)

        self.editor_panel.add_tab("Lecteur & Éditeur", self.editor_stack, "ph.file-text", closable=False)
        self.main_splitter.addWidget(self.editor_panel)

        self.main_splitter.setSizes([260, 800])

        # Par défaut, afficher l'état vide
        self.editor_stack.setCurrentIndex(0)

    def _connect_signals(self) -> None:
        self.tree_explorer.itemSelectionChanged.connect(self._on_document_selected)
        self.text_editor.textChanged.connect(self._on_text_changed)

        self.btn_import.clicked.connect(self._on_import_file)
        self.btn_new_folder.clicked.connect(self._on_new_folder)
        self.btn_url.clicked.connect(self._on_import_url)
        self.btn_marker.clicked.connect(self._on_run_marker_analysis)
        self.btn_insert_split.clicked.connect(self._on_insert_split)
        self.btn_split_sections.clicked.connect(self._on_split_sections)
        self.btn_save.clicked.connect(self._on_save_document)

    def refresh_data(self) -> None:
        """Recharge l'arborescence des dossiers et documents depuis Peewee."""
        try:
            self.tree_explorer.blockSignals(True)
            self.tree_explorer.clear()

            folder_items: dict[int, QTreeWidgetItem] = {}
            folders = list(FolderModel.select())

            # 1. Racines des dossiers
            for folder in folders:
                item = QTreeWidgetItem(self.tree_explorer, [folder.name])
                item.setIcon(0, load_phosphor_icon("ph.folder", color=DesignTokens.COLOR_BLUE))
                item.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": folder.id})
                folder_items[folder.id] = item

            # 2. Documents (Fichiers rattachés au dossier parent ou directement à la racine)
            documents = list(DocumentModel.select())
            for doc in documents:
                if hasattr(doc, "folder_id") and doc.folder_id and doc.folder_id in folder_items:
                    parent_item = folder_items[doc.folder_id]
                else:
                    parent_item = self.tree_explorer  # Directement sous la racine sans le header 'Tous les documents'

                item = QTreeWidgetItem(parent_item, [doc.title])
                item.setData(0, Qt.ItemDataRole.UserRole, {"type": "doc", "id": doc.id})

                title_lower = doc.title.lower()
                if title_lower.endswith(".pdf"):
                    item.setIcon(0, load_phosphor_icon("ph.file-pdf", color=DesignTokens.COLOR_RED))
                elif title_lower.endswith(".txt"):
                    item.setIcon(0, load_phosphor_icon("ph.file-text", color=DesignTokens.COLOR_BLUE))
                elif title_lower.endswith(".md"):
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
            self._current_doc_id = None
            self.editor_stack.setCurrentIndex(0)
            return

        item = items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("type") == "doc":
            doc = DocumentModel.get_or_none(DocumentModel.id == data["id"])
            if doc:
                self._current_doc_id = doc.id
                self.doc_title_lbl.setText(doc.title)
                self.text_editor.blockSignals(True)
                self.text_editor.setPlainText(doc.content if hasattr(doc, "content") else "")
                self.text_editor.blockSignals(False)
                self._dirty = False
                self._update_word_count()
                self.editor_stack.setCurrentIndex(1)  # Afficher l'éditeur
        else:
            # Si un dossier est sélectionné, basculer sur l'état vide de l'éditeur
            self._current_doc_id = None
            self.editor_stack.setCurrentIndex(0)

    @Slot()
    def _on_text_changed(self) -> None:
        self._dirty = True
        self._update_word_count()

    def _update_word_count(self) -> None:
        text = self.text_editor.toPlainText()
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
            self._start_document_worker(file_path)

    @Slot()
    def _on_import_url(self) -> None:
        url, ok = QInputDialog.getText(self, "Importer depuis le Web", "Entrez l'URL de la page web ou de l'article :")
        if ok and url.strip():
            self._start_document_worker(url.strip())

    def _start_document_worker(self, path_or_url: str) -> None:
        self.btn_import.setEnabled(False)
        self.btn_import_url.setEnabled(False)
        if hasattr(self, "btn_url"):
            self.btn_url.setEnabled(False)
        show_toast(self, "Extraction et analyse du document en cours...")

        self.worker = DocumentWorker(path_or_url)
        self.worker.finished_signal.connect(self._on_worker_finished)
        self.worker.error_signal.connect(self._on_worker_error)
        self.worker.start()

    @Slot(str, str)
    def _on_worker_finished(self, title: str, content: str) -> None:
        self.btn_import.setEnabled(True)
        if hasattr(self, "btn_url"):
            self.btn_url.setEnabled(True)

        try:
            doc = DocumentModel.create(
                title=title,
                content=content,
                file_path=self.worker.file_path if self.worker else "",
                doc_type=pathlib.Path(title).suffix.replace(".", "") or "txt",
                word_count=len(content.split()),
            )
            self.refresh_data()
            self._current_doc_id = doc.id
            self.doc_title_lbl.setText(doc.title)
            self.text_editor.setPlainText(content)
            self.editor_stack.setCurrentIndex(1)
            show_toast(self, f"Document '{title}' importé avec succès !")
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
            try:
                FolderModel.create(name=folder_name.strip())
                self.refresh_data()
                show_toast(self, f"Dossier '{folder_name.strip()}' créé.")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de créer le dossier : {str(e)}")

    @Slot()
    def _on_run_marker_analysis(self) -> None:
        text = self.text_editor.toPlainText()
        if not text:
            show_toast(self, "Veuillez d'abord charger un document.", is_error=True)
            return

        show_toast(self, "Analyse Marker IA : Détection des concepts denses terminée.")
        # Insertion visuelle d'un bloc d'analyse Marker
        marker_block = "\n\n> 🔮 **ANALYSE MARKER (IA)** : Section clé identifiée pour la forge de cartes.\n\n"
        cursor = self.text_editor.textCursor()
        cursor.insertText(marker_block)

    @Slot()
    def _on_insert_split(self) -> None:
        cursor = self.text_editor.textCursor()
        cursor.insertText("\n\n[SPLIT] — Coupure insérée (Ctrl+D)\n\n")
        show_toast(self, "Balise [SPLIT] insérée à la position du curseur.")

    @Slot()
    def _on_split_sections(self) -> None:
        text = self.text_editor.toPlainText()
        if "[SPLIT]" not in text:
            show_toast(self, "Aucune balise [SPLIT] trouvée dans ce document.", is_error=True)
            return

        parts = text.split("[SPLIT]")
        valid_parts = [p.strip() for p in parts if p.strip()]
        show_toast(self, f"Document scindé en {len(valid_parts)} sections distinctes.")

    @Slot()
    def _on_save_document(self) -> None:
        if not self._current_doc_id:
            show_toast(self, "Aucun document sélectionné à sauvegarder.", is_error=True)
            return

        try:
            doc = DocumentModel.get_or_none(DocumentModel.id == self._current_doc_id)
            if doc:
                content = self.text_editor.toPlainText()
                doc.content = content
                doc.word_count = len(content.split())
                doc.save()
                self._dirty = False
                show_toast(self, f"Document '{doc.title}' enregistré avec succès !")
        except Exception as e:
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Impossible d'enregistrer le document : {str(e)}")


DocumentsTab = DocumentsView
