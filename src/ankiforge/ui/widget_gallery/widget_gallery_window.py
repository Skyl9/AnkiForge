"""Fenêtre de la galerie de widgets (mode développeur)."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
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

from ankiforge.ui.style_engine import get_style_engine
from ankiforge.ui.style_engine.themes import get_theme_families
from ankiforge.ui.widget_gallery.families import load_families
from ankiforge.ui.widget_gallery.preview_container import PreviewContainer
from ankiforge.ui.widget_gallery.registry import GalleryEntry, WidgetGalleryRegistry
from ankiforge.utils.i18n import tr

logger = logging.getLogger(__name__)

LAYOUT_IDS = ["ide", "macos", "dashboard", "glassmorphism"]


class WidgetGalleryWindow(QDialog):
    """Fenêtre de galerie de widgets pour le mode développeur."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Galerie de widgets (mode développeur)"))
        self.resize(1000, 700)
        self._current_entry: GalleryEntry | None = None
        self._loaded_families = load_families()
        if not self._loaded_families:
            logger.warning("Aucune famille de galerie n'a pu être chargée")
        else:
            logger.debug("Familles de galerie chargées : %s", ", ".join(self._loaded_families))
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

        toolbar = QHBoxLayout()

        self.theme_combo = QComboBox(self)
        for family in get_theme_families():
            self.theme_combo.addItem(family.name, family.id)
        engine = get_style_engine()
        current_theme_id = engine.current_theme.id
        for idx in range(self.theme_combo.count()):
            if self.theme_combo.itemData(idx) == current_theme_id:
                self.theme_combo.setCurrentIndex(idx)
                break
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        toolbar.addWidget(self.theme_combo)

        self.layout_combo = QComboBox(self)
        for layout_id in LAYOUT_IDS:
            self.layout_combo.addItem(layout_id, layout_id)
        self.layout_combo.currentIndexChanged.connect(self._on_layout_changed)
        toolbar.addWidget(self.layout_combo)

        toolbar.addStretch()

        self.open_modal_btn = QPushButton(tr("Ouvrir en modal"), self)
        self.open_modal_btn.setEnabled(False)
        self.open_modal_btn.clicked.connect(self._on_open_modal)
        toolbar.addWidget(self.open_modal_btn)
        layout.addLayout(toolbar)

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

    def _on_theme_changed(self, index: int) -> None:
        theme_id = self.theme_combo.itemData(index)
        if not theme_id:
            return
        try:
            engine = get_style_engine()
            engine.apply_theme(str(theme_id), QApplication.instance())
        except Exception as exc:
            logger.exception("Échec changement de thème: %s", exc)

    def _on_layout_changed(self, index: int) -> None:
        layout_id = self.layout_combo.itemData(index)
        if not layout_id:
            return
        try:
            app = QApplication.instance()
            mw = app.activeWindow() if app else None
            if mw and hasattr(mw, "apply_layout"):
                mw.apply_layout(str(layout_id))
            else:
                logger.debug("Pas de fenêtre principale pour appliquer le layout %s", layout_id)
        except Exception as exc:
            logger.exception("Échec changement de layout: %s", exc)

    def _on_open_modal(self) -> None:
        entry = self._current_entry
        if entry is None or entry.family != "dialogs":
            return
        try:
            widget = entry.factory()
            if isinstance(widget, QDialog) or hasattr(widget, "exec"):
                widget.exec()
            else:
                widget.show()
        except Exception as exc:
            logger.exception("Échec ouverture modale: %s", exc)
