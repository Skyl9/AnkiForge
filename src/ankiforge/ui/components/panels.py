from typing import Any

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSplitter, QStackedWidget, QVBoxLayout, QWidget

import ankiforge.ui.components.tabs as tabs_mod
from ankiforge.ui.components.buttons import IconButton, PrimaryButton, SecondaryButton
from ankiforge.ui.components.tabs import ScrollableTabBarWidget
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.utils.icon_loader import load_phosphor_icon


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
                border: 2px dashed {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                background-color: transparent;
                margin: 8px;
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

        # Add vertical centering stretch
        layout.addStretch()

        center_layout = QVBoxLayout()
        center_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.setSpacing(12)

        self.icon_lbl = QLabel()
        self.icon_lbl.setPixmap(load_phosphor_icon("ph.squares-four", color=DesignTokens.TEXT_MUTED).pixmap(32, 32))
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setStyleSheet("border: none; background: transparent;")
        center_layout.addWidget(self.icon_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        self.text_lbl = QLabel("Panneau Libre")
        self.text_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: 600; border: none; background: transparent;")
        self.text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(self.text_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        self.sub_lbl = QLabel("Glissez-déposez un onglet ou une fenêtre ici pour l'ancrer.")
        self.sub_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; margin: 4px 0; border: none; background: transparent;")
        self.sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_lbl.setWordWrap(True)
        center_layout.addWidget(self.sub_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        center_layout.addSpacing(4)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(12)
        buttons_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.add_tab_btn = PrimaryButton("Ouvrir un onglet...", self)
        self.add_tab_btn.clicked.connect(self._show_add_tab_menu)
        buttons_layout.addWidget(self.add_tab_btn)

        self.restore_btn = SecondaryButton("Restaurer tout", self)
        self.restore_btn.clicked.connect(self.parent_panel.restore_all_registered_tabs)
        buttons_layout.addWidget(self.restore_btn)

        center_layout.addLayout(buttons_layout)

        layout.addLayout(center_layout)

        # Add vertical centering stretch
        layout.addStretch()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-ankiforge-tab"):
            self.setStyleSheet(f"""
                PanelPlaceholderWidget {{
                    border: 2px dashed {DesignTokens.ACCENT_PRIMARY};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                    background-color: {DesignTokens.BG_ACTIVE};
                    margin: 8px;
                }}
                QLabel {{
                    border: none;
                    background-color: transparent;
                }}
            """)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(f"""
            PanelPlaceholderWidget {{
                border: 2px dashed {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                background-color: rgba(255, 255, 255, 0.01);
                margin: 8px;
            }}
            QLabel {{
                border: none;
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

    def _show_add_tab_menu(self):
        self.parent_panel._show_tabs_menu_at_button(self.add_tab_btn)


class PanelDragOverlay(QWidget):
    """Transparent glass pane overlay to draw the drag split preview rect on top of all child widgets."""

    def __init__(self, parent_panel: QWidget) -> None:
        super().__init__(parent_panel)
        self.parent_panel = parent_panel
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setVisible(False)

    def paintEvent(self, event) -> None:
        direction = getattr(self.parent_panel, "_split_direction", None)
        if direction:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Semi-transparent primary violet background
            color = QColor(DesignTokens.ACCENT_PRIMARY)
            color.setAlpha(60)  # ~24% opacity

            # Solid border
            border_color = QColor(DesignTokens.ACCENT_PRIMARY)
            border_color.setAlpha(180)

            rect = self.parent_panel._get_split_rect()

            painter.setBrush(color)
            painter.setPen(QPen(border_color, 2, Qt.PenStyle.SolidLine))
            painter.drawRoundedRect(rect, DesignTokens.RADIUS_MD, DesignTokens.RADIUS_MD)


class IdePanel(QFrame):
    """Panneau IDE avec tab bar dans le header, bouton détacher, et widgets additionnels.

    Reproduit le pattern .ide-panel / .ide-tabs / .ide-tab de la maquette HTML.
    Chaque onglet est un QPushButton dans le header avec un indicateur accent 2px en haut.
    """

    detach_requested = Signal()
    tab_changed = Signal(int)

    def __init__(self, title: str = "", detachable: bool = False, tab_variant: str = "ide", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._title = title
        self._detachable = detachable
        self.setMinimumSize(150, 100)
        self._registered_tabs: dict[str, dict] = {}

        self.layout_v = QVBoxLayout(self)
        self.layout_v.setContentsMargins(0, 0, 0, 0)
        self.layout_v.setSpacing(0)

        # --- Header (ide-tabs) ---
        self.header = QFrame()
        self.header.setObjectName("header")
        self.header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
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

        # Tab Bar
        self.tabs_bar = ScrollableTabBarWidget(variant=tab_variant)
        self.tabs_bar.tab_changed.connect(self._on_tab_changed)
        self.tabs_bar.tab_reordered.connect(self._on_tab_reordered)
        self.tabs_bar.tab_close_requested.connect(self._on_tab_close_requested)
        self.header_layout.addWidget(self.tabs_bar, stretch=1)

        # Extra widgets zone (e.g. view toggles)
        self._extra_widgets_zone = QWidget()
        self._extra_widgets_zone.setObjectName("extraWidgetsZone")
        self._extra_widgets_zone.setStyleSheet("QWidget#extraWidgetsZone { border: none; background: transparent; }")
        self._extra_layout = QHBoxLayout(self._extra_widgets_zone)
        self._extra_layout.setContentsMargins(0, 0, 0, 0)
        self._extra_layout.setSpacing(4)
        self._extra_widgets_zone.setVisible(False)
        self.header_layout.addWidget(self._extra_widgets_zone)

        action_btn_style = f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """

        self.menu_btn = IconButton("ph.plus", "Gérer les onglets", 24)
        self.menu_btn.setStyleSheet(action_btn_style)
        self.menu_btn.clicked.connect(self._show_tabs_menu)
        self.header_layout.addWidget(self.menu_btn)
        self._show_menu_btn: bool = True

        # Detach button
        if detachable:
            self.detach_btn = IconButton("ph.arrow-up-right", "Détacher", 24)
            self.detach_btn.setStyleSheet(action_btn_style)
            self.detach_btn.clicked.connect(self.detach_panel)
            self.header_layout.addWidget(self.detach_btn)

        self.header.setStyleSheet(f"""
            QFrame#header {{
                background-color: {DesignTokens.BG_SIDEBAR};
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)

        self.layout_v.addWidget(self.header)

        # --- Content (ide-panel-content) ---
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("idePanelContentStack")
        self.content_stack.setStyleSheet("QStackedWidget#idePanelContentStack { border: none; background: transparent; }")
        self.layout_v.addWidget(self.content_stack)

        self.placeholder_widget = PanelPlaceholderWidget(self)
        self.layout_v.addWidget(self.placeholder_widget)
        self.placeholder_widget.setVisible(False)
        self._split_direction: str | None = None
        self.setAcceptDrops(True)

        self.drag_overlay = PanelDragOverlay(self)

        self._toggle_placeholder()

    def refresh_theme(self, profile: Any = None) -> None:
        self.header.setStyleSheet(f"""
            QFrame#header {{
                background-color: {DesignTokens.BG_SIDEBAR};
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        if hasattr(self, "tabs_bar") and hasattr(self.tabs_bar, "refresh_theme"):
            self.tabs_bar.refresh_theme(profile)
        if hasattr(self, "menu_btn") and hasattr(self.menu_btn, "refresh_theme"):
            self.menu_btn.refresh_theme(profile)
        if hasattr(self, "detach_btn") and hasattr(self.detach_btn, "refresh_theme"):
            self.detach_btn.refresh_theme(profile)
        if self._static_title_label is not None:
            self._static_title_label.setStyleSheet(f"font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; border: none; padding-left: 16px;")

    def _toggle_placeholder(self):
        if len(self.tabs_bar.tabs) == 0:
            # Hide header when empty to remove tab effect at the top
            self.header.setVisible(False)
            self.menu_btn.setVisible(False)
            if hasattr(self, "detach_btn"):
                self.detach_btn.setVisible(False)
            self._extra_widgets_zone.setVisible(False)

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
                    # Static panel: keep visible and show placeholder
                    self.placeholder_widget.setVisible(True)
                    self.content_stack.setVisible(False)
                    if self._static_title_label is not None:
                        self._static_title_label.setVisible(True)
            else:
                # If this is the last panel remaining in the workspace, show placeholder
                self.placeholder_widget.setVisible(True)
                self.content_stack.setVisible(False)
                if self._static_title_label is not None:
                    self._static_title_label.setVisible(True)
        else:
            # Show header when populated
            self.header.setVisible(True)
            self.menu_btn.setVisible(getattr(self, "_show_menu_btn", True))
            if hasattr(self, "detach_btn"):
                self.detach_btn.setVisible(True)
            if self._extra_layout.count() > 0:
                self._extra_widgets_zone.setVisible(True)

            self.placeholder_widget.setVisible(False)
            self.content_stack.setVisible(True)
            if self._static_title_label is not None:
                self._static_title_label.setVisible(False)

    def set_menu_button_visible(self, visible: bool) -> None:
        """Contrôle la visibilité du bouton '+' de gestion des onglets."""
        self._show_menu_btn = visible
        self.menu_btn.setVisible(visible)

    def register_tab(self, title: str, widget: QWidget, icon_name: str = "", closable: bool = True, active_by_default: bool = True, icon_color: str = ""):
        title = title.strip()
        self._registered_tabs[title] = {"widget": widget, "icon_name": icon_name, "closable": closable, "active": False, "icon_color": icon_color}
        if active_by_default:
            self.open_tab(title)

    def set_tab_text(self, index: int, text: str) -> None:
        if hasattr(self, "tabs_bar"):
            self.tabs_bar.set_tab_text(index, text)

    def set_tab_title(self, index: int, title: str) -> None:
        self.set_tab_text(index, title)

    def open_tab(self, title: str):
        title = title.strip()
        if title in self._registered_tabs:
            info = self._registered_tabs[title]

            # Safety check: verify if the C++ widget has been deleted
            try:
                _ = info["widget"].parent()
            except RuntimeError:
                # C++ object was deleted. Remove from registration.
                self._registered_tabs.pop(title, None)
                self._toggle_placeholder()
                return

            if info["active"]:
                for i, btn in enumerate(self.tabs_bar.tabs):
                    if btn.text().strip() == title:
                        self.set_active_tab(i)
                        return

            info["active"] = True
            idx = self.tabs_bar.add_tab(title, info["icon_name"], info["closable"], info.get("icon_color", ""))
            self.content_stack.addWidget(info["widget"])
            info["widget"].show()
            self._toggle_placeholder()
            self.set_active_tab(len(self.tabs_bar.tabs) - 1)
            return

        owner, idx = find_tab_owner(title)
        if owner:
            if owner == self:
                self.set_active_tab(idx)
            else:
                widget, tab_title, closable = owner.remove_tab_widget(idx)
                self.insert_tab_widget(len(self.tabs_bar.tabs), title, widget, closable=closable)

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
        self._show_tabs_menu_at_button(self.menu_btn)

    def _show_tabs_menu_at_button(self, button: QPushButton) -> None:
        from PySide6.QtCore import QPoint

        from ankiforge.ui.theme import StyledMenu

        menu = StyledMenu(self)

        # 1. Find top-level view widget
        top_view = self
        while top_view and top_view.parentWidget() and top_view.parentWidget() != top_view.window():
            if top_view.parentWidget().__class__.__name__ == "QStackedWidget":
                break
            top_view = top_view.parentWidget()

        if not top_view:
            top_view = self.window()

        # 2. Collect catalog from all panels in the same view
        all_view_panels = top_view.findChildren(IdePanel)
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

                # Use a custom property to store action title
                action.setProperty("tab_title", title)
                action.setProperty("tab_is_here", is_here)

                if is_here:
                    action.setEnabled(False)
                else:
                    action.triggered.connect(self._on_menu_action_triggered)

                menu.addAction(action)

        menu.exec(button.mapToGlobal(QPoint(0, button.height())))

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

        from PySide6.QtGui import QCursor

        from ankiforge.ui.components.tabs import FloatingDockWindow

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

    def add_tab(self, title: str, widget: QWidget, icon_name: str = "", closable: bool = False, icon_color: str = "") -> int:
        """Ajoute un onglet avec titre, contenu et icône optionnelle."""
        self.register_tab(title, widget, icon_name, closable, active_by_default=True, icon_color=icon_color)
        return len(self.tabs_bar.tabs) - 1

    def remove_tab_widget(self, index: int) -> tuple[QWidget, str, bool]:
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
        title = title.strip()
        self._registered_tabs[title] = {"widget": widget, "icon_name": icon_name, "closable": closable, "active": True}
        self.tabs_bar.insert_tab(index, title, icon_name)
        self.content_stack.insertWidget(index, widget)
        widget.show()
        self.set_active_tab(index)
        self._toggle_placeholder()
        return index

    def set_active_tab(self, index: int) -> None:
        """Active un onglet par son index."""
        self.tabs_bar.set_active_tab(index)

    def restore_all_registered_tabs(self):
        """Restore all registered tabs in this panel."""
        for title in list(self._registered_tabs.keys()):
            # Safety check: skip if C++ widget is deleted
            info = self._registered_tabs.get(title)
            if info:
                try:
                    _ = info["widget"].parent()
                except RuntimeError:
                    self._registered_tabs.pop(title, None)
                    continue
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

    def _on_tab_changed(self, idx: int) -> None:
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
            if tabs_mod._dragged_tab_info:
                src_panel = tabs_mod._dragged_tab_info["source_panel"]
                if src_panel == self and len(self.tabs_bar.tabs) <= 1:
                    event.ignore()
                    return
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-ankiforge-tab"):
            if tabs_mod._dragged_tab_info:
                src_panel = tabs_mod._dragged_tab_info["source_panel"]
                if src_panel == self and len(self.tabs_bar.tabs) <= 1:
                    self._split_direction = None
                    self.drag_overlay.setVisible(False)
                    event.ignore()
                    return

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

            if self._split_direction:
                self.drag_overlay.setGeometry(self.rect())
                self.drag_overlay.setVisible(True)
                self.drag_overlay.update()
            else:
                self.drag_overlay.setVisible(False)

            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._split_direction = None
        self.drag_overlay.setVisible(False)

    def paintEvent(self, event):
        # Painting is now done by the drag_overlay glass pane on top of all child widgets
        super().paintEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "drag_overlay"):
            self.drag_overlay.setGeometry(self.rect())

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
            direction = getattr(self, "_split_direction", None)
            self._split_direction = None
            self.drag_overlay.setVisible(False)

            if direction:
                if tabs_mod._dragged_tab_info:
                    src_panel = tabs_mod._dragged_tab_info["source_panel"]
                    idx = tabs_mod._dragged_tab_info["index"]
                    widget = tabs_mod._dragged_tab_info["widget"]
                    title = tabs_mod._dragged_tab_info["title"]
                    icon_name = tabs_mod._dragged_tab_info["icon_name"]

                    widget, title, closable = src_panel.remove_tab_widget(idx)
                    self.split_panel(direction, title, widget, icon_name, closable)

                    tabs_mod._dragged_tab_info = None
                event.acceptProposedAction()
            else:
                # Center drop: dock the tab to this panel!
                if tabs_mod._dragged_tab_info:
                    src_panel = tabs_mod._dragged_tab_info["source_panel"]
                    idx = tabs_mod._dragged_tab_info["index"]
                    widget = tabs_mod._dragged_tab_info["widget"]
                    title = tabs_mod._dragged_tab_info["title"]
                    icon_name = tabs_mod._dragged_tab_info["icon_name"]

                    if src_panel != self:
                        widget, title, closable = src_panel.remove_tab_widget(idx)
                        self.insert_tab_widget(len(self.tabs_bar.tabs), title, widget, icon_name, closable)

                    tabs_mod._dragged_tab_info = None
                event.acceptProposedAction()
            self.update()

    def split_panel(self, direction: str, title: str, widget: QWidget, icon_name: str, closable: bool = True):
        parent = self.parentWidget()
        if not parent:
            return

        new_panel = IdePanel(detachable=self._detachable, tab_variant=self.tabs_bar.variant)
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
        apply_shadow(self, blur=DesignTokens.SHADOW_GLASS_BLUR, offset_y=4)


class MetricCard(QFrame):
    """Carte métrique avec valeur, label, icône, trend. Usage: Batch CI/CD, Stats."""

    def __init__(self, label: str, value: str, icon_name: str, trend: str = "", trend_positive: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        apply_shadow(self, blur=12, offset_y=4, color=QColor(99, 102, 241, 40))
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        self.lbl = QLabel(label)
        self.lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px;")

        self.val = QLabel(value)
        self.val.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 16px; font-weight: bold;")

        layout.addWidget(self.lbl)
        layout.addWidget(self.val)


class EmptyStateWidget(QFrame):
    """Widget d'état vide avec icône, titre et description."""

    def __init__(
        self,
        icon_name: str = "ph.ghost",
        title: str = "Aucun élément",
        description: str = "",
        action_button: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        self.icon_lbl = QLabel()
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_MUTED).pixmap(48, 48))
        self.icon_lbl.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.icon_lbl)

        self.title_lbl = QLabel(title)
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl.setStyleSheet(f"font-size: 16px; font-weight: 600; color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        layout.addWidget(self.title_lbl)

        if description:
            self.desc_lbl = QLabel(description)
            self.desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.desc_lbl.setWordWrap(True)
            self.desc_lbl.setStyleSheet(f"font-size: 12px; color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent; max-width: 400px;")
            layout.addWidget(self.desc_lbl)

        if action_button:
            layout.addWidget(action_button, alignment=Qt.AlignmentFlag.AlignCenter)
