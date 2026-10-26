"""Fenêtre de la galerie de widgets (mode développeur)."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.widget_gallery.preview_container import PreviewContainer
from ankiforge.ui.widget_gallery.registry import GalleryEntry, WidgetGalleryRegistry
from ankiforge.utils.i18n import tr

logger = logging.getLogger(__name__)


class WidgetGalleryWindow(QDialog):
    """Fenêtre de galerie de widgets pour le mode développeur."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Galerie de widgets (mode développeur)"))
        self.resize(1000, 700)
        self._current_entry: GalleryEntry | None = None
        self._setup_ui()
        self._populate()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText(tr("Rechercher un widget..."))
        self.search_edit.textChanged.connect(self._on_search)
        layout.addWidget(self.search_edit)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.itemSelectionChanged.connect(self._on_selection)
        splitter.addWidget(self.tree)

        self.preview = PreviewContainer(self)
        splitter.addWidget(self.preview)
        splitter.setSizes([300, 700])
        layout.addWidget(splitter)

        btn_row = QHBoxLayout()

        self.open_modal_btn = QPushButton(tr("Ouvrir en modal"), self)
        self.open_modal_btn.setEnabled(False)
        btn_row.addWidget(self.open_modal_btn)
        layout.addLayout(btn_row)

    def _populate(self) -> None:
        self.tree.clear()
        for family in WidgetGalleryRegistry.families():
            fam_item = QTreeWidgetItem([family])
            self.tree.addTopLevelItem(fam_item)
            for entry in WidgetGalleryRegistry.list(family=family):
                child = QTreeWidgetItem([entry.name])
                child.setData(0, Qt.ItemDataRole.UserRole, entry)
                fam_item.addChild(child)
        self.tree.expandAll()

    def _on_search(self, text: str) -> None:
        self.tree.clear()
        entries = WidgetGalleryRegistry.list(query=text if text.strip() else None)
        families = sorted({e.family for e in entries})
        for family in families:
            fam_item = QTreeWidgetItem([family])
            self.tree.addTopLevelItem(fam_item)
            for entry in entries:
                if entry.family != family:
                    continue
                child = QTreeWidgetItem([entry.name])
                child.setData(0, Qt.ItemDataRole.UserRole, entry)
                fam_item.addChild(child)
        self.tree.expandAll()

    def _on_selection(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        item = items[0]
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if entry is None:
            return
        self._current_entry = entry
        self.preview.set_entry(entry)
        self.open_modal_btn.setEnabled(entry.family == "dialogs")
