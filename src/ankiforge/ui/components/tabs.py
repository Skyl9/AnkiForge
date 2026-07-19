from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QButtonGroup, QScrollArea, QApplication, QFrame, QStackedWidget
from PySide6.QtCore import Signal, Qt, QMimeData, QPoint
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon
from PySide6.QtGui import QDrag, QDropEvent, QDragEnterEvent, QDragMoveEvent, QMouseEvent, QPainter, QColor, QPen
from typing import Any

_dragged_tab_info = None
_floating_windows = []


class IdeTabBar(QWidget):
    """Tab bar style JetBrains avec indicateur accent 2px en haut."""

    tab_changed = Signal(int)
    tab_reordered = Signal(int, int)
    tab_close_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)
        self.layout_h = QHBoxLayout(self)
        self.layout_h.setContentsMargins(0, 0, 0, 0)
        self.layout_h.setSpacing(0)
        self.btn_group = QButtonGroup(self)
        self.btn_group.idClicked.connect(self.tab_changed.emit)
        self.tabs: list[QPushButton] = []
        self.layout_h.addStretch()

    def add_tab(self, title: str, icon_name: str = "", closable: bool = False) -> int:
        idx = len(self.tabs)
        btn = QPushButton(f"{icon_name} {title}".strip())
        btn.setCheckable(True)
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {DesignTokens.TEXT_SECONDARY};
                border: none;
                border-top: 2px solid transparent;
                padding: 0 16px;
                font-family: "{DesignTokens.FONT_MAIN}";
            }}
            QPushButton:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
            QPushButton:checked {{
                color: {DesignTokens.TEXT_PRIMARY};
                border-top: 2px solid {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_PANEL};
            }}
        """)

        self.btn_group.addButton(btn, idx)
        self.tabs.append(btn)
        self.layout_h.insertWidget(idx, btn)

        if len(self.tabs) == 1:
            btn.setChecked(True)

        return idx

    def set_active(self, index: int) -> None:
        if 0 <= index < len(self.tabs):
            self.tabs[index].setChecked(True)
            self.tab_changed.emit(index)


class PillTabBar(QWidget):
    """Tab bar style pill/segment. Usage: sous-navigation dans les panneaux."""

    tab_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        self.layout_h = QHBoxLayout(self)
        self.layout_h.setContentsMargins(2, 2, 2, 2)
        self.layout_h.setSpacing(2)
        self.setStyleSheet(f"""
            PillTabBar {{
                background-color: {DesignTokens.BG_INPUT};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        self.btn_group = QButtonGroup(self)
        self.btn_group.idClicked.connect(self.tab_changed.emit)
        self.tabs: list[QPushButton] = []

    def add_tab(self, title: str) -> int:
        idx = len(self.tabs)
        btn = QPushButton(title)
        btn.setCheckable(True)
        btn.setFixedHeight(28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {DesignTokens.TEXT_SECONDARY};
                border: none;
                border-radius: {DesignTokens.RADIUS_SM - 2}px;
                padding: 0 12px;
                font-family: "{DesignTokens.FONT_MAIN}";
            }}
            QPushButton:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QPushButton:checked {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        self.btn_group.addButton(btn, idx)
        self.tabs.append(btn)
        self.layout_h.addWidget(btn)

        if len(self.tabs) == 1:
            btn.setChecked(True)

        return idx


class SettingsTabBar(QWidget):
    """Tab bar verticale pour le modal Settings."""

    tab_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.layout_v = QVBoxLayout(self)
        self.layout_v.setContentsMargins(0, 0, 0, 0)
        self.layout_v.setSpacing(4)
        self.btn_group = QButtonGroup(self)
        self.btn_group.idClicked.connect(self.tab_changed.emit)
        self.tabs: list[QPushButton] = []
        self.layout_v.addStretch()

    def add_tab(self, title: str, icon_name: str) -> int:
        idx = len(self.tabs)
        btn = QPushButton(f"{icon_name}  {title}")
        btn.setCheckable(True)
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        btn.setStyleSheet(f"""
            QPushButton {{
                text-align: left;
                background-color: transparent;
                color: {DesignTokens.TEXT_SECONDARY};
                border: none;
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 0 12px;
                font-family: "{DesignTokens.FONT_MAIN}";
            }}
            QPushButton:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
            QPushButton:checked {{
                background-color: {DesignTokens.BG_ACTIVE};
                color: {DesignTokens.ACCENT_PRIMARY};
                font-weight: bold;
            }}
        """)

        self.btn_group.addButton(btn, idx)
        self.tabs.append(btn)
        self.layout_v.insertWidget(idx, btn)

        if len(self.tabs) == 1:
            btn.setChecked(True)

        return idx


class TabButton(QPushButton):
    """Bouton d'onglet draggable."""

    close_requested = Signal()
    detach_requested = Signal()

    def __init__(self, title: str, icon_name: str = "", closable: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.closable = closable
        text = f" {title}" if icon_name else title
        self.setText(text)

        if icon_name:
            self.setProperty("icon_name", icon_name)
            self.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_SECONDARY))

        self.setCheckable(True)
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            TabButton {{
                background-color: transparent;
                color: {DesignTokens.TEXT_SECONDARY};
                border: none;
                border-bottom: 2px solid transparent;
                padding: 0 12px;
                font-family: "{DesignTokens.FONT_MAIN}";
                font-size: {DesignTokens.FONT_SIZE_BASE}px;
            }}
            TabButton:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
            TabButton:checked {{
                color: {DesignTokens.TEXT_PRIMARY};
                border-bottom: 2px solid {DesignTokens.ACCENT_PRIMARY};
                background-color: transparent;
            }}
        """)
        self._drag_start_pos = QPoint()

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def contextMenuEvent(self, event):
        from ankiforge.ui.theme import StyledMenu

        menu = StyledMenu(self)
        action_close = menu.addAction("Fermer l'onglet")
        action_detach = menu.addAction("Détacher l'onglet")

        action = menu.exec(event.globalPos())
        if action == action_close:
            self.close_requested.emit()
        elif action == action_detach:
            self.detach_requested.emit()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return super().mouseMoveEvent(event)

        distance = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
        if distance > QApplication.startDragDistance():
            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setData("application/x-ankiforge-tab", b"")
            drag.setMimeData(mime_data)

            pixmap = self.grab()
            drag.setPixmap(pixmap)
            drag.setHotSpot(self._drag_start_pos)

            panel: Any = self
            while panel and not hasattr(panel, "remove_tab_widget"):
                panel = panel.parentWidget()

            scroll_bar: Any = self
            while scroll_bar and not hasattr(scroll_bar, "tabs"):
                scroll_bar = scroll_bar.parentWidget()

            global _dragged_tab_info
            if panel and scroll_bar:
                try:
                    index = scroll_bar.tabs.index(self)
                    widget = panel.content_stack.widget(index)
                    title = self.text().strip()
                    icon_name = self.property("icon_name") or ""
                    _dragged_tab_info = {"source_panel": panel, "index": index, "widget": widget, "title": title, "icon_name": icon_name}
                except ValueError:
                    pass

            action = drag.exec(Qt.DropAction.MoveAction)

            if action in (Qt.DropAction.IgnoreAction, None) and _dragged_tab_info:
                src_panel = _dragged_tab_info["source_panel"]
                idx = _dragged_tab_info["index"]
                widget = _dragged_tab_info["widget"]
                title = _dragged_tab_info["title"]
                icon_name = _dragged_tab_info["icon_name"]

                src_panel.remove_tab_widget(idx)

                fw = FloatingDockWindow()
                fw.insert_tab_widget(0, title, widget, icon_name)
                fw.move(event.globalPosition().toPoint())
                _floating_windows.append(fw)
                fw.show()

            _dragged_tab_info = None
            return

        super().mouseMoveEvent(event)


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
            global _dragged_tab_info
            if _dragged_tab_info:
                source_panel = _dragged_tab_info["source_panel"]
                from_index = _dragged_tab_info["index"]
                widget = _dragged_tab_info["widget"]
                title = _dragged_tab_info["title"]
                icon_name = _dragged_tab_info["icon_name"]

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

                _dragged_tab_info = None

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


class ScrollableTabBarWidget(QWidget):
    """Barre d'onglets scrollable avec drag & drop."""

    tab_changed = Signal(int)
    tab_reordered = Signal(int, int)
    tab_close_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)

        self.layout_main = QHBoxLayout(self)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        self.layout_main.setSpacing(0)

        self.btn_left = QPushButton("<")
        self.btn_left.setFixedSize(24, 36)
        self.btn_left.setFlat(True)
        self.btn_left.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none;")
        self.btn_left.clicked.connect(self._scroll_left)
        self.btn_left.hide()

        self.btn_right = QPushButton(">")
        self.btn_right.setFixedSize(24, 36)
        self.btn_right.setFlat(True)
        self.btn_right.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none;")
        self.btn_right.clicked.connect(self._scroll_right)
        self.btn_right.hide()

        self.scroll_area = QScrollArea()
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")

        self.container = TabContainer()
        self.scroll_area.setWidget(self.container)

        self.layout_main.addWidget(self.btn_left)
        self.layout_main.addWidget(self.scroll_area)
        self.layout_main.addWidget(self.btn_right)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)
        self.btn_group.idClicked.connect(self._on_tab_clicked)
        self.tabs: list[TabButton] = []

        self.container.tab_reordered.connect(self._on_tab_reordered)

        self.scroll_area.horizontalScrollBar().rangeChanged.connect(self._update_scroll_buttons)
        self.scroll_area.horizontalScrollBar().valueChanged.connect(self._update_scroll_buttons)

    def add_tab(self, title: str, icon_name: str = "", closable: bool = False) -> int:
        return self.insert_tab(len(self.tabs), title, icon_name, closable)

    def insert_tab(self, index: int, title: str, icon_name: str = "", closable: bool = False) -> int:
        index = max(0, min(index, len(self.tabs)))
        btn = TabButton(title, icon_name, closable)

        self.btn_group.addButton(btn)
        self.tabs.insert(index, btn)
        self.container.layout_h.insertWidget(index, btn)

        if closable:
            btn.close_requested.connect(lambda b=btn: self._on_close_requested(b))

        btn.detach_requested.connect(lambda b=btn: self._on_detach_requested(b))

        for i, t in enumerate(self.tabs):
            self.btn_group.setId(t, i)

        if len(self.tabs) == 1:
            btn.setChecked(True)
            self.tab_changed.emit(0)

        return index

    def remove_tab(self, index: int):
        if 0 <= index < len(self.tabs):
            btn = self.tabs.pop(index)
            self.btn_group.removeButton(btn)
            self.container.layout_h.removeWidget(btn)
            btn.deleteLater()

            for i, t in enumerate(self.tabs):
                self.btn_group.setId(t, i)

            if self.tabs:
                new_idx = min(index, len(self.tabs) - 1)
                self.set_active_tab(new_idx)

    def set_active_tab(self, index: int) -> None:
        if 0 <= index < len(self.tabs):
            self.tabs[index].setChecked(True)
            self.tab_changed.emit(index)
            self.scroll_area.ensureWidgetVisible(self.tabs[index])

    def _on_tab_clicked(self, idx: int):
        self.tab_changed.emit(idx)

    def _on_close_requested(self, btn: TabButton):
        try:
            idx = self.tabs.index(btn)
            self.tab_close_requested.emit(idx)
        except ValueError:
            pass

    def _on_detach_requested(self, btn: TabButton):
        try:
            idx = self.tabs.index(btn)
        except ValueError:
            return

        panel: Any = self
        while panel and not hasattr(panel, "remove_tab_widget"):
            panel = panel.parentWidget()

        if panel:
            from PySide6.QtGui import QCursor

            widget, title, closable = panel.remove_tab_widget(idx)
            fw = FloatingDockWindow()
            fw.insert_tab_widget(0, title, widget, btn.property("icon_name") or "", closable)
            fw.move(QCursor.pos())
            _floating_windows.append(fw)
            fw.show()

    def _on_tab_reordered(self, from_idx: int, to_idx: int):
        tab = self.tabs.pop(from_idx)
        self.tabs.insert(to_idx, tab)

        self.container.layout_h.removeWidget(tab)
        self.container.layout_h.insertWidget(to_idx, tab)

        for i, t in enumerate(self.tabs):
            self.btn_group.setId(t, i)

        self.tab_reordered.emit(from_idx, to_idx)

    def _scroll_left(self):
        bar = self.scroll_area.horizontalScrollBar()
        bar.setValue(bar.value() - 100)

    def _scroll_right(self):
        bar = self.scroll_area.horizontalScrollBar()
        bar.setValue(bar.value() + 100)

    def _update_scroll_buttons(self):
        bar = self.scroll_area.horizontalScrollBar()
        self.btn_left.setVisible(bar.value() > bar.minimum())
        self.btn_right.setVisible(bar.value() < bar.maximum())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scroll_buttons()


