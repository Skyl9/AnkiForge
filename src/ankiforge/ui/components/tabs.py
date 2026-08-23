from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QButtonGroup, QScrollArea, QApplication, QFrame, QStackedWidget
from PySide6.QtCore import Signal, Qt, QMimeData, QPoint, QPropertyAnimation, QEasingCurve
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon
from PySide6.QtGui import QDrag, QDropEvent, QDragEnterEvent, QDragMoveEvent, QMouseEvent, QPainter, QColor, QPen
from typing import Any, Tuple

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
        btn = QPushButton(f" {title}" if icon_name else title)

        if icon_name:
            btn.setProperty("icon_name", icon_name)
            btn.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_SECONDARY))

        btn.setCheckable(True)
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {DesignTokens.TEXT_SECONDARY};
                border: none;
                border-right: 1px solid {DesignTokens.BORDER_COLOR};
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
                border-right: 1px solid {DesignTokens.BORDER_COLOR};
                background-color: {DesignTokens.BG_PANEL};
                font-weight: bold;
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

    def refresh_theme(self, profile: Any = None) -> None:
        for btn in self.tabs:
            icon_name = btn.property("icon_name")
            if icon_name:
                c = DesignTokens.ACCENT_PRIMARY if btn.isChecked() else DesignTokens.TEXT_SECONDARY
                btn.setIcon(load_phosphor_icon(icon_name, color=c))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {DesignTokens.TEXT_SECONDARY};
                    border: none;
                    border-right: 1px solid {DesignTokens.BORDER_COLOR};
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
                    border-right: 1px solid {DesignTokens.BORDER_COLOR};
                    background-color: {DesignTokens.BG_PANEL};
                    font-weight: bold;
                }}
            """)


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
                font-weight: bold;
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

    def set_tab_text(self, index: int, text: str) -> None:
        if 0 <= index < len(self.tabs):
            btn = self.tabs[index]
            icon_name = btn.property("icon_name") or ""
            display_text = f" {text}" if icon_name else text
            btn.setText(display_text)


class TabButton(QPushButton):
    """Bouton d'onglet draggable."""

    close_requested = Signal()
    detach_requested = Signal()

    def __init__(self, title: str, icon_name: str = "", closable: bool = False, variant: str = "ide", icon_color: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.closable = closable
        text = f" {title}" if icon_name else title
        self.setText(text)

        if icon_name:
            self.setProperty("icon_name", icon_name)
            color = icon_color if icon_color else DesignTokens.TEXT_SECONDARY
            self.setIcon(load_phosphor_icon(icon_name, color=color))

        self.setCheckable(True)
        self.setFixedHeight(36)

        from PySide6.QtWidgets import QSizePolicy

        sizePolicy = self.sizePolicy()
        sizePolicy.setHorizontalPolicy(QSizePolicy.Policy.Minimum)
        self.setSizePolicy(sizePolicy)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("variant", variant)
        self.setProperty("closable", "true" if closable else "false")
        self.toggled.connect(self._on_toggled)

        self._apply_style()

        if self.closable:
            self.close_btn = QPushButton(self)
            self.close_btn.setFixedSize(16, 16)
            self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.close_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border-radius: 8px;
                    border: none;
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                }}
            """)
            self.close_btn.setIcon(load_phosphor_icon("ph.x", color=DesignTokens.TEXT_SECONDARY))
            self.close_btn.clicked.connect(self.close_requested.emit)
        self._drag_start_pos = QPoint()

    def _apply_style(self) -> None:
        padding_right = 28 if self.closable else 12
        variant = self.property("variant") or "ide"
        if variant == "document":
            self.setStyleSheet(f"""
                TabButton {{
                    background-color: transparent;
                    color: {DesignTokens.TEXT_SECONDARY};
                    border: none;
                    border-right: 1px solid {DesignTokens.BORDER_COLOR};
                    border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                    border-top: 2px solid transparent;
                    border-top-left-radius: {DesignTokens.RADIUS_SM}px;
                    border-top-right-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 0 {padding_right}px 0 12px;
                    font-family: "{DesignTokens.FONT_MAIN}";
                    font-size: {DesignTokens.FONT_SIZE_BASE}px;
                    text-align: left;
                }}
                TabButton:hover {{
                    color: {DesignTokens.TEXT_PRIMARY};
                    background-color: {DesignTokens.BG_HOVER};
                }}
                TabButton:checked {{
                    background-color: {DesignTokens.BG_INPUT};
                    color: {DesignTokens.TEXT_PRIMARY};
                    border-bottom: 1px solid {DesignTokens.BG_INPUT};
                    border-top: 2px solid {DesignTokens.ACCENT_PRIMARY};
                    font-weight: bold;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                TabButton {{
                    background-color: {DesignTokens.BG_SIDEBAR};
                    color: {DesignTokens.TEXT_SECONDARY};
                    border: none;
                    border-top: 2px solid transparent;
                    padding: 0 {padding_right}px 0 8px;
                    font-family: "{DesignTokens.FONT_MAIN}";
                    font-size: 12px;
                    text-align: left;
                }}
                TabButton:hover {{
                    color: {DesignTokens.TEXT_PRIMARY};
                    background-color: {DesignTokens.BG_HOVER};
                }}
                TabButton:checked {{
                    background-color: {DesignTokens.BG_PANEL};
                    color: {DesignTokens.TEXT_PRIMARY};
                    border-top: 2px solid {DesignTokens.ACCENT_PRIMARY};
                    font-weight: 600;
                }}
            """)

    def refresh_theme(self, profile: Any = None) -> None:
        self._apply_style()
        icon_name = self.property("icon_name")
        if icon_name:
            c = DesignTokens.ACCENT_PRIMARY if self.isChecked() else DesignTokens.TEXT_SECONDARY
            self.setIcon(load_phosphor_icon(icon_name, color=c))
        if hasattr(self, "close_btn"):
            self.close_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border-radius: 8px;
                    border: none;
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                }}
            """)
            self.close_btn.setIcon(load_phosphor_icon("ph.x", color=DesignTokens.TEXT_SECONDARY))

    def _on_toggled(self, checked: bool) -> None:
        icon_name = self.property("icon_name")
        if icon_name:
            c = DesignTokens.ACCENT_PRIMARY if checked else DesignTokens.TEXT_SECONDARY
            self.setIcon(load_phosphor_icon(icon_name, color=c))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "close_btn"):
            self.close_btn.move(self.width() - 22, (self.height() - 16) // 2)

    def contextMenuEvent(self, event):
        from ankiforge.ui.theme import StyledMenu

        menu = StyledMenu(self)
        action_close = menu.addAction("Fermer l'onglet")
        action_close.setIcon(load_phosphor_icon("ph.x", color=DesignTokens.TEXT_PRIMARY))

        # Check if this tab is inside a FloatingDockWindow
        panel: Any = self
        while panel and not hasattr(panel, "remove_tab_widget"):
            panel = panel.parentWidget()

        is_detached = panel and (panel.__class__.__name__ == "FloatingDockWindow")

        if is_detached:
            action_dock = menu.addAction("Rattacher l'onglet")
            action_dock.setIcon(load_phosphor_icon("ph.arrow-down-left", color=DesignTokens.TEXT_PRIMARY))
        else:
            action_detach = menu.addAction("Détacher l'onglet")
            action_detach.setIcon(load_phosphor_icon("ph.arrow-up-right", color=DesignTokens.TEXT_PRIMARY))

        action = menu.exec(event.globalPos())
        if action == action_close:
            self.close_requested.emit()
        elif is_detached and action == action_dock:
            # Re-dock this specific tab immediately
            scroll_bar: Any = self
            while scroll_bar and not hasattr(scroll_bar, "tabs"):
                scroll_bar = scroll_bar.parentWidget()

            if scroll_bar and panel:
                try:
                    idx = scroll_bar.tabs.index(self)
                    widget, title, closable = panel.remove_tab_widget(idx)

                    # Retrieve original dock attributes using Python attributes
                    orig_panel = getattr(widget, "original_panel", None)
                    orig_idx = getattr(widget, "original_index", None)
                    orig_title = getattr(widget, "original_title", title)
                    orig_icon_name = getattr(widget, "original_icon_name", "")
                    orig_closable = getattr(widget, "original_closable", closable)

                    if orig_panel and orig_idx is not None:
                        try:
                            # Safety check if C++ object is still valid
                            _ = orig_panel.parent()
                            target_idx = min(orig_idx, len(orig_panel.tabs_bar.tabs))
                            orig_panel.insert_tab_widget(target_idx, orig_title, widget, orig_icon_name, orig_closable)
                        except RuntimeError:
                            pass
                except ValueError:
                    pass
        elif not is_detached and action == action_detach:
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

                # Check if we are dragging the last tab of a FloatingDockWindow onto the desktop
                if src_panel.__class__.__name__ == "FloatingDockWindow" and len(src_panel.tabs_bar.tabs) <= 1:
                    # Ignore the detach: keep the tab in its current floating window
                    _dragged_tab_info = None
                    return

                idx = _dragged_tab_info["index"]
                widget = _dragged_tab_info["widget"]
                title = _dragged_tab_info["title"]
                icon_name = _dragged_tab_info["icon_name"]

                src_panel.remove_tab_widget(idx)

                # Store original dock properties on the widget for automatic re-docking on close
                widget.original_panel = src_panel
                widget.original_index = idx
                widget.original_title = title
                widget.original_icon_name = icon_name
                widget.original_closable = True

                fw = FloatingDockWindow()
                fw.insert_tab_widget(0, title, widget, icon_name)

                # Center header under cursor
                from PySide6.QtGui import QCursor

                cursor_pos = QCursor.pos()
                fw.move(cursor_pos.x() - fw.width() // 2, cursor_pos.y() - 18)

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

    def __init__(self, variant: str = "ide", parent=None):
        super().__init__(parent)
        self.variant = variant
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

    def add_tab(self, title: str, icon_name: str = "", closable: bool = False, icon_color: str = "") -> int:
        return self.insert_tab(len(self.tabs), title, icon_name, closable, icon_color)

    def set_tab_text(self, index: int, text: str) -> None:
        if 0 <= index < len(self.tabs):
            btn = self.tabs[index]
            icon_name = btn.property("icon_name") or ""
            display_text = f" {text}" if icon_name else text
            btn.setText(display_text)

    def insert_tab(self, index: int, title: str, icon_name: str = "", closable: bool = False, icon_color: str = "") -> int:
        index = max(0, min(index, len(self.tabs)))
        btn = TabButton(title, icon_name, closable, self.variant, icon_color)

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

    def refresh_theme(self, profile: Any = None) -> None:
        for tab in self.tabs:
            if hasattr(tab, "refresh_theme"):
                tab.refresh_theme(profile)
        if hasattr(self, "btn_left"):
            self.btn_left.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none;")
        if hasattr(self, "btn_right"):
            self.btn_right.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none;")

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
            icon_name = btn.property("icon_name") or ""

            # Store original dock properties on the widget for automatic re-docking on close
            widget.original_panel = panel
            widget.original_index = idx
            widget.original_title = title
            widget.original_icon_name = icon_name
            widget.original_closable = closable

            fw = FloatingDockWindow()
            fw.insert_tab_widget(0, title, widget, icon_name, closable)
            cursor_pos = QCursor.pos()
            fw.move(cursor_pos.x() - fw.width() // 2, cursor_pos.y() - 18)
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
        self.resize(800, 600)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL};")

        # Setup snappy and smooth fade-in animation
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(100)
        self._fade_anim.setStartValue(0.7)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.layout_v = QVBoxLayout(self)
        self.layout_v.setContentsMargins(0, 0, 0, 0)
        self.layout_v.setSpacing(0)

        self.header = QFrame()
        self.header.setFixedHeight(36)
        self.header.setStyleSheet(f"border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(8, 0, 8, 0)
        self.header_layout.setSpacing(8)

        self.tabs_bar = ScrollableTabBarWidget()
        self.header_layout.addWidget(self.tabs_bar, 1)

        # Add plus and re-dock buttons on the right side of header layout
        from ankiforge.ui.components.buttons import IconButton

        self.menu_btn = IconButton("ph.plus", "Ouvrir un onglet...", 16)
        self.dock_btn = IconButton("ph.arrow-down-left", "Rattacher la fenêtre", 16)

        # Connect actions
        self.dock_btn.clicked.connect(self.close)
        self.menu_btn.clicked.connect(self._show_tabs_menu)

        self.header_layout.addWidget(self.menu_btn, 0)
        self.header_layout.addWidget(self.dock_btn, 0)

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

    def remove_tab_widget(self, index: int) -> Tuple[QWidget, str, bool]:
        widget = self.content_stack.widget(index)
        if widget is None:
            raise ValueError(f"No widget at index {index}")

        btn = self.tabs_bar.tabs[index]
        title = btn.text().strip()
        closable = btn.property("closable")
        if closable is None:
            closable = True

        self.tabs_bar.remove_tab(index)
        self.content_stack.removeWidget(widget)

        if self.content_stack.count() == 0:
            self.close()
            self.deleteLater()

        return widget, title, closable

    def insert_tab_widget(self, index: int, title: str, widget: QWidget, icon_name: str = "", closable: bool = True):
        self.tabs_bar.insert_tab(index, title, icon_name, closable)
        self.content_stack.insertWidget(index, widget)
        widget.show()
        self.set_active_tab(index)

        # Resize to fit the widget size hint or current size fully
        target_size = widget.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            target_size = widget.sizeHint()

        header_height = 36
        new_width = max(800, target_size.width())
        new_height = max(600, target_size.height() + header_height)
        self.resize(new_width, new_height)

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_animated", False):
            self._animated = True
            self.setWindowOpacity(0.7)
            self._fade_anim.start()
            from PySide6.QtCore import QTimer

            QTimer.singleShot(150, lambda: self.setWindowOpacity(1.0))

    def set_active_tab(self, index: int):
        self.tabs_bar.set_active_tab(index)

    def closeEvent(self, event):
        # Safely remove all widgets from the stack to prevent their C++ destruction
        while self.content_stack.count() > 0:
            w = self.content_stack.widget(0)
            if w:
                self.content_stack.removeWidget(w)
                w.setParent(None)
                w.hide()

                # Retrieve original dock properties using Python attributes
                orig_panel = getattr(w, "original_panel", None)
                orig_idx = getattr(w, "original_index", None)
                orig_title = getattr(w, "original_title", None)
                orig_icon_name = getattr(w, "original_icon_name", "")
                orig_closable = getattr(w, "original_closable", True)

                # Re-dock back to the original panel if valid
                if orig_panel and orig_idx is not None and orig_title:
                    try:
                        # Safety check if C++ object is still valid
                        _ = orig_panel.parent()

                        # Dock back to its original index (cap to current tabs count to prevent index out of bounds)
                        target_idx = min(orig_idx, len(orig_panel.tabs_bar.tabs))
                        orig_panel.insert_tab_widget(target_idx, orig_title, w, orig_icon_name, orig_closable)
                    except RuntimeError:
                        # Original panel was deleted, do nothing
                        pass

        if self in _floating_windows:
            _floating_windows.remove(self)
        self.deleteLater()
        event.accept()

    def _show_tabs_menu(self):
        # Find any widget in the stack to get its original_panel
        if self.content_stack.count() > 0:
            w = self.content_stack.widget(0)
            orig_panel = getattr(w, "original_panel", None)
            if orig_panel:
                self._show_tabs_menu_at_button(self.menu_btn, orig_panel)

    def _show_tabs_menu_at_button(self, button, orig_panel):
        from ankiforge.ui.theme import StyledMenu
        from PySide6.QtGui import QAction
        from PySide6.QtCore import QPoint

        menu = StyledMenu(self)

        # 1. Find top-level view widget
        top_view = orig_panel
        while top_view and top_view.parentWidget() and top_view.parentWidget() != top_view.window():
            if top_view.parentWidget().__class__.__name__ == "QStackedWidget":
                break
            top_view = top_view.parentWidget()

        if not top_view:
            top_view = orig_panel.window()

        # 2. Collect catalog from all panels in the same view
        all_view_panels = top_view.findChildren(orig_panel.__class__)
        catalog = {}
        for panel in all_view_panels:
            for title, info in panel._registered_tabs.items():
                catalog[title] = (panel, info)

        if not catalog:
            action = QAction("Aucun onglet disponible", self)
            action.setEnabled(False)
            menu.addAction(action)
        else:
            for title in catalog:
                is_here = False
                for btn in self.tabs_bar.tabs:
                    if btn.text().strip() == title.strip():
                        is_here = True
                        break

                action = QAction(title, self)
                action.setCheckable(True)
                action.setChecked(is_here)

                if is_here:
                    action.setEnabled(False)
                else:
                    action.triggered.connect(lambda checked, t=title: self.open_tab(t, orig_panel))
                menu.addAction(action)

        menu.exec(button.mapToGlobal(QPoint(0, button.height())))

    def open_tab(self, title: str, orig_panel):
        from ankiforge.ui.components.panels import find_tab_owner

        # Find where the tab is currently located
        owner, idx = find_tab_owner(title)
        if owner:
            if owner == self:
                self.set_active_tab(idx)
            else:
                widget, tab_title, closable = owner.remove_tab_widget(idx)

                # Store original dock properties on widget for re-docking
                if not hasattr(widget, "original_panel") or widget.original_panel is None:
                    widget.original_panel = getattr(owner, "original_panel", None) or owner
                    widget.original_index = idx
                    widget.original_title = tab_title
                    widget.original_icon_name = getattr(owner, "_registered_tabs", {}).get(tab_title, {}).get("icon_name", "")
                    widget.original_closable = closable

                self.insert_tab_widget(self.tabs_bar.count(), title, widget, widget.original_icon_name, closable)
        else:
            # If not active anywhere, find it in the view's registered tabs and pull it in
            if orig_panel:
                top_view = orig_panel
                while top_view and top_view.parentWidget() and top_view.parentWidget() != top_view.window():
                    if top_view.parentWidget().__class__.__name__ == "QStackedWidget":
                        break
                    top_view = top_view.parentWidget()
                if not top_view:
                    top_view = orig_panel.window()

                all_view_panels = top_view.findChildren(orig_panel.__class__)
                for panel in all_view_panels:
                    if title in panel._registered_tabs:
                        info = panel._registered_tabs[title]

                        try:
                            _ = info["widget"].parent()
                        except RuntimeError:
                            panel._registered_tabs.pop(title, None)
                            return

                        info["active"] = True

                        # Store original properties on widget
                        info["widget"].original_panel = panel
                        info["widget"].original_index = list(panel._registered_tabs.keys()).index(title)
                        info["widget"].original_title = title
                        info["widget"].original_icon_name = info["icon_name"]
                        info["widget"].original_closable = info["closable"]

                        self.insert_tab_widget(self.tabs_bar.count(), title, info["widget"], info["icon_name"], info["closable"])
                        break
