"""
Main Window & Navigation for AnkiForge.
"""

from typing import Dict, Tuple, Optional, Type, Any, cast
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QLabel, QScrollArea, QPushButton, QFrame, QMessageBox, QButtonGroup
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QSize, QObject, QEvent
from PySide6.QtGui import QMouseEvent

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.ui.components.inputs import GlowLineEdit
from ankiforge.ui.components.buttons import IconButton
from ankiforge.ui.components.misc import DaemonStatusWidget, UserAvatar

from ankiforge.services.ai.flexible_service import AIManager


class ClickableLabel(QLabel):
    """QLabel cliquable pour déclencher des signaux."""

    clicked = Signal()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class SidebarItem(QPushButton):
    """Bouton de navigation dans la sidebar."""

    def __init__(self, view_id: str, icon_name: str, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.view_id = view_id
        self.icon_name = icon_name
        self.title = title

        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)

        self._collapsed = False

        # Set icon
        self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.TEXT_SECONDARY))
        self.setIconSize(QSize(20, 20))
        self.setText(f"  {self.title}")
        self.setStyleSheet(self._get_style(False))
        self.toggled.connect(self._on_toggled)

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        if collapsed:
            self.setText("")
            self.setToolTip(self.title)
        else:
            self.setText(f"  {self.title}")
            self.setToolTip("")

    def _on_toggled(self, checked: bool) -> None:
        if checked:
            self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.ACCENT_PRIMARY))
        else:
            self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.TEXT_SECONDARY))
        self.setStyleSheet(self._get_style(checked))

    def _get_style(self, checked: bool) -> str:
        bg_color = DesignTokens.BG_ACTIVE if checked else "transparent"
        text_color = DesignTokens.ACCENT_PRIMARY if checked else DesignTokens.TEXT_SECONDARY
        return f"""
            SidebarItem {{
                background-color: {bg_color};
                color: {text_color};
                border: none;
                border-radius: {DesignTokens.RADIUS_SM}px;
                text-align: left;
                padding-left: 12px;
                font-weight: {"bold" if checked else "normal"};
                font-size: {DesignTokens.FONT_SIZE_BASE}px;
            }}
            SidebarItem:hover {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """


