"""
Layout Glassmorphism (Moderne / Semi-Translucide) pour AnkiForge.
Design contemporain avec panneaux semi-transparents, bordures lumineuses et esthétique futuriste.
"""

from typing import Dict, Optional, Tuple, Type
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
from ankiforge.ui.components.misc import DaemonStatusWidget
from ankiforge.ui.layouts.base_layout import BaseLayout
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.utils.icon_loader import load_logo_icon, load_phosphor_icon


class GlassTabButton(QPushButton):
    """Bouton style Glassmorphism avec reflets et bordure douce."""

    def __init__(self, view_id: str, icon_name: str, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.view_id = view_id
        self.icon_name = icon_name
        self.title = title

        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(34)
        self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.TEXT_MUTED))
        self.setIconSize(QSize(16, 16))
        self.setText(f" {self.title}")

        self._update_style(False)
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        if checked:
            self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.ACCENT_PRIMARY))
        else:
            self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.TEXT_MUTED))
        self._update_style(checked)

    def _update_style(self, checked: bool) -> None:
        if checked:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    color: {DesignTokens.TEXT_PRIMARY};
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                    padding: 0 14px;
                    font-size: 12px;
                    font-weight: bold;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(255, 255, 255, 0.03);
                    color: {DesignTokens.TEXT_MUTED};
                    border: 1px solid {DesignTokens.BORDER_LIGHT};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                    padding: 0 14px;
                    font-size: 12px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                    border-color: {DesignTokens.BORDER_COLOR};
                    color: {DesignTokens.TEXT_PRIMARY};
                }}
            """)


class GlassmorphismLayout(BaseLayout):
    """
    Layout Concept Glassmorphism :
    - En-tête flottant effet verre dépoli
    - Navigation par pilules translucides
    - Conteneur de travail avec bordure néon douce
    """

    def __init__(self, profile_name: str = "default", parent: Optional[QWidget] = None) -> None:
        super().__init__(profile_name, parent)
        self._nav_buttons: Dict[str, GlassTabButton] = {}
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._setup_ui()

    def get_layout_id(self) -> str:
        return "glassmorphism"

    def get_display_name(self) -> str:
        return "Concept Glassmorphism (Moderne / Translucide)"

    def get_description(self) -> str:
        return "Conteneurs semi-translucides effet verre dépoli, reflets lumineux et boutons arrondis."

    def _setup_ui(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 14)
        main_layout.setSpacing(12)

        # 1. Barre de navigation Glass flottante
        glass_header = QFrame()
        glass_header.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        apply_shadow(glass_header, blur=18, offset_y=3, color="rgba(0, 0, 0, 0.35)")

        header_layout = QHBoxLayout(glass_header)
        header_layout.setContentsMargins(14, 8, 14, 8)
        header_layout.setSpacing(12)

        logo = QLabel()
        logo.setPixmap(load_logo_icon(DesignTokens.ACCENT_PRIMARY).pixmap(22, 22))
        logo.setStyleSheet("border: none; background: transparent;")

        title = QLabel("AnkiForge")
        title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 15px; border: none; background: transparent;")

        header_layout.addWidget(logo)
        header_layout.addWidget(title)

        # ScrollArea pour les pilules
        self.nav_scroll = QScrollArea()
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setFixedHeight(40)
        self.nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.nav_scroll.setStyleSheet("background: transparent; border: none;")

        self.nav_container = QWidget()
        self.nav_container.setStyleSheet("background: transparent; border: none;")
        self.nav_layout = QHBoxLayout(self.nav_container)
        self.nav_layout.setContentsMargins(0, 0, 0, 0)
        self.nav_layout.setSpacing(6)

        self.nav_scroll.setWidget(self.nav_container)
        header_layout.addWidget(self.nav_scroll, 1)

        # Actions
        self.token_lbl = QLabel("0.00 $")
        self.token_lbl.setStyleSheet(f"""
            QLabel {{
                background-color: rgba(16, 185, 129, 0.12);
                color: {DesignTokens.COLOR_GREEN};
                border: 1px solid rgba(16, 185, 129, 0.3);
                border-radius: 8px;
                padding: 4px 8px;
                font-family: {DesignTokens.FONT_CODE};
                font-size: 11px;
                font-weight: bold;
            }}
        """)
        header_layout.addWidget(self.token_lbl)

        self.daemon_status = DaemonStatusWidget()
        self.daemon_status.set_status("idle", "Prêt")
        header_layout.addWidget(self.daemon_status)

        self.search_btn = IconButton("magnifying-glass", tooltip="Rechercher (Ctrl+K)", size=22)
        self.search_btn.clicked.connect(self.search_clicked.emit)
        header_layout.addWidget(self.search_btn)

        self.profile_btn = IconButton("user-circle", tooltip=f"Espace de travail : {self.profile_name}", size=22)
        self.profile_btn.clicked.connect(self.profile_switch_requested.emit)
        header_layout.addWidget(self.profile_btn)

        self.settings_btn = IconButton("gear", tooltip="Paramètres", size=22)
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        header_layout.addWidget(self.settings_btn)

        main_layout.addWidget(glass_header)

        # 2. Conteneur principal Glass
        self.stack_container = QFrame()
        self.stack_container.setStyleSheet("""
            QFrame {
                background-color: rgba(18, 20, 28, 0.75);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }
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

    def populate_navigation(self, view_registry: Dict[str, Tuple[str, str, str, Type[QWidget]]]) -> None:
        for btn in self._nav_buttons.values():
            self._button_group.removeButton(btn)
            btn.deleteLater()
        self._nav_buttons.clear()

        for view_id, (_cat, icon, title, _cls) in view_registry.items():
            btn = GlassTabButton(view_id, icon, title)
            btn.clicked.connect(lambda checked=False, vid=view_id: self.view_selected.emit(vid, None))
            self._nav_buttons[view_id] = btn
            self._button_group.addButton(btn)
            self.nav_layout.addWidget(btn)

    def update_daemon_status(self, status: str, text: str) -> None:
        self.daemon_status.set_status(status, text)

    def update_token_tracker(self, cost: str, tokens: str) -> None:
        clean_cost = str(cost).replace("$", "").strip()
        self.token_lbl.setText(f"{clean_cost} $")

    def set_profile_name(self, profile_name: str) -> None:
        super().set_profile_name(profile_name)
        if hasattr(self, "profile_btn") and self.profile_btn:
            self.profile_btn.setToolTip(f"Espace de travail : {profile_name}")
