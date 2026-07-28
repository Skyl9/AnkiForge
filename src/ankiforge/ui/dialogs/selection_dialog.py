"""
Dialogue générique de sélection d'éléments (Paquets, Modèles, etc.).
"""

from typing import Any, Callable, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QWidget,
)

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.components import PrimaryButton, SecondaryButton
from ankiforge.utils.icon_loader import load_phosphor_icon


class SelectionDialog(QDialog):
    """
    Fenêtre modale générique permettant de filtrer et sélectionner un élément dans une liste.
    """

    def __init__(self, title: str, items: Sequence[Any], display_func: Callable[[Any], str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(400, 500)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; color: {DesignTokens.TEXT_PRIMARY};")

        self.items = items
        self.display_func = display_func
        self.selected_item: Optional[Any] = None

        self._setup_ui()
        self._populate_list(self.items)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Barre de recherche
        search_layout = QHBoxLayout()
        search_icon = QLabel()
        search_icon.setPixmap(load_phosphor_icon("ph.magnifying-glass", color=DesignTokens.TEXT_MUTED).pixmap(18, 18))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher...")
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM};
                padding: 6px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.search_input.textChanged.connect(self._filter_items)
        search_layout.addWidget(search_icon)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        # Liste des éléments
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM};
                outline: none;
            }}
            QListWidget::item {{
                padding: 10px;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
                border-left: 2px solid {DesignTokens.ACCENT_PRIMARY};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.list_widget)

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

    def _populate_list(self, items: Sequence[Any]) -> None:
        self.list_widget.clear()
        for item in items:
            list_item = QListWidgetItem(self.display_func(item))
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.list_widget.addItem(list_item)

    def _filter_items(self, text: str) -> None:
        text = text.lower()
        filtered = [item for item in self.items if text in self.display_func(item).lower()]
        self._populate_list(filtered)

    def _on_selection_changed(self) -> None:
        selected = self.list_widget.selectedItems()
        self.btn_accept.setEnabled(len(selected) > 0)
        if selected:
            self.selected_item = selected[0].data(Qt.ItemDataRole.UserRole)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        self.selected_item = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def get_selected_item(self) -> Optional[Any]:
        return self.selected_item