class FloatingDockWindow(QWidget):
    """Fenêtre flottante pour les onglets détachés."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle("AnkiForge - Detached Tab")
        self.resize(600, 400)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL};")

        self.layout_v = QVBoxLayout(self)
        self.layout_v.setContentsMargins(0, 0, 0, 0)
        self.layout_v.setSpacing(0)

        self.header = QFrame()
        self.header.setFixedHeight(36)
        self.header.setStyleSheet(f"border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(0, 0, 0, 0)

        self.tabs_bar = ScrollableTabBarWidget()
        self.header_layout.addWidget(self.tabs_bar)
        self.layout_v.addWidget(self.header)

        self.content_stack = QStackedWidget()
        self.layout_v.addWidget(self.content_stack)

        self.tabs_bar.tab_changed.connect(self.content_stack.setCurrentIndex)
        self.tabs_bar.tab_reordered.connect(self._on_tab_reordered)

    def _on_tab_reordered(self, from_idx: int, to_idx: int):
        widget = self.content_stack.widget(from_idx)
        if widget is None:
            return
        self.content_stack.removeWidget(widget)
        self.content_stack.insertWidget(to_idx, widget)

    def remove_tab_widget(self, index: int) -> QWidget:
        widget = self.content_stack.widget(index)
        if widget is None:
            raise ValueError(f"No widget at index {index}")
        self.tabs_bar.remove_tab(index)
        self.content_stack.removeWidget(widget)

        if self.content_stack.count() == 0:
            self.close()
            self.deleteLater()

        return widget

    def insert_tab_widget(self, index: int, title: str, widget: QWidget, icon_name: str = "", closable: bool = True):
        self.tabs_bar.insert_tab(index, title, icon_name, closable)
        self.content_stack.insertWidget(index, widget)
        self.set_active_tab(index)

    def set_active_tab(self, index: int):
        self.tabs_bar.set_active_tab(index)

    def closeEvent(self, event):
        for i in range(self.content_stack.count()):
            w = self.content_stack.widget(i)
            if w:
                w.setParent(None)
        if self in _floating_windows:
            _floating_windows.remove(self)
        self.deleteLater()
        event.accept()
