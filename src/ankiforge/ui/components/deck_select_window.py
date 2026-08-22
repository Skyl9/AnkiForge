"""
Composant de sélection de dossier / deck.
Reproduit la maquette `folder_select_modal.html`.
"""

from typing import Optional, Dict
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem, QAbstractItemView
from PySide6.QtGui import QColor, QPalette
from PySide6.QtCore import Qt, Signal

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.database.models import DeckModel


class DeckSelectWindow(QWidget):
    """
    Fenêtre de sélection de paquet (Deck) avec arborescence et recherche.
    """

    deck_selected = Signal(int, str)  # (deck_id, deck_name)

    def __init__(self, title: str = "Sélectionner un Dossier / Deck (Collection)", parent: Optional[QWidget] = None) -> None:
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
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 14, 14, 14)
        content_layout.setSpacing(12)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher un dossier (ex: Informatique, C++)...")
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

        content_layout.addWidget(self.search_input)

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

        content_layout.addWidget(self.tree)
        layout.addWidget(content)

        # 3. Footer
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(8)

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.clicked.connect(self.close)

        self.btn_confirm = PrimaryButton("Valider ce dossier")
        self.btn_confirm.clicked.connect(self._on_confirm)
        self.btn_confirm.setEnabled(False)

        footer_layout.addStretch()
        footer_layout.addWidget(btn_cancel)
        footer_layout.addWidget(self.btn_confirm)
        layout.addWidget(footer)

        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemDoubleClicked.connect(self._on_confirm)

        self._load_decks()

    def _load_decks(self) -> None:
        """Charge l'arborescence des paquets depuis DeckModel."""
        self.tree.clear()

        # 0. Item root global
        global_item = QTreeWidgetItem(["Tous les paquets"])
        global_item.setData(0, Qt.ItemDataRole.UserRole, -1)
        global_item.setIcon(0, load_phosphor_icon("folders", color=DesignTokens.COLOR_BLUE))
        self.tree.addTopLevelItem(global_item)

        decks = list(DeckModel.select())

        # Dictionnaire pour retrouver les items par ID
        self._items_by_id: Dict[int, QTreeWidgetItem] = {}

        # 1. Créer tous les items
        for deck in decks:
            item = QTreeWidgetItem([deck.name])
            item.setData(0, Qt.ItemDataRole.UserRole, deck.id)

            # Icon
            icon = load_phosphor_icon("folder", color=DesignTokens.COLOR_BLUE)
            item.setIcon(0, icon)

            self._items_by_id[deck.id] = item

        # 2. Établir la hiérarchie
        for deck in decks:
            item = self._items_by_id[deck.id]
            if deck.parent_deck_id and deck.parent_deck_id in self._items_by_id:
                parent_item = self._items_by_id[deck.parent_deck_id]
                parent_item.addChild(item)
            else:
                global_item.addChild(item)

        # 3. Étendre tout par défaut (pour que ce soit facile à voir)
        self.tree.expandAll()

    def _on_search_changed(self, text: str) -> None:
        """Filtre l'arborescence : affiche les noeuds correspondants ET leurs parents."""
        query = text.lower().strip()

        if not query:
            # Réafficher tout
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                if item:
                    self._set_item_visibility_recursive(item, True)
            return

        # Sinon, cacher tout d'abord
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item:
                self._set_item_visibility_recursive(item, False)

        # Parcourir et afficher les correspondances et remonter pour afficher les parents
        for item in self._items_by_id.values():
            if query in item.text(0).lower():
                # On le rend visible
                item.setHidden(False)
                # Et tous ses parents
                parent = item.parent()
                while parent:
                    parent.setHidden(False)
                    parent.setExpanded(True)
                    parent = parent.parent()

    def _set_item_visibility_recursive(self, item: QTreeWidgetItem, visible: bool) -> None:
        item.setHidden(not visible)
        for i in range(item.childCount()):
            self._set_item_visibility_recursive(item.child(i), visible)

    def _on_selection_changed(self) -> None:
        selected = self.tree.selectedItems()
        self.btn_confirm.setEnabled(len(selected) > 0)

    def _on_confirm(self) -> None:
        selected = self.tree.selectedItems()
        if selected:
            item = selected[0]
            deck_id = item.data(0, Qt.ItemDataRole.UserRole)
            deck_name = item.text(0)
            self.deck_selected.emit(deck_id, deck_name)
            self.close()
