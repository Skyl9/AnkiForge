"""
Dialogue de sélection de paquet Anki avec prise en charge de l'arborescence (::).
"""

from typing import Any, Optional, Sequence, Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QLabel,
    QWidget,
)

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.components import PrimaryButton, SecondaryButton
from ankiforge.utils.icon_loader import load_phosphor_icon


class DeckSelectionDialog(QDialog):
    """
    Fenêtre modale permettant de sélectionner un paquet sous forme d'arborescence.
    """

    def __init__(self, title: str, items: Sequence[Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(400, 500)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; color: {DesignTokens.TEXT_PRIMARY};")

        self.items = items
        self.selected_item: Optional[Any] = None

        self._setup_ui()
        self._populate_tree(self.items)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Barre de recherche
        search_layout = QHBoxLayout()
        search_icon = QLabel()
        search_icon.setPixmap(load_phosphor_icon("ph.magnifying-glass", color=DesignTokens.TEXT_MUTED).pixmap(18, 18))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher un paquet...")
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 6px 10px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.search_input.textChanged.connect(self._filter_items)
        search_layout.addWidget(search_icon)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        # Arbre des paquets
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 4px;
                outline: none;
            }}
            QTreeWidget::item {{
                padding: 6px;
                border-radius: 4px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QTreeWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QTreeWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
                color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.tree_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.tree_widget)

        # Boutons d'action
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = SecondaryButton("Annuler")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_accept = PrimaryButton("Sélectionner")
        self.btn_accept.clicked.connect(self.accept)
        self.btn_accept.setEnabled(False)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_accept)
        layout.addLayout(btn_layout)

    def _populate_tree(self, items: Sequence[Any], filter_text: str = "") -> None:
        self.tree_widget.clear()

        # Build hierarchy
        nodes: Dict[str, QTreeWidgetItem] = {}

        # Sort items by name so parents are created before children
        sorted_items = sorted(items, key=lambda i: getattr(i, "name", str(i)))

        for item in sorted_items:
            name = getattr(item, "name", str(item))
            if filter_text and filter_text.lower() not in name.lower():
                continue

            parts = name.split("::")
            parent_item = None

            # Construct path to find parent
            for i in range(1, len(parts)):
                parent_path = "::".join(parts[:i])
                if parent_path in nodes:
                    parent_item = nodes[parent_path]

            node_name = parts[-1]

            if parent_item:
                tree_item = QTreeWidgetItem(parent_item, [f"🎴 {node_name}"])
            else:
                tree_item = QTreeWidgetItem(self.tree_widget, [f"🎴 {node_name}"])

            tree_item.setData(0, Qt.ItemDataRole.UserRole, item)
            nodes[name] = tree_item

        self.tree_widget.expandAll()

    def _filter_items(self, text: str) -> None:
        self._populate_tree(self.items, text)

    def _on_selection_changed(self) -> None:
        selected = self.tree_widget.selectedItems()
        self.btn_accept.setEnabled(len(selected) > 0)
        if selected:
            self.selected_item = selected[0].data(0, Qt.ItemDataRole.UserRole)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        self.selected_item = item.data(0, Qt.ItemDataRole.UserRole)
        if self.selected_item is not None:
            self.accept()

    def get_selected_item(self) -> Optional[Any]:
        return self.selected_item
