from typing import Any
from PySide6.QtCore import Signal
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QWidget,
)

from ankiforge.ui.theme import DesignTokens


class TabContainer(QWidget):
    """Conteneur qui gère le drag & drop des onglets."""

    tab_reordered = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.layout_h = QHBoxLayout(self)
        self.layout_h.setContentsMargins(0, 0, 0, 0)
        self.layout_h.setSpacing(4)
        self.layout_h.addStretch()
        self._drop_index = -1

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasFormat("application/x-ankiforge-tab"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        if event.mimeData().hasFormat("application/x-ankiforge-tab"):
            pos = event.position().toPoint()
            self._drop_index = 0
            for i in range(self.layout_h.count() - 1):
                item = self.layout_h.itemAt(i)
                if item and item.widget():
                    w = item.widget()
                    if w and pos.x() > w.x() + w.width() / 2:
                        self._drop_index = i + 1
            event.acceptProposedAction()
            self.update()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._drop_index = -1
        self.update()

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasFormat("application/x-ankiforge-tab"):
            from ankiforge.ui.components.tabs.tab_button import get_dragged_tab_info, set_dragged_tab_info

            dragged_info = get_dragged_tab_info()
            if dragged_info:
                source_panel = dragged_info["source_panel"]
                from_index = dragged_info["index"]
                widget = dragged_info["widget"]
                title = dragged_info["title"]
                icon_name = dragged_info["icon_name"]

                target_panel: Any = self
                while target_panel and not hasattr(target_panel, "insert_tab_widget"):
                    target_panel = target_panel.parentWidget()

                to_index = self._drop_index

                if target_panel == source_panel:
                    if from_index != to_index and from_index != to_index - 1:
                        if to_index > from_index:
                            to_index -= 1
                        self.tab_reordered.emit(from_index, to_index)
                else:
                    if target_panel:
                        source_panel.remove_tab_widget(from_index)
                        target_panel.insert_tab_widget(to_index, title, widget, icon_name)
                        target_panel.set_active_tab(to_index)

                set_dragged_tab_info(None)

            self._drop_index = -1
            self.update()
            event.acceptProposedAction()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._drop_index >= 0:
            painter = QPainter(self)
            pen = QPen(QColor(DesignTokens.ACCENT_PRIMARY))
            pen.setWidth(2)
            painter.setPen(pen)
            x = 0
            if self._drop_index < self.layout_h.count() - 1:
                item = self.layout_h.itemAt(self._drop_index)
                if item:
                    w = item.widget()
                    if w:
                        x = w.x() - 2
            else:
                item = self.layout_h.itemAt(self.layout_h.count() - 2)
                if item:
                    w = item.widget()
                    if w:
                        x = w.x() + w.width() + 2

            painter.drawLine(x, 0, x, self.height())
