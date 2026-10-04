"""
Moteur de Style Centralisé (StyleEngine) pour AnkiForge.
Génère et applique dynamiquement les règles QSS sémantiques basées sur les sélecteurs de propriétés Qt.
"""

import contextlib
import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from ankiforge.ui.style_engine.appearance import (
    AppearancePreference,
    ModeSource,
    add_system_mode_listener,
    notify_system_mode_changed,
    probe_system_mode_source,
)
from ankiforge.ui.style_engine.theme_profile import ThemeProfile
from ankiforge.ui.style_engine.themes import (
    BUILTIN_THEMES,
    JETBRAINS_DARK,
    ThemeFamily,
    get_family_for_theme,
    get_theme_families,
    get_unique_builtin_themes,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.paths import get_resource_path

logger = logging.getLogger(__name__)


class StyleEngine(QObject):
    """
    Moteur de style centralisé singleton.
    Gère la compilation du QSS sémantique et le hot-reloading de l'interface.
    """

    theme_changed = Signal(ThemeProfile)
    system_mode_changed = Signal(object)

    # Clés d'apparence persistées par profil (cf. ADR 0004)
    KEY_THEME_FAMILY = "theme_family"
    KEY_MODE_SOURCE = "mode_source"
    KEY_LAST_MANUAL_MODE = "last_manual_mode"
    KEY_LEGACY_THEME_ID = "theme_id"

    _instance: "StyleEngine | None" = None

    def __init__(self) -> None:
        super().__init__()
        self._current_theme: ThemeProfile = JETBRAINS_DARK
        self._custom_themes: dict[str, ThemeProfile] = {}
        self._custom_families: dict[str, ThemeFamily] = {}
        self._active_profile_name: str | None = None
        self._active_layout_id: str | None = None
        self._system_listener_connected: bool = False
        add_system_mode_listener(self._on_system_mode_notified)
        self._ensure_system_theme_listener()
        self.load_theme_library()

    @classmethod
    def instance(cls) -> "StyleEngine":
        if cls._instance is None:
            cls._instance = StyleEngine()
        return cls._instance

    @property
    def current_theme(self) -> ThemeProfile:
        return self._current_theme

    def register_theme(self, theme: ThemeProfile) -> None:
        """Enregistre un thème personnalisé (ex: issu d'un Addon)."""
        self._custom_themes[theme.id] = theme

    def get_theme(self, theme_id: str) -> ThemeProfile:
        """Récupère un profil de thème par son identifiant avec repli sur le thème par défaut."""
        if theme_id in self._custom_themes:
            return self._custom_themes[theme_id]
        return BUILTIN_THEMES.get(theme_id, JETBRAINS_DARK)

    def get_available_themes(self, mode: str | None = None) -> list[ThemeProfile]:
        """Renvoie la liste de tous les thèmes disponibles, optionnellement filtrée par 'dark' ou 'light'."""
        all_themes = get_unique_builtin_themes()
        all_themes.extend(self._custom_themes.values())
        if mode == "dark":
            return [t for t in all_themes if t.is_dark]
        elif mode == "light":
            return [t for t in all_themes if not t.is_dark]
        return all_themes

    def generate_stylesheet(self, theme: ThemeProfile | None = None) -> str:
        """
        Compile la feuille de style globale complète à partir d'un ThemeProfile.
        Définit tous les sélecteurs sémantiques pour éliminer le CSS codé en dur dans les composants.
        """
        p = theme or self._current_theme
        green_bg = p.color_green_bg or "rgba(16, 185, 129, 0.15)"
        green_text = p.color_green_text or p.color_green
        green_border = p.color_green_border or p.color_green
        red_bg = p.color_red_bg or "rgba(239, 68, 68, 0.15)"
        red_text = p.color_red_text or p.color_red
        red_border = p.color_red_border or p.color_red
        yellow_bg = p.color_yellow_bg or "rgba(245, 158, 11, 0.15)"
        yellow_text = p.color_yellow_text or p.color_yellow
        yellow_border = p.color_yellow_border or p.color_yellow

        check_icon_path = str(get_resource_path("src", "ressources", "icons", "check_white.svg")).replace("\\", "/")
        dash_icon_path = str(get_resource_path("src", "ressources", "icons", "dash_white.svg")).replace("\\", "/")

        return f"""
        /* --- Base & Conteneurs --- */
        QWidget {{
            font-family: "{p.font_main}";
            font-size: {p.font_size_base}px;
            color: {p.text_primary};
        }}

        QMainWindow, QDialog, QStackedWidget {{
            background-color: {p.bg_main};
        }}

        /* --- Boutons Sémantiques (QPushButton) --- */
        QPushButton {{
            font-family: "{p.font_main}";
            font-size: {p.font_size_base}px;
            font-weight: 500;
            border-radius: {p.radius_sm}px;
            padding: 8px 16px;
            border: 1px solid {p.border_color};
            border-top: 1px solid {p.border_light};
            background-color: {p.bg_input};
            color: {p.text_primary};
        }}
        QPushButton:hover {{
            background-color: {p.bg_hover};
            border: 1px solid {p.accent_primary};
        }}
        QPushButton:disabled {{
            background-color: {p.bg_hover};
            color: {p.text_muted};
            border-color: {p.border_color};
        }}

        /* Role: Primary Button */
        QPushButton[role="primary"] {{
            background-color: {p.accent_primary};
            color: #ffffff;
            font-weight: 600;
            border: 1px solid {p.accent_primary};
            border-top: 1px solid rgba(255, 255, 255, 0.35);
            border-bottom: 2px solid rgba(0, 0, 0, 0.35);
        }}
        QPushButton[role="primary"]:hover {{
            background-color: {p.accent_hover};
            border: 1.5px solid #ffffff;
        }}
        QPushButton[role="primary"]:focus {{
            border: 2px solid #ffffff;
            background-color: {p.accent_hover};
        }}
        QPushButton[role="primary"]:pressed {{
            background-color: {p.accent_hover};
            border: 2px solid #ffffff;
            border-bottom: 1px solid rgba(0, 0, 0, 0.2);
            padding-top: 9px;
        }}
        QPushButton[role="primary"]:disabled {{
            background-color: {p.bg_hover};
            color: {p.text_muted};
            border-color: {p.border_color};
        }}

        /* Role: Secondary Button */
        QPushButton[role="secondary"] {{
            background-color: {p.bg_input};
            color: {p.text_primary};
            border: 1px solid {p.border_color};
            border-top: 1px solid {p.border_light};
        }}
        QPushButton[role="secondary"]:hover {{
            background-color: {p.bg_hover};
            border: 1.5px solid {p.accent_primary};
            color: {p.text_primary};
        }}
        QPushButton[role="secondary"]:focus {{
            border: 2px solid {p.border_focus};
            background-color: {p.bg_panel};
            color: {p.text_primary};
        }}
        QPushButton[role="secondary"]:pressed {{
            background-color: {p.bg_active};
            border: 2px solid {p.border_focus};
            padding-top: 9px;
        }}
        QPushButton[role="secondary"]:disabled {{
            background-color: {p.bg_input};
            color: {p.text_muted};
            border-color: {p.border_color};
        }}

        /* Role: Danger Button */
        QPushButton[role="danger"] {{
            background-color: rgba(239, 68, 68, 0.14);
            color: {p.color_red};
            border: 1px solid rgba(239, 68, 68, 0.3);
            border-top: 1px solid rgba(239, 68, 68, 0.5);
            font-weight: 600;
        }}
        QPushButton[role="danger"]:hover {{
            background-color: rgba(239, 68, 68, 0.28);
            border: 1.5px solid {p.color_red};
        }}
        QPushButton[role="danger"]:focus {{
            border: 2px solid {p.color_red};
            background-color: rgba(239, 68, 68, 0.22);
        }}
        QPushButton[role="danger"]:pressed {{
            background-color: rgba(239, 68, 68, 0.40);
            border: 2px solid {p.color_red};
            padding-top: 9px;
        }}

        /* Role: Ghost / Icon Button */
        QPushButton[role="ghost"] {{
            background-color: transparent;
            border: none;
            padding: 4px 8px;
            color: {p.text_secondary};
        }}
        QPushButton[role="ghost"]:hover {{
            background-color: {p.bg_hover};
            color: {p.text_primary};
        }}
        QPushButton[role="icon"] {{
            background-color: {p.bg_input};
            border: 1px solid {p.border_color};
            border-top: 1px solid {p.border_light};
            border-radius: {p.radius_sm}px;
            padding: 2px;
            color: {p.text_secondary};
        }}
        QPushButton[role="icon"]:hover {{
            background-color: {p.bg_hover};
            border: 1.5px solid {p.accent_primary};
            color: {p.text_primary};
        }}
        QPushButton[role="icon"]:focus {{
            border: 2px solid {p.accent_primary};
            background-color: {p.bg_panel};
        }}
        QPushButton[role="icon"]:pressed {{
            background-color: {p.bg_active};
            border: 2px solid {p.accent_primary};
            padding-top: 3px;
        }}

        /* Density: Compacte — boutons inline (pieds de carte, barres d'outils) */
        QPushButton[density="compact"] {{
            font-size: {p.font_size_sm}px;
            padding: 2px 12px;
        }}
        QPushButton[density="compact"]:pressed {{
            padding-top: 3px;
        }}

        /* --- Champs de Saisie & Formulaires --- */
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{
            background-color: {p.bg_input};
            border: 1px solid {p.border_color};
            border-top: 1px solid {p.border_light};
            border-radius: {p.radius_sm}px;
            color: {p.text_primary};
            padding: 6px 10px;
            selection-background-color: {p.accent_primary};
            selection-color: #ffffff;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
            border: 1.5px solid {p.accent_primary};
            background-color: {p.bg_panel};
        }}
        QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled {{
            background-color: {p.bg_main};
            color: {p.text_muted};
            border-color: {p.border_light};
        }}

        /* GlowLineEdit / Omnibox / Search inputs */
        GlowLineEdit, QLineEdit[role="search"] {{
            background-color: {p.bg_input};
            border: 1px solid {p.border_color};
            border-top: 1px solid {p.border_light};
            border-radius: {p.radius_sm}px;
            color: {p.text_primary};
            padding: 4px 10px;
            font-size: 12px;
        }}
        GlowLineEdit:hover, QLineEdit[role="search"]:hover {{
            border: 1.5px solid {p.accent_primary};
            background-color: {p.bg_hover};
            color: {p.text_primary};
        }}
        GlowLineEdit:focus, QLineEdit[role="search"]:focus {{
            border: 2px solid {p.accent_primary};
            background-color: {p.bg_panel};
            color: {p.text_primary};
        }}

        /* BranchKpiWidget A/B */
        BranchKpiWidget {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            border-radius: 8px;
            padding: 4px;
        }}
        BranchKpiWidget QLabel {{
            background: transparent;
        }}

        /* --- JetBrains IDE Tabs (TabButton, ScrollableTabBarWidget, IdeTabBar) --- */
        TabButton {{
            background-color: transparent;
            color: {p.text_secondary};
            border: none;
            border-right: 1px solid {p.border_color};
            border-top: 2px solid transparent;
            padding: 0 14px;
            font-family: "{p.font_main}";
            font-size: {p.font_size_base}px;
            text-align: left;
        }}
        TabButton[closable="true"] {{
            padding-right: 28px;
        }}
        TabButton:hover {{
            color: {p.text_primary};
            background-color: {p.bg_hover};
        }}
        TabButton:checked {{
            background-color: {p.bg_panel};
            color: {p.text_primary};
            border-top: 2px solid {p.accent_primary};
            border-right: 1px solid {p.border_color};
            font-weight: bold;
        }}
        TabButton[variant="document"] {{
            background-color: transparent;
            color: {p.text_secondary};
            border: none;
            border-right: 1px solid {p.border_color};
            border-bottom: 1px solid {p.border_color};
            border-top: 2px solid transparent;
            border-top-left-radius: {p.radius_sm}px;
            border-top-right-radius: {p.radius_sm}px;
            padding: 0 12px;
        }}
        TabButton[variant="document"][closable="true"] {{
            padding-right: 28px;
        }}
        TabButton[variant="document"]:hover {{
            color: {p.text_primary};
            background-color: {p.bg_hover};
        }}
        TabButton[variant="document"]:checked {{
            background-color: {p.bg_panel};
            color: {p.text_primary};
            border-bottom: 1px solid {p.bg_panel};
            border-top: 2px solid {p.accent_primary};
            border-right: 1px solid {p.border_color};
            font-weight: bold;
        }}

        /* PillTabBar */
        PillTabBar {{
            background-color: {p.bg_input};
            border-radius: {p.radius_sm}px;
        }}
        PillTabBar QPushButton {{
            background: transparent;
            color: {p.text_muted};
            border: none;
            border-radius: {p.radius_sm - 2}px;
            padding: 4px 12px;
            font-size: 12px;
            font-weight: 500;
        }}
        PillTabBar QPushButton:hover {{
            color: {p.text_primary};
        }}
        PillTabBar QPushButton:checked {{
            background-color: {p.bg_panel};
            color: {p.text_primary};
            font-weight: bold;
        }}

        /* UnderlineTabBar */
        UnderlineTabBar {{
            background: transparent;
            border-bottom: 1px solid {p.border_color};
        }}
        UnderlineTabBar QPushButton {{
            background: transparent;
            color: {p.text_muted};
            border: none;
            border-bottom: 2px solid transparent;
            padding: 6px 14px;
            font-size: 13px;
        }}
        UnderlineTabBar QPushButton:hover {{
            color: {p.text_primary};
        }}
        UnderlineTabBar QPushButton:checked {{
            color: {p.accent_primary};
            border-bottom: 2px solid {p.accent_primary};
            font-weight: bold;
        }}

        /* --- Dashboard Components --- */
        DashboardHeroBanner {{
            background-color: {p.bg_active};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_lg}px;
        }}
        DashboardActionButton {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_md}px;
        }}
        DashboardActionButton:hover {{
            background-color: {p.bg_hover};
            border: 1px solid {p.accent_primary};
        }}
        ActivityItem {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_sm}px;
        }}
        ActivityItem:hover {{
            background-color: {p.bg_hover};
            border-color: {p.accent_primary};
        }}
        DashboardDropZone {{
            background-color: {p.bg_panel};
            border: 2px dashed {p.border_color};
            border-radius: {p.radius_md}px;
        }}
        DashboardDropZone:hover {{
            border: 2px dashed {p.accent_primary};
            background-color: {p.bg_hover};
        }}
        StatItem {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_sm}px;
        }}

        /* ComboBox Dropdown */
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 24px;
            border-left: none;
        }}
        QComboBox QAbstractItemView {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_sm}px;
            color: {p.text_primary};
            selection-background-color: {p.bg_hover};
            selection-color: {p.accent_primary};
            padding: 4px;
        }}

        /* --- Panneaux & Cartes Sémantiques (QFrame) --- */
        QFrame[card-style="panel"], IdePanel, GlassPanel, RoundedPanel {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_md}px;
        }}
        QFrame[card-style="glass"] {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_md}px;
        }}
        QFrame[card-style="elevated"] {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_lg}px;
        }}

        /* En-tête des panneaux IDE */
        IdePanel > QFrame#header, QFrame#IdePanelHeader {{
            background-color: {p.bg_sidebar};
            border: none;
            border-bottom: 1px solid {p.border_color};
        }}

        /* Cartes Métriques et CI/CD */
        CicdMetricCard, MetricCard, StatCard, TemplateCard {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_md}px;
        }}
        CicdMetricCard:hover, TemplateCard:hover {{
            background-color: {p.bg_hover};
            border-color: {p.border_focus};
        }}

        /* Terminal CI/CD et Inspecteurs */
        CicdTerminal, ModelInspector {{
            background-color: {p.bg_input};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_sm}px;
            color: {p.text_primary};
        }}

        /* Barre Latérale et Barre Supérieure */
        Sidebar, QWidget#Sidebar {{
            background-color: {p.bg_sidebar};
            border-right: 1px solid {p.border_color};
        }}
        SidebarItem, SidebarProfileItem, QPushButton#SidebarUserBtn, MCPStatusWidget, QPushButton#SidebarMCPBtn {{
            background-color: transparent;
            color: {p.text_secondary};
            border: none;
            border-radius: {p.radius_sm}px;
            text-align: left;
            padding-left: 12px;
            font-size: {p.font_size_base}px;
        }}
        SidebarItem:hover, SidebarProfileItem:hover, QPushButton#SidebarUserBtn:hover, MCPStatusWidget:hover, QPushButton#SidebarMCPBtn:hover {{
            background-color: {p.bg_hover};
            color: {p.text_primary};
        }}
        SidebarItem:checked, SidebarProfileItem:checked, MCPStatusWidget:checked, QPushButton#SidebarMCPBtn:checked {{
            background-color: {p.bg_active};
            color: {p.accent_primary};
            font-weight: bold;
        }}
        SidebarItem:pressed, SidebarProfileItem:pressed, QPushButton#SidebarUserBtn:pressed, MCPStatusWidget:pressed, QPushButton#SidebarMCPBtn:pressed {{
            background-color: {p.bg_active};
        }}
        MCPStatusWidget[status="error"], QPushButton#SidebarMCPBtn[status="error"] {{
            color: {red_text};
        }}
        MCPStatusWidget[status="mutating"], QPushButton#SidebarMCPBtn[status="mutating"] {{
            color: {yellow_text};
        }}

        /* --- Sidebar sub-elements --- */
        QLabel#SidebarLogoText {{
            color: {p.text_primary};
            font-weight: bold;
            font-size: 16px;
            border: none;
        }}
        QWidget#SidebarHeader {{
            border-bottom: 1px solid {p.border_color};
            background-color: transparent;
        }}
        QWidget#SidebarFooter {{
            border-top: 1px solid {p.border_color};
            background-color: transparent;
        }}
        QFrame#SidebarSeparator {{
            background-color: {p.border_color};
            border: none;
            margin: 4px 0px;
        }}
        QLabel#SidebarSectionTitle {{
            color: {p.text_muted};
            font-size: 11px;
            font-weight: bold;
            border: none;
        }}
        QFrame#SidebarSectionSep {{
            background-color: {p.border_color};
            border: none;
            margin: 11px 4px;
        }}
        QLabel#SidebarUserName {{
            color: {p.text_primary};
            border: none;
            font-weight: 500;
            font-size: 12px;
            background: transparent;
        }}
        QLabel#SidebarCardsIcon, QLabel#SidebarSwitchIcon {{
            border: none;
            background: transparent;
        }}

        /* --- NavBadgeButton : pastille de travail en cours sur la navigation --- */
        /* Teintes dérivées (§1.0) : lues sur DesignTokens, car `color_yellow_bg` /
           `color_yellow_text` / `color_yellow_border` sont calculées par
           `apply_theme_profile` et non stockées sur le profil brut. */
        QLabel#NavBadge {{
            background-color: {DesignTokens.COLOR_YELLOW_BG};
            color: {DesignTokens.COLOR_YELLOW_TEXT};
            border: 1px solid {DesignTokens.COLOR_YELLOW_BORDER};
            font-size: 9px;
            font-weight: bold;
            border-radius: {p.radius_sm}px;
        }}

        /* --- TopBar & sub-elements --- */
        TopBar, QWidget#TopBar {{
            background-color: {p.bg_sidebar};
            border-bottom: 1px solid {p.border_color};
        }}
        QWidget#TopBarBrand {{
            background-color: transparent;
            border-right: 1px solid {p.border_color};
        }}
        QWidget#TopBarContent {{
            background-color: transparent;
        }}
        QLabel#TopBarBreadcrumbLabel {{
            color: {p.text_primary};
            font-weight: 600;
            font-size: 13px;
            border: none;
            background: transparent;
        }}
        QLabel#TopBarBreadcrumbIcon {{
            border: none;
            background: transparent;
        }}
        QFrame#TopBarTokenTracker, QWidget#TopBarTokenTracker {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_sm}px;
        }}
        QLabel#TopBarTokenLabel {{
            color: {p.text_secondary};
            font-family: '{p.font_code}';
            font-size: 11px;
            border: none;
            background: transparent;
        }}
        QLabel#TopBarDollarIcon {{
            border: none;
            background: transparent;
        }}
        QLabel#TopBarNotifBadge {{
            background-color: {p.color_red};
            color: #ffffff;
            font-size: 10px;
            font-weight: bold;
            border-radius: 9px;
            border: none;
        }}

        /* --- NotificationMenuPopup --- */
        NotificationMenuPopup, QFrame#NotificationMenuPopup {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_md}px;
        }}

        /* --- GlobalTitleBar --- */
        GlobalTitleBar, QFrame#GlobalTitleBar {{
            background-color: {p.bg_main};
        }}
        QLabel#GlobalTitleBarLabel {{
            color: {p.text_muted};
            font-size: 11px;
        }}

        /* Zone de défilement générique */
        QScrollArea {{
            background-color: transparent;
            border: none;
        }}

        /* --- Onglets (QTabWidget, QTabBar, TabButton) --- */
        QTabWidget::pane {{
            border: 1px solid {p.border_color};
            background-color: {p.bg_main};
            border-radius: {p.radius_sm}px;
        }}
        QTabBar::tab {{
            background-color: {p.bg_input};
            color: {p.text_secondary};
            padding: 6px 14px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            font-size: 11px;
            font-weight: 500;
        }}
        QTabBar::tab:hover {{
            color: {p.text_primary};
            background-color: {p.bg_hover};
        }}
        QTabBar::tab:selected {{
            background-color: {p.bg_main};
            color: {p.accent_primary};
            border-bottom: 2px solid {p.accent_primary};
            font-weight: bold;
        }}

        /* --- Tableaux & Grilles (QTableWidget, QTableView) --- */
        QTableWidget, QTableView {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            gridline-color: {p.border_color};
            color: {p.text_primary};
            border-radius: {p.radius_sm}px;
            selection-background-color: {p.bg_hover};
            selection-color: {p.text_primary};
        }}
        QHeaderView::section {{
            background-color: {p.bg_sidebar};
            color: {p.text_muted};
            font-size: {p.font_size_sm}px;
            font-weight: bold;
            text-transform: uppercase;
            padding: 6px 12px;
            border: none;
            border-bottom: 1px solid {p.border_color};
        }}
        QTableView::item {{
            padding: 8px 12px;
            border: none;
        }}
        QTableView::item:hover {{
            background-color: {p.bg_hover};
        }}
        QTableView::item:selected {{
            background-color: {p.bg_active};
            color: {p.text_primary};
        }}

        /* --- Barres de Défilement (QScrollBar) --- */
        QScrollBar:vertical {{
            border: none;
            background: transparent;
            width: 10px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background-color: {p.border_color};
            min-height: 24px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {p.text_muted};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QScrollBar:horizontal {{
            border: none;
            background: transparent;
            height: 10px;
            margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background-color: {p.border_color};
            min-width: 24px;
            border-radius: 5px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background-color: {p.text_muted};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
        }}

        /* --- Arborescences & Listes (QTreeWidget, QListWidget, QListView, QTreeView) --- */
        QTreeWidget, QListWidget, QListView, QTreeView {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_sm}px;
            color: {p.text_primary};
            padding: 4px;
            outline: none;
        }}
        QTreeWidget::item, QListWidget::item, QListView::item, QTreeView::item {{
            padding: 6px 8px;
            border-radius: 4px;
            color: {p.text_primary};
        }}
        QTreeWidget::item:hover, QListWidget::item:hover, QListView::item:hover, QTreeView::item:hover {{
            background-color: {p.bg_hover};
        }}
        QTreeWidget::item:selected, QListWidget::item:selected, QListView::item:selected, QTreeView::item:selected {{
            background-color: {p.bg_active};
            color: {p.text_primary};
        }}

        /* --- Cases à cocher & Boutons Radio --- */
        QCheckBox, QRadioButton {{
            color: {p.text_primary};
            spacing: 8px;
        }}
        QCheckBox:disabled, QRadioButton:disabled {{
            color: {p.text_muted};
        }}
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 16px;
            height: 16px;
            border: 1px solid {p.border_color};
            border-radius: 4px;
            background-color: {p.bg_input};
        }}
        QRadioButton::indicator {{
            border-radius: 8px;
        }}
        QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
            border-color: {p.accent_primary};
        }}
        QCheckBox::indicator:checked {{
            background-color: {p.accent_primary};
            border-color: {p.accent_primary};
            image: url({check_icon_path});
        }}
        QCheckBox::indicator:indeterminate {{
            background-color: {p.accent_primary};
            border-color: {p.accent_primary};
            image: url({dash_icon_path});
        }}
        QRadioButton::indicator:checked {{
            background-color: {p.accent_primary};
            border-color: {p.accent_primary};
        }}

        /* --- Sliders --- */
        QSlider::groove:horizontal {{
            height: 6px;
            background-color: {p.bg_input};
            border-radius: 3px;
        }}
        QSlider::sub-page:horizontal {{
            background-color: {p.accent_primary};
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background-color: #ffffff;
            border: 2px solid {p.accent_primary};
            width: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{
            background-color: {p.accent_hover};
        }}

        /* --- Zones de Défilement & Barres d'état --- */
        QScrollArea {{
            border: none;
            background-color: transparent;
        }}
        QStatusBar {{
            background-color: {p.bg_sidebar};
            color: {p.text_muted};
            border-top: 1px solid {p.border_color};
        }}
        /* --- MCPStatusWidget & #MCPStatusBadge --- */
        #MCPStatusBadge {{
            border-radius: 10px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: 500;
            background-color: {p.bg_input};
            color: {p.text_muted};
            border: 1px solid {p.border_color};
        }}
        #MCPStatusBadge[status="running"] {{
            background-color: {green_bg};
            color: {green_text};
            border: 1px solid {green_border};
        }}
        #MCPStatusBadge[status="stopped"] {{
            background-color: {p.bg_input};
            color: {p.text_muted};
            border: 1px solid {p.border_color};
        }}
        #MCPStatusBadge[status="error"] {{
            background-color: {red_bg};
            color: {red_text};
            border: 1px solid {red_border};
        }}
        #MCPStatusBadge[status="mutating"] {{
            background-color: {yellow_bg};
            color: {yellow_text};
            border: 1px solid {yellow_border};
        }}
        #MCPStatusBadge:hover {{
            border-color: {p.border_focus};
        }}
        QToolBar {{
            background-color: {p.bg_panel};
            border-bottom: 1px solid {p.border_color};
            spacing: 6px;
            padding: 4px;
        }}

        /* --- GroupBox --- */
        QGroupBox {{
            border: 1px solid {p.border_color};
            border-radius: {p.radius_md}px;
            margin-top: 12px;
            padding-top: 14px;
            font-weight: bold;
            color: {p.text_primary};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0 4px;
            color: {p.text_muted};
        }}

        /* --- Splitters --- */
        QSplitter::handle:horizontal {{
            background-color: transparent;
            width: 6px;
        }}
        QSplitter::handle:horizontal:hover {{
            background-color: {p.accent_primary};
        }}
        QSplitter::handle:vertical {{
            background-color: transparent;
            height: 6px;
        }}
        QSplitter::handle:vertical:hover {{
            background-color: {p.accent_primary};
        }}

        /* --- Menus & Tooltips --- */
        QMenu {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            padding: 6px;
            border-radius: {p.radius_sm}px;
        }}
        QMenu::item {{
            padding: 6px 24px 6px 20px;
            border-radius: 4px;
            color: {p.text_primary};
        }}
        QMenu::item:selected {{
            background-color: {p.bg_hover};
            color: {p.accent_primary};
        }}
        QToolTip {{
            background-color: {p.bg_panel};
            color: {p.text_primary};
            border: 1px solid {p.border_color};
            border-radius: 4px;
            padding: 4px 8px;
            font-size: {p.font_size_sm}px;
        }}

        /* --- Barres de Progression --- */
        QProgressBar {{
            background-color: {p.bg_input};
            border: none;
            border-radius: 4px;
            max-height: 8px;
            text-align: center;
            color: transparent;
        }}
        QProgressBar::chunk {{
            background-color: {p.accent_primary};
            border-radius: 4px;
        }}

        /* --- Consultant IA View & Chat Components --- */
        ConsultantSessionSidebar, QFrame#ConsultantSessionSidebar {{
            background-color: {p.bg_sidebar};
        }}
        SessionItemWidget, QFrame#SessionItemWidget {{
            background-color: transparent;
            border-radius: {p.radius_sm}px;
            padding: 4px;
        }}
        SessionItemWidget:hover, QFrame#SessionItemWidget:hover {{
            background-color: {p.bg_hover};
        }}
        SessionItemWidget[active="true"], QFrame#SessionItemWidget[active="true"] {{
            background-color: {p.bg_input};
            border-left: 2px solid {p.accent_primary};
        }}

        ContextHubWidget, QFrame#ContextHubWidget {{
            background-color: {p.bg_panel};
            border: none;
        }}
        ContextAssetCard, QFrame#ContextAssetCard {{
            background-color: {p.bg_input};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_sm}px;
        }}
        ContextAssetCard:hover, QFrame#ContextAssetCard:hover {{
            border-color: {p.accent_primary};
        }}

        InlineDiffCardWidget, QFrame#InlineDiffCardWidget {{
            background-color: {p.bg_input};
            border: 1px solid {p.accent_primary};
            border-radius: {p.radius_md}px;
        }}
        FieldDiffWidget, QFrame#FieldDiffWidget {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_sm}px;
        }}
        SplitCardItemWidget, QFrame#SplitCardItemWidget {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_sm}px;
        }}

        ChatMessageWidget, QFrame#ChatMessageWidget {{
            background-color: transparent;
        }}
        ThoughtStepWidget, QFrame#ThoughtStepWidget {{
            background-color: {p.bg_input};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_sm}px;
        }}
        ToolCallWidget, QFrame#ToolCallWidget {{
            background-color: {p.bg_input};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_sm}px;
        }}

        /* --- Reasoning Viewer (CoT) Modal --- */
        ReasoningViewerDialog, QDialog#ReasoningViewerDialog {{
            background-color: {p.bg_main};
        }}

        /* --- LLM Discovery & Model Selector Modal --- */
        ModelCardWidget, QFrame#ModelCard {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_md}px;
        }}
        ModelCardWidget:hover, QFrame#ModelCard:hover {{
            border-color: {p.accent_primary};
            background-color: {p.bg_hover};
        }}
        ModelCardWidget[current="true"], QFrame#ModelCard[current="true"] {{
            border: 1.5px solid {p.color_green};
            background-color: {p.color_green_bg};
        }}
        ModelCardWidget[current="true"]:hover, QFrame#ModelCard[current="true"]:hover {{
            border-color: {p.color_green};
            background-color: {p.color_green_bg};
        }}
        QFrame#ModelCardUseCase {{
            background-color: {p.bg_input};
            border: 1px solid {p.border_light};
            border-radius: {p.radius_sm}px;
        }}
        QFrame#FilterCard {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_md}px;
        }}
        QFrame#ComparePane {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            border-top: 2px solid {p.accent_primary};
            border-radius: {p.radius_md}px;
        }}
        QFrame#CompareModelColumn {{
            background-color: {p.bg_input};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_sm}px;
        }}
        FilterChipButton {{
            background-color: {p.bg_input};
            color: {p.text_secondary};
            border: 1px solid {p.border_color};
            border-radius: 9999px;
            font-size: 11px;
            font-weight: 500;
            padding: 3px 10px;
        }}
        FilterChipButton:hover {{
            background-color: {p.bg_hover};
            color: {p.text_primary};
            border-color: {p.accent_primary};
        }}
        FilterChipButton:focus {{
            border-color: {p.accent_primary};
            outline: none;
        }}
        FilterChipButton:checked {{
            background-color: {p.accent_bg};
            color: {p.accent_primary};
            border: 1px solid {p.accent_primary};
            font-weight: 600;
        }}
        FilterChipButton:disabled {{
            background-color: {p.bg_main};
            color: {p.text_muted};
            border-color: {p.border_color};
        }}

        /* --- Sélecteur de Dispositions & Miniatures (LayoutGridSelector) --- */
        LayoutThumbnailCard, QFrame#LayoutThumbnailCard {{
            background-color: {p.bg_panel};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_md}px;
        }}
        LayoutThumbnailCard:hover, QFrame#LayoutThumbnailCard:hover {{
            border: 1px solid {p.accent_hover};
        }}
        LayoutThumbnailCard:focus, QFrame#LayoutThumbnailCard:focus {{
            border: 2px solid {p.accent_primary};
        }}
        LayoutThumbnailCard[selected="true"], QFrame#LayoutThumbnailCard[selected="true"] {{
            border: 2px solid {p.accent_primary};
            background-color: {p.bg_panel};
        }}
        QFrame#LayoutCardPreview {{
            border-top-left-radius: {p.radius_md}px;
            border-top-right-radius: {p.radius_md}px;
        }}

        /* --- Composants à décorants QPainter (thème-aware) ---
           Widgets qui dessinent en QPainter (paintEvent / QtCharts) et doivent
           consommer les DesignTokens pour rester conformes en clair et sombre :
           DonutChartWidget, RetentionCurveCanvas, ScopeRangeBarWidget,
           ProgressTableCellWidget, ImageOcclusionEditor, ActivityChartWidget. */
        QChartView, DonutChartWidget {{
            background: transparent;
        }}
        QChartView QLabel, DonutChartWidget QLabel {{
            background: transparent;
            color: {p.text_primary};
        }}

        /* --- Inspecteur de Document : cartes liées cliquables (LinkedNoteCard) --- */
        QFrame#LinkedNoteCard {{
            background-color: {p.bg_input};
            border: 1px solid {p.border_color};
            border-radius: {p.radius_md}px;
            padding: 10px;
        }}
        QFrame#LinkedNoteCard:hover {{
            background-color: {p.bg_hover};
            border: 1px solid {p.accent_primary};
        }}
        QFrame#LinkedNoteCard:focus {{
            border: 1px solid {p.accent_primary};
        }}

        /* --- Compatibilité Vision du moteur sélectionné (VisionCapabilityNotice) --- */
        QLabel#visionCapNotice {{
            background-color: {red_bg};
            border: 1px solid {red_border};
            border-radius: {p.radius_sm}px;
            color: {red_text};
            font-size: {p.font_size_sm}px;
            padding: 4px 8px;
        }}
        """

    def apply_theme(self, theme_or_id: str | ThemeProfile, app: QApplication | None = None) -> None:
        """
        Applique un thème à l'ensemble de l'application en mettant à jour DesignTokens, QPalette et QSS.
        """
        profile = self.get_theme(theme_or_id) if isinstance(theme_or_id, str) else theme_or_id

        self._current_theme = profile

        # Mettre à jour DesignTokens
        DesignTokens.apply_theme_profile(profile)

        application = app or QApplication.instance()
        if isinstance(application, QApplication):
            # Palette Qt
            palette = QPalette()
            palette.setColor(QPalette.ColorRole.Window, QColor(profile.bg_main))
            palette.setColor(QPalette.ColorRole.WindowText, QColor(profile.text_primary))
            palette.setColor(QPalette.ColorRole.Base, QColor(profile.bg_input))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(profile.bg_panel))
            palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(profile.bg_panel))
            palette.setColor(QPalette.ColorRole.ToolTipText, QColor(profile.text_primary))
            palette.setColor(QPalette.ColorRole.Text, QColor(profile.text_primary))
            palette.setColor(QPalette.ColorRole.Button, QColor(profile.bg_panel))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor(profile.text_primary))
            palette.setColor(QPalette.ColorRole.BrightText, QColor(profile.color_red))
            palette.setColor(QPalette.ColorRole.Link, QColor(profile.accent_primary))
            palette.setColor(QPalette.ColorRole.Highlight, QColor(profile.accent_primary))
            palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
            application.setPalette(palette)

            # Application de la police système par défaut pour éliminer les fallbacks lents ("Sans Serif")
            app_font = QFont(profile.font_main, profile.font_size_base)
            application.setFont(app_font)

            # Global QSS
            application.setStyleSheet(self.generate_stylesheet(profile))

            # Re-polish global de tous les widgets existants
            self.force_global_repolish(application)

        self.theme_changed.emit(profile)

    def force_global_repolish(self, app: QApplication | None = None) -> None:
        """
        Force le dé-polissage et re-polissage de tous les widgets actifs pour
        appliquer immédiatement la nouvelle feuille de style QSS sans redémarrage.
        Invoque également refresh_theme(profile) sur tous les widgets le supportant.
        """
        application = app or QApplication.instance()
        if isinstance(application, QApplication):
            style = application.style()
            profile = self._current_theme
            for widget in application.allWidgets():
                try:
                    if hasattr(widget, "refresh_theme") and callable(widget.refresh_theme):
                        try:
                            widget.refresh_theme(profile)
                        except TypeError:
                            with contextlib.suppress(TypeError, RuntimeError):
                                widget.refresh_theme()
                        except (RuntimeError, AttributeError) as err:
                            logger.debug("Échec rafraîchissement thème du widget %s : %s", widget, err)
                    style.unpolish(widget)
                    style.polish(widget)
                    widget.update()
                except RuntimeError as err:
                    logger.debug("Widget Qt détruit pendant la propagation de style : %s", err)

    def clear_custom_library(self) -> None:
        """Vide le registre en mémoire des familles et thèmes personnalisés."""
        self._custom_families.clear()
        self._custom_themes.clear()

    def load_theme_library(self, themes_dir: Path | None = None) -> list[ThemeFamily]:
        """Scanne le répertoire global de la bibliothèque de thèmes (~/.ankiforge/themes/)
        et peuple les registres mémoire de familles et de thèmes personnalisés."""
        from ankiforge.ui.style_engine.theme_storage import load_custom_theme_families

        self.clear_custom_library()
        custom_families = load_custom_theme_families(themes_dir=themes_dir)
        for fam in custom_families:
            self.register_theme_family(fam)
        return list(self._custom_families.values())

    def register_theme_family(self, family: ThemeFamily) -> None:
        """Enregistre une famille de thème personnalisée et ses deux variantes."""
        self._custom_families[family.id] = family
        self.register_theme(family.dark_theme)
        self.register_theme(family.light_theme)

    def import_theme(self, source_path: Path | str, themes_dir: Path | None = None) -> tuple[ThemeFamily, Path]:
        """Importe un fichier de thème dans la bibliothèque sur disque et l'enregistre en mémoire."""
        from ankiforge.ui.style_engine.theme_storage import import_theme_file

        family, saved_path = import_theme_file(source_path, themes_dir=themes_dir)
        self.register_theme_family(family)
        return family, saved_path

    def export_theme(self, family_or_id: ThemeFamily | str, target_path: Path | str) -> Path:
        """Exporte une famille de thème vers un fichier JSON externe."""
        from ankiforge.ui.style_engine.theme_storage import export_theme_file

        if isinstance(family_or_id, str):
            family = self.get_family_for_theme(family_or_id)
            if family is None:
                raise LookupError(f"Famille de thème introuvable pour l'export : {family_or_id}")
        else:
            family = family_or_id

        return export_theme_file(family, target_path)

    def get_theme_families(self) -> list[ThemeFamily]:
        """Retourne la liste des familles de thèmes (12 intégrées + familles de la bibliothèque sur disque)."""
        families = list(get_theme_families())
        families.extend(self._custom_families.values())
        return families

    def get_family_for_theme(self, theme_id: str) -> ThemeFamily | None:
        """Retrouve la famille d'un thème (personnalisé ou intégré)."""
        theme_id_clean = theme_id.lower().strip()
        if theme_id_clean in self._custom_families:
            return self._custom_families[theme_id_clean]
        for fam in self._custom_families.values():
            if fam.dark_theme.id == theme_id_clean or fam.light_theme.id == theme_id_clean:
                return fam
        return get_family_for_theme(theme_id)

    def set_color_mode(self, mode: str, app: QApplication | None = None) -> ThemeProfile:
        """Bascule le régime de la famille active — calculé par les deux axes, sans persistance."""
        return self._apply_manual_mode(ModeSource.coerce(mode, default=ModeSource.DARK), app=app)

    def toggle_color_mode(self, app: QApplication | None = None) -> ThemeProfile:
        """Bascule entre Sombre et Clair pour la famille active — sans persistance."""
        return self._apply_manual_mode(ModeSource.LIGHT if self._current_theme.is_dark else ModeSource.DARK, app=app)

    def _apply_manual_mode(self, source: ModeSource, app: QApplication | None = None) -> ThemeProfile:
        """Calcule la Variante par les deux axes : famille du thème courant × régime demandé."""
        family = self.get_family_for_theme(self._current_theme.id)
        preference = AppearancePreference(family_id=family.id if family is not None else None, mode_source=source, last_manual_mode=source)
        return self.apply_appearance(preference, app=app)

    # ── Les deux axes d'apparence : Famille de Thème × Source du Mode (ADR 0004) ──────────

    def preference_from_theme_id(self, theme_id: str) -> AppearancePreference:
        """Interprète un identifiant de Variante comme une préférence à deux axes.

        Sert à lire les préférences écrites avant le refactoring, où un scalaire unique
        portait à la fois l'identité graphique et le régime visuel.
        """
        family = self.get_family_for_theme(theme_id)
        regime = ModeSource.DARK if self.get_theme(theme_id).is_dark else ModeSource.LIGHT
        return AppearancePreference(family_id=family.id if family is not None else None, mode_source=regime, last_manual_mode=regime)

    def save_appearance_preference(self, profile_name: str, preference: AppearancePreference) -> AppearancePreference:
        """Persiste les deux axes d'apparence du profil (BDD SQLite + QSettings) et renvoie la préférence écrite.

        `AppearancePreference` est déjà normalisé à la construction : il est persisté tel quel.
        """
        try:
            from ankiforge.database.models import SettingModel

            SettingModel.set_value(f"profiles/{profile_name}/{self.KEY_THEME_FAMILY}", preference.family_id or "", category="appearance")
            SettingModel.set_value(f"profiles/{profile_name}/{self.KEY_MODE_SOURCE}", preference.mode_source.value, category="appearance")
            SettingModel.set_value(f"profiles/{profile_name}/{self.KEY_LAST_MANUAL_MODE}", preference.last_manual_mode.value, category="appearance")
        except Exception as err:
            logger.debug("Sauvegarde de l'apparence en BDD ignorée : %s", err)

        from ankiforge.utils.environment import get_app_qsettings

        settings = get_app_qsettings("obsidian")
        settings.setValue(f"profiles/{profile_name}/{self.KEY_THEME_FAMILY}", preference.family_id or "")
        settings.setValue(f"profiles/{profile_name}/{self.KEY_MODE_SOURCE}", preference.mode_source.value)
        settings.setValue(f"profiles/{profile_name}/{self.KEY_LAST_MANUAL_MODE}", preference.last_manual_mode.value)
        return preference

    def get_appearance_preference(self, profile_name: str) -> AppearancePreference:
        """Lit les deux axes d'apparence du profil, en normalisant la lecture héritée.

        Si aucun axe n'est persisté, l'ancien identifiant de thème unique est interprété :
        la Famille en est déduite et la Source du Mode dérivée de son régime. Cette lecture
        reste sans migration — ``SettingModel`` est un magasin clé/valeur sans schéma à faire
        évoluer, et la normalisation rattrape les profils écrits par les versions antérieures.
        """
        family_id = self._read_appearance_key(profile_name, self.KEY_THEME_FAMILY)
        mode_source = self._read_appearance_key(profile_name, self.KEY_MODE_SOURCE)
        last_manual_mode = self._read_appearance_key(profile_name, self.KEY_LAST_MANUAL_MODE)

        if family_id is None and mode_source is None and last_manual_mode is None:
            legacy_theme_id = self._read_appearance_key(profile_name, self.KEY_LEGACY_THEME_ID)
            if legacy_theme_id:
                return self.preference_from_theme_id(legacy_theme_id)

        return AppearancePreference(
            family_id=family_id or None,
            mode_source=ModeSource.coerce(mode_source, default=ModeSource.DARK),
            last_manual_mode=ModeSource.coerce(last_manual_mode, default=ModeSource.DARK),
        )

    def _read_appearance_key(self, profile_name: str, key: str) -> str | None:
        """Lit une clé d'apparence depuis la BDD SQLite, puis depuis le QSettings scopé « obsidian »."""
        full_key = f"profiles/{profile_name}/{key}"
        try:
            from ankiforge.database.models import SettingModel

            value = self._clean_appearance_value(SettingModel.get_value(full_key))
            if value is not None:
                return value
        except Exception as err:
            logger.debug("Lecture de l'apparence en BDD ignorée : %s", err)

        from ankiforge.utils.environment import get_app_qsettings

        return self._clean_appearance_value(get_app_qsettings("obsidian").value(full_key, ""))

    @staticmethod
    def _clean_appearance_value(value: object) -> str | None:
        """Normalise une valeur stockée : une chaîne vide est l'absence de choix, pas un choix."""
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def get_default_family_for_layout(self, layout_id: str | None) -> ThemeFamily:
        """Famille de repli d'un layout : n'est utilisée que si aucune Famille n'a été choisie."""
        from ankiforge.ui.layouts.layout_manager import LayoutManager

        family = self.get_family_for_theme(LayoutManager.get_default_family_id(layout_id or LayoutManager.DEFAULT_LAYOUT_ID))
        if family is None:  # pragma: no cover - la table layout→famille référence toujours des familles réelles
            fallback = self.get_family_for_theme(LayoutManager.DEFAULT_FAMILY_ID)
            if fallback is None:  # pragma: no cover - garde-fou : aucune famille ne peut disparaître
                raise LookupError("Aucune famille de thème disponible")
            return fallback
        return family

    def _ensure_system_theme_listener(self) -> None:
        """Attache le signal colorSchemeChanged de Qt sans timer de scrutation."""
        if self._system_listener_connected:
            return
        try:
            from PySide6.QtGui import QGuiApplication

            app = QGuiApplication.instance()
            if app is None:
                return
            hints = QGuiApplication.styleHints()
            if hasattr(hints, "colorSchemeChanged"):
                hints.colorSchemeChanged.connect(self._on_qt_color_scheme_changed)
                self._system_listener_connected = True
        except (AttributeError, RuntimeError) as err:
            logger.debug("Impossible d'attacher le signal colorSchemeChanged : %s", err)

    def _on_qt_color_scheme_changed(self, _scheme: object = None) -> None:
        """Callback réactif au signal Qt colorSchemeChanged — sans timer de scrutation."""
        notify_system_mode_changed(probe_system_mode_source())

    def _on_system_mode_notified(self, regime: ModeSource | None) -> None:
        """Reçoit la notification de changement de régime système et répercute si ModeSource.SYSTEM."""
        self.system_mode_changed.emit(regime)
        self._handle_system_regime_change(regime)

    def _handle_system_regime_change(self, _regime: ModeSource | None) -> None:
        from ankiforge.utils.paths import get_active_profile

        profile_name = self._active_profile_name or get_active_profile()
        preference = self.get_appearance_preference(profile_name)
        if preference.mode_source is ModeSource.SYSTEM:
            from ankiforge.ui.layouts.layout_manager import LayoutManager

            layout_id = self._active_layout_id or LayoutManager.get_saved_layout_id(profile_name)
            self.apply_appearance(preference, layout_id=layout_id)

    def resolve_appearance(self, preference: AppearancePreference, layout_id: str | None = None) -> ThemeProfile:
        """Calcule la Variante effective : la Famille choisie (ou celle du layout) croisée avec le régime résolu."""
        family = self.get_family_for_theme(preference.family_id) if preference.family_id else None
        if family is None:
            family = self.get_default_family_for_layout(layout_id)
        return family.dark_theme if preference.resolve_mode() is ModeSource.DARK else family.light_theme

    def apply_appearance(self, preference: AppearancePreference, layout_id: str | None = None, app: QApplication | None = None) -> ThemeProfile:
        """Applique la Variante calculée à partir des deux axes d'apparence."""
        self._ensure_system_theme_listener()
        variant = self.resolve_appearance(preference, layout_id=layout_id)
        self.apply_theme(variant, app=app)
        return variant

    def apply_appearance_for_profile(self, profile_name: str, layout_id: str | None = None) -> ThemeProfile:
        """Applique l'apparence persistée du profil ; le layout ne fournit qu'une famille de repli."""
        self._active_profile_name = profile_name
        self._active_layout_id = layout_id
        self._ensure_system_theme_listener()
        return self.apply_appearance(self.get_appearance_preference(profile_name), layout_id=layout_id)


def get_style_engine() -> StyleEngine:
    """Fonction utilitaire pour obtenir le StyleEngine singleton."""
    return StyleEngine.instance()