class Sidebar(QWidget):
    """Sidebar collapsible 260px <-> 68px."""

    view_selected = Signal(str)
    settings_requested = Signal()
    toggle_requested = Signal()

    def __init__(self, profile_name: str = "default", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_SIDEBAR};")
        self.setFixedWidth(DesignTokens.SIDEBAR_WIDTH_EXPANDED)

        self.is_collapsed = False
        self._items: Dict[str, SidebarItem] = {}
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Logo Header
        self.header = QWidget()
        self.header.setFixedHeight(60)
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(16, 0, 16, 0)

        self.logo_icon = ClickableLabel()
        self.logo_icon.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logo_icon.clicked.connect(self.toggle_requested.emit)
        from ankiforge.utils.icon_loader import load_logo_icon

        self.logo_icon.setPixmap(load_logo_icon(DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))

        self.logo_text = QLabel("AnkiForge")
        self.logo_text.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 16px; border: none;")

        self.header.setStyleSheet("border: none;")

        self.toggle_btn = IconButton("list", tooltip="Toggle Sidebar", size=24)
        self.toggle_btn.clicked.connect(self.toggle_requested.emit)

        self.header_layout.addWidget(self.logo_icon)
        self.header_layout.addWidget(self.logo_text)
        self.header_layout.addStretch()
        self.header_layout.addWidget(self.toggle_btn)

        main_layout.addWidget(self.header)

        # 2. ScrollArea for sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background-color: transparent; border: none;")

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background-color: transparent;")
        self.sections_layout = QVBoxLayout(self.scroll_content)
        self.sections_layout.setContentsMargins(12, 12, 12, 12)
        self.sections_layout.setSpacing(24)
        self.sections_layout.addStretch()

        scroll.setWidget(self.scroll_content)
        main_layout.addWidget(scroll)

        # 3. Footer
        self.footer = QWidget()
        footer_layout = QVBoxLayout(self.footer)
        footer_layout.setContentsMargins(12, 12, 12, 12)
        footer_layout.setSpacing(4)

        self.settings_btn = SidebarItem("settings", "gear", "Paramètres")
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.Shape.HLine)
        self.separator.setStyleSheet(f"background-color: {DesignTokens.BORDER_COLOR}; border: none; margin: 4px 0px;")
        self.separator.setFixedHeight(1)
        footer_layout.addWidget(self.separator)

        footer_layout.addWidget(self.settings_btn)

        self.user_widget = QWidget()
        self.user_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.user_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QWidget:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        self.user_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        user_layout = QHBoxLayout(self.user_widget)
        user_layout.setContentsMargins(8, 8, 8, 8)
        self.avatar = UserAvatar("U", size=24)
        self.user_name = QLabel(f"Tristan R.<br><span style='color: {DesignTokens.TEXT_MUTED}; font-weight: normal; font-size: 10px;'>{profile_name}</span>")
        self.user_name.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; font-weight: bold; font-size: 12px;")
        user_layout.addWidget(self.avatar)
        user_layout.addWidget(self.user_name)
        user_layout.addStretch()

        footer_layout.addWidget(self.user_widget)

        main_layout.addWidget(self.footer)

    def add_section(self, title: str, items: list[Tuple[str, str, str]]) -> None:
        """Ajoute une section avec un titre et une liste de (view_id, icon, text)."""
        section_widget = QWidget()
        layout = QVBoxLayout(section_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title_lbl = QLabel(title.upper())
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; border: none;")
        title_lbl.setFixedHeight(20)
        layout.addWidget(title_lbl)

        for view_id, icon, text in items:
            btn = SidebarItem(view_id, icon, text)
            btn.clicked.connect(lambda checked=False, vid=view_id: self.view_selected.emit(vid))
            self._items[view_id] = btn
            self._button_group.addButton(btn)
            layout.addWidget(btn)

        # Insert before the stretch
        self.sections_layout.insertWidget(self.sections_layout.count() - 1, section_widget)
        # Keep track of title labels for collapsing
        section_widget.title_lbl = title_lbl

    def set_collapsed(self, collapsed: bool) -> None:
        self.is_collapsed = collapsed
        width = DesignTokens.SIDEBAR_WIDTH_COLLAPSED if collapsed else DesignTokens.SIDEBAR_WIDTH_EXPANDED

        # Animate width
        self.anim = QPropertyAnimation(self, b"minimumWidth")
        self.anim.setDuration(200)
        self.anim.setStartValue(self.width())
        self.anim.setEndValue(width)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.anim.start()

        self.setMaximumWidth(width)

        # Toggle visibility
        self.logo_text.setVisible(not collapsed)
        self.toggle_btn.setVisible(not collapsed)
        self.user_name.setVisible(not collapsed)

        if collapsed:
            self.header_layout.setContentsMargins(22, 0, 0, 0)
        else:
            self.header_layout.setContentsMargins(16, 0, 16, 0)

        for i in range(self.sections_layout.count() - 1):
            item = self.sections_layout.itemAt(i)
            if item is not None:
                widget = item.widget()
                if widget and hasattr(widget, "title_lbl"):
                    cast(Any, widget).title_lbl.setVisible(not collapsed)

        for btn in self._items.values():
            btn.set_collapsed(collapsed)

        self.settings_btn.set_collapsed(collapsed)

    def set_active_view(self, view_id: str) -> None:
        for vid, btn in self._items.items():
            is_active = vid == view_id
            btn.setChecked(is_active)
            btn._on_toggled(is_active)


class TopBar(QWidget):
    """Barre supérieure 60px : omnibox + actions daemon/tokens/notifications."""

    search_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(DesignTokens.TOPBAR_HEIGHT)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(16)

        # Omnibox
        self.omnibox = GlowLineEdit()
        self.omnibox.setPlaceholderText("Rechercher... (Ctrl+K)")
        self.omnibox.setFixedWidth(400)
        self.omnibox.installEventFilter(self)
        layout.addWidget(self.omnibox)

        layout.addStretch()

        # Token tracker
        self.token_lbl = QLabel("0 tk | 0.00$")
        self.token_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-family: {DesignTokens.FONT_CODE};")
        layout.addWidget(self.token_lbl)

        # Daemon Status
        self.daemon_status = DaemonStatusWidget()
        self.daemon_status.set_status("idle", "Daemon en attente")
        layout.addWidget(self.daemon_status)

        # Notifications
        self.notif_btn = IconButton("bell", tooltip="Notifications", size=24)
        layout.addWidget(self.notif_btn)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj == self.omnibox and event.type() == QEvent.Type.MouseButtonPress:
            self.search_clicked.emit()
            return True
        return super().eventFilter(obj, event)

    def _on_omnibox_click(self, event: QMouseEvent) -> None:
        self.search_clicked.emit()

    def update_daemon_status(self, status: str, text: str) -> None:
        self.daemon_status.set_status(status, text)

    def update_token_tracker(self, cost: str, tokens: str) -> None:
        self.token_lbl.setText(f"{tokens} tk | {cost}$")


class GlobalTitleBar(QFrame):
    """Barre de titre globale 28px pour macOS drag."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(DesignTokens.GLOBAL_TOPBAR_HEIGHT)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("AnkiForge")
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_lbl)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.window().windowHandle().startSystemMove()
        super().mousePressEvent(event)


class DummyView(QWidget):
    """Vue temporaire pour le QStackedWidget."""

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        lbl = QLabel(f"[{title}] View Content Placeholder")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 24px;")
        layout.addWidget(lbl)

    def refresh_data(self) -> None:
        pass

    def is_dirty(self) -> bool:
        return False


class MainWindow(QMainWindow):
    """Fenêtre principale ankiforge_obsidian."""

    from ankiforge.ui.views.dashboard_view import DashboardView
    from ankiforge.ui.views.creation_view import CreationView
    from ankiforge.ui.views.edition_view import EditionView
    from ankiforge.ui.views.consultant_view import ConsultantView
    from ankiforge.ui.views.batch_view import BatchView
    from ankiforge.ui.views.documents_view import DocumentsView
    from ankiforge.ui.views.card_models_view import CardModelsView
    from ankiforge.ui.views.agents_view import AgentsView
    from ankiforge.ui.views.pipelines_view import PipelinesView
    from ankiforge.ui.views.ab_tests_view import ABTestsView

    VIEW_REGISTRY: Dict[str, Tuple[str, str, str, Type[QWidget]]] = {
        # view_id -> (category, icon, title, WidgetClass)
        "dashboard": ("Général", "squares-four", "Tableau de bord", DashboardView),
        "creation": ("Forge & Outils", "magic-wand", "Studio de Création", CreationView),
        "edition": ("Forge & Outils", "cards", "Édition / Analyse", EditionView),
        "consultant": ("Forge & Outils", "robot", "AI Consultant", ConsultantView),
        "batch": ("Forge & Outils", "factory", "Batch Factory", BatchView),
        "documents": ("Bibliothèque", "file-text", "My Documents", DocumentsView),
        "card-models": ("Bibliothèque", "swatches", "Card Models", CardModelsView),
        "agents": ("Laboratoire IA", "cpu", "Éditeur d'Agents", AgentsView),
        "pipelines": ("Laboratoire IA", "git-merge", "Pipelines", PipelinesView),
        "ab-tests": ("Laboratoire IA", "scales", "Tests A/B", ABTestsView),
    }

    def __init__(self, ai_manager: Optional[AIManager], profile_name: str = "default") -> None:
        super().__init__()
        self.ai_manager = ai_manager
        self.profile_name = profile_name
        self.setWindowTitle("AnkiForge")
        self.resize(1280, 800)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        # Main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Global topbar (28px) -> Removed to reclaim native window space and remove redundant title label

        # 2. App body (QHBoxLayout)
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar(profile_name=self.profile_name)
        self.sidebar.toggle_requested.connect(self._toggle_sidebar)
        self.sidebar.view_selected.connect(self._on_view_selected)
        self.sidebar.settings_requested.connect(self._open_settings_modal)
        body_layout.addWidget(self.sidebar)

        # Main content
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # TopBar
        self.topbar = TopBar()
        self.topbar.search_clicked.connect(self._open_command_palette)
        content_layout.addWidget(self.topbar)

        # StackedWidget
        self.stacked_widget = QStackedWidget()
        content_layout.addWidget(self.stacked_widget)

        body_layout.addWidget(content_widget, stretch=1)
        main_layout.addWidget(body_widget, stretch=1)

        self._view_widgets: Dict[str, QWidget] = {}
        self._current_view_id: Optional[str] = None

        self._populate_sidebar_and_register()

    def _populate_sidebar_and_register(self) -> None:
        # Group by category
        categories: Dict[str, list[Tuple[str, str, str]]] = {}
        for view_id, (cat, icon, title, cls) in self.VIEW_REGISTRY.items():
            if cat not in categories:
                categories[cat] = []
            categories[cat].append((view_id, icon, title))

            # Instantiate view
            if cls == DummyView:
                widget = cls(title)
            else:
                try:
                    widget = cast(Any, cls)(ai_manager=self.ai_manager)
                except TypeError:
                    widget = cast(Any, cls)()

            # Connect navigation signals if view supports it
            if hasattr(widget, "request_navigation"):
                widget.request_navigation.connect(self._on_view_selected)

            self._register_view(view_id, widget)

        for cat, items in categories.items():
            self.sidebar.add_section(cat, items)

        # Set default view
        if "dashboard" in self._view_widgets:
            self._on_view_selected("dashboard")

    def _register_view(self, view_id: str, widget: QWidget) -> None:
        """Ajoute un widget au QStackedWidget avec un identifiant."""
        self.stacked_widget.addWidget(widget)
        self._view_widgets[view_id] = widget

    def _on_view_selected(self, view_id: str) -> None:
        """Navigation: vérifie dirty state, switch la vue, appelle refresh_data()."""
        if self._current_view_id == view_id:
            return

        if not self._can_switch_view():
            # Reset sidebar selection visually if rejected
            if self._current_view_id:
                self.sidebar.set_active_view(self._current_view_id)
            return

        widget = self._view_widgets.get(view_id)
        if widget:
            self.stacked_widget.setCurrentWidget(widget)
            self._current_view_id = view_id
            self.sidebar.set_active_view(view_id)

            if hasattr(widget, "refresh_data"):
                cast(Any, widget).refresh_data()

    def _can_switch_view(self) -> bool:
        """Vérifie is_dirty() sur la vue courante. Dialogue de confirmation si sale."""
        if not self._current_view_id:
            return True

        current_widget = self._view_widgets.get(self._current_view_id)
        if current_widget and hasattr(current_widget, "is_dirty"):
            if cast(Any, current_widget).is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Modifications non sauvegardées",
                    "Vous avez des modifications en cours. Voulez-vous vraiment quitter ?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                return reply == QMessageBox.StandardButton.Yes
        return True

    def _toggle_sidebar(self) -> None:
        self.sidebar.set_collapsed(not self.sidebar.is_collapsed)

    def _open_settings_modal(self) -> None:
        """Ouvre le modal de paramètres de l'application."""
        from ankiforge.ui.widgets.settings_modal import SettingsModal

        modal = SettingsModal(ai_manager=self.ai_manager, parent=self)
        modal.exec()

    def _open_command_palette(self) -> None:
        """Ouvre le CommandPalette (Phase 3). Raccourci: Ctrl/⌘+K."""
        print("Command Palette Requested")

    def closeEvent(self, event) -> None:
        # Close all floating windows
        from ankiforge.ui.components.tabs import _floating_windows

        for fw in list(_floating_windows):
            fw.close()
        super().closeEvent(event)
