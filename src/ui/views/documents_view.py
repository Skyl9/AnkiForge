# src/ui/views/documents_view.py
import os
import re

import markdown
import qtawesome as qta
from PySide6.QtCore import Qt, QThread, Signal, QUrl, Slot, QTimer
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QFont, QColor, QKeySequence, QShortcut
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
                               QTextEdit, QPushButton, QLabel, QSplitter,
                               QFileDialog, QMessageBox, QInputDialog, QAbstractItemView, QTabWidget)

from src.database.models import db, DocumentModel, FolderModel
from src.services.parsing.document_parser import DocumentParser
from src.ui.widgets.toast import show_toast


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

        # 1. Le bouton "Insérer une coupure" dans la toolbar
        self.btn_insert_split = QPushButton(qta.icon('fa5s.cut', color='#FF9800'), " Insérer Coupure (Ctrl+D)")
        self.btn_insert_split.setStyleSheet("font-weight: bold; color: #FF9800;")
        self.btn_insert_split.clicked.connect(self.insert_split_tag)
        self.btn_insert_split.setEnabled(False)
        editor_toolbar.insertWidget(2, self.btn_insert_split)  # Insère avant le bouton scinder

        # 2. Le Splitter d'édition
        self.editor_splitter = QSplitter(Qt.Orientation.Horizontal)

        self.preview_text = QTextEdit()
        self.preview_text.setStyleSheet(
            "background-color: #1E1E1E; color: #D4D4D4; font-family: 'Consolas', monospace; font-size: 14px;")
        self.highlighter = MarkdownHighlighter(self.preview_text.document())

        self.render_view = QWebEngineView()

        # On ajoute les deux vues côte à côte
        self.editor_splitter.addWidget(self.preview_text)
        self.editor_splitter.addWidget(self.render_view)
        self.editor_splitter.setSizes([400, 400])

        right_layout.addWidget(self.editor_splitter)

        # 3. Le Timer pour l'aperçu en temps réel (Debouncing de 500ms)
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(500)
        self.render_timer.timeout.connect(self.update_live_preview)

        self.preview_text.textChanged.connect(self._on_text_changed)

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

        # Insérer un tag [SPLIT] (Ctrl+D)
        self.shortcut_insert_split = QShortcut(QKeySequence("Ctrl+D"), self)
        self.shortcut_insert_split.activated.connect(self.insert_split_tag)

    @Slot()
    def _enable_save(self) -> None:
        if self.current_doc_id_editing:
            self.btn_save_doc.setEnabled(True)

    @Slot()
    def _on_text_changed(self) -> None:
        """Déclenché à chaque frappe au clavier."""
        self._enable_save()
        self.render_timer.start()  # Relance le chrono de 500ms

    @Slot()
    def insert_split_tag(self) -> None:
        """Insère la balise de découpage à l'emplacement du curseur."""
        if not self.current_doc_id_editing: return

        cursor = self.preview_text.textCursor()
        cursor.insertText("\n\n[SPLIT]\n\n")
        self.preview_text.setTextCursor(cursor)
        self.preview_text.setFocus()

    @Slot()
    def update_live_preview(self) -> None:
        """Met à jour le rendu HTML avec le style visuel de coupure."""
        if not self.current_doc_id_editing: return

        raw_md = self.preview_text.toPlainText()

        # 👇 ASTUCE : On remplace le texte brut par une belle balise HTML avant de parser
        visual_split_html = """
            <div style="text-align: center; margin: 30px 0; padding: 15px; background-color: #ff980015; border: 2px dashed #ff9800; border-radius: 8px;">
                <span style="color: #ff9800; font-weight: bold; font-size: 16px;">✂️ --- POINT DE DÉCOUPAGE --- ✂️</span>
                <br><span style="color: #888; font-size: 12px;">Le document sera scindé ici</span>
            </div>
            """
        vis_md = raw_md.replace("[SPLIT]", f"\n\n{visual_split_html}\n\n")

        html_content = markdown.markdown(vis_md, extensions=['tables', 'fenced_code'])

        final_html = f"""
            <html><head><meta charset="utf-8">
            <script>window.MathJax = {{ tex: {{ inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']] }} }};</script>
            <script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 20px; line-height: 1.6; color: #E0E0E0; background-color: #121212; }}
                h1, h2, h3 {{ color: #90CAF9; border-bottom: 1px solid #333; padding-bottom: 5px; }}
                img {{ max-width: 100%; border-radius: 5px; }}
                code {{ background-color: #2D2D2D; padding: 2px 4px; border-radius: 3px; font-family: monospace; color: #CE9178; }}
                pre code {{ display: block; padding: 10px; overflow-x: auto; background-color: #1E1E1E; border: 1px solid #333; }}
                table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
                th, td {{ border: 1px solid #444; padding: 8px; text-align: left; }}
                th {{ background-color: #2D2D2D; }}
            </style>
            </head><body>
            {html_content}
            </body></html>
            """

        # Reste de la logique d'URL (identique à avant)
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
        self.btn_insert_split.setEnabled(False)
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

            # 👇 LIGNES MANQUANTES À AJOUTER 👇
            self.btn_insert_split.setEnabled(True)  # Active le bouton Ciseaux
            self.update_live_preview()  # Force le rendu immédiat

        else:
            self.lbl_doc_title.setText("<b>Aucun document sélectionné</b>")
            self.preview_text.clear()
            self.render_view.setHtml("")
            self.current_doc_id_editing = None
            self.btn_save_doc.setEnabled(False)
            self.btn_split_doc.setEnabled(False)
            self.btn_insert_split.setEnabled(False)  # 👈 Désactiver ici aussi

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
                "Pour scinder le document en plusieurs parties, cliquez sur 'Insérer Coupure' ou écrivez [SPLIT] dans le texte."
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
            show_toast(self, f"Document découpé en {len(parts)} parties !")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de scinder le document :\n{e}")