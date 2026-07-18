from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut, QMouseEvent
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QDockWidget, QLabel, QScrollArea, QFrame, QMessageBox, QPushButton

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.components import StyledLineEdit, IconButton, DaemonStatusWidget, UserAvatar
from ankiforge.ui.views.dashboard_view import DashboardView
from ankiforge.ui.views.creation_view import CreationTab as CreationView
from ankiforge.ui.views.edition_view import EditionTab as EditionView
from ankiforge.ui.views.consultant_view import ConsultantTab as ConsultantView
from ankiforge.ui.views.batch_view import BatchTab as BatchView
from ankiforge.ui.views.documents_view import DocumentsTab as DocumentsView
from ankiforge.ui.views.models_view import ModelsTab as ModelsView
from ankiforge.ui.views.agents_view import AgentsTab as AgentsView
from ankiforge.ui.views.pipelines_view import PipelinesView
from ankiforge.ui.views.ab_test_view import ABTestTab as ABTestView


class Sidebar(QWidget):
    """Sidebar collapsible 260px ↔ 68px."""

    view_selected = Signal(str)
    settings_requested = Signal()
    toggle_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(DesignTokens.SIDEBAR_WIDTH_EXPANDED)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_SIDEBAR}; border-right: 1px solid {DesignTokens.BORDER_COLOR};")

        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        self.layout_main.setSpacing(0)

        # Header (Logo + Toggle)
        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 16, 16, 16)
        logo = QLabel("ankiforge_obsidian")
        logo.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 16px;")
        toggle_btn = IconButton("≡", size=24)  # Placeholder for toggle
        toggle_btn.clicked.connect(self.toggle_requested.emit)
        header_layout.addWidget(logo)
        header_layout.addStretch()
        header_layout.addWidget(toggle_btn)
        self.layout_main.addWidget(header)

        # Scroll Area for sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        self.content_layout.setSpacing(16)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.content_widget)
        self.layout_main.addWidget(scroll, stretch=1)

        # Footer
        footer = QFrame()
        footer_layout = QHBoxLayout(footer)
        footer.setStyleSheet(f"border-top: 1px solid {DesignTokens.BORDER_COLOR};")
        settings_btn = IconButton("⚙", size=32)
        settings_btn.clicked.connect(self.settings_requested.emit)
        user_avatar = UserAvatar("TR")
        footer_layout.addWidget(settings_btn)
        footer_layout.addStretch()
        footer_layout.addWidget(user_avatar)
        self.layout_main.addWidget(footer)

        self._buttons: dict[str, IconButton] = {}

    def add_section(self, title: str, items: list[tuple[str, str, str]]) -> None:
        """items: (view_id, icon_name, title)"""
        if self.content_layout.count() > 0:
            self.content_layout.addSpacing(20)

        lbl = QLabel(title.upper())
        lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.content_layout.addWidget(lbl)

        for view_id, icon_name, item_title in items:
            btn = QPushButton(f"{icon_name}  {item_title}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    text-align: left;
                    padding-left: 20px;
                    border: none;
                    background: transparent;
                    color: {DesignTokens.TEXT_SECONDARY};
                    font-weight: 500;
                    border-radius: {DesignTokens.RADIUS_SM}px;
                }}
                QPushButton:hover {{
                    background: {DesignTokens.BG_HOVER};
                    color: {DesignTokens.TEXT_PRIMARY};
                }}
            """)
            btn.setFixedHeight(40)
            btn.clicked.connect(lambda checked=False, vid=view_id: self.view_selected.emit(vid))
            self.content_layout.addWidget(btn)
            self._buttons[view_id] = btn

    def set_active_view(self, view_id: str) -> None:
        for vid, btn in self._buttons.items():
            if vid == view_id:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        text-align: left;
                        padding-left: 20px;
                        border: none;
                        background: {DesignTokens.BG_ACTIVE};
                        color: {DesignTokens.ACCENT_PRIMARY};
                        font-weight: 600;
                        border-radius: {DesignTokens.RADIUS_SM}px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        text-align: left;
                        padding-left: 20px;
                        border: none;
                        background: transparent;
                        color: {DesignTokens.TEXT_SECONDARY};
                        font-weight: 500;
                        border-radius: {DesignTokens.RADIUS_SM}px;
                    }}
                    QPushButton:hover {{
                        background: {DesignTokens.BG_HOVER};
                        color: {DesignTokens.TEXT_PRIMARY};
                    }}
                """)


