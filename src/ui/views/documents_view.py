# src/ui/views/documents_view.py
import os
import re

import markdown
import qtawesome as qta
from PySide6.QtCore import Qt, QThread, Signal, QUrl, Slot
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QFont, QColor, QKeySequence, QShortcut
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
    def __init__(self, document):
        super().__init__(document)
        self.rules = []

        header_format = QTextCharFormat()
        header_format.setFontWeight(QFont.Weight.Bold)  # Standard Qt6
        header_format.setForeground(QColor("#569CD6"))
        self.rules.append((r"^(#+)(.*)", header_format))

        bold_format = QTextCharFormat()
        bold_format.setFontWeight(QFont.Weight.Bold)
        bold_format.setForeground(QColor("#CE9178"))
        self.rules.append((r"\*\*(.*?)\*\*", bold_format))

        italic_format = QTextCharFormat()
        italic_format.setFontItalic(True)
        italic_format.setForeground(QColor("#CE9178"))
        self.rules.append((r"\*(.*?)\*", italic_format))

        math_format = QTextCharFormat()
        math_format.setForeground(QColor("#4EC9B0"))
        self.rules.append((r"(\$\$.*?\$\$|\$.*?\$)", math_format))

        img_format = QTextCharFormat()
        img_format.setForeground(QColor("#C586C0"))
        self.rules.append((r"!\[.*?\]\(.*?\)", img_format))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


