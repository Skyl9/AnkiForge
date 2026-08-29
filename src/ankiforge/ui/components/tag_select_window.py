"""
Fenêtre de sélection de tag.
Basée sur DeckSelectWindow pour maintenir une cohérence d'UX.
"""

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ankiforge.database.models import NoteModel
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class TagSelectWindow(QWidget):
    """
    Fenêtre de sélection de Tag avec arborescence (::) et recherche.
    """

    tag_selected = Signal(str)  # (tag_name)

    def __init__(self, title: str = "Sélectionner ou Ajouter un Tag", allowed_tags: set[str] | None = None, parent: QWidget | None = None) -> None:
        self.allowed_tags = allowed_tags
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(450, 500)

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {DesignTokens.BG_PANEL};
            }}
        """)

        # 1. Content
        self.setWindowFlags(Qt.WindowType.Dialog if parent else Qt.WindowType.Window)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Search Bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher ou saisir un nouveau tag...")
        search_icon = load_phosphor_icon("magnifying-glass", color=DesignTokens.TEXT_MUTED)
        self.search_input.addAction(search_icon, QLineEdit.ActionPosition.LeadingPosition)
        self.search_input.setFixedHeight(32)

        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 0 10px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                font-family: '{DesignTokens.FONT_MAIN}';
            }}
            QLineEdit:focus {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.search_input.textChanged.connect(self._on_search_changed)

        layout.addWidget(self.search_input)

        # TreeWidget
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setExpandsOnDoubleClick(True)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        # Override native highlight palette
        palette = self.tree.palette()
        palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 0, 0, 0))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(DesignTokens.ACCENT_PRIMARY))
        self.tree.setPalette(palette)

        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 13px;
                font-family: '{DesignTokens.FONT_MAIN}';
                show-decoration-selected: 1;
                outline: none;
            }}
            QTreeWidget::item {{
                padding: 6px 4px;
                border: none;
            }}
            QTreeWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QTreeWidget::item:selected {{
                font-weight: bold;
            }}
        """)

        layout.addWidget(self.tree)

        # 3. Footer
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(8)

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.clicked.connect(self.close)

        self.btn_confirm = PrimaryButton("Valider ce tag")
        self.btn_confirm.clicked.connect(self._on_confirm)
        # Activer le bouton si on a tapé quelque chose de nouveau ou sélectionné
        self.btn_confirm.setEnabled(False)

        footer_layout.addStretch()
        footer_layout.addWidget(btn_cancel)
        footer_layout.addWidget(self.btn_confirm)
        layout.addWidget(footer)

        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemDoubleClicked.connect(self._on_confirm)

        self._items_by_path: dict[str, QTreeWidgetItem] = {}
        self._load_tags()

    def _load_tags(self) -> None:
        """Charge l'arborescence des tags depuis NoteModel."""
        self.tree.clear()
        self._items_by_path.clear()

        all_tags = set()
        if self.allowed_tags is not None:
            all_tags = self.allowed_tags.copy()
        else:
            for note in NoteModel.select(NoteModel.tags).where(NoteModel.tags.is_null(False)):
                try:
                    tags = json.loads(note.tags)
                    if isinstance(tags, list):
                        for t in tags:
                            if t.strip():
                                all_tags.add(t.strip())
                except Exception as e:
                    import logging

                    logging.warning(f"An error occurred: {e}")

        # Trier alphabétiquement pour que les parents soient créés avant les enfants
        sorted_tags = sorted(list(all_tags))

        for tag in sorted_tags:
            parts = tag.split("::")
            parent_item = None

            # Construire ou trouver les parents
            for i in range(1, len(parts)):
                parent_path = "::".join(parts[:i])
                if parent_path in self._items_by_path:
                    parent_item = self._items_by_path[parent_path]
                else:
                    # Créer le noeud parent intermédiaire s'il n'existe pas
                    new_item = QTreeWidgetItem(parent_item, [parts[i - 1]]) if parent_item else QTreeWidgetItem(self.tree, [parts[i - 1]])
                    new_item.setData(0, Qt.ItemDataRole.UserRole, parent_path)
                    new_item.setIcon(0, load_phosphor_icon("tag", color=DesignTokens.ACCENT_PRIMARY))
                    self._items_by_path[parent_path] = new_item
                    parent_item = new_item

            node_name = parts[-1]
            item = QTreeWidgetItem(parent_item, [node_name]) if parent_item else QTreeWidgetItem(self.tree, [node_name])

            item.setData(0, Qt.ItemDataRole.UserRole, tag)
            item.setIcon(0, load_phosphor_icon("tag", color=DesignTokens.ACCENT_PRIMARY))
            self._items_by_path[tag] = item

        self.tree.expandAll()

    def _on_search_changed(self, text: str) -> None:
        """Filtre l'arborescence et permet d'ajouter un nouveau tag."""
        query = text.lower().strip()

        if query:
            self.btn_confirm.setEnabled(True)
        else:
            self.btn_confirm.setEnabled(len(self.tree.selectedItems()) > 0)

        if not query:
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                if item:
                    self._set_item_visibility_recursive(item, True)
            return

        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item:
                self._set_item_visibility_recursive(item, False)

        for path, item in self._items_by_path.items():
            if query in path.lower() or query in item.text(0).lower():
                item.setHidden(False)
                parent = item.parent()
                while parent:
                    parent.setHidden(False)
                    parent.setExpanded(True)
                    parent = parent.parent()

    def _set_item_visibility_recursive(self, item: QTreeWidgetItem, visible: bool) -> None:
        item.setHidden(not visible)
        for i in range(item.childCount()):
            child = item.child(i)
            if child:
                self._set_item_visibility_recursive(child, visible)

    def _on_selection_changed(self) -> None:
        selected = self.tree.selectedItems()
        if selected:
            tag = selected[0].data(0, Qt.ItemDataRole.UserRole)
            self.search_input.setText(tag)
        self.btn_confirm.setEnabled(len(self.search_input.text().strip()) > 0)

    def _on_confirm(self) -> None:
        tag = self.search_input.text().strip()
        if tag:
            self.tag_selected.emit(tag)
            self.close()