class TopBar(QWidget):
    """Barre supérieure 60px : omnibox + actions daemon/tokens/notifications."""

    search_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(DesignTokens.TOPBAR_HEIGHT)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)

        self.omnibox = StyledLineEdit()
        self.omnibox.setPlaceholderText("Rechercher ou lancer une commande (Ctrl+K)...")
        self.omnibox.setFixedWidth(400)
        self.omnibox.mousePressEvent = self._on_omnibox_clicked
        self.omnibox.setReadOnly(True)

        self.daemon_status = DaemonStatusWidget()
        self.token_lbl = QLabel("0 tokens - $0.00")
        self.token_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")

        bell_btn = IconButton("🔔", size=32)

        layout.addWidget(self.omnibox)
        layout.addStretch()
        layout.addWidget(self.daemon_status)
        layout.addWidget(self.token_lbl)
        layout.addWidget(bell_btn)

    def _on_omnibox_clicked(self, event: QMouseEvent):
        self.search_clicked.emit()

    def update_daemon_status(self, status: str, text: str) -> None:
        self.daemon_status.set_status(status, text)


class GlobalTopBar(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(DesignTokens.GLOBAL_TOPBAR_HEIGHT)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("ankiforge_obsidian")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px;")
        layout.addWidget(title)


class MainWindow(QMainWindow):
    """Fenêtre principale ankiforge_obsidian."""

    def __init__(self, ai_manager: Any) -> None:
        super().__init__()
        self.ai_manager = ai_manager

        try:
            from ankiforge.services.background_daemon import BackgroundDaemon

            self.daemon = BackgroundDaemon()
        except ModuleNotFoundError:
            from ankiforge.services.background_daemon import BackgroundDaemon

            self.daemon = BackgroundDaemon()

        self.daemon.start()

        self.setWindowTitle(self.tr("ankiforge_obsidian - AI Flashcard Generator"))
        self.resize(1200, 850)

        self.view_registry: dict[str, Any] = {}
        self.current_view_id = ""

        self._setup_ui()
        self._setup_views()
        self._setup_shortcuts()

    def _setup_ui(self) -> None:
        self.setDockNestingEnabled(True)

        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.global_topbar = GlobalTopBar()
        main_layout.addWidget(self.global_topbar)

        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.view_selected.connect(self._on_view_selected)
        self.sidebar.settings_requested.connect(self._open_settings_modal)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.topbar = TopBar()
        self.topbar.search_clicked.connect(self._open_command_palette)

        self.dock_manager = QMainWindow()
        self.dock_manager.setWindowFlags(Qt.WindowType.Widget)
        self.dock_manager.setDockNestingEnabled(True)
        dummy = QWidget()
        dummy.setStyleSheet("background: transparent;")
        self.dock_manager.setCentralWidget(dummy)

        content_layout.addWidget(self.topbar)
        content_layout.addWidget(self.dock_manager, stretch=1)

        body_layout.addWidget(self.sidebar)
        body_layout.addWidget(content_widget, stretch=1)

        main_layout.addWidget(body_widget, stretch=1)
        self.setCentralWidget(central_widget)

    def _setup_views(self) -> None:
        VIEWS = [
            ("dashboard", "Général", "■", "Tableau de bord", DashboardView(self.ai_manager)),
            ("creation", "Forge & Outils", "✨", "Studio de Création", CreationView(self.ai_manager)),
            ("edition", "Forge & Outils", "📝", "Édition / Analyse", EditionView()),
            ("consultant", "Forge & Outils", "🤖", "AI Consultant", ConsultantView(self.ai_manager)),
            ("batch", "Forge & Outils", "🏭", "Batch Factory", BatchView(self.ai_manager)),
            ("documents", "Bibliothèque", "📄", "My Documents", DocumentsView()),
            ("card-models", "Bibliothèque", "🎨", "Card Models", ModelsView()),
            ("agents", "Laboratoire IA", "🧠", "Éditeur d'Agents", AgentsView()),
            ("pipelines", "Laboratoire IA", "🔗", "Pipelines", PipelinesView()),
            ("ab-tests", "Laboratoire IA", "⚖", "Tests A/B", ABTestView()),
        ]

        sections: dict[str, list] = {}
        for view_id, cat, icon, title, widget in VIEWS:
            if cat not in sections:
                sections[cat] = []
            sections[cat].append((view_id, icon, title))
            self._register_view(view_id, title, widget)

        for cat, items in sections.items():
            self.sidebar.add_section(cat, items)

        if VIEWS:
            self._on_view_selected(VIEWS[0][0])

    def _register_view(self, view_id: str, title: str, widget: QWidget) -> None:
        dock = QDockWidget(title, self.dock_manager)
        dock.setObjectName(f"dock_{view_id}")
        dock.setWidget(widget)

        dock.setStyleSheet(f"""
            QDockWidget {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                border: none;
            }}
        """)

        title_bar = QWidget()
        title_bar.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL};")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(10, 4, 10, 4)

        lbl = QLabel(title)
        lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 12px;")
        title_layout.addWidget(lbl)
        title_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background: transparent;
                color: {DesignTokens.TEXT_MUTED};
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
                background: {DesignTokens.BG_HOVER};
                border-radius: 4px;
            }}
        """)
        close_btn.clicked.connect(dock.hide)
        title_layout.addWidget(close_btn)

        dock.setTitleBarWidget(title_bar)

        self.dock_manager.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        if hasattr(self, "_last_dock"):
            self.dock_manager.tabifyDockWidget(self._last_dock, dock)
        self._last_dock: Any = dock

        self.view_registry[view_id] = {"dock": dock, "widget": widget}
        dock.hide()

    @Slot(str)
    def _on_view_selected(self, view_id: str) -> None:
        if view_id == self.current_view_id:
            dock = self.view_registry[view_id]["dock"]
            if not dock.isVisible():
                dock.show()
            dock.raise_()
            return

        if not self._can_switch_view():
            return

        self.current_view_id = view_id
        dock = self.view_registry[view_id]["dock"]
        if not dock.isVisible():
            dock.show()
        dock.raise_()
        self.sidebar.set_active_view(view_id)

        widget = self.view_registry[view_id]["widget"]
        refresh_method = getattr(widget, "refresh_data", None)
        if callable(refresh_method):
            refresh_method()

    def _can_switch_view(self) -> bool:
        if not self.current_view_id:
            return True
        current_widget = self.view_registry[self.current_view_id]["widget"]
        if hasattr(current_widget, "is_dirty") and current_widget.is_dirty():
            reply = QMessageBox.question(
                self,
                self.tr("Données non sauvegardées"),
                self.tr("Voulez-vous vraiment quitter cet onglet et perdre vos données ?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                if hasattr(current_widget, "reset_unsaved_state"):
                    current_widget.reset_unsaved_state()
                return True
            return False
        return True

    def _setup_shortcuts(self) -> None:
        self.shortcut_search = QShortcut(QKeySequence("Ctrl+K"), self)
        self.shortcut_search.activated.connect(self._open_command_palette)

    def _open_settings_modal(self) -> None:
        pass  # Placeholder Phase 3

    def _open_command_palette(self) -> None:
        pass  # Placeholder Phase 3
