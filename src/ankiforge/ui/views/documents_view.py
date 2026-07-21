import typing

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget, QTreeWidgetItem, QTextEdit, QLabel
from PySide6.QtCore import Qt

from ankiforge.ui.components.panels import IdePanel
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.database.models import DocumentModel, FolderModel
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class DocumentsView(QWidget):
    def __init__(self, parent: typing.Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(0, 0, 0, 0)

        self.panel = IdePanel(detachable=True)
        self.layout_main.addWidget(self.panel)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Panel (Explorer)
        self.left_widget = QWidget()
        self.left_layout = QVBoxLayout(self.left_widget)

        self.toolbar_left = QHBoxLayout()
        self.btn_import = PrimaryButton("Importer", self)
        self.btn_new_folder = SecondaryButton("Nouveau dossier", self)
        self.toolbar_left.addWidget(self.btn_import)
        self.toolbar_left.addWidget(self.btn_new_folder)
        self.left_layout.addLayout(self.toolbar_left)

        self.tree_explorer = QTreeWidget()
        self.tree_explorer.setHeaderLabel("Explorateur")
        self.tree_explorer.itemSelectionChanged.connect(self._on_document_selected)
        self.left_layout.addWidget(self.tree_explorer)

        self.splitter.addWidget(self.left_widget)

        # Right Panel (Reader)
        self.right_widget = QWidget()
        self.right_layout = QVBoxLayout(self.right_widget)

        self.toolbar_right = QHBoxLayout()
        self.btn_marker = PrimaryButton("Analyse Marker", self)
        self.btn_url = SecondaryButton("Import URL", self)
        self.btn_save = PrimaryButton("Enregistrer", self)
        self.lbl_word_count = QLabel("Mots: 0")
        self.lbl_word_count.setStyleSheet(f"background-color: {DesignTokens.BG_HOVER}; border-radius: 12px; padding: 4px 8px; color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")

        self.toolbar_right.addWidget(self.btn_marker)
        self.toolbar_right.addWidget(self.btn_url)
        self.toolbar_right.addStretch()
        self.toolbar_right.addWidget(self.lbl_word_count)
        self.toolbar_right.addWidget(self.btn_save)

        self.right_layout.addLayout(self.toolbar_right)

        self.text_editor = QTextEdit()
        self.text_editor.textChanged.connect(self._on_text_changed)
        self.right_layout.addWidget(self.text_editor)

        self.splitter.addWidget(self.right_widget)

        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)

        # We need a wrapper to add to the IdePanel tabs
        self.wrapper = QWidget()
        wrapper_layout = QVBoxLayout(self.wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(self.splitter)

        self.panel.add_tab("My Documents", self.wrapper, "ph.files", closable=False)

        self._current_doc_id: typing.Optional[int] = None
        self._dirty = False

    def refresh_data(self) -> None:
        self.tree_explorer.clear()

        folders = FolderModel.select()
        folder_items = {}

        # Add a "Sans dossier" root
        root_no_folder = QTreeWidgetItem(self.tree_explorer, ["Sans dossier"])
        root_no_folder.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": None})

        for folder in folders:
            item = QTreeWidgetItem(self.tree_explorer, [folder.name])
            item.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": folder.id})
            folder_items[folder.id] = item

        documents = DocumentModel.select()
        for doc in documents:
            parent_item = folder_items.get(doc.folder_id) if doc.folder_id else root_no_folder
            item = QTreeWidgetItem(parent_item, [doc.title])
            item.setData(0, Qt.ItemDataRole.UserRole, {"type": "doc", "id": doc.id})
            if doc.title.lower().endswith(".pdf"):
                item.setIcon(0, load_phosphor_icon("ph.file-pdf", color="#ef4444"))
            elif doc.title.lower().endswith(".txt"):
                item.setIcon(0, load_phosphor_icon("ph.file-text", color="#3b82f6"))
            elif doc.title.lower().endswith(".md"):
                item.setIcon(0, load_phosphor_icon("ph.file-code", color="#eab308"))
            else:
                item.setIcon(0, load_phosphor_icon("ph.file-text", color=DesignTokens.TEXT_MUTED))

        self.tree_explorer.expandAll()

    def is_dirty(self) -> bool:
        return self._dirty

    def _on_document_selected(self) -> None:
        items = self.tree_explorer.selectedItems()
        if not items:
            return

        item = items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data["type"] == "doc":
            doc = DocumentModel.get_or_none(DocumentModel.id == data["id"])
            if doc:
                self._current_doc_id = doc.id
                self.text_editor.blockSignals(True)
                self.text_editor.setPlainText(doc.content)
                self.text_editor.blockSignals(False)
                self._dirty = False
                self._update_word_count()

    def _on_text_changed(self) -> None:
        self._dirty = True
        self._update_word_count()

    def _update_word_count(self) -> None:
        text = self.text_editor.toPlainText()
        count = len(text.split())
        self.lbl_word_count.setText(f"Mots: {count}")
