"""
Layout macOS (Apple Native Style) pour AnkiForge.
Barre supérieure unifiée (Unified Toolbar), contrôles segmentés arrondis, typographie épurée et affichage pleine largeur.
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
from ankiforge.ui.layouts.base_layout import BaseLayout
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_logo_icon, load_phosphor_icon


class MacosSegmentButton(QPushButton):
    """Bouton pour la barre segmentée de style macOS natif."""

    def __init__(self, view_id: str, icon_name: str, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.view_id = view_id
        self.icon_name = icon_name
        self.title = title

        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(30)
        self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.TEXT_SECONDARY))
        self.setIconSize(QSize(16, 16))
        self.setText(f" {self.title}")
        self.setToolTip(self.title)

        self._update_style(False)
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        if checked:
            self.setIcon(load_phosphor_icon(self.icon_name, color="#ffffff"))
        else:
            self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.TEXT_SECONDARY))
        self._update_style(checked)

    def _update_style(self, checked: bool) -> None:
        if checked:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.ACCENT_PRIMARY};
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    padding: 0 12px;
                    font-size: 12px;
                    font-weight: 600;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {DesignTokens.TEXT_SECONDARY};
                    border: none;
                    border-radius: 6px;
                    padding: 0 12px;
                    font-size: 12px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: rgba(255, 255, 255, 0.06);
                    color: {DesignTokens.TEXT_PRIMARY};
                }}
            """)


class MacosLayout(BaseLayout):
    """
    Layout Concept macOS :
    - Barre supérieure unifiée 54px avec navigation segmentée
    - Zéro barre latérale pour maximiser la largeur de travail
    - Look épuré et minimaliste
    """

    def __init__(self, profile_name: str = "default", parent: Optional[QWidget] = None) -> None:
        super().__init__(profile_name, parent)
        self._nav_buttons: Dict[str, MacosSegmentButton] = {}
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._setup_ui()

    def get_layout_id(self) -> str:
        return "macos"

    def get_display_name(self) -> str:
        return "Concept macOS (Épuré / Barre Supérieure)"

    def get_description(self) -> str:
        return "Barre supérieure unifiée avec sélecteur segmenté horizontal, typographie aérée et vue plein écran."

    def _setup_ui(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Barre unifiée macOS (54px)
        self.top_toolbar = QWidget()
        self.top_toolbar.setFixedHeight(54)
        self.top_toolbar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.top_toolbar.setStyleSheet(f"""
            QWidget {{
                background-color: {DesignTokens.BG_SIDEBAR};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        top_layout = QHBoxLayout(self.top_toolbar)
        top_layout.setContentsMargins(16, 0, 16, 0)
        top_layout.setSpacing(12)

        # Logo & Profil
        logo_label = QLabel()
        logo_label.setPixmap(load_logo_icon(DesignTokens.ACCENT_PRIMARY).pixmap(20, 20))
        logo_label.setStyleSheet("border: none; background: transparent;")

        app_title = QLabel("AnkiForge")
        app_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 14px; border: none; background: transparent;")

        self.profile_badge = QLabel(f"• {self.profile_name}")
        self.profile_badge.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")

        top_layout.addWidget(logo_label)
        top_layout.addWidget(app_title)
        top_layout.addWidget(self.profile_badge)

        # Séparateur vertical discret
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"background-color: {DesignTokens.BORDER_COLOR}; border: none; margin: 14px 4px;")
        sep.setFixedWidth(1)
        top_layout.addWidget(sep)

        # Zone centrale : Barre segmentée dans un conteneur arrondi scrollable si besoin
        self.nav_scroll = QScrollArea()
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setFixedHeight(38)
        self.nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.nav_scroll.setStyleSheet("background: transparent; border: none;")

        self.nav_container = QWidget()
        self.nav_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.nav_container.setStyleSheet(f"""
            QWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        self.nav_layout = QHBoxLayout(self.nav_container)
        self.nav_layout.setContentsMargins(4, 4, 4, 4)
        self.nav_layout.setSpacing(2)

        self.nav_scroll.setWidget(self.nav_container)
        top_layout.addWidget(self.nav_scroll, 1)

        # Actions droites : Search, Token Tracker, Daemon Status, Settings
        self.search_btn = IconButton("magnifying-glass", tooltip="Rechercher (Ctrl+K)", size=22)
        self.search_btn.clicked.connect(self.search_clicked.emit)
        top_layout.addWidget(self.search_btn)

        # Token Tracker compact
        self.token_lbl = QLabel("0.00 $")
        self.token_lbl.setToolTip("Dépenses IA cumulées")
        self.token_lbl.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.COLOR_GREEN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 4px 8px;
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 11px;
                font-weight: 600;
            }}
        """)
        top_layout.addWidget(self.token_lbl)

        # Profile Button
        self.profile_btn = IconButton("user-circle", tooltip=f"Espace de travail : {self.profile_name}", size=22)
        self.profile_btn.clicked.connect(self.profile_switch_requested.emit)
        top_layout.addWidget(self.profile_btn)

        # Settings
        self.settings_btn = IconButton("gear", tooltip="Paramètres", size=22)
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        top_layout.addWidget(self.settings_btn)

        main_layout.addWidget(self.top_toolbar)

        # 2. Zone centrale de contenu
        self.stack_container = QWidget()
        self.stack_layout = QVBoxLayout(self.stack_container)
        self.stack_layout.setContentsMargins(0, 0, 0, 0)
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
        # Nettoyer
        for btn in self._nav_buttons.values():
            self._button_group.removeButton(btn)
            btn.deleteLater()
        self._nav_buttons.clear()

        # Ajouter chaque vue sous forme de bouton segmenté
        for view_id, (_cat, icon, title, _cls) in view_registry.items():
            btn = MacosSegmentButton(view_id, icon, title)
            btn.clicked.connect(lambda checked=False, vid=view_id: self.view_selected.emit(vid, None))
            self._nav_buttons[view_id] = btn
            self._button_group.addButton(btn)
            self.nav_layout.addWidget(btn)

    def update_token_tracker(self, cost: str, tokens: str) -> None:
        clean_cost = str(cost).replace("$", "").strip()
        self.token_lbl.setText(f"{clean_cost} $")
        self.token_lbl.setToolTip(f"Dépenses : {clean_cost} $ ({tokens} jetons)")

    def set_profile_name(self, profile_name: str) -> None:
        super().set_profile_name(profile_name)
        if hasattr(self, "profile_btn") and self.profile_btn:
            self.profile_btn.setToolTip(f"Espace de travail : {profile_name}")
        if hasattr(self, "profile_badge") and self.profile_badge:
            self.profile_badge.setText(f"• {profile_name}")
