import logging
import re

import markdown
import qtawesome as qta
from PySide6.QtCore import Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DocumentModel, FolderModel, db
from ankiforge.services.workers.document_worker import DocumentWorker
from ankiforge.ui.components.components import ActionButton, DangerButton, HeaderLabel, PrimaryButton, RoundedPanel
from ankiforge.ui.theme import is_dark_mode
from ankiforge.ui.widgets.safe_web_preview import SafeWebEngineView
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.anki_renderer import get_mathjax_script
from ankiforge.utils.paths import get_app_data_dir

logger = logging.getLogger(__name__)


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


class DocumentsTab(QWidget):
    """
    Vue de gestion de la bibliothèque de documents (Cours).
    Permet d'importer (PDF, Web, Markdown), d'éditer, de scinder et de classer
    les documents sources qui seront utilisés pour générer les cartes Anki.
    """

    def __init__(self) -> None:
        """Initialise l'onglet de gestion des documents."""
        super().__init__()

        # État interne
        self.worker: DocumentWorker | None = None
        self.shortcut_insert_split: QShortcut | None = None
        self.shortcut_backspace: QShortcut | None = None
        self.shortcut_delete: QShortcut | None = None
        self.shortcut_save: QShortcut | None = None

        self.current_folder_id_for_import = None
        self.current_doc_id_editing = None

        self._setup_ui()
        self._connect_signals()
        self._setup_shortcuts()

        self.load_tree()

    def _setup_ui(self) -> None:
        """Construit et organise les layouts et widgets de la vue."""
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(20)

        self._build_header()

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(10)

        self._build_explorer_panel()
        self._build_editor_panel()

        self.main_splitter.setSizes([250, 750])
        self.layout.addWidget(self.main_splitter)

    def _build_header(self) -> None:
        """Construit l'en-tête contenant le titre et les boutons d'importation."""
        header_layout = QHBoxLayout()
        header_layout.addWidget(HeaderLabel("Bibliothèque de Cours"))
        header_layout.addStretch()

        self.btn_import = ActionButton("fa5s.file-import", " Analyser un PDF/TXT (Marker)")
        self.btn_import_web = ActionButton("fa5s.globe", " Depuis le Web (URL)")
        self.btn_cancel_import = DangerButton(qta.icon("fa5s.stop", color="white"), " Annuler l'analyse")
        self.btn_cancel_import.hide()

        header_layout.addWidget(self.btn_import)
        header_layout.addWidget(self.btn_import_web)
        header_layout.addWidget(self.btn_cancel_import)

        self.layout.addLayout(header_layout)

    def _build_explorer_panel(self) -> None:
        """Construit le panneau latéral gauche (Arborescence des dossiers et documents)."""
        left_panel = RoundedPanel()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(15, 15, 15, 15)

        lbl_explorateur = QLabel("EXPLORATEUR DE DOCUMENTS")
        lbl_explorateur.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 5px;")
        left_layout.addWidget(lbl_explorateur)

        toolbar = QHBoxLayout()
        self.btn_new_folder = ActionButton("fa5s.folder-plus", " Dossier")
        self.btn_new_doc = ActionButton("fa5s.file-medical", " Doc")
        self.btn_delete = DangerButton(qta.icon("fa5s.trash", color="white"), "")
        self.btn_delete.setToolTip("Supprimer (Suppr)")

        toolbar.addWidget(self.btn_new_folder)
        toolbar.addWidget(self.btn_new_doc)
        toolbar.addWidget(self.btn_delete)
        left_layout.addLayout(toolbar)

        self.tree = DraggableTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFrameShape(QFrame.Shape.NoFrame)
        self.tree.viewport().setAutoFillBackground(False)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

        left_layout.addWidget(self.tree)
        self.main_splitter.addWidget(left_panel)

    def _build_editor_panel(self) -> None:
        """Construit le panneau principal de droite (Éditeur Markdown et Rendu Web)."""
        right_panel = RoundedPanel()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(15, 15, 15, 15)

        editor_toolbar = QHBoxLayout()
        self.lbl_doc_title = QLabel("AUCUN DOCUMENT SÉLECTIONNÉ")
        self.lbl_doc_title.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; text-transform: uppercase; letter-spacing: 1px;")

        self.btn_insert_split = ActionButton("fa5s.cut", " Insérer Coupure (Ctrl+D)")
        self.btn_insert_split.setEnabled(False)

        self.btn_split_doc = ActionButton("fa5s.cut", " Scinder aux balises [SPLIT]")
        self.btn_split_doc.setEnabled(False)

        self.btn_save_doc = PrimaryButton(qta.icon("fa5s.save", color="white"), " Sauvegarder (Ctrl+S)")
        self.btn_save_doc.setEnabled(False)

        editor_toolbar.addWidget(self.lbl_doc_title)
        editor_toolbar.addStretch()
        editor_toolbar.addWidget(self.btn_insert_split)
        editor_toolbar.addWidget(self.btn_split_doc)
        editor_toolbar.addWidget(self.btn_save_doc)

        right_layout.addLayout(editor_toolbar)

        self.editor_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.editor_splitter.setHandleWidth(10)

        # Éditeur de texte (Markdown)
        self.preview_text = QTextEdit()
        self.preview_text.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_text.viewport().setAutoFillBackground(False)

        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.preview_text.setFont(font)

        self.highlighter = MarkdownHighlighter(self.preview_text.document())

        # Rendu Web (HTML rendu)
        self.render_view = SafeWebEngineView()
        self.render_view.page().setBackgroundColor(Qt.GlobalColor.transparent)

        self.editor_splitter.addWidget(self.preview_text)
        self.editor_splitter.addWidget(self.render_view)
        self.editor_splitter.setSizes([400, 400])

        right_layout.addWidget(self.editor_splitter)
        self.main_splitter.addWidget(right_panel)

        # Timer pour le rafraîchissement dynamique du rendu
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(500)

    def _connect_signals(self) -> None:
        """Centralise le branchement des signaux (UI et Custom) vers leurs slots."""
        # En-tête
        self.btn_import.clicked.connect(self.import_document)
        self.btn_import_web.clicked.connect(self.import_web_url)
        self.btn_cancel_import.clicked.connect(self.cancel_import)

        # Explorateur
        self.btn_new_folder.clicked.connect(self.create_folder)
        self.btn_new_doc.clicked.connect(self.create_manual_document)
        self.btn_delete.clicked.connect(self.delete_item)
        self.tree.itemClicked.connect(self.on_item_selected)
        self.tree.doc_moved.connect(self._on_document_moved)

        # Éditeur
        self.btn_insert_split.clicked.connect(self.insert_split_tag)
        self.btn_split_doc.clicked.connect(self.split_document_multiple)
        self.btn_save_doc.clicked.connect(self.save_document_edits)

        self.preview_text.textChanged.connect(self._on_text_changed)
        self.render_timer.timeout.connect(self.update_live_preview)

    def _setup_shortcuts(self) -> None:
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
        if not self.current_doc_id_editing:
            return

        cursor = self.preview_text.textCursor()
        cursor.insertText("\n\n[SPLIT]\n\n")
        self.preview_text.setTextCursor(cursor)
        self.preview_text.setFocus()

    @Slot()
    def update_live_preview(self) -> None:
        """Met à jour le rendu HTML avec le style visuel de coupure."""
        if not self.current_doc_id_editing:
            return

        raw_md = self.preview_text.toPlainText()

        visual_split_html = """
                <div style="text-align: center; margin: 30px 0; padding: 15px; background-color: rgba(255, 152, 0, 0.1); border: 2px dashed #ff9800; border-radius: 8px;">
                    <span style="color: #ff9800; font-weight: bold; font-size: 16px;">✂️ --- POINT DE DÉCOUPAGE --- ✂️</span>
                    <br><span style="color: #888; font-size: 12px;">Le document sera scindé ici</span>
                </div>
                """
        vis_md = raw_md.replace("[SPLIT]", f"\n\n{visual_split_html}\n\n")

        html_content = markdown.markdown(vis_md, extensions=["tables", "fenced_code"])

        # Palette dynamique
        dark = is_dark_mode()
        text_color = "#E0E0E0" if dark else "#333333"
        header_color = "#90CAF9" if dark else "#1976D2"
        code_bg = "#1E1E1E" if dark else "#F5F5F5"
        code_border = "#333" if dark else "#DDD"
        inline_code_color = "#CE9178" if dark else "#A31515"

        final_html = f"""
                <html><head><meta charset="utf-8">
                {get_mathjax_script()}
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 10px; line-height: 1.6; color: {text_color}; background-color: transparent; margin: 0; }}
                    h1, h2, h3 {{ color: {header_color}; border-bottom: 1px solid {code_border}; padding-bottom: 5px; }}
                    img {{ max-width: 100%; border-radius: 5px; }}
                    code {{ background-color: {code_bg}; padding: 2px 4px; border-radius: 3px; font-family: monospace; color: {inline_code_color}; }}
                    pre code {{ display: block; padding: 10px; overflow-x: auto; background-color: {code_bg}; border: 1px solid {code_border}; color: {text_color}; }}
                    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
                    th, td {{ border: 1px solid {code_border}; padding: 8px; text-align: left; }}
                    th {{ background-color: {code_bg}; }}

                    ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
                    ::-webkit-scrollbar-track {{ background: transparent; }}
                    ::-webkit-scrollbar-thumb {{ background: #555; border-radius: 5px; }}
                    ::-webkit-scrollbar-thumb:hover {{ background: #777; }}
                </style>
                </head><body>
                {html_content}
                </body></html>
                """

        media_dir = get_app_data_dir() / "media"
        media_dir.mkdir(exist_ok=True)

        base_url = QUrl.fromLocalFile(str(media_dir) + "/")
        self.render_view.setHtmlSafe(final_html, base_url)

    @Slot()
    def refresh_data(self) -> None:
        """Méthode standardisée appelée par la MainWindow au changement d'onglet."""
        self.load_tree()

    @Slot()
    def load_tree(self) -> None:
        self.tree.clear()

        folders = FolderModel.select().order_by(FolderModel.name)
        for folder in folders:
            folder_item = QTreeWidgetItem(self.tree, [f" {folder.name}"])
            folder_item.setIcon(0, qta.icon("fa5s.folder", color="#FFC107"))
            folder_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": folder.id})
            # Standard Qt6 : Qt.ItemFlag
            folder_item.setFlags(folder_item.flags() | Qt.ItemFlag.ItemIsDropEnabled)

            docs = DocumentModel.select().where(DocumentModel.folder == folder).order_by(DocumentModel.title)
            for doc in docs:
                doc_item = QTreeWidgetItem(folder_item, [f" {doc.title}"])
                doc_item.setIcon(0, qta.icon("fa5s.file-alt", color="#90CAF9"))
                doc_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "doc", "id": doc.id})
                doc_item.setFlags((doc_item.flags() | Qt.ItemFlag.ItemIsDragEnabled) & ~Qt.ItemFlag.ItemIsDropEnabled)

        orphan_docs = DocumentModel.select().where(DocumentModel.folder.is_null()).order_by(DocumentModel.title)
        orphan_root = QTreeWidgetItem(self.tree, [" Non classés"])
        orphan_root.setIcon(0, qta.icon("fa5s.box-open", color="#B0BEC5"))
        orphan_root.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": None})
        orphan_root.setFlags(orphan_root.flags() | Qt.ItemFlag.ItemIsDropEnabled)

        for doc in orphan_docs:
            doc_item = QTreeWidgetItem(orphan_root, [f" {doc.title}"])
            doc_item.setIcon(0, qta.icon("fa5s.file-alt", color="#90CAF9"))
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
            logger.info(f"Document {doc_id} déplacé vers le dossier {new_folder_id}.")
        except Exception as e:
            logger.exception(f"Impossible de déplacer le document {doc_id} :")
            QMessageBox.critical(self, "Erreur BDD", f"Impossible de déplacer le document :\n{e}")
            self.load_tree()

    @Slot()
    def create_folder(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau dossier", "Nom du dossier :")
        if ok and name.strip():
            with db.atomic():
                FolderModel.create(name=name.strip())
            logger.info(f"Dossier créé : {name.strip()}")
            self.load_tree()

    @Slot()
    def create_manual_document(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau Document", "Titre du document :")
        if not ok or not name.strip():
            return

        selected_items = self.tree.selectedItems()
        target_folder = None
        if selected_items:
            data = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("type") == "folder" and data.get("id") is not None:
                target_folder = FolderModel.get_by_id(data.get("id"))

        with db.atomic():
            DocumentModel.create(title=name.strip(), content="# Nouveau Cours\n\n...", folder=target_folder)
        logger.info(f"Document manuel créé : {name.strip()}")
        self.load_tree()

    @Slot()
    def save_document_edits(self) -> None:
        if not self.current_doc_id_editing or not self.btn_save_doc.isEnabled():
            return
        try:
            with db.atomic():
                doc = DocumentModel.get_by_id(self.current_doc_id_editing)
                doc.content = self.preview_text.toPlainText()
                doc.save()
            logger.info(f"Modifications du document '{doc.title}' sauvegardées.")
            self.btn_save_doc.setEnabled(False)
            self.btn_save_doc.setText(" Sauvegardé !")
            self.btn_save_doc.setIcon(qta.icon("fa5s.check", color="white"))

            from PySide6.QtCore import QTimer

            QTimer.singleShot(1500, self._reset_save_btn)
        except Exception as e:
            logger.exception("Erreur lors de la sauvegarde du document :")
            QMessageBox.critical(self, "Erreur BDD", str(e))

    @Slot()
    def _reset_save_btn(self):
        self.btn_save_doc.setText(" Sauvegarder (Ctrl+S)")
        self.btn_save_doc.setIcon(qta.icon("fa5s.save", color="white"))

    @Slot()
    def delete_item(self) -> None:
        selected_items = self.tree.selectedItems()
        if not selected_items:
            return
        data = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type = data.get("type")
        item_id = data.get("id")

        if item_type == "folder":
            if item_id is None:
                QMessageBox.critical(self, "Erreur", "Impossible de supprimer le dossier système 'Non classés'.")
                return
            folder = FolderModel.get_by_id(item_id)
            # Standard Qt6 : QMessageBox.StandardButton
            reply = QMessageBox.question(
                self,
                "Confirmation",
                f"Supprimer le dossier '{folder.name}' et TOUS ses documents ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    with db.atomic():
                        DocumentModel.delete().where(DocumentModel.folder == folder).execute()
                        folder.delete_instance()
                    logger.info(f"Dossier '{folder.name}' et son contenu supprimés.")
                    self._reset_editor_after_delete()
                except Exception as e:
                    logger.exception(f"Erreur lors de la suppression du dossier '{folder.name}' :")
                    QMessageBox.critical(self, "Erreur de suppression", f"Erreur :\n{e}")

        elif item_type == "doc":
            doc = DocumentModel.get_by_id(item_id)
            reply = QMessageBox.question(
                self,
                "Confirmation",
                f"Supprimer le document '{doc.title}' ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                with db.atomic():
                    doc.delete_instance()
                logger.info(f"Document '{doc.title}' supprimé.")
                self._reset_editor_after_delete()

    def _reset_editor_after_delete(self):
        self.preview_text.clear()
        self.render_view.setHtml("<html><body style='background: transparent;'></body></html>")
        self.current_doc_id_editing = None
        self.lbl_doc_title.setText("<b>Aucun document sélectionné</b>")
        self.btn_save_doc.setEnabled(False)
        self.btn_split_doc.setEnabled(False)
        self.btn_insert_split.setEnabled(False)
        self.load_tree()

    @Slot(QTreeWidgetItem, int)
    def on_item_selected(self, item: QTreeWidgetItem, column: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

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

            self.btn_insert_split.setEnabled(True)  # Active le bouton Ciseaux
            self.update_live_preview()  # Force le rendu immédiat

        else:
            self.lbl_doc_title.setText("<b>Aucun document sélectionné</b>")
            self.preview_text.clear()
            self.render_view.setHtml("<html><body style='background: transparent;'></body></html>")
            self.current_doc_id_editing = None
            self.btn_save_doc.setEnabled(False)
            self.btn_split_doc.setEnabled(False)
            self.btn_insert_split.setEnabled(False)

    @Slot()
    def import_document(self) -> None:
        self.current_folder_id_for_import = None
        selected_items = self.tree.selectedItems()
        if selected_items:
            data = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("type") == "folder":
                self.current_folder_id_for_import = data.get("id")

        path, _ = QFileDialog.getOpenFileName(self, "Importer un cours", "", "Documents (*.pdf *.txt *.md)")
        if not path:
            return

        self.btn_import.hide()
        self.btn_cancel_import.show()
        self.btn_cancel_import.setEnabled(True)
        self.tree.setEnabled(False)

        self.lbl_doc_title.setText("<b>⏳ Importation et Analyse en cours...</b>")
        self.preview_text.blockSignals(True)
        self.preview_text.setPlainText("🤖 Démarrage du script d'importation...\n")
        self.preview_text.blockSignals(False)

        self.worker = DocumentWorker(path)
        self.worker.log_signal.connect(self._on_parsing_log)
        self.worker.finished_signal.connect(self._on_parsing_success)
        self.worker.error_signal.connect(self._on_parsing_error)
        self.worker.cancelled_signal.connect(self._on_parsing_cancelled)
        self.worker.start()

    @Slot()
    def cancel_import(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.btn_cancel_import.setEnabled(False)
            self.btn_cancel_import.setText(" Arrêt de l'IA...")

    @Slot()
    def _on_parsing_cancelled(self):
        self._reset_import_ui()
        self.lbl_doc_title.setText("<b>Aucun document sélectionné</b>")
        logger.info("Analyse interrompue par l'utilisateur.")
        show_toast(self, "Analyse interrompue.", is_error=True)

    def _reset_import_ui(self):
        self.btn_cancel_import.hide()
        self.btn_cancel_import.setText(" Annuler l'analyse")
        self.btn_import.show()
        self.btn_import_web.show()
        self.btn_import_web.setEnabled(True)
        self.btn_import.setEnabled(True)
        self.tree.setEnabled(True)

    @Slot(str, str)
    def _on_parsing_success(self, base_title: str, content: str) -> None:
        self._reset_import_ui()
        folder = FolderModel.get_by_id(self.current_folder_id_for_import) if self.current_folder_id_for_import else None
        title = base_title
        counter = 1
        while DocumentModel.get_or_none(DocumentModel.title == title):
            title = f"{base_title} ({counter})"
            counter += 1
        try:
            with db.atomic():
                new_doc = DocumentModel.create(title=title, content=content, folder=folder)

            self.btn_import.setEnabled(True)
            self.tree.setEnabled(True)

            # 👇 FEEDBACK : On prévient et on affiche immédiatement le résultat !
            logger.info(f"Document '{title}' importé avec succès.")
            show_toast(self, f"✨ Document '{title}' importé avec succès !")
            self.load_tree()
            self.jump_to_document(new_doc.id)

        except Exception as e:
            logger.exception(f"Impossible de sauvegarder le document '{title}' :")
            QMessageBox.critical(self, "Erreur BDD", f"Impossible de sauvegarder le document :\n{e}")

    @Slot(str)
    def _on_parsing_log(self, log_line: str) -> None:
        """Affiche les logs de Marker en temps réel"""
        self.preview_text.append(log_line)
        # Scroll automatique vers le bas
        scrollbar = self.preview_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @Slot(str)
    def _on_parsing_error(self, error_msg: str) -> None:
        self._reset_import_ui()
        self.btn_import.setEnabled(True)
        self.tree.setEnabled(True)
        self.lbl_doc_title.setText("<b>Aucun document sélectionné</b>")
        QMessageBox.critical(self, "Erreur", error_msg)

    @Slot()
    def split_document_multiple(self) -> None:
        if not self.current_doc_id_editing:
            return

        full_text = self.preview_text.toPlainText()
        parts = full_text.split("[SPLIT]")

        if len(parts) <= 1:
            logger.info("Tentative de scission sans balise [SPLIT].")
            show_toast(self, "Astuce : Insérez [SPLIT] dans le texte pour scinder le document.")
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
                        DocumentModel.create(title=f"{base_title} (Partie {i + 1})", content=content_part, folder=original_doc.folder)

            logger.info(f"Document '{base_title}' scindé en {len(parts)} parties.")
            self.load_tree()
            self.preview_text.setPlainText(original_doc.content)
            show_toast(self, f"Document découpé en {len(parts)} parties !")
        except Exception as e:
            logger.exception(f"Échec de la scission du document '{base_title}' :")
            show_toast(self, f"Échec de la sauvegarde : {str(e)}", is_error=True)

    @Slot(int)
    def jump_to_document(self, doc_id: int) -> None:
        """Déplie l'arbre et sélectionne le document demandé."""
        from PySide6.QtWidgets import QTreeWidgetItemIterator

        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("type") == "doc" and data.get("id") == doc_id:
                parent = item.parent()
                if parent:
                    parent.setExpanded(True)
                self.tree.setCurrentItem(item)
                self.on_item_selected(item, 0)
                return
            iterator += 1

    @Slot()
    def import_web_url(self) -> None:
        self.current_folder_id_for_import = None
        selected_items = self.tree.selectedItems()
        if selected_items:
            data = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("type") == "folder":
                self.current_folder_id_for_import = data.get("id")

        # Demander l'URL à l'utilisateur
        url, ok = QInputDialog.getText(self, "Import Web", "Entrez l'URL de l'article ou du cours :")
        if not ok or not url.strip():
            return

        url = url.strip()
        if not url.startswith("http"):
            url = "https://" + url

        self.btn_import.hide()
        self.btn_import_web.hide()
        self.btn_cancel_import.show()
        self.btn_cancel_import.setEnabled(True)
        self.tree.setEnabled(False)

        self.lbl_doc_title.setText("<b>⏳ Aspiration de la page Web en cours...</b>")
        self.preview_text.blockSignals(True)
        self.preview_text.setPlainText(f"🤖 Connexion à {url}...\n")
        self.preview_text.blockSignals(False)

        # On utilise le même worker que pour les PDF !
        self.worker = DocumentWorker(url)
        self.worker.log_signal.connect(self._on_parsing_log)
        self.worker.finished_signal.connect(self._on_parsing_success)
        self.worker.error_signal.connect(self._on_parsing_error)
        self.worker.cancelled_signal.connect(self._on_parsing_cancelled)
        self.worker.start()
