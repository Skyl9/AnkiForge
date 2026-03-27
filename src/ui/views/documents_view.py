# src/ui/views/documents_view.py
import os
import re

import markdown
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QFont, QColor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
                               QTextEdit, QPushButton, QLabel, QSplitter,
                               QFileDialog, QMessageBox, QInputDialog, QAbstractItemView, QTabWidget)

from src.database.models import db, DocumentModel, FolderModel
from src.services.parsing.document_parser import DocumentParser


# ==========================================
# COLORATION SYNTAXIQUE MARKDOWN
# ==========================================
class MarkdownHighlighter(QSyntaxHighlighter):
    """Applique des couleurs au texte Markdown en direct."""

    def __init__(self, document):
        super().__init__(document)
        self.rules = []

        # Titres (# Titre)
        header_format = QTextCharFormat()
        header_format.setFontWeight(QFont.Bold)
        header_format.setForeground(QColor("#569CD6"))  # Bleu doux
        self.rules.append((r"^(#+)(.*)", header_format))

        # Gras (**texte**)
        bold_format = QTextCharFormat()
        bold_format.setFontWeight(QFont.Bold)
        bold_format.setForeground(QColor("#CE9178"))  # Orange
        self.rules.append((r"\*\*(.*?)\*\*", bold_format))

        # Italique (*texte*)
        italic_format = QTextCharFormat()
        italic_format.setFontItalic(True)
        italic_format.setForeground(QColor("#CE9178"))
        self.rules.append((r"\*(.*?)\*", italic_format))

        # Maths LaTeX ($...$ ou $$...$$)
        math_format = QTextCharFormat()
        math_format.setForeground(QColor("#4EC9B0"))  # Vert turquoise
        self.rules.append((r"(\$\$.*?\$\$|\$.*?\$)", math_format))

        # Images (![alt](url))
        img_format = QTextCharFormat()
        img_format.setForeground(QColor("#C586C0"))  # Violet
        self.rules.append((r"!\[.*?\]\(.*?\)", img_format))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


class DraggableTreeWidget(QTreeWidget):
    """Un arbre personnalisé qui gère parfaitement le glisser-déposer en BDD."""
    doc_moved = Signal(int, object)  # Emet l'ID du document et le nouvel ID du dossier

    def dropEvent(self, event):
        dragged_item = self.currentItem()
        if not dragged_item:
            super().dropEvent(event)
            return

        # On vérifie qu'on déplace bien un document et pas un dossier
        data = dragged_item.data(0, Qt.UserRole)
        if not data or data.get("type") != "doc":
            event.ignore()
            return

        # On laisse l'interface faire le déplacement visuel
        super().dropEvent(event)

        # On regarde qui est le nouveau parent APRES le déplacement visuel
        new_parent = dragged_item.parent()
        new_folder_id = None

        if new_parent:
            parent_data = new_parent.data(0, Qt.UserRole)
            if parent_data and parent_data.get("type") == "folder":
                new_folder_id = parent_data.get("id")

        # On envoie le signal à la base de données
        self.doc_moved.emit(data.get("id"), new_folder_id)


# ==========================================
# THREAD D'EXTRACTION MARKER
# ==========================================
class ParserWorker(QThread):
    finished_signal = Signal(str, str)
    error_signal = Signal(str)

    def __init__(self, file_path: str, parser: DocumentParser):
        super().__init__()
        self.file_path = file_path
        self.parser = parser

    def run(self):
        try:
            title = os.path.basename(self.file_path)
            content = self.parser.parse_document(self.file_path)
            self.finished_signal.emit(title, content)
        except Exception as e:
            self.error_signal.emit(str(e))


class DocumentsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.current_folder_id_for_import = None
        self.current_doc_id_editing = None

        self.layout = QVBoxLayout(self)

        # --- En-tête ---
        header_layout = QHBoxLayout()
        title = QLabel("<b>📚 Bibliothèque de Cours</b>")
        title.setStyleSheet("font-size: 20px;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.btn_import = QPushButton("📄 Analyser un PDF/TXT (Marker)")
        self.btn_import.setStyleSheet("background-color: #3F51B5; color: white; font-weight: bold; padding: 6px;")
        self.btn_import.clicked.connect(self.import_document)
        header_layout.addWidget(self.btn_import)

        self.layout.addLayout(header_layout)

        # --- Contenu Principal ---
        splitter = QSplitter(Qt.Horizontal)

        # --- Panneau Gauche : L'arborescence ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        self.btn_new_folder = QPushButton("📁 Dossier")
        self.btn_new_folder.clicked.connect(self.create_folder)

        self.btn_new_doc = QPushButton("📄 Doc")
        self.btn_new_doc.clicked.connect(self.create_manual_document)

        self.btn_delete = QPushButton("🗑️")
        self.btn_delete.setStyleSheet("color: #F44336; font-weight: bold;")
        self.btn_delete.clicked.connect(self.delete_item)

        toolbar.addWidget(self.btn_new_folder)
        toolbar.addWidget(self.btn_new_doc)
        toolbar.addWidget(self.btn_delete)
        left_layout.addLayout(toolbar)

        self.tree = DraggableTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setDragDropMode(QAbstractItemView.InternalMove)

        self.tree.doc_moved.connect(self._on_document_moved)
        self.tree.itemClicked.connect(self.on_item_selected)

        left_layout.addWidget(self.tree)
        splitter.addWidget(left_panel)

        # --- Panneau Droit : Éditeur & Rendu ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        editor_toolbar = QHBoxLayout()
        self.lbl_doc_title = QLabel("<b>Aucun document sélectionné</b>")
        editor_toolbar.addWidget(self.lbl_doc_title)
        editor_toolbar.addStretch()

        self.btn_save_doc = QPushButton("💾 Sauvegarder les modifications")
        self.btn_save_doc.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.btn_save_doc.clicked.connect(self.save_document_edits)
        self.btn_save_doc.setEnabled(False)
        editor_toolbar.addWidget(self.btn_save_doc)

        right_layout.addLayout(editor_toolbar)

        # 👇 NOUVEAU : Système d'onglets pour séparer Code et Rendu 👇
        self.editor_tabs = QTabWidget()

        # Onglet 1 : Éditeur Code
        self.preview_text = QTextEdit()
        self.preview_text.setStyleSheet(
            "background-color: #1E1E1E; color: #D4D4D4; font-family: 'Consolas', monospace; font-size: 14px;")
        self.highlighter = MarkdownHighlighter(self.preview_text.document())  # Coloration activée !
        self.preview_text.textChanged.connect(
            lambda: self.btn_save_doc.setEnabled(self.current_doc_id_editing is not None))

        # Onglet 2 : Rendu Web
        self.render_view = QWebEngineView()

        self.editor_tabs.addTab(self.preview_text, "📝 Éditeur Markdown")
        self.editor_tabs.addTab(self.render_view, "👁️ Aperçu du Document")

        # Quand on clique sur l'onglet Aperçu, on génère le HTML
        self.editor_tabs.currentChanged.connect(self.on_tab_changed)

        right_layout.addWidget(self.editor_tabs)
        splitter.addWidget(right_panel)
        splitter.setSizes([250, 750])

        self.layout.addWidget(splitter)
        self.load_tree()

    # ==========================================
    # LOGIQUE D'AFFICHAGE & RENDU
    # ==========================================

    def on_tab_changed(self, index: int) -> None:
        """Génère le rendu HTML seulement quand on clique sur l'onglet Aperçu."""
        if index == 1 and self.current_doc_id_editing:
            raw_md = self.preview_text.toPlainText()

            # Conversion Markdown -> HTML (gère les balises HTML existantes comme <img>)
            html_content = markdown.markdown(raw_md, extensions=['tables', 'fenced_code'])

            # Injection de MathJax et d'un joli style CSS
            final_html = f"""
            <html><head><meta charset="utf-8">
            <script>
                window.MathJax = {{ tex: {{ inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']] }} }};
            </script>
            <script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; padding: 20px; line-height: 1.6; color: #333; }}
                h1, h2, h3 {{ color: #2c3e50; border-bottom: 1px solid #eee; padding-bottom: 5px; }}
                img {{ max-width: 100%; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
                code {{ background-color: #f4f4f4; padding: 2px 4px; border-radius: 3px; font-family: monospace; }}
                pre code {{ display: block; padding: 10px; overflow-x: auto; }}
            </style>
            </head><body>
            {html_content}
            </body></html>
            """

            # On donne à Chromium le droit de lire le dossier media pour afficher les images !
            BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            media_dir = os.path.join(BASE_DIR, 'data', 'media')
            if not media_dir.endswith(os.sep): media_dir += os.sep
            base_url = QUrl.fromLocalFile(media_dir)

            self.render_view.setHtml(final_html, base_url)

    def load_tree(self) -> None:
        self.tree.clear()

        folders = FolderModel.select().order_by(FolderModel.name)
        for folder in folders:
            folder_item = QTreeWidgetItem(self.tree, [f"📂 {folder.name}"])
            folder_item.setData(0, Qt.UserRole, {"type": "folder", "id": folder.id})
            folder_item.setFlags(folder_item.flags() | Qt.ItemIsDropEnabled)

            docs = DocumentModel.select().where(DocumentModel.folder == folder).order_by(DocumentModel.title)
            for doc in docs:
                doc_item = QTreeWidgetItem(folder_item, [f"📄 {doc.title}"])
                doc_item.setData(0, Qt.UserRole, {"type": "doc", "id": doc.id})
                doc_item.setFlags((doc_item.flags() | Qt.ItemIsDragEnabled) & ~Qt.ItemIsDropEnabled)

        orphan_docs = DocumentModel.select().where(DocumentModel.folder.is_null()).order_by(DocumentModel.title)
        orphan_root = QTreeWidgetItem(self.tree, ["📂 Non classés"])
        orphan_root.setData(0, Qt.UserRole, {"type": "folder", "id": None})
        orphan_root.setFlags(orphan_root.flags() | Qt.ItemIsDropEnabled)

        for doc in orphan_docs:
            doc_item = QTreeWidgetItem(orphan_root, [f"📄 {doc.title}"])
            doc_item.setData(0, Qt.UserRole, {"type": "doc", "id": doc.id})
            doc_item.setFlags((doc_item.flags() | Qt.ItemIsDragEnabled) & ~Qt.ItemIsDropEnabled)

        self.tree.expandAll()

    # ==========================================
    # ACTIONS (Drag&Drop, Suppression, Création)
    # ==========================================

    def _on_document_moved(self, doc_id: int, new_folder_id: object) -> None:
        """Met à jour la base de données quand un document a été lâché."""
        try:
            with db.atomic():
                doc = DocumentModel.get_by_id(doc_id)
                folder = FolderModel.get_by_id(new_folder_id) if new_folder_id else None
                doc.folder = folder
                doc.save()
        except Exception as e:
            QMessageBox.critical(self, "Erreur BDD", f"Impossible de déplacer le document :\n{e}")
            self.load_tree()  # On recharge l'arbre pour annuler le faux mouvement visuel

    def create_folder(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau dossier", "Nom du dossier :")
        if ok and name.strip():
            with db.atomic():
                FolderModel.create(name=name.strip())
            self.load_tree()

    def create_manual_document(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau Document", "Titre du document :")
        if not ok or not name.strip(): return

        selected_items = self.tree.selectedItems()
        target_folder = None
        if selected_items:
            data = selected_items[0].data(0, Qt.UserRole)
            if data and data.get("type") == "folder" and data.get("id") is not None:
                target_folder = FolderModel.get_by_id(data.get("id"))

        with db.atomic():
            DocumentModel.create(title=name.strip(), content="# Nouveau Cours\n\n...", folder=target_folder)
        self.load_tree()

    def save_document_edits(self) -> None:
        if not self.current_doc_id_editing: return
        try:
            with db.atomic():
                doc = DocumentModel.get_by_id(self.current_doc_id_editing)
                doc.content = self.preview_text.toPlainText()
                doc.save()
            self.btn_save_doc.setEnabled(False)
            self.btn_save_doc.setText("✅ Sauvegardé !")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1500, lambda: self.btn_save_doc.setText("💾 Sauvegarder les modifications"))
        except Exception as e:
            QMessageBox.critical(self, "Erreur BDD", str(e))

    def delete_item(self) -> None:
        selected_items = self.tree.selectedItems()
        if not selected_items: return
        data = selected_items[0].data(0, Qt.UserRole)
        print(data)
        if not data: return

        item_type = data.get("type")
        item_id = data.get("id")

        if item_type == "folder":
            if item_id is None:
                QMessageBox.critical(self, "Erreur de suppression",
                                     f"Impossible de supprimer le dossier par défaut: Non classé")
                return
            folder = FolderModel.get_by_id(item_id)
            reply = QMessageBox.question(self, "Confirmation",
                                         f"Supprimer le dossier '{folder.name}' et TOUS ses documents ?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                try:
                    with db.atomic():
                        # Exécution explicite : on tue d'abord les documents, puis le dossier
                        DocumentModel.delete().where(DocumentModel.folder == folder).execute()
                        folder.delete_instance()

                    self.preview_text.clear()
                    self.render_view.setHtml("")
                    self.current_doc_id_editing = None
                    self.lbl_doc_title.setText("<b>Aucun document sélectionné</b>")
                    self.load_tree()
                except Exception as e:
                    QMessageBox.critical(self, "Erreur de suppression", f"Impossible de supprimer le dossier :\n{e}")
        elif item_type == "doc":
            doc = DocumentModel.get_by_id(item_id)
            reply = QMessageBox.question(self, "Confirmation", f"Supprimer '{doc.title}' ?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                with db.atomic():
                    doc.delete_instance()
                self.preview_text.clear()
                self.render_view.setHtml("")
                self.current_doc_id_editing = None
                self.lbl_doc_title.setText("<b>Aucun document sélectionné</b>")
                self.load_tree()

    def on_item_selected(self, item: QTreeWidgetItem, column: int) -> None:
        data = item.data(0, Qt.UserRole)
        if not data: return

        if data.get("type") == "doc":
            doc_id = data.get("id")
            doc = DocumentModel.get_by_id(doc_id)

            self.lbl_doc_title.setText(f"<b>📄 {doc.title}</b>")
            self.preview_text.blockSignals(True)
            self.preview_text.setPlainText(doc.content)
            self.preview_text.blockSignals(False)

            self.current_doc_id_editing = doc_id
            self.btn_save_doc.setEnabled(False)

            # Forcer le rafraîchissement si on est déjà sur l'onglet "Aperçu"
            if self.editor_tabs.currentIndex() == 1:
                self.on_tab_changed(1)
        else:
            self.lbl_doc_title.setText("<b>Aucun document sélectionné</b>")
            self.preview_text.clear()
            self.render_view.setHtml("")
            self.current_doc_id_editing = None
            self.btn_save_doc.setEnabled(False)

    # ==========================================
    # IMPORT (Marker)
    # ==========================================

    def import_document(self) -> None:
        self.current_folder_id_for_import = None
        selected_items = self.tree.selectedItems()
        if selected_items:
            data = selected_items[0].data(0, Qt.UserRole)
            if data and data.get("type") == "folder":
                self.current_folder_id_for_import = data.get("id")

        path, _ = QFileDialog.getOpenFileName(self, "Importer un cours", "", "Documents (*.pdf *.txt *.md)")
        if not path: return

        doc_title = os.path.basename(path)
        self.btn_import.setEnabled(False)
        self.preview_text.setPlainText("🤖 Analyse du document en cours...\nLe Mac va ventiler, c'est normal ! 🚀")

        self.worker = ParserWorker(path, DocumentParser())
        self.worker.finished_signal.connect(self._on_parsing_success)
        self.worker.error_signal.connect(self._on_parsing_error)
        self.worker.start()

    def _on_parsing_success(self, title: str, content: str) -> None:
        folder = FolderModel.get_by_id(self.current_folder_id_for_import) if self.current_folder_id_for_import else None
        with db.atomic(): DocumentModel.create(title=title, content=content, folder=folder)
        self.btn_import.setEnabled(True)
        self.load_tree()

    def _on_parsing_error(self, error_msg: str) -> None:
        self.btn_import.setEnabled(True)
        QMessageBox.critical(self, "Erreur", error_msg)
