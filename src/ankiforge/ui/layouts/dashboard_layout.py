"""
Layout Dashboard (Portail Moderne & Cartes) pour AnkiForge.
Disposition aérée centrée sur les flux de travail avec barre de navigation élégante et conteneur façon carte.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.buttons import IconButton
from ankiforge.ui.layouts.base_layout import BaseLayout
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_logo_icon, load_phosphor_icon


class DashboardTabButton(QPushButton):
    """Bouton d'onglet pour le Dashboard Layout."""

    def __init__(self, view_id: str, icon_name: str, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.view_id = view_id
        self.icon_name = icon_name
        self.title = title

        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(34)
        self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.TEXT_SECONDARY))
        self.setIconSize(QSize(18, 18))
        self.setText(f" {self.title}")

        self._update_style(False)
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        if checked:
            self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.ACCENT_PRIMARY))
        else:
            self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.TEXT_SECONDARY))
        self._update_style(checked)

    def _update_style(self, checked: bool) -> None:
        if checked:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    color: {DesignTokens.ACCENT_PRIMARY};
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: 8px;
                    padding: 0 14px;
                    font-size: 12px;
                    font-weight: bold;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_PANEL};
                    color: {DesignTokens.TEXT_SECONDARY};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 8px;
                    padding: 0 14px;
                    font-size: 12px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                    color: {DesignTokens.TEXT_PRIMARY};
                    border-color: rgba(255, 255, 255, 0.2);
                }}
            """)


class DashboardLayout(BaseLayout):
    """
    Layout Concept Dashboard :
    - En-tête aéré avec marque, recherche, télémétrie et barre d'onglets façon cartes
    - Zone de contenu stylisée
    """

    def __init__(self, profile_name: str = "default", parent: QWidget | None = None) -> None:
        super().__init__(profile_name, parent)
        self._nav_buttons: dict[str, DashboardTabButton] = {}
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._setup_ui()

    def get_layout_id(self) -> str:
        return "dashboard"

    def get_display_name(self) -> str:
        return "Concept Dashboard (Portail Moderne & Cartes)"

    def get_description(self) -> str:
        return "Disposition spacieuse avec en-tête horizontal élégant et navigation par cartes de modules."

    def _setup_ui(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 16)
        main_layout.setSpacing(12)

        # 1. Header Bar
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)

        logo = QLabel()
        logo.setPixmap(load_logo_icon(DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        logo.setStyleSheet("border: none; background: transparent;")

        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title_lbl = QLabel("AnkiForge Portal")
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 15px; font-weight: bold;")
        self.profile_lbl = QLabel(f"Espace de travail : {self.profile_name}")
        self.profile_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        self.profile_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.profile_lbl.setToolTip("Cliquez pour changer d'espace de travail")
        self.profile_lbl.mousePressEvent = lambda event: self.profile_switch_requested.emit()
        title_box.addWidget(title_lbl)
        title_box.addWidget(self.profile_lbl)

        header_layout.addWidget(logo)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        # Token Tracker & Status
        self.token_lbl = QLabel("🪙 0.00 $")
        self.token_lbl.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.COLOR_GREEN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 10px;
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 12px;
                font-weight: bold;
            }}
        """)
        header_layout.addWidget(self.token_lbl)

        self.search_btn = IconButton("magnifying-glass", tooltip="Rechercher (Ctrl+K)", size=24)
        self.search_btn.clicked.connect(self.search_clicked.emit)
        header_layout.addWidget(self.search_btn)

        self.profile_btn = IconButton("user-circle", tooltip=f"Espace : {self.profile_name}", size=24)
        self.profile_btn.clicked.connect(self.profile_switch_requested.emit)
        header_layout.addWidget(self.profile_btn)

        self.settings_btn = IconButton("gear", tooltip="Paramètres", size=24)
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        header_layout.addWidget(self.settings_btn)

        main_layout.addWidget(header)

        # 2. Navigation bar (onglets en cartes)
        self.nav_scroll = QScrollArea()
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setFixedHeight(44)
        self.nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.nav_scroll.setStyleSheet("background: transparent; border: none;")

        self.nav_container = QWidget()
        self.nav_layout = QHBoxLayout(self.nav_container)
        self.nav_layout.setContentsMargins(0, 0, 0, 0)
        self.nav_layout.setSpacing(8)

        self.nav_scroll.setWidget(self.nav_container)
        main_layout.addWidget(self.nav_scroll)

        # 3. Conteneur principal
        self.stack_container = QFrame()
        self.stack_container.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        self.stack_layout = QVBoxLayout(self.stack_container)
        self.stack_layout.setContentsMargins(4, 4, 4, 4)
        self.stack_layout.setSpacing(0)

        main_layout.addWidget(self.stack_container, 1)

    def set_stacked_widget(self, stacked_widget: QStackedWidget) -> None:
        self.stacked_widget = stacked_widget
        while self.stack_layout.count():
            item = self.stack_layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.setParent(None)
        self.stack_layout.addWidget(stacked_widget)

    def set_active_view(self, view_id: str) -> None:
        self._current_view_id = view_id
        btn = self._nav_buttons.get(view_id)
        if btn:
            btn.setChecked(True)

    def populate_navigation(self, view_registry: dict[str, tuple[str, str, str, type[QWidget]]]) -> None:
        for btn in self._nav_buttons.values():
            self._button_group.removeButton(btn)
            btn.deleteLater()
        self._nav_buttons.clear()

        for view_id, (_cat, icon, title, _cls) in view_registry.items():
            btn = DashboardTabButton(view_id, icon, title)
            btn.clicked.connect(lambda checked=False, vid=view_id: self.view_selected.emit(vid, None))
            self._nav_buttons[view_id] = btn
            self._button_group.addButton(btn)
            self.nav_layout.addWidget(btn)

    def update_token_tracker(self, cost: str, tokens: str) -> None:
        clean_cost = str(cost).replace("$", "").strip()
        self.token_lbl.setText(f"🪙 {clean_cost} $")

    def set_profile_name(self, profile_name: str) -> None:
        super().set_profile_name(profile_name)
        if hasattr(self, "profile_lbl") and self.profile_lbl:
            self.profile_lbl.setText(f"Espace de travail : {profile_name}")
        if hasattr(self, "profile_btn") and self.profile_btn:
            self.profile_btn.setToolTip(f"Espace : {profile_name}")
