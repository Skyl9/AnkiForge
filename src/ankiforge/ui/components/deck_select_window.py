"""
Composant de sélection de dossier / deck.
Reproduit la maquette `folder_select_modal.html`.
"""

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QInputDialog, QLineEdit, QMessageBox, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ankiforge.database.models import DeckModel
from ankiforge.repositories.deck_repository import DeckRepository
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens, StyledMenu
from ankiforge.utils.hierarchy import SEPARATOR, join_hierarchy, leaf_name, split_hierarchy
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

#: Identifiant du nœud racine virtuel « Tous les paquets » (aucun DeckModel réel ne porte cet id).
ALL_DECKS_NODE_ID = -1


class DeckSelectWindow(QWidget):
    """
    Fenêtre de sélection de paquet (Deck) avec arborescence et recherche.
    """

    deck_selected = Signal(int, str)  # (deck_id, deck_name)

    def __init__(
        self,
        title: str = "Sélectionner un Dossier / Deck (Collection)",
        allow_all: bool = True,
        selected_deck_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.allow_all = allow_all
        self.selected_deck_id = selected_deck_id
        self._deck_repo = DeckRepository()

        self.setWindowTitle(title)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(480, 520)

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
        self.search_input.setPlaceholderText(self.tr("Rechercher un dossier (ex: Informatique, C++)..."))
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
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_context_menu)

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

        btn_new_deck = SecondaryButton("Nouveau paquet")
        btn_new_deck.setIcon(load_phosphor_icon("folder-plus", color=DesignTokens.TEXT_PRIMARY))
        btn_new_deck.clicked.connect(lambda: self._open_create_deck_dialog())

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.clicked.connect(self.close)

        self.btn_confirm = PrimaryButton("Valider ce dossier")
        self.btn_confirm.clicked.connect(self._on_confirm)
        self.btn_confirm.setEnabled(False)

        footer_layout.addWidget(btn_new_deck)
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
        self._items_by_id: dict[int, QTreeWidgetItem] = {}

        global_item: QTreeWidgetItem | None = None
        if self.allow_all:
            global_item = QTreeWidgetItem([self.tr("Tous les paquets")])
            global_item.setData(0, Qt.ItemDataRole.UserRole, ALL_DECKS_NODE_ID)
            global_item.setIcon(0, load_phosphor_icon("folders", color=DesignTokens.COLOR_BLUE))
            self.tree.addTopLevelItem(global_item)
            self._items_by_id[ALL_DECKS_NODE_ID] = global_item

        decks = list(DeckModel.select().order_by(DeckModel.name.asc()))

        # 1. Créer tous les items
        for deck in decks:
            item = QTreeWidgetItem([deck.name])
            item.setData(0, Qt.ItemDataRole.UserRole, deck.id)

            icon = load_phosphor_icon("folder", color=DesignTokens.COLOR_BLUE)
            item.setIcon(0, icon)

            self._items_by_id[deck.id] = item

        # 2. Établir la hiérarchie
        for deck in decks:
            item = self._items_by_id[deck.id]
            if deck.parent_deck_id and deck.parent_deck_id in self._items_by_id:
                parent_item = self._items_by_id[deck.parent_deck_id]
                parent_item.addChild(item)
            elif global_item:
                global_item.addChild(item)
            else:
                self.tree.addTopLevelItem(item)

        self.tree.expandAll()

        if self.selected_deck_id is not None and self.selected_deck_id in self._items_by_id:
            item = self._items_by_id[self.selected_deck_id]
            self.tree.setCurrentItem(item)
            self.btn_confirm.setEnabled(True)

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
        if not selected:
            self.btn_confirm.setEnabled(False)
            return

        item = selected[0]
        deck_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not self.allow_all and deck_id == ALL_DECKS_NODE_ID:
            self.btn_confirm.setEnabled(False)
        else:
            self.btn_confirm.setEnabled(True)

    def _on_confirm(self) -> None:
        selected = self.tree.selectedItems()
        if selected:
            item = selected[0]
            deck_id = item.data(0, Qt.ItemDataRole.UserRole)
            if not self.allow_all and deck_id == ALL_DECKS_NODE_ID:
                return
            deck_name = item.text(0)
            self.deck_selected.emit(deck_id, deck_name)
            self.close()

    def _open_create_deck_dialog(self, initial_name: str = "") -> None:
        from ankiforge.ui.dialogs.create_deck_dialog import CreateDeckDialog

        dlg = CreateDeckDialog(initial_name=initial_name, parent=self)
        dlg.deck_created.connect(self._on_deck_created)
        dlg.exec()

    def _on_deck_created(self, deck_id: int, deck_name: str) -> None:
        self.selected_deck_id = deck_id
        self._load_decks()
        if deck_id in self._items_by_id:
            item = self._items_by_id[deck_id]
            self.tree.setCurrentItem(item)
            self.btn_confirm.setEnabled(True)

    # ── Modification en place du paquet de destination ─────────────────────────
    # Le modal ne se contentait que de sélectionner ou créer un paquet : renommer,
    # supprimer et créer un sous-paquet devaient se faire ailleurs. Ces actions
    # modifient l'arborescence sans quitter le flux de création.

    def _build_context_menu(self, deck_id: object) -> StyledMenu | None:
        """Construit le menu « Modifier » d'un paquet, ou None si le nœud n'est pas modifiable.

        Le nœud racine virtuel « Tous les paquets » et les données invalides sont
        ignorés : seul un paquet réel est modifiable.
        """
        if not isinstance(deck_id, int) or deck_id == ALL_DECKS_NODE_ID:
            return None
        menu = StyledMenu(self)
        menu.addAction(load_phosphor_icon("folder-plus", color=DesignTokens.TEXT_PRIMARY), self.tr("Nouveau sous-paquet")).triggered.connect(lambda: self._create_subdeck(deck_id))
        menu.addAction(load_phosphor_icon("pencil-simple", color=DesignTokens.TEXT_PRIMARY), self.tr("Renommer le paquet")).triggered.connect(lambda: self._rename_deck(deck_id))
        menu.addAction(load_phosphor_icon("trash", color=DesignTokens.COLOR_RED), self.tr("Supprimer le paquet")).triggered.connect(lambda: self._delete_deck(deck_id))
        return menu

    def _on_tree_context_menu(self, pos: QPoint) -> None:
        """Ouvre le menu « Modifier » sur le paquet ciblé par le clic droit.

        Le clic droit sélectionne d'abord le nœud ciblé (comportement standard des
        menus contextuels) : les actions agissent donc toujours sur la sélection courante.
        """
        item = self.tree.itemAt(pos)
        if item is None:
            return
        deck_id = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(deck_id, int) and deck_id != ALL_DECKS_NODE_ID:
            self.tree.setCurrentItem(item)
        menu = self._build_context_menu(deck_id)
        if menu is not None:
            menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _create_subdeck(self, deck_id: int) -> None:
        """Ouvre la création d'un paquet en le pré-remplissant sous le paquet sélectionné."""
        deck = self._deck_repo.get_deck_by_id(deck_id)
        if deck is None:
            return
        self._open_create_deck_dialog(initial_name=f"{deck.name}{SEPARATOR}")

    def _rename_deck(self, deck_id: int) -> None:
        """Renomme la feuille du paquet (les sous-paquets suivent le préfixe)."""
        deck = self._deck_repo.get_deck_by_id(deck_id)
        if deck is None:
            return

        current_leaf = leaf_name(deck.name)
        new_leaf, ok = QInputDialog.getText(self, self.tr("Renommer le paquet"), self.tr("Nouveau nom :"), text=current_leaf)
        new_leaf = new_leaf.strip()
        if not ok or not new_leaf or new_leaf == current_leaf:
            return

        parts = split_hierarchy(deck.name)
        new_name = join_hierarchy([*parts[:-1], new_leaf])
        # La collision porte sur l'identité hiérarchique entière : un paquet « B » existe déjà
        # si un « B » exact OU un descendant « B::… » occupe sa place (le préfixe serait doublé).
        colliding = self._deck_repo.get_descendant_decks(new_name)
        if any(d.id != deck_id for d in colliding):
            QMessageBox.warning(self, self.tr("Renommage impossible"), tr("Un paquet nommé « %1 » existe déjà.", new_name))
            return

        renamed = self._deck_repo.rename_deck(deck_id, new_name)
        if renamed is None:
            return
        self.selected_deck_id = renamed.id
        self._load_decks()

    def _delete_deck(self, deck_id: int) -> None:
        """Supprime le paquet, ses sous-paquets et leurs cartes, après confirmation."""
        deck = self._deck_repo.get_deck_by_id(deck_id)
        if deck is None:
            return

        confirm = QMessageBox.question(
            self,
            self.tr("Supprimer le paquet"),
            tr("Supprimer le paquet « %1 » ainsi que ses sous-paquets et leurs cartes ?", deck.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        # Capturer la sous-arborescence AVANT suppression : après coup, les enregistrements
        # n'existent plus et ne pourraient plus désigner une éventuelle sélection orpheline.
        subtree_ids = {d.id for d in self._deck_repo.get_descendant_decks(deck.name)}

        if not self._deck_repo.delete_deck(deck_id):
            return
        if self.selected_deck_id in subtree_ids:
            self.selected_deck_id = None
            self.btn_confirm.setEnabled(False)
        self._load_decks()
