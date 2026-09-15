from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)


class DocumentTreeWidget(QTreeWidget):
    """QTreeWidget customisé pour supporter le Drag & Drop, l'arborescence et le filtrage rapide."""

    itemMoved = Signal(object, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def dropEvent(self, event: QDropEvent) -> None:
        source_item = self.currentItem()
        if not source_item:
            event.ignore()
            return

        source_data = source_item.data(0, Qt.ItemDataRole.UserRole)
        target_item = self.itemAt(event.position().toPoint())
        target_data = target_item.data(0, Qt.ItemDataRole.UserRole) if target_item else None

        event.ignore()
        if source_item == target_item:
            return

        if source_data:
            self.itemMoved.emit(source_data, target_data)

    def filter_text(self, query: str) -> None:
        """Filtre récursivement les documents et dossiers affichés."""
        query = query.strip().lower()

        def _filter_item(item: QTreeWidgetItem) -> bool:
            match = query in item.text(0).lower()
            child_match = False
            for i in range(item.childCount()):
                child = item.child(i)
                if _filter_item(child):
                    child_match = True
            is_visible = match or child_match or not query
            item.setHidden(not is_visible)
            if child_match and query:
                item.setExpanded(True)
            return is_visible

        for i in range(self.topLevelItemCount()):
            _filter_item(self.topLevelItem(i))
