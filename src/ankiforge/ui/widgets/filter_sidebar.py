import logging
from typing import cast
import json

from PySide6.QtCore import Qt, Signal, Slot, QPoint
from PySide6.QtWidgets import QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem, QFrame, QMenu
from PySide6.QtGui import QAction

from ankiforge.database.models import DeckModel, NoteModel, CardModel
from ankiforge.ui.components.components import RoundedPanel

logger = logging.getLogger(__name__)


class FilterSidebar(RoundedPanel):
    """
    Panneau latéral permettant de naviguer dans les paquets Anki
    et de filtrer par tags.
    """

    deck_selected = Signal(int)  # ID du paquet
    tag_selected = Signal(object)  # str ou None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        lbl_nav = QLabel("EXPLORATEUR")
        lbl_nav.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        layout.addWidget(lbl_nav)

        self.deck_tree = QTreeWidget()
        self.deck_tree.setHeaderHidden(True)
        self.deck_tree.setFrameShape(QFrame.Shape.NoFrame)
        self.deck_tree.setStyleSheet("background: transparent;")
        layout.addWidget(self.deck_tree)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background-color: palette(alternate-base); max-height: 1px; border: none; margin-top: 8px; margin-bottom: 8px;")
        layout.addWidget(separator)

        lbl_tags = QLabel("FILTRES (TAGS)")
        lbl_tags.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-top: 10px;")
        layout.addWidget(lbl_tags)

        self.tag_list = QListWidget()
        self.tag_list.setFrameShape(QFrame.Shape.NoFrame)
        self.tag_list.setStyleSheet("background: transparent;")
        self.tag_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.tag_list)

    def _connect_signals(self):
        self.deck_tree.itemClicked.connect(self._on_deck_clicked)
        self.tag_list.itemClicked.connect(self._on_tag_clicked)
        self.tag_list.customContextMenuRequested.connect(self._show_tag_context_menu)

    def refresh_decks(self):
        self.deck_tree.clear()
        try:
            decks = DeckModel.select().order_by(DeckModel.name)
            tree_nodes: dict[str, QTreeWidgetItem] = {}
            for deck in decks:
                parts = deck.name.split("::")
                display_name = parts[-1]
                if len(parts) == 1:
                    item = QTreeWidgetItem(self.deck_tree, [f"📁 {display_name}"])
                else:
                    parent_name = "::".join(parts[:-1])
                    parent_item = tree_nodes.get(parent_name, self.deck_tree)
                    item = QTreeWidgetItem(parent_item, [f"📂 {display_name}"])

                item.setData(0, Qt.ItemDataRole.UserRole, deck.id)
                tree_nodes[deck.name] = item
            self.deck_tree.expandAll()
        except Exception as e:
            logger.error(f"Erreur lors du rafraîchissement des paquets : {e}")

    def refresh_tags(self, deck_id: int | None, is_quarantine: bool = False):
        self.tag_list.clear()

        all_item = QListWidgetItem("🏷️ Tous les tags")
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        self.tag_list.addItem(all_item)

        if not deck_id:
            return

        tag_counts: dict[str, int] = {}
        status_condition = (NoteModel.status == "pending") if is_quarantine else (NoteModel.status != "pending")

        try:
            selected_deck = DeckModel.get_by_id(deck_id)
            matching_decks = DeckModel.select().where(DeckModel.name.startswith(selected_deck.name))

            notes = NoteModel.select(NoteModel.tags).join(CardModel).where(CardModel.deck.in_(matching_decks) & status_condition).distinct()

            for note in notes:
                if not note.tags:
                    continue
                try:
                    tags = cast(list[str], json.loads(note.tags))
                    for tag in tags:
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1
                except json.JSONDecodeError:
                    continue

            for tag, count in sorted(tag_counts.items()):
                item = QListWidgetItem(f"🏷️ {tag} ({count})")
                item.setData(Qt.ItemDataRole.UserRole, tag)
                self.tag_list.addItem(item)
        except Exception as e:
            logger.error(f"Erreur lors du rafraîchissement des tags : {e}")

    @Slot(QTreeWidgetItem, int)
    def _on_deck_clicked(self, item: QTreeWidgetItem, column: int):
        deck_id = item.data(0, Qt.ItemDataRole.UserRole)
        if deck_id:
            self.deck_selected.emit(deck_id)

    def select_deck(self, deck_id: int) -> bool:
        """Selects a deck programmatically in the tree."""
        from PySide6.QtWidgets import QTreeWidgetItemIterator

        iterator = QTreeWidgetItemIterator(self.deck_tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, Qt.ItemDataRole.UserRole) == deck_id:
                self.deck_tree.setCurrentItem(item)
                return True
            iterator += 1
        return False

    @Slot(QListWidgetItem)
    def _on_tag_clicked(self, item: QListWidgetItem):
        tag = item.data(Qt.ItemDataRole.UserRole)
        self.tag_selected.emit(tag)

    @Slot(QPoint)
    def _show_tag_context_menu(self, pos: QPoint):
        item = self.tag_list.itemAt(pos)
        if not item:
            return

        tag = item.data(Qt.ItemDataRole.UserRole)
        if tag is None:
            return

        menu = QMenu(self)
        # On pourrait ajouter des actions comme "Renommer le tag" ou "Supprimer le tag" ici
        # Pour l'instant on garde ça simple pour le refactoring
        action = QAction(f"Options pour '{tag}'", self)
        menu.addAction(action)
        menu.exec(self.tag_list.mapToGlobal(pos))
