from typing import Tuple
from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QTimer, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.tabs.tab_button import _floating_windows
from ankiforge.ui.theme import DesignTokens


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

        from ankiforge.ui.components.tabs.bars.scrollable_bar import ScrollableTabBarWidget

        self.tabs_bar = ScrollableTabBarWidget()
        self.header_layout.addWidget(self.tabs_bar, 1)

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
            QTimer.singleShot(150, lambda: self.setWindowOpacity(1.0))

    def set_active_tab(self, index: int):
        self.tabs_bar.set_active_tab(index)

    def closeEvent(self, event):
        while self.content_stack.count() > 0:
            w = self.content_stack.widget(0)
            if w:
                self.content_stack.removeWidget(w)
                w.setParent(None)
                w.hide()

                orig_panel = getattr(w, "original_panel", None)
                orig_idx = getattr(w, "original_index", None)
                orig_title = getattr(w, "original_title", None)
                orig_icon_name = getattr(w, "original_icon_name", "")
                orig_closable = getattr(w, "original_closable", True)

                if orig_panel and orig_idx is not None and orig_title:
                    try:
                        _ = orig_panel.parent()
                        target_idx = min(orig_idx, len(orig_panel.tabs_bar.tabs))
                        orig_panel.insert_tab_widget(target_idx, orig_title, w, orig_icon_name, orig_closable)
                    except RuntimeError:
                        pass

        if self in _floating_windows:
            _floating_windows.remove(self)
        self.deleteLater()
        event.accept()

    def _show_tabs_menu(self):
        if self.content_stack.count() > 0:
            w = self.content_stack.widget(0)
            orig_panel = getattr(w, "original_panel", None)
            if orig_panel:
                self._show_tabs_menu_at_button(self.menu_btn, orig_panel)

    def _show_tabs_menu_at_button(self, button, orig_panel):
        from ankiforge.ui.theme import StyledMenu

        menu = StyledMenu(self)

        top_view = orig_panel
        while top_view and top_view.parentWidget() and top_view.parentWidget() != top_view.window():
            if top_view.parentWidget().__class__.__name__ == "QStackedWidget":
                break
            top_view = top_view.parentWidget()

        if not top_view:
            top_view = orig_panel.window()

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

        owner, idx = find_tab_owner(title)
        if owner:
            if owner == self:
                self.set_active_tab(idx)
            else:
                widget, tab_title, closable = owner.remove_tab_widget(idx)

                if not hasattr(widget, "original_panel") or widget.original_panel is None:
                    widget.original_panel = getattr(owner, "original_panel", None) or owner
                    widget.original_index = idx
                    widget.original_title = tab_title
                    widget.original_icon_name = getattr(owner, "_registered_tabs", {}).get(tab_title, {}).get("icon_name", "")
                    widget.original_closable = closable

                self.insert_tab_widget(self.tabs_bar.tabs_bar.count() if hasattr(self.tabs_bar, "tabs_bar") else len(self.tabs_bar.tabs), title, widget, widget.original_icon_name, closable)
        else:
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

                        info["widget"].original_panel = panel
                        info["widget"].original_index = list(panel._registered_tabs.keys()).index(title)
                        info["widget"].original_title = title
                        info["widget"].original_icon_name = info["icon_name"]
                        info["widget"].original_closable = info["closable"]

                        self.insert_tab_widget(len(self.tabs_bar.tabs), title, info["widget"], info["icon_name"], info["closable"])
                        break
