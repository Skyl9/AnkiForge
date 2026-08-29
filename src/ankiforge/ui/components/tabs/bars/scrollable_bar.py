from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QWidget,
)

from ankiforge.ui.components.tabs.tab_button import (
    TabButton,
    _floating_windows,
)
from ankiforge.ui.components.tabs.tab_container import TabContainer
from ankiforge.ui.theme import DesignTokens


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

            widget.original_panel = panel
            widget.original_index = idx
            widget.original_title = title
            widget.original_icon_name = icon_name
            widget.original_closable = closable

            from ankiforge.ui.components.tabs.floating_dock import FloatingDockWindow

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