class DraggableTreeWidget(QTreeWidget):
    doc_moved = Signal(int, object)

    def dropEvent(self, event):
        dragged_item = self.currentItem()
        if not dragged_item:
            super().dropEvent(event)
            return

        # Standard Qt6: ItemDataRole.UserRole
        data = dragged_item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get("type") != "doc":
            event.ignore()
            return

        super().dropEvent(event)

        new_parent = dragged_item.parent()
        new_folder_id = None

        if new_parent:
            parent_data = new_parent.data(0, Qt.ItemDataRole.UserRole)
            if parent_data and parent_data.get("type") == "folder":
                new_folder_id = parent_data.get("id")

        self.doc_moved.emit(data.get("id"), new_folder_id)


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

        header_layout = QHBoxLayout()
        title = QLabel("<h2>Bibliothèque de Cours</h2>")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.btn_import = QPushButton(qta.icon('fa5s.file-import', color='white'), " Analyser un PDF/TXT (Marker)")
        self.btn_import.setStyleSheet("background-color: #3F51B5; color: white; font-weight: bold; padding: 6px;")
        self.btn_import.clicked.connect(self.import_document)
        header_layout.addWidget(self.btn_import)

        self.layout.addLayout(header_layout)

        # Standard Qt6: Qt.Orientation.Horizontal
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        self.btn_new_folder = QPushButton(qta.icon('fa5s.folder-plus'), " Dossier")
        self.btn_new_folder.clicked.connect(self.create_folder)

        self.btn_new_doc = QPushButton(qta.icon('fa5s.file-medical'), " Doc")
        self.btn_new_doc.clicked.connect(self.create_manual_document)

        self.btn_delete = QPushButton(qta.icon('fa5s.trash', color='#F44336'), "")
        self.btn_delete.setToolTip("Supprimer (Suppr)")
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
        # Standard Qt6: QAbstractItemView.DragDropMode
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

        self.tree.doc_moved.connect(self._on_document_moved)
        self.tree.itemClicked.connect(self.on_item_selected)

        left_layout.addWidget(self.tree)
        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        editor_toolbar = QHBoxLayout()
        self.lbl_doc_title = QLabel("<b>Aucun document sélectionné</b>")
        editor_toolbar.addWidget(self.lbl_doc_title)
        editor_toolbar.addStretch()

        self.btn_save_doc = QPushButton(qta.icon('fa5s.save', color='white'), " Sauvegarder (Ctrl+S)")
        self.btn_save_doc.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.btn_save_doc.clicked.connect(self.save_document_edits)
        self.btn_save_doc.setEnabled(False)
        editor_toolbar.addWidget(self.btn_save_doc)

        self.btn_split_doc = QPushButton(qta.icon('fa5s.cut', color='white'), " Scinder aux balises [SPLIT]")
        self.btn_split_doc.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold;")
        self.btn_split_doc.clicked.connect(self.split_document_multiple)
        self.btn_split_doc.setEnabled(False)
        editor_toolbar.addWidget(self.btn_split_doc)

        right_layout.addLayout(editor_toolbar)

        self.editor_tabs = QTabWidget()

        self.preview_text = QTextEdit()
        self.preview_text.setStyleSheet(
            "background-color: #1E1E1E; color: #D4D4D4; font-family: 'Consolas', monospace; font-size: 14px;")
        self.highlighter = MarkdownHighlighter(self.preview_text.document())
        self.preview_text.textChanged.connect(self._enable_save)

        self.render_view = QWebEngineView()

        # Icônes vectorielles pour les onglets
        self.editor_tabs.addTab(self.preview_text, qta.icon('fa5s.edit'), " Éditeur Markdown")
        self.editor_tabs.addTab(self.render_view, qta.icon('fa5s.eye'), " Aperçu du Document")
        self.editor_tabs.currentChanged.connect(self.on_tab_changed)

        right_layout.addWidget(self.editor_tabs)
        splitter.addWidget(right_panel)
        splitter.setSizes([250, 750])

        self.layout.addWidget(splitter)

        # 👇 NOUVEAU : LES RACCOURCIS CLAVIER 👇
        self.setup_shortcuts()

        self.load_tree()

    def setup_shortcuts(self) -> None:
        """Initialise les raccourcis clavier globaux pour cet onglet."""
        # Sauvegarde (Ctrl+S ou Cmd+S sur Mac)
        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_save.activated.connect(self.save_document_edits)

        # Suppression (Touche Suppr / Delete)
        self.shortcut_delete = QShortcut(QKeySequence.StandardKey.Delete, self.tree)
        self.shortcut_delete.activated.connect(self.delete_item)

        # Suppression Mac (Touche Retour Arrière)
        self.shortcut_backspace = QShortcut(QKeySequence("Backspace"), self.tree)
        self.shortcut_backspace.activated.connect(self.delete_item)

    @Slot()
    def _enable_save(self) -> None:
        if self.current_doc_id_editing:
            self.btn_save_doc.setEnabled(True)

    @Slot(int)
    def on_tab_changed(self, index: int) -> None:
        if index == 1 and self.current_doc_id_editing:
            raw_md = self.preview_text.toPlainText()
            html_content = markdown.markdown(raw_md, extensions=['tables', 'fenced_code'])

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

            BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            media_dir = os.path.join(BASE_DIR, 'data', 'media')
            if not media_dir.endswith(os.sep): media_dir += os.sep
            base_url = QUrl.fromLocalFile(media_dir)

            self.render_view.setHtml(final_html, base_url)

    @Slot()
    def load_tree(self) -> None:
        self.tree.clear()

        folders = FolderModel.select().order_by(FolderModel.name)
        for folder in folders:
            folder_item = QTreeWidgetItem(self.tree, [f" {folder.name}"])
            folder_item.setIcon(0, qta.icon('fa5s.folder', color='#FFC107'))
            folder_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": folder.id})
            # Standard Qt6 : Qt.ItemFlag
            folder_item.setFlags(folder_item.flags() | Qt.ItemFlag.ItemIsDropEnabled)

            docs = DocumentModel.select().where(DocumentModel.folder == folder).order_by(DocumentModel.title)
            for doc in docs:
                doc_item = QTreeWidgetItem(folder_item, [f" {doc.title}"])
                doc_item.setIcon(0, qta.icon('fa5s.file-alt', color='#90CAF9'))
                doc_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "doc", "id": doc.id})
                doc_item.setFlags((doc_item.flags() | Qt.ItemFlag.ItemIsDragEnabled) & ~Qt.ItemFlag.ItemIsDropEnabled)

        orphan_docs = DocumentModel.select().where(DocumentModel.folder.is_null()).order_by(DocumentModel.title)
        orphan_root = QTreeWidgetItem(self.tree, [" Non classés"])
        orphan_root.setIcon(0, qta.icon('fa5s.box-open', color='#B0BEC5'))
        orphan_root.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": None})
        orphan_root.setFlags(orphan_root.flags() | Qt.ItemFlag.ItemIsDropEnabled)

        for doc in orphan_docs:
            doc_item = QTreeWidgetItem(orphan_root, [f" {doc.title}"])
            doc_item.setIcon(0, qta.icon('fa5s.file-alt', color='#90CAF9'))
            doc_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "doc", "id": doc.id})
            doc_item.setFlags((doc_item.flags() | Qt.ItemFlag.ItemIsDragEnabled) & ~Qt.ItemFlag.ItemIsDropEnabled)

        self.tree.expandAll()

    @Slot(int, object)
    def _on_document_moved(self, doc_id: int, new_folder_id: object) -> None:
        try:
            with db.atomic():
                doc = DocumentModel.get_by_id(doc_id)
                folder = FolderModel.get_by_id(new_folder_id) if new_folder_id else None
                doc.folder = folder
                doc.save()
        except Exception as e:
            QMessageBox.critical(self, "Erreur BDD", f"Impossible de déplacer le document :\n{e}")
            self.load_tree()

    @Slot()
    def create_folder(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau dossier", "Nom du dossier :")
        if ok and name.strip():
            with db.atomic():
                FolderModel.create(name=name.strip())
            self.load_tree()

    @Slot()
    def create_manual_document(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau Document", "Titre du document :")
        if not ok or not name.strip(): return

        selected_items = self.tree.selectedItems()
        target_folder = None
        if selected_items:
            data = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("type") == "folder" and data.get("id") is not None:
                target_folder = FolderModel.get_by_id(data.get("id"))

        with db.atomic():
            DocumentModel.create(title=name.strip(), content="# Nouveau Cours\n\n...", folder=target_folder)
        self.load_tree()

    @Slot()
    def save_document_edits(self) -> None:
        if not self.current_doc_id_editing or not self.btn_save_doc.isEnabled(): return
        try:
            with db.atomic():
                doc = DocumentModel.get_by_id(self.current_doc_id_editing)
                doc.content = self.preview_text.toPlainText()
                doc.save()
            self.btn_save_doc.setEnabled(False)
            self.btn_save_doc.setText(" Sauvegardé !")
            self.btn_save_doc.setIcon(qta.icon('fa5s.check', color='white'))

            from PySide6.QtCore import QTimer
            QTimer.singleShot(1500, self._reset_save_btn)
        except Exception as e:
            QMessageBox.critical(self, "Erreur BDD", str(e))

    @Slot()
    def _reset_save_btn(self):
        self.btn_save_doc.setText(" Sauvegarder (Ctrl+S)")
        self.btn_save_doc.setIcon(qta.icon('fa5s.save', color='white'))

    @Slot()
    def delete_item(self) -> None:
        selected_items = self.tree.selectedItems()
        if not selected_items: return
        data = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
        if not data: return

        item_type = data.get("type")
        item_id = data.get("id")

        if item_type == "folder":
            if item_id is None:
                QMessageBox.critical(self, "Erreur", "Impossible de supprimer le dossier système 'Non classés'.")
                return
            folder = FolderModel.get_by_id(item_id)
            # Standard Qt6 : QMessageBox.StandardButton
            reply = QMessageBox.question(self, "Confirmation",
                                         f"Supprimer le dossier '{folder.name}' et TOUS ses documents ?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    with db.atomic():
                        DocumentModel.delete().where(DocumentModel.folder == folder).execute()
                        folder.delete_instance()
                    self._reset_editor_after_delete()
                except Exception as e:
                    QMessageBox.critical(self, "Erreur de suppression", f"Erreur :\n{e}")

        elif item_type == "doc":
            doc = DocumentModel.get_by_id(item_id)
            reply = QMessageBox.question(self, "Confirmation", f"Supprimer le document '{doc.title}' ?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                with db.atomic():
                    doc.delete_instance()
                self._reset_editor_after_delete()

    def _reset_editor_after_delete(self):
        self.preview_text.clear()
        self.render_view.setHtml("")
        self.current_doc_id_editing = None
        self.lbl_doc_title.setText("<b>Aucun document sélectionné</b>")
        self.btn_save_doc.setEnabled(False)
        self.btn_split_doc.setEnabled(False)
        self.load_tree()

    @Slot(QTreeWidgetItem, int)
    def on_item_selected(self, item: QTreeWidgetItem, column: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
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
            self.btn_split_doc.setEnabled(True)

            if self.editor_tabs.currentIndex() == 1:
                self.on_tab_changed(1)
        else:
            self.lbl_doc_title.setText("<b>Aucun document sélectionné</b>")
            self.preview_text.clear()
            self.render_view.setHtml("")
            self.current_doc_id_editing = None
            self.btn_save_doc.setEnabled(False)
            self.btn_split_doc.setEnabled(False)

    @Slot()
    def import_document(self) -> None:
        self.current_folder_id_for_import = None
        selected_items = self.tree.selectedItems()
        if selected_items:
            data = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("type") == "folder":
                self.current_folder_id_for_import = data.get("id")

        path, _ = QFileDialog.getOpenFileName(self, "Importer un cours", "", "Documents (*.pdf *.txt *.md)")
        if not path: return

        self.btn_import.setEnabled(False)
        self.preview_text.setPlainText(
            "🤖 Analyse du document en cours...\nLe moteur de Deep Learning (Marker) extrait les données... 🚀")

        self.worker = ParserWorker(path, DocumentParser())
        self.worker.finished_signal.connect(self._on_parsing_success)
        self.worker.error_signal.connect(self._on_parsing_error)
        self.worker.start()

    @Slot(str, str)
    def _on_parsing_success(self, title: str, content: str) -> None:
        folder = FolderModel.get_by_id(self.current_folder_id_for_import) if self.current_folder_id_for_import else None
        with db.atomic(): DocumentModel.create(title=title, content=content, folder=folder)
        self.btn_import.setEnabled(True)
        self.load_tree()

    @Slot(str)
    def _on_parsing_error(self, error_msg: str) -> None:
        self.btn_import.setEnabled(True)
        QMessageBox.critical(self, "Erreur", error_msg)

    @Slot()
    def split_document_multiple(self) -> None:
        if not self.current_doc_id_editing:
            return

        full_text = self.preview_text.toPlainText()
        parts = full_text.split("[SPLIT]")

        if len(parts) <= 1:
            QMessageBox.information(
                self, "Astuce",
                "Pour scinder le document en plusieurs parties, écrivez [SPLIT] dans le texte aux endroits où vous souhaitez couper."
            )
            return

        try:
            with db.atomic():
                original_doc = DocumentModel.get_by_id(self.current_doc_id_editing)
                base_title = original_doc.title

                original_doc.title = f"{base_title} (Partie 1)"
                original_doc.content = parts[0].strip()
                original_doc.save()

                for i in range(1, len(parts)):
                    content_part = parts[i].strip()
                    if len(content_part) > 0:
                        DocumentModel.create(
                            title=f"{base_title} (Partie {i + 1})",
                            content=content_part,
                            folder=original_doc.folder
                        )

            self.load_tree()
            self.preview_text.setPlainText(original_doc.content)
            QMessageBox.information(self, "Succès 🎉", f"Le document a été découpé en {len(parts)} morceaux distincts !")

        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de scinder le document :\n{e}")