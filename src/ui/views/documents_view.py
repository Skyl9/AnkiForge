# src/ui/views/documents_view.py
import os
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
                               QTextEdit, QPushButton, QLabel, QSplitter,
                               QFileDialog, QMessageBox, QInputDialog)

from src.database.models import db, DocumentModel, FolderModel
from src.services.parsing.document_parser import DocumentParser


class ParserWorker(QThread):
    """Thread séparé pour lancer Marker en arrière-plan."""
    finished_signal = Signal(str, str)  # title, content
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
        self.current_folder_id_for_import = None  # Mémorise où on veut importer le fichier

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

        # Barre d'outils des dossiers
        toolbar = QHBoxLayout()
        self.btn_new_folder = QPushButton("📁 Nouveau Dossier")
        self.btn_new_folder.clicked.connect(self.create_folder)
        self.btn_delete = QPushButton("🗑️ Supprimer")
        self.btn_delete.setStyleSheet("color: #F44336; font-weight: bold;")
        self.btn_delete.clicked.connect(self.delete_item)

        toolbar.addWidget(self.btn_new_folder)
        toolbar.addWidget(self.btn_delete)
        left_layout.addLayout(toolbar)

        # L'Arbre des documents
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self.on_item_selected)
        left_layout.addWidget(self.tree)

        splitter.addWidget(left_panel)

        # --- Panneau Droit : L'aperçu ---
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText(
            "Sélectionnez un document pour voir le Markdown extrait...\n\nSélectionnez un dossier puis cliquez sur 'Analyser' pour y ranger un nouveau cours.")
        splitter.addWidget(self.preview_text)

        splitter.setSizes([300, 600])
        self.layout.addWidget(splitter)

        self.load_tree()

    def load_tree(self) -> None:
        """Charge les dossiers et les documents depuis SQLite."""
        self.tree.clear()

        # 1. Charger les dossiers
        folders = FolderModel.select().order_by(FolderModel.name)
        for folder in folders:
            folder_item = QTreeWidgetItem(self.tree, [f"📂 {folder.name}"])
            folder_item.setData(0, Qt.UserRole, {"type": "folder", "id": folder.id})

            # Ajouter les documents de ce dossier
            docs = DocumentModel.select().where(DocumentModel.folder == folder).order_by(DocumentModel.title)
            for doc in docs:
                doc_item = QTreeWidgetItem(folder_item, [f"📄 {doc.title}"])
                doc_item.setData(0, Qt.UserRole, {"type": "doc", "id": doc.id})

        # 2. Charger les documents orphelins (sans dossier)
        orphan_docs = DocumentModel.select().where(DocumentModel.folder.is_null()).order_by(DocumentModel.title)
        if orphan_docs.count() > 0:
            orphan_root = QTreeWidgetItem(self.tree, ["📁 Non classés"])
            orphan_root.setData(0, Qt.UserRole, {"type": "folder", "id": None})
            for doc in orphan_docs:
                doc_item = QTreeWidgetItem(orphan_root, [f"📄 {doc.title}"])
                doc_item.setData(0, Qt.UserRole, {"type": "doc", "id": doc.id})

        self.tree.expandAll()

    def create_folder(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau dossier", "Nom du dossier :")
        if ok and name.strip():
            if FolderModel.get_or_none(FolderModel.name == name.strip()):
                QMessageBox.warning(self, "Erreur", "Un dossier porte déjà ce nom.")
                return
            with db.atomic():
                FolderModel.create(name=name.strip())
            self.load_tree()

    def delete_item(self) -> None:
        selected_items = self.tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Attention", "Veuillez sélectionner un élément à supprimer.")
            return

        item = selected_items[0]
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        item_type = data.get("type")
        item_id = data.get("id")

        if item_type == "folder" and item_id is not None:
            # Suppression d'un dossier
            folder = FolderModel.get_by_id(item_id)
            reply = QMessageBox.question(self, "Confirmation",
                                         f"Supprimer le dossier '{folder.name}' et TOUS les documents qu'il contient ?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                with db.atomic():
                    folder.delete_instance()  # CASCADE supprimera les documents
                self.preview_text.clear()
                self.load_tree()

        elif item_type == "doc":
            # Suppression d'un document
            doc = DocumentModel.get_by_id(item_id)
            reply = QMessageBox.question(self, "Confirmation", f"Supprimer le document '{doc.title}' ?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                with db.atomic():
                    doc.delete_instance()
                self.preview_text.clear()
                self.load_tree()

    def on_item_selected(self, item: QTreeWidgetItem, column: int) -> None:
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        if data.get("type") == "doc":
            doc = DocumentModel.get_by_id(data.get("id"))
            self.preview_text.setPlainText(doc.content)
        else:
            # Si on clique sur un dossier, on vide l'aperçu
            self.preview_text.clear()

    def import_document(self) -> None:
        # On regarde si un dossier est sélectionné pour ranger le fichier directement dedans
        selected_items = self.tree.selectedItems()
        self.current_folder_id_for_import = None

        if selected_items:
            data = selected_items[0].data(0, Qt.UserRole)
            if data and data.get("type") == "folder":
                self.current_folder_id_for_import = data.get("id")

        path, _ = QFileDialog.getOpenFileName(self, "Importer un cours", "", "Documents PDF/TXT (*.pdf *.txt *.md)")
        if not path:
            return

        doc_title = os.path.basename(path)
        if DocumentModel.get_or_none(DocumentModel.title == doc_title):
            QMessageBox.warning(self, "Doublon", "Ce document existe déjà dans la bibliothèque.")
            return

        self.btn_import.setEnabled(False)
        self.btn_import.setText("⏳ Extraction IA (Marker) en cours...")
        self.preview_text.setPlainText("🤖 Analyse du document en cours...\nLe Mac va ventiler, c'est normal ! 🚀")

        self.worker = ParserWorker(path, DocumentParser())
        self.worker.finished_signal.connect(self._on_parsing_success)
        self.worker.error_signal.connect(self._on_parsing_error)
        self.worker.start()

    def _on_parsing_success(self, title: str, content: str) -> None:
        folder = None
        if self.current_folder_id_for_import:
            folder = FolderModel.get_by_id(self.current_folder_id_for_import)

        with db.atomic():
            DocumentModel.create(title=title, content=content, folder=folder)

        self.btn_import.setEnabled(True)
        self.btn_import.setText("📄 Analyser un PDF/TXT (Marker)")
        self.load_tree()
        QMessageBox.information(self, "Succès", f"Le document '{title}' a été analysé et rangé !")

    def _on_parsing_error(self, error_msg: str) -> None:
        self.btn_import.setEnabled(True)
        self.btn_import.setText("📄 Analyser un PDF/TXT (Marker)")
        self.preview_text.setPlainText("")
        QMessageBox.critical(self, "Erreur d'extraction", f"Marker a rencontré un problème :\n{error_msg}")