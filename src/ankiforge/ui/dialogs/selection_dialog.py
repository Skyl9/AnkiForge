"""
Dialogue générique de sélection d'éléments (Paquets, Modèles, etc.).
"""

from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class SelectionDialog(QDialog):
    """
    Fenêtre modale générique permettant de filtrer et sélectionner un élément dans une liste.
    """

    def __init__(self, title: str, items: Sequence[Any], display_func: Callable[[Any], str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(400, 500)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; color: {DesignTokens.TEXT_PRIMARY};")

        self.items = items
        self.display_func = display_func
        self.selected_item: Any | None = None

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
                background-color: {DesignTokens.BG_ACTIVE};
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
        if not items:
            empty_item = QListWidgetItem("Aucun élément disponible")
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            empty_item.setForeground(QColor(DesignTokens.TEXT_MUTED))
            self.list_widget.addItem(empty_item)
            return
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
        valid = [s for s in selected if s.data(Qt.ItemDataRole.UserRole) is not None]
        self.btn_accept.setEnabled(len(valid) > 0)
        if valid:
            self.selected_item = valid[0].data(Qt.ItemDataRole.UserRole)
        else:
            self.selected_item = None

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is not None:
            self.selected_item = data
            self.accept()

    def get_selected_item(self) -> Any | None:
        return self.selected_item


class MultiSelectionDialog(QDialog):
    """
    Fenêtre modale permettant de cocher un ou plusieurs éléments avec filtres et actions rapides.
    """

    def __init__(
        self,
        title: str,
        items: Sequence[Any],
        display_func: Callable[[Any], str],
        initial_selected: Sequence[Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(500, 520)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; color: {DesignTokens.TEXT_PRIMARY};")

        self.items = list(items)
        self.display_func = display_func
        self.checked_items: set[Any] = set(initial_selected or [])

        self._setup_ui()
        self._populate_list(self.items)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Barre de recherche & boutons rapides
        top_row = QHBoxLayout()
        search_icon = QLabel()
        search_icon.setPixmap(load_phosphor_icon("ph.magnifying-glass", color=DesignTokens.TEXT_MUTED).pixmap(18, 18))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher un modèle...")
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
        top_row.addWidget(search_icon)
        top_row.addWidget(self.search_input)

        btn_all = SecondaryButton("Tout cocher")
        btn_all.setFixedHeight(30)
        btn_all.clicked.connect(self._select_all)
        top_row.addWidget(btn_all)

        btn_none = SecondaryButton("Tout décocher")
        btn_none.setFixedHeight(30)
        btn_none.clicked.connect(self._deselect_all)
        top_row.addWidget(btn_none)

        layout.addLayout(top_row)

        # Liste des éléments avec cases à cocher
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
        """)
        self.list_widget.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.list_widget)

        # Boutons d'action
        btn_layout = QHBoxLayout()
        self.lbl_count = QLabel("0 modèle(s) sélectionné(s)")
        self.lbl_count.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px;")
        btn_layout.addWidget(self.lbl_count)
        btn_layout.addStretch()

        self.btn_cancel = SecondaryButton("Annuler")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_accept = PrimaryButton("Valider la sélection")
        self.btn_accept.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_accept)
        layout.addLayout(btn_layout)

    def _populate_list(self, items: Sequence[Any]) -> None:
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for item in items:
            name = self.display_func(item)
            desc = getattr(item, "description", "") or ""
            text = f"{name} — {desc}" if desc else name
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            list_item.setFlags(list_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            is_checked = item in self.checked_items or any(getattr(item, "id", None) == getattr(c, "id", None) for c in self.checked_items if hasattr(item, "id"))
            list_item.setCheckState(Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
            self.list_widget.addItem(list_item)
        self.list_widget.blockSignals(False)
        self._update_counter()

    def _filter_items(self, text: str) -> None:
        text = text.lower()
        filtered = [item for item in self.items if text in self.display_func(item).lower() or text in str(getattr(item, "description", "")).lower()]
        self._populate_list(filtered)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        obj = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self.checked_items.add(obj)
        else:
            self.checked_items = {c for c in self.checked_items if getattr(c, "id", c) != getattr(obj, "id", obj)}
        self._update_counter()

    def _select_all(self) -> None:
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setCheckState(Qt.CheckState.Checked)
        self.checked_items = set(self.items)
        self._update_counter()

    def _deselect_all(self) -> None:
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setCheckState(Qt.CheckState.Unchecked)
        self.checked_items.clear()
        self._update_counter()

    def _update_counter(self) -> None:
        count = len(self.checked_items)
        self.lbl_count.setText(f"{count} modèle(s) sélectionné(s)")
        self.btn_accept.setEnabled(count > 0)

    def get_selected_items(self) -> list[Any]:
        return [item for item in self.items if item in self.checked_items or any(getattr(item, "id", None) == getattr(c, "id", None) for c in self.checked_items if hasattr(item, "id"))]
