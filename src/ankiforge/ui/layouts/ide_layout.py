"""
Layout IDE (JetBrains / Power-User style) pour AnkiForge.
Sidebar latérale sombre rétractable (260px <-> 68px), Topbar avec Omnibox et zone centrale pour QStackedWidget.
"""

from typing import Dict, List, Optional, Tuple, Type
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.layouts.base_layout import BaseLayout


class IdeLayout(BaseLayout):
    """
    Layout Concept IDE :
    - Sidebar latérale gauche rétractable
    - TopBar avec Omnibox, Token Tracker et Daemon Status
    - Zone centrale pour le QStackedWidget
    """

    def __init__(self, profile_name: str = "default", parent: Optional[QWidget] = None) -> None:
        super().__init__(profile_name, parent)
        self._setup_ui()

    def get_layout_id(self) -> str:
        return "ide"

    def get_display_name(self) -> str:
        return "Concept IDE (JetBrains / Power-User)"

    def get_description(self) -> str:
        return "Barre latérale sombre rétractable, recherche globale Omnibox et panneaux modulaires."

    def _setup_ui(self) -> None:
        from ankiforge.ui.components.sidebar import Sidebar
        from ankiforge.ui.components.topbar import TopBar

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. TopBar (Pleine largeur avec section marque/logo synchronisée avec la Sidebar)
        self.topbar = TopBar()
        self.topbar.search_clicked.connect(self.search_clicked.emit)
        self.topbar.import_clicked.connect(self.import_requested.emit)
        self.topbar.export_clicked.connect(self.export_requested.emit)
        self.topbar.notif_clicked.connect(self.notif_requested.emit)
        self.topbar.toggle_requested.connect(self._toggle_sidebar)
        main_layout.addWidget(self.topbar)

        # 2. Zone inférieure : Sidebar à gauche + Content/StackedWidget à droite
        self.bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(self.bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar(profile_name=self.profile_name)
        self.sidebar.toggle_requested.connect(self._toggle_sidebar)
        self.sidebar.view_selected.connect(lambda vid: self.view_selected.emit(vid, None))
        self.sidebar.settings_requested.connect(self.settings_requested.emit)
        self.sidebar.profile_switch_requested.connect(self.profile_switch_requested.emit)

        # Raccorder les références pour compatibilité rétroactive
        self.sidebar.toggle_btn = self.topbar.toggle_btn
        self.sidebar.logo_icon = self.topbar.logo_icon

        bottom_layout.addWidget(self.sidebar)

        # Conteneur pour le stacked widget
        self.stack_container = QWidget()
        self.stack_layout = QVBoxLayout(self.stack_container)
        self.stack_layout.setContentsMargins(0, 0, 0, 0)
        self.stack_layout.setSpacing(0)
        bottom_layout.addWidget(self.stack_container, 1)

        main_layout.addWidget(self.bottom_widget, 1)

    def _toggle_sidebar(self) -> None:
        collapsed = not self.sidebar.is_collapsed
        self.sidebar.set_collapsed(collapsed)
        self.topbar.set_collapsed(collapsed)
        self.toggle_sidebar_requested.emit()

    def set_stacked_widget(self, stacked_widget: QStackedWidget) -> None:
        self.stacked_widget = stacked_widget
        # Nettoyer l'ancien widget s'il y en a un
        while self.stack_layout.count():
            item = self.stack_layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.setParent(None)
        self.stack_layout.addWidget(stacked_widget)

    def set_active_view(self, view_id: str) -> None:
        self._current_view_id = view_id
        self.sidebar.set_active_view(view_id)

    def populate_navigation(self, view_registry: Dict[str, Tuple[str, str, str, Type[QWidget]]]) -> None:
        categories: Dict[str, List[Tuple[str, str, str]]] = {}
        for view_id, (cat, icon, title, _cls) in view_registry.items():
            if cat not in categories:
                categories[cat] = []
            categories[cat].append((view_id, icon, title))

        for cat, items in categories.items():
            self.sidebar.add_section(cat, items)

    def update_token_tracker(self, cost: str, tokens: str) -> None:
        self.topbar.update_token_tracker(cost, tokens)

    def set_profile_name(self, profile_name: str) -> None:
        super().set_profile_name(profile_name)
        if hasattr(self, "sidebar") and self.sidebar:
            self.sidebar.set_profile_name(profile_name)
