"""Composant de sélection de dossier / deck.

Reproduit la maquette `folder_select_modal.html`.
"""

from typing import cast

from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QCloseEvent, QColor, QKeyEvent, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

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
    """Fenêtre de sélection de paquet (Deck) avec arborescence et recherche."""

    deck_selected = Signal(int, str)  # (deck_id, deck_name)

    #: Mémoire de session des identifiants de paquets actuellement dépliés (None au tout premier affichage)
    _session_expanded_deck_ids: set[int] | None = None

    @classmethod
    def reset_session_expanded_state(cls) -> None:
        """Réinitialise la mémoire de session des paquets dépliés (utilisé en tests ou changement de profil)."""
        cls._session_expanded_deck_ids = None

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

        self._is_restoring_expansion: bool = False
        self._pre_search_expanded_ids: set[int] | None = None
        self._items_by_id: dict[int, QTreeWidgetItem] = {}
        self._full_names_by_id: dict[int, str] = {}

        self.setWindowTitle(title)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(500, 540)

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {DesignTokens.BG_PANEL};
            }}
        """)

        # 1. Content
        self.setWindowFlags(Qt.WindowType.Dialog if parent else Qt.WindowType.Window)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 14, 14, 14)
        content_layout.setSpacing(10)

        # Ligne de recherche & contrôles d'expansion
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.tr("Rechercher un dossier (ex: Informatique, C++)..."))
        search_icon = load_phosphor_icon("magnifying-glass", color=DesignTokens.TEXT_MUTED)
        self.search_input.addAction(search_icon, QLineEdit.ActionPosition.LeadingPosition)
        self.search_input.setClearButtonEnabled(True)
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
        search_row.addWidget(self.search_input, 1)

        self.btn_expand_all = QPushButton()
        self.btn_expand_all.setFixedSize(32, 32)
        self.btn_expand_all.setIcon(load_phosphor_icon("arrows-out", color=DesignTokens.TEXT_MUTED))
        self.btn_expand_all.setToolTip(self.tr("Tout déplier"))
        self.btn_expand_all.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
                border: 1px solid {DesignTokens.BORDER_FOCUS};
            }}
        """)
        self.btn_expand_all.clicked.connect(self.expand_all_nodes)
        search_row.addWidget(self.btn_expand_all)

        self.btn_collapse_all = QPushButton()
        self.btn_collapse_all.setFixedSize(32, 32)
        self.btn_collapse_all.setIcon(load_phosphor_icon("arrows-in", color=DesignTokens.TEXT_MUTED))
        self.btn_collapse_all.setToolTip(self.tr("Tout replier"))
        self.btn_collapse_all.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
                border: 1px solid {DesignTokens.BORDER_FOCUS};
            }}
        """)
        self.btn_collapse_all.clicked.connect(self.collapse_all_nodes)
        search_row.addWidget(self.btn_collapse_all)

        content_layout.addLayout(search_row)

        # Bandeau Sticky Conteneur au-dessus de l'arborescence
        self.sticky_header = QFrame()
        self.sticky_header.setObjectName("DeckSelectStickyHeader")
        sticky_layout = QHBoxLayout(self.sticky_header)
        sticky_layout.setContentsMargins(10, 6, 10, 6)
        sticky_layout.setSpacing(8)

        self.ico_sticky_container = QLabel()
        self.ico_sticky_container.setFixedSize(16, 16)
        self.ico_sticky_container.setPixmap(load_phosphor_icon("folder", color=DesignTokens.TEXT_MUTED).pixmap(16, 16))

        self.lbl_sticky_container = QLabel(self.tr("Aucun paquet sélectionné"))
        self.lbl_sticky_container.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_sticky_container.setStyleSheet(f"""
            QLabel {{
                color: {DesignTokens.TEXT_MUTED};
                font-size: 11px;
                font-family: '{DesignTokens.FONT_MAIN}';
            }}
        """)
        sticky_layout.addWidget(self.ico_sticky_container)
        sticky_layout.addWidget(self.lbl_sticky_container, 1)

        self.sticky_header.setStyleSheet(f"""
            QFrame#DeckSelectStickyHeader {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                min-height: 28px;
            }}
        """)
        content_layout.addWidget(self.sticky_header)

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
        self.tree.currentItemChanged.connect(self._on_current_item_changed)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.itemCollapsed.connect(self._on_item_collapsed)
        self.tree.itemDoubleClicked.connect(self._on_confirm)

        # Installation des raccourcis et navigation clavier
        self.search_input.installEventFilter(self)
        self.tree.installEventFilter(self)

        self._load_decks()

    def get_deck_full_name(self, deck_id: int) -> str:
        """Retourne le nom hiérarchique complet d'un paquet à partir de son identifiant."""
        return self._full_names_by_id.get(deck_id, "")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Enregistre l'état d'expansion courant à la fermeture."""
        self._sync_session_expanded_state()
        super().closeEvent(event)

    def _sync_session_expanded_state(self) -> None:
        """Sauvegarde les identifiants de paquets actuellement dépliés dans la session."""
        if not self._is_restoring_expansion and self._pre_search_expanded_ids is None:
            DeckSelectWindow._session_expanded_deck_ids = {did for did, it in self._items_by_id.items() if it.isExpanded()}

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        if self._is_restoring_expansion or self._pre_search_expanded_ids is not None:
            return
        deck_id = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(deck_id, int):
            if DeckSelectWindow._session_expanded_deck_ids is None:
                DeckSelectWindow._session_expanded_deck_ids = set()
            DeckSelectWindow._session_expanded_deck_ids.add(deck_id)

    def _on_item_collapsed(self, item: QTreeWidgetItem) -> None:
        if self._is_restoring_expansion or self._pre_search_expanded_ids is not None:
            return
        deck_id = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(deck_id, int):
            if DeckSelectWindow._session_expanded_deck_ids is None:
                DeckSelectWindow._session_expanded_deck_ids = set()
            DeckSelectWindow._session_expanded_deck_ids.discard(deck_id)

    def expand_all_nodes(self) -> None:
        """Déplie l'ensemble des noeuds de l'arborescence."""
        self._is_restoring_expansion = True
        try:
            self.tree.expandAll()
            if DeckSelectWindow._session_expanded_deck_ids is None:
                DeckSelectWindow._session_expanded_deck_ids = set()
            for did in self._items_by_id:
                DeckSelectWindow._session_expanded_deck_ids.add(did)
        finally:
            self._is_restoring_expansion = False

    def collapse_all_nodes(self) -> None:
        """Replie l'ensemble des noeuds de l'arborescence."""
        self._is_restoring_expansion = True
        try:
            self.tree.collapseAll()
            if DeckSelectWindow._session_expanded_deck_ids is not None:
                DeckSelectWindow._session_expanded_deck_ids.clear()
            if self.allow_all and ALL_DECKS_NODE_ID in self._items_by_id:
                self._items_by_id[ALL_DECKS_NODE_ID].setExpanded(True)
                if DeckSelectWindow._session_expanded_deck_ids is not None:
                    DeckSelectWindow._session_expanded_deck_ids.add(ALL_DECKS_NODE_ID)
        finally:
            self._is_restoring_expansion = False

    def _update_sticky_header(self, item: QTreeWidgetItem | None = None) -> None:
        """Met à jour le bandeau sticky affichant le conteneur du paquet sélectionné."""
        if item is None:
            selected = self.tree.selectedItems()
            item = selected[0] if selected else self.tree.currentItem()

        if item is None:
            self.ico_sticky_container.setPixmap(load_phosphor_icon("folder", color=DesignTokens.TEXT_MUTED).pixmap(16, 16))
            self.lbl_sticky_container.setText(self.tr("Aucun paquet sélectionné"))
            return

        deck_id = item.data(0, Qt.ItemDataRole.UserRole)
        if deck_id == ALL_DECKS_NODE_ID:
            self.ico_sticky_container.setPixmap(load_phosphor_icon("folders", color=DesignTokens.COLOR_BLUE).pixmap(16, 16))
            self.lbl_sticky_container.setText(self.tr("Tous les paquets (Collection entière)"))
            return

        full_name = self.get_deck_full_name(deck_id) if isinstance(deck_id, int) else item.text(0)
        parts = split_hierarchy(full_name)

        if len(parts) <= 1:
            self.ico_sticky_container.setPixmap(load_phosphor_icon("folder", color=DesignTokens.COLOR_BLUE).pixmap(16, 16))
            root_title = parts[0] if parts else full_name
            self.lbl_sticky_container.setText(tr("Paquet racine : %1", root_title))
        else:
            container_path = " › ".join(parts[:-1])
            self.ico_sticky_container.setPixmap(load_phosphor_icon("folder-open", color=DesignTokens.COLOR_BLUE).pixmap(16, 16))
            self.lbl_sticky_container.setText(tr("Dans : %1", container_path))

    def _load_decks(self) -> None:
        """Charge l'arborescence des paquets sans préfixes avec restauration de l'état d'expansion."""
        self.tree.clear()
        self._items_by_id = {}
        self._full_names_by_id = {}

        global_item: QTreeWidgetItem | None = None
        if self.allow_all:
            all_title = self.tr("Tous les paquets")
            global_item = QTreeWidgetItem([all_title])
            global_item.setData(0, Qt.ItemDataRole.UserRole, ALL_DECKS_NODE_ID)
            global_item.setData(0, Qt.ItemDataRole.UserRole + 1, all_title)
            global_item.setIcon(0, load_phosphor_icon("folders", color=DesignTokens.COLOR_BLUE))
            self.tree.addTopLevelItem(global_item)
            self._items_by_id[ALL_DECKS_NODE_ID] = global_item
            self._full_names_by_id[ALL_DECKS_NODE_ID] = all_title

        decks = list(DeckModel.select().order_by(DeckModel.name.asc()))

        # 1. Créer tous les items avec leaf_name uniquement
        for deck in decks:
            display_title = leaf_name(deck.name)
            item = QTreeWidgetItem([display_title])
            item.setData(0, Qt.ItemDataRole.UserRole, deck.id)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, deck.name)
            self._full_names_by_id[deck.id] = deck.name

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

        # 3. Restauration fidèle de l'état d'expansion sans tout redéplier
        self._is_restoring_expansion = True
        try:
            if DeckSelectWindow._session_expanded_deck_ids is not None:
                for did, it in self._items_by_id.items():
                    it.setExpanded(did in DeckSelectWindow._session_expanded_deck_ids)
            else:
                DeckSelectWindow._session_expanded_deck_ids = set()
                # Premier affichage : déplier uniquement les racines
                for i in range(self.tree.topLevelItemCount()):
                    top_it = self.tree.topLevelItem(i)
                    if top_it:
                        top_it.setExpanded(True)
                        top_id = top_it.data(0, Qt.ItemDataRole.UserRole)
                        if isinstance(top_id, int):
                            DeckSelectWindow._session_expanded_deck_ids.add(top_id)

            # Si un paquet spécifique est présélectionné, s'assurer que ses ancêtres sont dépliés
            if self.selected_deck_id is not None and self.selected_deck_id in self._items_by_id:
                target_item = self._items_by_id[self.selected_deck_id]
                parent_node = target_item.parent()
                while parent_node:
                    parent_node.setExpanded(True)
                    p_id = parent_node.data(0, Qt.ItemDataRole.UserRole)
                    if isinstance(p_id, int) and DeckSelectWindow._session_expanded_deck_ids is not None:
                        DeckSelectWindow._session_expanded_deck_ids.add(p_id)
                    parent_node = parent_node.parent()

                self.tree.setCurrentItem(target_item)
                self.tree.scrollToItem(target_item, QAbstractItemView.ScrollHint.PositionAtCenter)
                self.btn_confirm.setEnabled(True)
            elif global_item and self.allow_all:
                self.tree.setCurrentItem(global_item)
        finally:
            self._is_restoring_expansion = False

        self._update_sticky_header()

    def _on_search_changed(self, text: str) -> None:
        """Filtre l'arborescence : cherche dans la feuille ET le chemin complet, restaure l'expansion post-recherche."""
        query = text.lower().strip()

        if not query:
            # Réafficher tout
            self._is_restoring_expansion = True
            try:
                for i in range(self.tree.topLevelItemCount()):
                    item = self.tree.topLevelItem(i)
                    if item:
                        self._set_item_visibility_recursive(item, True)

                # Restaurer fidèlement l'état d'expansion antérieur à la recherche
                if self._pre_search_expanded_ids is not None:
                    for did, it in self._items_by_id.items():
                        it.setExpanded(did in self._pre_search_expanded_ids)
                    self._pre_search_expanded_ids = None
            finally:
                self._is_restoring_expansion = False
            self._update_sticky_header()
            return

        # Début de recherche : sauvegarder l'état d'expansion actif
        if self._pre_search_expanded_ids is None:
            self._pre_search_expanded_ids = {did for did, it in self._items_by_id.items() if it.isExpanded()}

        self._is_restoring_expansion = True
        try:
            # Cacher tous les noeuds d'abord
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                if item:
                    self._set_item_visibility_recursive(item, False)

            # Rendre visibles les correspondances (nom de feuille OU chemin complet) et leurs ancêtres
            for did, item in self._items_by_id.items():
                full_name = self.get_deck_full_name(did).lower()
                display_name = item.text(0).lower()
                if query in display_name or query in full_name:
                    item.setHidden(False)
                    parent = item.parent()
                    while parent:
                        parent.setHidden(False)
                        parent.setExpanded(True)
                        parent = parent.parent()
        finally:
            self._is_restoring_expansion = False

        self._update_sticky_header()

    def _set_item_visibility_recursive(self, item: QTreeWidgetItem, visible: bool) -> None:
        item.setHidden(not visible)
        for i in range(item.childCount()):
            self._set_item_visibility_recursive(item.child(i), visible)

    def _on_selection_changed(self) -> None:
        selected = self.tree.selectedItems()
        if not selected:
            self.btn_confirm.setEnabled(False)
            self._update_sticky_header(None)
            return

        item = selected[0]
        deck_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not self.allow_all and deck_id == ALL_DECKS_NODE_ID:
            self.btn_confirm.setEnabled(False)
        else:
            self.btn_confirm.setEnabled(True)
        self._update_sticky_header(item)

    def _on_current_item_changed(self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None) -> None:
        self._update_sticky_header(current)

    def _on_confirm(self) -> None:
        selected = self.tree.selectedItems()
        if selected:
            item = selected[0]
            deck_id = item.data(0, Qt.ItemDataRole.UserRole)
            if not self.allow_all and deck_id == ALL_DECKS_NODE_ID:
                return
            deck_name = self.get_deck_full_name(deck_id)
            if not deck_name:
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

    def eventFilter(self, obj: object, event: QEvent) -> bool:
        """Navigation clavier et raccourcis dans le sélecteur de paquet."""
        if event.type() == QEvent.Type.KeyPress:
            key_event = cast(QKeyEvent, event)
            key = key_event.key()
            modifiers = key_event.modifiers()

            if (modifiers & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_N:
                self._open_create_deck_dialog()
                return True

            if key == Qt.Key.Key_Escape:
                if obj is self.search_input and self.search_input.text():
                    self.search_input.clear()
                    return True
                self.close()
                return True

            if obj is self.search_input:
                if key == Qt.Key.Key_Down:
                    cur = self.tree.currentItem()
                    if cur is None:
                        if self.tree.topLevelItemCount() > 0:
                            self.tree.setCurrentItem(self.tree.topLevelItem(0))
                    else:
                        below = self.tree.itemBelow(cur)
                        if below is not None:
                            self.tree.setCurrentItem(below)
                    return True
                elif key == Qt.Key.Key_Up:
                    cur = self.tree.currentItem()
                    if cur is not None:
                        above = self.tree.itemAbove(cur)
                        if above is not None:
                            self.tree.setCurrentItem(above)
                    return True
                elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self._on_confirm()
                    return True

            elif obj is self.tree and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._on_confirm()
                return True

        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Gère les raccourcis globaux du sélecteur de paquet (Ctrl+N, Échap, Entrée)."""
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier) and event.key() == Qt.Key.Key_N:
            self._open_create_deck_dialog()
            event.accept()
            return
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_confirm()
            event.accept()
            return
        super().keyPressEvent(event)
