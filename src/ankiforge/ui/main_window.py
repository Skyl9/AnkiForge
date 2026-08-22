"""
Main Window & Navigation for AnkiForge.
"""

from typing import Dict, Tuple, Optional, Type, Any, cast
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QLabel, QScrollArea, QPushButton, QFrame, QMessageBox, QButtonGroup
from PySide6.QtCore import Qt, Signal, QSize, QObject, QEvent
from PySide6.QtGui import QMouseEvent, QKeySequence, QShortcut

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.agents_view import AgentsView
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.ui.components.inputs import GlowLineEdit
from ankiforge.ui.components.buttons import IconButton
from ankiforge.ui.components.misc import DaemonStatusWidget

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

    def refresh_theme(self, profile: Any) -> None:
        color = profile.accent_primary if self.isChecked() else profile.text_secondary
        self.setIcon(load_phosphor_icon(self.icon_name, color=color))


class Sidebar(QWidget):
    """Sidebar collapsible 260px <-> 68px."""

    view_selected = Signal(str)
    settings_requested = Signal()
    toggle_requested = Signal()

    def __init__(self, profile_name: str = "default", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(DesignTokens.SIDEBAR_WIDTH_EXPANDED)

        self.profile_name = profile_name
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

        self.header.setStyleSheet(f"border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; background-color: transparent;")

        self.toggle_btn = IconButton("list", tooltip="Toggle Sidebar", size=24)
        self.toggle_btn.clicked.connect(self.toggle_requested.emit)

        self.header_layout.addWidget(self.logo_icon)
        self.header_layout.addWidget(self.logo_text)
        self.header_layout.addStretch()
        self.header_layout.addWidget(self.toggle_btn)

        main_layout.addWidget(self.header)

        # 2. ScrollArea for sections
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; } QScrollBar { width: 0px; height: 0px; }")

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background-color: transparent;")
        self.sections_layout = QVBoxLayout(self.scroll_content)
        self.sections_layout.setContentsMargins(12, 12, 12, 12)
        self.sections_layout.setSpacing(24)
        self.sections_layout.addStretch()

        self.scroll.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll)

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
        self.user_widget.setObjectName("UserWidget")
        self.user_widget.setProperty("card-style", "panel")
        self.user_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.user_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self.user_widget.mousePressEvent = lambda event: self.settings_requested.emit()
        user_layout = QHBoxLayout(self.user_widget)
        user_layout.setContentsMargins(8, 8, 8, 8)

        self.cards_icon = QLabel()
        self.cards_icon.setPixmap(load_phosphor_icon("cards", color=DesignTokens.ACCENT_PRIMARY).pixmap(20, 20))
        self.cards_icon.setStyleSheet("border: none; background: transparent;")

        self.user_name = QLabel(f"Profil: {profile_name}<br><span style='color: {DesignTokens.COLOR_GREEN}; font-weight: normal; font-size: 11px;'>Forge Local Prête</span>")
        self.user_name.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; font-weight: bold; font-size: 12px;")
        user_layout.addWidget(self.cards_icon)
        user_layout.addWidget(self.user_name)
        user_layout.addStretch()

        footer_layout.addWidget(self.user_widget)

        main_layout.addWidget(self.footer)

    def refresh_theme(self, profile: Any) -> None:
        from ankiforge.utils.icon_loader import load_logo_icon

        if hasattr(self, "logo_icon"):
            self.logo_icon.setPixmap(load_logo_icon(profile.accent_primary).pixmap(24, 24))
        if hasattr(self, "logo_text"):
            self.logo_text.setStyleSheet(f"color: {profile.text_primary}; font-weight: bold; font-size: 16px; border: none;")
        if hasattr(self, "header"):
            self.header.setStyleSheet(f"border-bottom: 1px solid {profile.border_color}; background-color: transparent;")
        if hasattr(self, "separator"):
            self.separator.setStyleSheet(f"background-color: {profile.border_color}; border: none; margin: 4px 0px;")
        if hasattr(self, "user_name"):
            self.user_name.setText(f"Profil: {getattr(self, 'profile_name', 'default')}<br><span style='color: {profile.color_green}; font-weight: normal; font-size: 11px;'>Forge Local Prête</span>")
            self.user_name.setStyleSheet(f"color: {profile.text_primary}; border: none; font-weight: bold; font-size: 12px;")
        if hasattr(self, "toggle_btn"):
            self.toggle_btn.refresh_theme(profile)
        for item in self._items.values():
            item.refresh_theme(profile)
        if hasattr(self, "settings_btn"):
            self.settings_btn.refresh_theme(profile)
        if hasattr(self, "cards_icon"):
            self.cards_icon.setPixmap(load_phosphor_icon("cards", color=profile.accent_primary).pixmap(20, 20))

    def add_section(self, title: str, items: list[Tuple[str, str, str]]) -> None:
        """Ajoute une section avec un titre, une ligne séparatrice et une liste de (view_id, icon, text)."""
        section_widget = QWidget()
        layout = QVBoxLayout(section_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header_container = QWidget()
        header_container.setFixedHeight(24)
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(12, 0, 0, 0)
        header_layout.setSpacing(0)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        title_lbl = QLabel(title.upper())
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; border: none;")
        title_lbl.setFixedHeight(20)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        sep_line = QFrame()
        sep_line.setFrameShape(QFrame.Shape.HLine)
        sep_line.setStyleSheet(f"background-color: {DesignTokens.BORDER_COLOR}; border: none; margin: 11px 4px;")
        sep_line.setFixedHeight(1)
        sep_line.setVisible(False)

        header_layout.addWidget(title_lbl)
        header_layout.addWidget(sep_line)

        layout.addWidget(header_container)

        for view_id, icon, text in items:
            btn = SidebarItem(view_id, icon, text)
            btn.clicked.connect(lambda checked=False, vid=view_id: self.view_selected.emit(vid))
            self._items[view_id] = btn
            self._button_group.addButton(btn)
            layout.addWidget(btn)

        # Insert before the stretch
        self.sections_layout.insertWidget(self.sections_layout.count() - 1, section_widget)
        section_widget.title_lbl = title_lbl
        section_widget.sep_line = sep_line

    def set_collapsed(self, collapsed: bool) -> None:
        self.is_collapsed = collapsed
        width = DesignTokens.SIDEBAR_WIDTH_COLLAPSED if collapsed else DesignTokens.SIDEBAR_WIDTH_EXPANDED

        # Direct fixed width update (prevents 16ms layout thrashing reflow loop)
        self.setFixedWidth(width)

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
                if widget and hasattr(widget, "title_lbl") and hasattr(widget, "sep_line"):
                    w = cast(Any, widget)
                    w.title_lbl.setVisible(not collapsed)
                    w.sep_line.setVisible(collapsed)

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
        self.setObjectName("TopBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(DesignTokens.TOPBAR_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(16)

        # Fil d'Ariane (Breadcrumb)
        self.breadcrumb_container = QWidget()
        breadcrumb_layout = QHBoxLayout(self.breadcrumb_container)
        breadcrumb_layout.setContentsMargins(0, 0, 0, 0)
        breadcrumb_layout.setSpacing(8)
        breadcrumb_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._current_breadcrumb_icon = "ph.house"
        self.breadcrumb_icon = QLabel()
        self.breadcrumb_icon.setPixmap(load_phosphor_icon(self._current_breadcrumb_icon, color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))
        self.breadcrumb_icon.setStyleSheet("border: none; background: transparent;")

        self.breadcrumb_lbl = QLabel("Tableau de bord")
        self.breadcrumb_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 13px; border: none; background: transparent;")

        breadcrumb_layout.addWidget(self.breadcrumb_icon)
        breadcrumb_layout.addWidget(self.breadcrumb_lbl)
        layout.addWidget(self.breadcrumb_container, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Omnibox
        self.omnibox = GlowLineEdit()
        self.omnibox.setPlaceholderText("Rechercher cartes, paquets ou commandes... (Ctrl+K)")
        self.omnibox.setMaximumWidth(420)
        self.omnibox.installEventFilter(self)
        layout.addWidget(self.omnibox)

        layout.addStretch()

        # Token cost tracker pill (28px compact height, vertically centered)
        self.token_container = QWidget()
        self.token_container.setFixedHeight(28)
        self.token_container.setProperty("card-style", "panel")
        self.token_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        token_layout = QHBoxLayout(self.token_container)
        token_layout.setContentsMargins(8, 0, 10, 0)
        token_layout.setSpacing(6)
        token_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.dollar_icon = QLabel()
        self.dollar_icon.setPixmap(load_phosphor_icon("currency-dollar", color=DesignTokens.COLOR_GREEN).pixmap(14, 14))
        self.dollar_icon.setStyleSheet("border: none; background: transparent;")

        self.token_lbl = QLabel("Dépenses : 0.00 $ (0 tk)")
        self.token_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-family: '{DesignTokens.FONT_CODE}'; font-size: 11px; border: none; background: transparent;")

        token_layout.addWidget(self.dollar_icon)
        token_layout.addWidget(self.token_lbl)

        layout.addWidget(self.token_container, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Daemon Status
        self.daemon_status = DaemonStatusWidget()
        self.daemon_status.set_status("idle", "Daemon en attente")
        layout.addWidget(self.daemon_status, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Notifications
        self.notif_btn = IconButton("bell", tooltip="Notifications", size=24)
        layout.addWidget(self.notif_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj == self.omnibox and event.type() == QEvent.Type.MouseButtonPress:
            self.search_clicked.emit()
            return True
        return super().eventFilter(obj, event)

    def _on_omnibox_click(self, event: QMouseEvent) -> None:
        self.search_clicked.emit()

    def update_breadcrumb(self, text: str, icon_name: str = "ph.folder") -> None:
        self._current_breadcrumb_icon = icon_name
        if hasattr(self, "breadcrumb_lbl"):
            self.breadcrumb_lbl.setText(text)
        if hasattr(self, "breadcrumb_icon"):
            self.breadcrumb_icon.setPixmap(load_phosphor_icon(icon_name, color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))

    def update_daemon_status(self, status: str, text: str) -> None:
        self.daemon_status.set_status(status, text)

    def update_token_tracker(self, cost: str, tokens: str) -> None:
        clean_cost = str(cost).replace("$", "").strip()
        self.token_lbl.setText(f"Dépenses : {clean_cost} $ ({tokens} tk)")

    def refresh_theme(self, profile: Any) -> None:
        if hasattr(self, "breadcrumb_lbl"):
            self.breadcrumb_lbl.setStyleSheet(f"color: {profile.text_primary}; font-weight: 600; font-size: 13px; border: none; background: transparent;")
        if hasattr(self, "breadcrumb_icon"):
            icon_name = getattr(self, "_current_breadcrumb_icon", "ph.folder")
            self.breadcrumb_icon.setPixmap(load_phosphor_icon(icon_name, color=profile.accent_primary).pixmap(16, 16))
        if hasattr(self, "dollar_icon"):
            self.dollar_icon.setPixmap(load_phosphor_icon("currency-dollar", color=profile.color_green).pixmap(14, 14))
        if hasattr(self, "token_lbl"):
            self.token_lbl.setStyleSheet(f"color: {profile.text_secondary}; font-family: '{profile.font_code}'; font-size: 11px; border: none; background: transparent;")
        if hasattr(self, "notif_btn") and hasattr(self.notif_btn, "refresh_theme"):
            self.notif_btn.refresh_theme(profile)
        if hasattr(self, "daemon_status") and hasattr(self.daemon_status, "refresh_theme"):
            self.daemon_status.refresh_theme(profile)


class GlobalTitleBar(QFrame):
    """Barre de titre globale 28px pour macOS drag."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(DesignTokens.GLOBAL_TOPBAR_HEIGHT)

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
    from ankiforge.ui.views.analysis_view import AnalysisView
    from ankiforge.ui.views.consultant_view import ConsultantView
    from ankiforge.ui.views.batch_view import BatchView
    from ankiforge.ui.views.documents_view import DocumentsView
    from ankiforge.ui.views.card_models_view import CardModelsView
    from ankiforge.ui.views.pipelines_view import PipelinesView
    from ankiforge.ui.views.ab_tests_view import ABTestsView

    VIEW_REGISTRY: Dict[str, Tuple[str, str, str, Type[QWidget]]] = {
        # view_id -> (category, icon, title, WidgetClass)
        "dashboard": ("Général", "squares-four", "Tableau de bord", DashboardView),
        "creation": ("Forge & Outils", "magic-wand", "Studio de Création", CreationView),
        "edition": ("Forge & Outils", "cards", "Édition & Navigateur", EditionView),
        "analysis": ("Forge & Outils", "chart-line-up", "Analyse & Audit IA", AnalysisView),
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
        self.setMinimumSize(1200, 720)

        # Dimensionner intelligemment pour occuper l'espace nécessaire sans tronquer l'affichage
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            w = min(1440, int(geom.width() * 0.90))
            h = min(900, int(geom.height() * 0.88))
            self.resize(w, h)
        else:
            self.resize(1380, 860)

        from ankiforge.ui.layouts.base_layout import BaseLayout
        from ankiforge.ui.layouts.layout_manager import LayoutManager

        self._view_widgets: Dict[str, QWidget] = {}
        self._current_view_id: Optional[str] = None
        self._settings_window: Optional[QWidget] = None
        self.current_layout: Optional[BaseLayout] = None
        self.stacked_widget = QStackedWidget()

        # Enregistrement initial des placeholders légers (Lazy Loading)
        for view_id, (_cat, _icon, title, _cls) in self.VIEW_REGISTRY.items():
            placeholder = DummyView(title)
            self.stacked_widget.addWidget(placeholder)
            self._view_widgets[view_id] = placeholder

        # Application du Thème visuel et du Layout actif pour le profil
        from ankiforge.ui.style_engine import get_style_engine

        self.engine = get_style_engine()
        self.engine.theme_changed.connect(self._on_theme_changed)
        saved_theme_id = self.engine.get_saved_theme_id(self.profile_name)
        self.engine.apply_theme(saved_theme_id)

        saved_layout_id = LayoutManager.get_saved_layout_id(self.profile_name)
        self.apply_layout(saved_layout_id)

        self._setup_debug_shortcuts()
        self._setup_global_shortcuts()

    @property
    def sidebar(self) -> Optional[Any]:
        """Propriété de compatibilité pour accéder à la sidebar si présente."""
        if self.current_layout is not None and hasattr(self.current_layout, "sidebar"):
            return self.current_layout.sidebar
        return None

    @property
    def topbar(self) -> Optional[Any]:
        """Propriété de compatibilité pour accéder à la topbar si présente."""
        if self.current_layout is not None and hasattr(self.current_layout, "topbar"):
            return self.current_layout.topbar
        return None

    def apply_layout(self, layout_id: str) -> None:
        """Bascule dynamiquement vers un nouveau layout à chaud (sans redémarrer l'application)."""
        from ankiforge.ui.layouts.layout_manager import LayoutManager

        if self.current_layout is not None:
            try:
                self.current_layout.view_selected.disconnect()
                self.current_layout.settings_requested.disconnect()
                self.current_layout.search_clicked.disconnect()
                self.current_layout.toggle_sidebar_requested.disconnect()
            except Exception:
                pass  # nosec B110

        new_layout = LayoutManager.create_layout(layout_id, profile_name=self.profile_name)
        self.current_layout = new_layout
        new_layout.view_selected.connect(self._on_view_selected)
        new_layout.settings_requested.connect(self._open_settings_modal)
        new_layout.search_clicked.connect(self._open_command_palette)

        new_layout.populate_navigation(self.VIEW_REGISTRY)
        new_layout.set_stacked_widget(self.stacked_widget)
        self.setCentralWidget(new_layout)
        LayoutManager.save_layout_id(self.profile_name, layout_id)
        LayoutManager.apply_theme_for_layout(layout_id)

        if self._current_view_id:
            new_layout.set_active_view(self._current_view_id)
        else:
            self._on_view_selected("dashboard")

    def _setup_debug_shortcuts(self) -> None:
        """Configure les raccourcis de debug (ex: Capture d'écran)."""
        screenshot_shortcut = QShortcut(QKeySequence("Ctrl+F12"), self)
        screenshot_shortcut.activated.connect(self._take_debug_screenshot)

    def _setup_global_shortcuts(self) -> None:
        """Configure les raccourcis clavier universels (Sauvegarde, Exécution, Recherche)."""
        self.shortcut_save = QShortcut(QKeySequence.StandardKey.Save, self)
        self.shortcut_save.activated.connect(self._on_shortcut_save)

        self.shortcut_run = QShortcut(QKeySequence(Qt.Key.Key_Return | Qt.KeyboardModifier.ControlModifier), self)
        self.shortcut_run.activated.connect(self._on_shortcut_run)

        self.shortcut_find = QShortcut(QKeySequence.StandardKey.Find, self)
        self.shortcut_find.activated.connect(self._on_shortcut_find)

    def _on_shortcut_save(self) -> None:
        """Déclenche la sauvegarde sur la vue active si elle le supporte."""
        current_widget = self.stacked_widget.currentWidget()
        if hasattr(current_widget, "_save_card"):
            current_widget._save_card()
        elif hasattr(current_widget, "save"):
            current_widget.save()

    def _on_shortcut_run(self) -> None:
        """Déclenche l'action primaire de la vue active (ex: Générer / Lancer)."""
        current_widget = self.stacked_widget.currentWidget()
        if hasattr(current_widget, "btn_generate_cards") and current_widget.btn_generate_cards.isEnabled():
            current_widget.btn_generate_cards.click()
        elif hasattr(current_widget, "_on_generate_clicked"):
            current_widget._on_generate_clicked()
        elif hasattr(current_widget, "_on_start_batch"):
            current_widget._on_start_batch()

    def _on_shortcut_find(self) -> None:
        """Donne le focus à l'omnibox ou au champ de recherche de la vue active."""
        current_widget = self.stacked_widget.currentWidget()
        if hasattr(current_widget, "search_input"):
            current_widget.search_input.setFocus()
            current_widget.search_input.selectAll()
        elif self.topbar and hasattr(self.topbar, "omnibox"):
            self.topbar.omnibox.setFocus()
            self.topbar.omnibox.selectAll()

    def _take_debug_screenshot(self) -> None:
        """Capture l'état actuel de la fenêtre et le sauvegarde."""
        from ankiforge.utils.paths import get_project_root

        output_dir = get_project_root() / "temp"
        output_dir.mkdir(exist_ok=True)

        output_path = output_dir / "analyse_screenshot.png"
        pixmap = self.grab()
        pixmap.save(str(output_path))
        print(f"[Debug] Capture d'écran de l'UI enregistrée dans : {output_path}")

    def _on_theme_changed(self, profile: Any) -> None:
        """Propagé immédiatement à la sidebar, la topbar et toutes les vues instanciées."""
        if self.sidebar and hasattr(self.sidebar, "refresh_theme"):
            self.sidebar.refresh_theme(profile)
        if self.topbar and hasattr(self.topbar, "refresh_theme"):
            self.topbar.refresh_theme(profile)
        for view_widget in self._view_widgets.values():
            if hasattr(view_widget, "refresh_theme"):
                try:
                    view_widget.refresh_theme(profile)
                except Exception:
                    pass  # nosec B110
        from ankiforge.ui.components.panels import IdePanel

        for panel in self.findChildren(IdePanel):
            if hasattr(panel, "refresh_theme"):
                try:
                    panel.refresh_theme(profile)
                except Exception:
                    pass  # nosec B110

    def _on_view_selected(self, view_id: str, data: Optional[dict] = None) -> None:
        """Navigation: instancie la vue à la demande (Lazy Loading), vérifie dirty state et switch."""
        if self._current_view_id == view_id and not data:
            return

        if self._current_view_id != view_id:
            if not self._can_switch_view():
                # Reset sidebar selection visually if rejected
                if self._current_view_id and self.sidebar:
                    self.sidebar.set_active_view(self._current_view_id)
                return

        # Lazy Instantiation de la vue réelle si c'est encore un DummyView
        if view_id in self.VIEW_REGISTRY:
            cat, icon, title, cls = self.VIEW_REGISTRY[view_id]
            current_widget = self._view_widgets.get(view_id)
            if isinstance(current_widget, DummyView) and cls != DummyView:
                try:
                    real_widget = cast(Any, cls)(ai_manager=self.ai_manager)
                except TypeError:
                    real_widget = cast(Any, cls)()

                if hasattr(real_widget, "request_navigation"):
                    real_widget.request_navigation.connect(self._on_view_selected)

                # Remplacer le placeholder par la vraie vue dans QStackedWidget
                idx = self.stacked_widget.indexOf(current_widget)
                if idx != -1:
                    self.stacked_widget.removeWidget(current_widget)
                    current_widget.deleteLater()
                    self.stacked_widget.insertWidget(idx, real_widget)
                    self._view_widgets[view_id] = real_widget

            if self.topbar and hasattr(self.topbar, "update_breadcrumb"):
                self.topbar.update_breadcrumb(title, icon)

        widget = self._view_widgets.get(view_id)
        if widget:
            self.stacked_widget.setCurrentWidget(widget)
            self._current_view_id = view_id
            if hasattr(self, "current_layout") and self.current_layout:
                self.current_layout.set_active_view(view_id)

            if hasattr(widget, "refresh_data"):
                cast(Any, widget).refresh_data()

            if view_id == "edition" and isinstance(data, dict) and "note_id" in data:
                if hasattr(widget, "select_note_by_id"):
                    cast(Any, widget).select_note_by_id(data["note_id"])

            if view_id == "creation" and isinstance(data, dict) and "prompt" in data:
                if hasattr(widget, "_open_document_tab"):
                    cast(Any, widget)._open_document_tab(title=data.get("title", "Forge IA"), content=data["prompt"])

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
        if self.sidebar:
            self.sidebar.set_collapsed(not self.sidebar.is_collapsed)

    def _open_settings_modal(self) -> None:
        """Ouvre la fenêtre de paramètres non bloquante."""
        if hasattr(self, "_settings_window") and self._settings_window is not None and self._settings_window.isVisible():
            self._settings_window.raise_()
            self._settings_window.activateWindow()
            if self.sidebar and hasattr(self.sidebar, "settings_btn"):
                self.sidebar.settings_btn.setChecked(True)
            return

        from ankiforge.ui.widgets.settings_modal import SettingsModal

        self._settings_window = SettingsModal(ai_manager=self.ai_manager, parent=self)
        self._settings_window.focus_changed.connect(self._on_settings_focus_changed)
        if self.sidebar and hasattr(self.sidebar, "settings_btn"):
            self.sidebar.settings_btn.setChecked(True)
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _on_settings_focus_changed(self, focused: bool) -> None:
        if self.sidebar and hasattr(self.sidebar, "settings_btn"):
            self.sidebar.settings_btn.setChecked(focused)

    def _open_command_palette(self) -> None:
        """Ouvre le CommandPalette (Phase 3). Raccourci: Ctrl/⌘+K."""
        print("Command Palette Requested")

    def closeEvent(self, event) -> None:
        # Close all floating windows
        from ankiforge.ui.components.tabs import _floating_windows

        for fw in list(_floating_windows):
            fw.close()
        super().closeEvent(event)
