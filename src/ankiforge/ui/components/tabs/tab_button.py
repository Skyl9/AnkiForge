from typing import Any

from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QDrag, QMouseEvent
from PySide6.QtWidgets import QApplication, QPushButton, QSizePolicy, QWidget

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

_dragged_tab_info: Any = None
_floating_windows: list[Any] = []


def get_dragged_tab_info() -> Any:
    global _dragged_tab_info
    return _dragged_tab_info


def set_dragged_tab_info(val: Any) -> None:
    global _dragged_tab_info
    _dragged_tab_info = val


def get_floating_windows() -> list[Any]:
    global _floating_windows
    return _floating_windows


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
            scroll_bar: Any = self
            while scroll_bar and not hasattr(scroll_bar, "tabs"):
                scroll_bar = scroll_bar.parentWidget()

            if scroll_bar and panel:
                try:
                    idx = scroll_bar.tabs.index(self)
                    widget, title, closable = panel.remove_tab_widget(idx)

                    orig_panel = getattr(widget, "original_panel", None)
                    orig_idx = getattr(widget, "original_index", None)
                    orig_title = getattr(widget, "original_title", title)
                    orig_icon_name = getattr(widget, "original_icon_name", "")
                    orig_closable = getattr(widget, "original_closable", closable)

                    if orig_panel and orig_idx is not None:
                        try:
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

                if src_panel.__class__.__name__ == "FloatingDockWindow" and len(src_panel.tabs_bar.tabs) <= 1:
                    _dragged_tab_info = None
                    return

                idx = _dragged_tab_info["index"]
                widget = _dragged_tab_info["widget"]
                title = _dragged_tab_info["title"]
                icon_name = _dragged_tab_info["icon_name"]

                src_panel.remove_tab_widget(idx)

                widget.original_panel = src_panel
                widget.original_index = idx
                widget.original_title = title
                widget.original_icon_name = icon_name
                widget.original_closable = True

                from ankiforge.ui.components.tabs.floating_dock import FloatingDockWindow

                fw = FloatingDockWindow()
                fw.insert_tab_widget(0, title, widget, icon_name)

                from PySide6.QtGui import QCursor

                cursor_pos = QCursor.pos()
                fw.move(cursor_pos.x() - fw.width() // 2, cursor_pos.y() - 18)

                _floating_windows.append(fw)
                fw.show()

            _dragged_tab_info = None
            return

        super().mouseMoveEvent(event)
