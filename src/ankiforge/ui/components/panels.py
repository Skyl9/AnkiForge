from PySide6.QtWidgets import QFrame, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget, QPushButton, QSplitter
from PySide6.QtCore import Signal, Qt, QRect
from PySide6.QtGui import QIcon, QPainter, QColor, QAction
from typing import Tuple
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.components.buttons import IconButton
from ankiforge.ui.components.tabs import ScrollableTabBarWidget
from ankiforge.utils.icon_loader import load_phosphor_icon
import ankiforge.ui.components.tabs as tabs_mod


def find_tab_owner(title: str):
    from PySide6.QtWidgets import QApplication

    for widget in QApplication.allWidgets():
        if hasattr(widget, "tabs_bar") and hasattr(widget, "content_stack"):
            for i, btn in enumerate(widget.tabs_bar.tabs):
                if btn.text().strip() == title.strip():
                    return widget, i
    return None, -1


def simplify_splitter_hierarchy(splitter: QSplitter):
    if not splitter:
        return

    if splitter.count() == 0:
        parent = splitter.parentWidget()
        splitter.setParent(None)
        splitter.deleteLater()
        if isinstance(parent, QSplitter):
            simplify_splitter_hierarchy(parent)
    elif splitter.count() == 1:
        remaining = splitter.widget(0)
        if remaining is None:
            return
        parent = splitter.parentWidget()
        if isinstance(parent, QSplitter):
            idx = parent.indexOf(splitter)
            parent_sizes = parent.sizes()
            parent.insertWidget(idx, remaining)
            splitter.setParent(None)
            splitter.deleteLater()
            parent.setSizes(parent_sizes)
            simplify_splitter_hierarchy(parent)
        elif parent is not None:
            layout = parent.layout()
            if layout and hasattr(layout, "insertWidget"):
                from typing import Any

                lay: Any = layout
                idx = lay.indexOf(splitter)
                if idx != -1:
                    lay.insertWidget(idx, remaining)
                    splitter.setParent(None)
                    splitter.deleteLater()


def redistribute_splitter_space(splitter: QSplitter):
    if not splitter or splitter.count() == 0:
        return
    # Get total size of splitter along its orientation
    total_size = 0
    for s in splitter.sizes():
        total_size += s
    if total_size <= 0:
        # Fallback if UI is not fully painted yet
        total_size = 800
    # Give all size to the remaining widgets equally
    num_widgets = splitter.count()
    if num_widgets > 0:
        splitter.setSizes([total_size // num_widgets] * num_widgets)


class PanelPlaceholderWidget(QFrame):
    """Placeholder for empty panels to accept drag and drop."""

    def __init__(self, parent_panel, parent=None):
        super().__init__(parent)
        self.parent_panel = parent_panel
        self.setStyleSheet(f"""
            PanelPlaceholderWidget {{
                border: 2px dashed {DesignTokens.TEXT_MUTED};
                border-radius: {DesignTokens.RADIUS_MD}px;
                background-color: transparent;
            }}
        """)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        parent_widget = self.parent_panel.parentWidget()
        if isinstance(parent_widget, QSplitter):
            top_layout = QHBoxLayout()
            top_layout.addStretch()
            self.close_btn = IconButton("ph.x", "Fermer le panneau", 16)
            self.close_btn.clicked.connect(self._close_split)
            top_layout.addWidget(self.close_btn)
            layout.addLayout(top_layout)

        center_layout = QVBoxLayout()
        center_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.icon_lbl = QLabel()
        self.icon_lbl.setPixmap(load_phosphor_icon("ph.plus-circle", color=DesignTokens.TEXT_MUTED).pixmap(32, 32))
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(self.icon_lbl)

        self.text_lbl = QLabel("Aucun onglet actif")
        self.text_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: 600;")
        self.text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(self.text_lbl)

        self.sub_lbl = QLabel("Utilisez le bouton [+] ci-dessus pour réactiver un onglet,\nou cliquez sur le bouton ci-dessous pour restaurer la disposition.")
        self.sub_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; margin: 4px 0;")
        self.sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_lbl.setWordWrap(True)
        center_layout.addWidget(self.sub_lbl)

        center_layout.addSpacing(12)
        self.restore_btn = QPushButton("Restaurer les onglets", self)
        self.restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.restore_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_MAIN};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.restore_btn.clicked.connect(self.parent_panel.restore_all_registered_tabs)
        center_layout.addWidget(self.restore_btn)

        layout.addLayout(center_layout)
        layout.addStretch()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-ankiforge-tab"):
            self.setStyleSheet(f"""
                PanelPlaceholderWidget {{
                    border: 2px dashed {DesignTokens.ACCENT_PRIMARY};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                    background-color: rgba(0, 122, 255, 0.1);
                }}
            """)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(f"""
            PanelPlaceholderWidget {{
                border: 2px dashed {DesignTokens.TEXT_MUTED};
                border-radius: {DesignTokens.RADIUS_MD}px;
                background-color: transparent;
            }}
        """)

    def dropEvent(self, event):
        if event.mimeData().hasFormat("application/x-ankiforge-tab"):
            if tabs_mod._dragged_tab_info:
                src_panel = tabs_mod._dragged_tab_info["source_panel"]
                idx = tabs_mod._dragged_tab_info["index"]
                widget = tabs_mod._dragged_tab_info["widget"]
                title = tabs_mod._dragged_tab_info["title"]
                icon_name = tabs_mod._dragged_tab_info["icon_name"]

                if src_panel != self.parent_panel:
                    widget, title, closable = src_panel.remove_tab_widget(idx)
                    self.parent_panel.insert_tab_widget(0, title, widget, icon_name, closable)

                tabs_mod._dragged_tab_info = None
            event.acceptProposedAction()
            self.dragLeaveEvent(event)

    def _close_split(self):
        parent_splitter = self.parent_panel.parentWidget()
        if isinstance(parent_splitter, QSplitter):
            self.parent_panel.setParent(None)
            self.parent_panel.deleteLater()

            if parent_splitter.count() <= 1:
                simplify_splitter_hierarchy(parent_splitter)
            else:
                redistribute_splitter_space(parent_splitter)


class IdePanel(QFrame):
    """Panneau IDE avec tab bar dans le header, bouton détacher, et widgets additionnels.

    Reproduit le pattern .ide-panel / .ide-tabs / .ide-tab de la maquette HTML.
    Chaque onglet est un QPushButton dans le header avec un indicateur accent 2px en haut.
    """

    detach_requested = Signal()
    tab_changed = Signal(int)

    def __init__(self, title: str = "", detachable: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            IdePanel {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        self._title = title
        self._detachable = detachable
        self.setMinimumSize(150, 100)
        self._registered_tabs: dict[str, dict] = {}

        self.layout_v = QVBoxLayout(self)
        self.layout_v.setContentsMargins(0, 0, 0, 0)
        self.layout_v.setSpacing(0)

        # --- Header (ide-tabs) ---
        self.header = QFrame()
        self.header.setStyleSheet(f"""
            QFrame {{
                background-color: transparent;
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        self.header.setFixedHeight(36)

        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(0, 0, 4, 0)
        self.header_layout.setSpacing(0)

        # If a plain title was given (no tabs added), show it as a static label
        self._static_title_label: QLabel | None = None
        if title:
            self._static_title_label = QLabel(title)
            self._static_title_label.setStyleSheet(f"font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; border: none; padding-left: 16px;")
            self.header_layout.addWidget(self._static_title_label)

        # Tabs container (ide-tabs-list) — scrollable horizontally
        self.tabs_bar = ScrollableTabBarWidget()
        self.tabs_bar.tab_changed.connect(self._on_tab_clicked)
        self.tabs_bar.tab_reordered.connect(self._on_tab_reordered)
        self.tabs_bar.tab_close_requested.connect(self._on_tab_close_requested)
        self.header_layout.addWidget(self.tabs_bar, stretch=1)

        # Extra widgets zone (e.g. view toggles)
        self._extra_widgets_zone = QWidget()
        self._extra_widgets_zone.setStyleSheet("border: none; background: transparent;")
        self._extra_layout = QHBoxLayout(self._extra_widgets_zone)
        self._extra_layout.setContentsMargins(0, 0, 0, 0)
        self._extra_layout.setSpacing(4)
        self._extra_widgets_zone.setVisible(False)
        self.header_layout.addWidget(self._extra_widgets_zone)

        self.menu_btn = IconButton("ph.plus", "Gérer les onglets", 24)
        self.menu_btn.clicked.connect(self._show_tabs_menu)
        self.header_layout.addWidget(self.menu_btn)

        # Detach button
        if detachable:
            self.detach_btn = IconButton("ph.arrow-up-right", "Détacher", 24)
            self.detach_btn.clicked.connect(self.detach_panel)
            self.header_layout.addWidget(self.detach_btn)

        self.layout_v.addWidget(self.header)

        # --- Content (ide-panel-content) ---
        self.content_stack = QStackedWidget()
        self.content_stack.setStyleSheet("border: none; background: transparent;")
        self.layout_v.addWidget(self.content_stack)

        self.placeholder_widget = PanelPlaceholderWidget(self)
        self.layout_v.addWidget(self.placeholder_widget)
        self.placeholder_widget.setVisible(False)
        self._split_direction: str | None = None
        self.setAcceptDrops(True)
        self._toggle_placeholder()

    def _toggle_placeholder(self):
        if len(self.tabs_bar.tabs) == 0:
            # Check for other non-empty panels in the same window/workspace hierarchy
            window = self.window()
            other_non_empty_panels = []
            if window:
                all_panels = window.findChildren(IdePanel)
                for p in all_panels:
                    if p != self and len(p.tabs_bar.tabs) > 0:
                        other_non_empty_panels.append(p)

            # If there are other panels with tabs, close this split and let them reclaim the space
            if other_non_empty_panels:
                parent_splitter = self.parentWidget()
                if isinstance(parent_splitter, QSplitter):
                    self.setParent(None)
                    self.deleteLater()

                    # Simplify the parent splitter hierarchy if needed
                    if parent_splitter.count() <= 1:
                        simplify_splitter_hierarchy(parent_splitter)
                    else:
                        redistribute_splitter_space(parent_splitter)
                else:
                    self.setVisible(False)
            else:
                # If this is the last panel remaining in the workspace, show placeholder
                self.placeholder_widget.setVisible(True)
                self.content_stack.setVisible(False)
                if self._static_title_label is not None:
                    self._static_title_label.setVisible(True)
        else:
            self.placeholder_widget.setVisible(False)
            self.content_stack.setVisible(True)
            if self._static_title_label is not None:
                self._static_title_label.setVisible(False)

    def register_tab(self, title: str, widget: QWidget, icon_name: str = "", closable: bool = True, active_by_default: bool = True):
        self._registered_tabs[title] = {"widget": widget, "icon_name": icon_name, "closable": closable, "active": False}
        if active_by_default:
            self.open_tab(title)

    def open_tab(self, title: str):
        title = title.strip()
        owner, idx = find_tab_owner(title)
        if owner:
            if owner == self:
                self.set_active_tab(idx)
            else:
                widget, tab_title, closable = owner.remove_tab_widget(idx)
                self.insert_tab_widget(len(self.tabs_bar.tabs), title, widget, closable=closable)
        else:
            if title in self._registered_tabs:
                info = self._registered_tabs[title]
                info["active"] = True
                idx = self.tabs_bar.add_tab(title, info["icon_name"], info["closable"])
                self.content_stack.addWidget(info["widget"])
                self._toggle_placeholder()
                self.set_active_tab(len(self.tabs_bar.tabs) - 1)

    def close_tab(self, title: str):
        title = title.strip()
        if title in self._registered_tabs and self._registered_tabs[title]["active"]:
            info = self._registered_tabs[title]
            widget = info["widget"]

            idx = -1
            for i, btn in enumerate(self.tabs_bar.tabs):
                if btn.text().strip() == title.strip():
                    idx = i
                    break

            if idx >= 0:
                self.tabs_bar.remove_tab(idx)
                self.content_stack.removeWidget(widget)
                widget.setParent(None)
                info["active"] = False
                self._toggle_placeholder()

    def _on_tab_close_requested(self, index: int):
        if 0 <= index < len(self.tabs_bar.tabs):
            title = self.tabs_bar.tabs[index].text().strip()
            self.close_tab(title)

    def _show_tabs_menu(self):
        from ankiforge.ui.theme import StyledMenu

        menu = StyledMenu(self)
        for title, _ in self._registered_tabs.items():
            action = QAction(title, self)
            action.setCheckable(True)

            is_active_here = False
            for btn in self.tabs_bar.tabs:
                if btn.text().strip() == title.strip():
                    is_active_here = True
                    break
            action.setChecked(is_active_here)

            action.setProperty("tab_title", title)
            action.triggered.connect(self._on_menu_action_triggered)
            menu.addAction(action)

        menu.exec(self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomLeft()))

    def _on_menu_action_triggered(self) -> None:
        from PySide6.QtGui import QAction

        action = self.sender()
        if not isinstance(action, QAction):
            return
        title = action.property("tab_title")
        if action.isChecked():
            self.open_tab(title)
        else:
            self.close_tab(title)

    def detach_panel(self):
        active_tabs = list(self.tabs_bar.tabs)
        if not active_tabs:
            return

        from ankiforge.ui.components.tabs import FloatingDockWindow
        from PySide6.QtGui import QCursor

        fw = FloatingDockWindow()
        # Remove backwards to avoid index shifting issues
        for btn in reversed(active_tabs):
            idx = self.tabs_bar.tabs.index(btn)
            icon_name = btn.property("icon_name") or ""
            widget, title, closable = self.remove_tab_widget(idx)
            fw.insert_tab_widget(0, title, widget, icon_name, closable)

        fw.move(QCursor.pos())
        tabs_mod._floating_windows.append(fw)
        fw.show()

    def add_tab(self, title: str, widget: QWidget, icon_name: str = "", closable: bool = False) -> int:
        """Ajoute un onglet avec titre, contenu et icône optionnelle."""
        self.register_tab(title, widget, icon_name, closable, active_by_default=True)
        return len(self.tabs_bar.tabs) - 1

    def remove_tab_widget(self, index: int) -> Tuple[QWidget, str, bool]:
        """Supprime un onglet et retourne son widget, titre et closable."""
        title = self.tabs_bar.tabs[index].text().strip()
        info = self._registered_tabs.get(title, {})
        closable = info.get("closable", True)
        if title in self._registered_tabs:
            self._registered_tabs[title]["active"] = False

        widget = self.content_stack.widget(index)
        if widget is None:
            raise ValueError(f"No widget at index {index}")
        self.tabs_bar.remove_tab(index)
        self.content_stack.removeWidget(widget)
        widget.setParent(None)
        self._toggle_placeholder()
        return widget, title, closable

    def insert_tab_widget(self, index: int, title: str, widget: QWidget, icon_name: str = "", closable: bool = True) -> int:
        """Insère un onglet à un index spécifique."""
        self._registered_tabs[title] = {"widget": widget, "icon_name": icon_name, "closable": closable, "active": True}
        self.tabs_bar.insert_tab(index, title, icon_name)
        self.content_stack.insertWidget(index, widget)
        self.set_active_tab(index)
        self._toggle_placeholder()
        return index

    def set_active_tab(self, index: int) -> None:
        """Active un onglet par son index."""
        self.tabs_bar.set_active_tab(index)

    def restore_all_registered_tabs(self):
        """Restore all registered tabs in this panel."""
        for title in list(self._registered_tabs.keys()):
            self.open_tab(title)

    def add_header_widget(self, widget: QWidget) -> None:
        """Ajoute un widget supplémentaire dans le header (après les tabs, avant le detach)."""
        self._extra_widgets_zone.setVisible(True)
        self._extra_layout.addWidget(widget)

    def add_header_separator(self) -> None:
        """Ajoute un séparateur vertical dans la zone extra du header."""
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(20)
        sep.setStyleSheet(f"color: {DesignTokens.BORDER_COLOR}; border: none; background: {DesignTokens.BORDER_COLOR}; max-width: 1px;")
        self._extra_widgets_zone.setVisible(True)
        self._extra_layout.addWidget(sep)

    def _on_tab_clicked(self, idx: int) -> None:
        self.content_stack.setCurrentIndex(idx)
        # Update icons for active/inactive state
        for i, btn in enumerate(self.tabs_bar.tabs):
            if i == idx:
                btn.setIcon(load_phosphor_icon(btn.property("icon_name") or "", color=DesignTokens.TEXT_PRIMARY) if btn.property("icon_name") else QIcon())
            else:
                btn.setIcon(load_phosphor_icon(btn.property("icon_name") or "", color=DesignTokens.TEXT_SECONDARY) if btn.property("icon_name") else QIcon())
        self.tab_changed.emit(idx)

    def _on_tab_reordered(self, from_idx: int, to_idx: int) -> None:
        # Reorder stacked widget
        widget = self.content_stack.widget(from_idx)
        if widget is None:
            return
        self.content_stack.removeWidget(widget)
        self.content_stack.insertWidget(to_idx, widget)
        # Update current index to follow the active tab
        for i, btn in enumerate(self.tabs_bar.tabs):
            if btn.isChecked():
                self.content_stack.setCurrentIndex(i)
                break

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-ankiforge-tab"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-ankiforge-tab"):
            pos = event.position().toPoint()
            w = self.width()
            h = self.height()
            self._split_direction = None
            if pos.x() < w * 0.25:
                self._split_direction = "left"
            elif pos.x() > w * 0.75:
                self._split_direction = "right"
            elif pos.y() < h * 0.25:
                self._split_direction = "top"
            elif pos.y() > h * 0.75:
                self._split_direction = "bottom"

            self.update()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._split_direction = None
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if getattr(self, "_split_direction", None):
            painter = QPainter(self)
            color = QColor(DesignTokens.ACCENT_PRIMARY)
            color.setAlpha(60)
            painter.fillRect(self._get_split_rect(), color)

    def _get_split_rect(self):
        w = self.width()
        h = self.height()
        if self._split_direction == "left":
            return QRect(0, 0, w // 2, h)
        elif self._split_direction == "right":
            return QRect(w // 2, 0, w // 2, h)
        elif self._split_direction == "top":
            return QRect(0, 0, w, h // 2)
        elif self._split_direction == "bottom":
            return QRect(0, h // 2, w, h // 2)
        return QRect(0, 0, 0, 0)

    def dropEvent(self, event):
        if event.mimeData().hasFormat("application/x-ankiforge-tab"):
            if getattr(self, "_split_direction", None):
                if tabs_mod._dragged_tab_info:
                    src_panel = tabs_mod._dragged_tab_info["source_panel"]
                    idx = tabs_mod._dragged_tab_info["index"]
                    widget = tabs_mod._dragged_tab_info["widget"]
                    title = tabs_mod._dragged_tab_info["title"]
                    icon_name = tabs_mod._dragged_tab_info["icon_name"]

                    if self._split_direction:
                        widget, title, closable = src_panel.remove_tab_widget(idx)
                        self.split_panel(self._split_direction, title, widget, icon_name, closable)

                    tabs_mod._dragged_tab_info = None
                event.acceptProposedAction()
            self._split_direction = None
            self.update()

    def split_panel(self, direction: str, title: str, widget: QWidget, icon_name: str, closable: bool = True):
        parent = self.parentWidget()
        if not parent:
            return

        new_panel = IdePanel(detachable=self._detachable)
        new_panel.add_tab(title, widget, icon_name, closable)

        is_horizontal = direction in ("left", "right")
        orientation = Qt.Orientation.Horizontal if is_horizontal else Qt.Orientation.Vertical

        if isinstance(parent, QSplitter):
            idx = parent.indexOf(self)
            new_splitter = QSplitter(orientation)
            parent.insertWidget(idx, new_splitter)

            if direction in ("left", "top"):
                new_splitter.addWidget(new_panel)
                new_splitter.addWidget(self)
            else:
                new_splitter.addWidget(self)
                new_splitter.addWidget(new_panel)
            new_splitter.setCollapsible(0, False)
            new_splitter.setCollapsible(1, False)
        else:
            layout = parent.layout()
            if layout and hasattr(layout, "insertWidget"):
                from typing import Any

                lay: Any = layout
                idx = lay.indexOf(self)
                if idx != -1:
                    new_splitter = QSplitter(orientation)
                    lay.removeWidget(self)
                    lay.insertWidget(idx, new_splitter)
                    if direction in ("left", "top"):
                        new_splitter.addWidget(new_panel)
                        new_splitter.addWidget(self)
                    else:
                        new_splitter.addWidget(self)
                        new_splitter.addWidget(new_panel)
                    new_splitter.setCollapsible(0, False)
                    new_splitter.setCollapsible(1, False)


class GlassPanel(QFrame):
    """Panneau glassmorphism (semi-transparent + blur effect)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            GlassPanel {{
                background-color: rgba(30, 33, 40, 0.6);
                border: 1px solid {DesignTokens.BORDER_LIGHT};
                border-radius: {DesignTokens.RADIUS_LG}px;
            }}
        """)
        apply_shadow(self, blur=DesignTokens.SHADOW_GLASS_BLUR, offset_y=4)


class MetricCard(QFrame):
    """Carte métrique avec valeur, label, icône, trend. Usage: Batch CI/CD, Stats."""

    def __init__(self, label: str, value: str, icon_name: str, trend: str = "", trend_positive: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            MetricCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        header = QHBoxLayout()
        self.lbl_label = QLabel(label)
        self.lbl_label.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px;")

        self.icon_label = QLabel(icon_name)
        self.icon_label.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED};")

        header.addWidget(self.lbl_label)
        header.addStretch()
        header.addWidget(self.icon_label)
        layout.addLayout(header)

        footer = QHBoxLayout()
        self.val_label = QLabel(value)
        self.val_label.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        footer.addWidget(self.val_label)

        if trend:
            self.trend_label = QLabel(trend)
            color = DesignTokens.COLOR_GREEN if trend_positive else DesignTokens.COLOR_RED
            self.trend_label.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: bold;")
            footer.addWidget(self.trend_label)

        footer.addStretch()
        layout.addLayout(footer)

    def set_value(self, value: str) -> None:
        self.val_label.setText(value)


class StatCard(QFrame):
    """Carte statistique. Usage: Dashboard sidebar, Settings stats."""

    def __init__(self, label: str, value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            StatCard {{
                background-color: {DesignTokens.BG_INPUT};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        self.lbl = QLabel(label)
        self.lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px;")

        self.val = QLabel(value)
        self.val.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 16px; font-weight: bold;")

        layout.addWidget(self.lbl)
        layout.addWidget(self.val)
