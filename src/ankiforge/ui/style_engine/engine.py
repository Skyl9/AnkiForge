"""
Moteur de Style Centralisé (StyleEngine) pour AnkiForge.
Génère et applique dynamiquement les règles QSS sémantiques basées sur les sélecteurs de propriétés Qt.
"""

import contextlib
from typing import Optional

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

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


class StyleEngine(QObject):
    """
    Moteur de style centralisé singleton.
    Gère la compilation du QSS sémantique et le hot-reloading de l'interface.
    """

    theme_changed = Signal(ThemeProfile)

    _instance: Optional["StyleEngine"] = None

    def __init__(self) -> None:
        super().__init__()
        self._current_theme: ThemeProfile = JETBRAINS_DARK
        self._custom_themes: dict[str, ThemeProfile] = {}

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
            border-color: transparent;
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
            border-color: transparent;
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
            border: 2px solid {p.accent_primary};
            background-color: {p.bg_panel};
            color: {p.text_primary};
        }}
        QPushButton[role="secondary"]:pressed {{
            background-color: {p.bg_active};
            border: 2px solid {p.accent_primary};
            padding-top: 9px;
        }}
        QPushButton[role="secondary"]:disabled {{
            background-color: {p.bg_input};
            color: {p.text_muted};
            border-color: {p.border_light};
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
        SidebarItem, SidebarProfileItem, QPushButton#SidebarUserBtn {{
            background-color: transparent;
            color: {p.text_secondary};
            border: none;
            border-radius: {p.radius_sm}px;
            text-align: left;
            padding-left: 12px;
            font-size: {p.font_size_base}px;
        }}
        SidebarItem:hover, SidebarProfileItem:hover, QPushButton#SidebarUserBtn:hover {{
            background-color: {p.bg_hover};
            color: {p.text_primary};
        }}
        SidebarItem:checked, SidebarProfileItem:checked {{
            background-color: {p.bg_active};
            color: {p.accent_primary};
            font-weight: bold;
        }}
        SidebarItem:pressed, SidebarProfileItem:pressed, QPushButton#SidebarUserBtn:pressed {{
            background-color: {p.bg_active};
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
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
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
                            with contextlib.suppress(Exception):
                                widget.refresh_theme()
                        except Exception:
                            pass
                    style.unpolish(widget)
                    style.polish(widget)
                    widget.update()
                except Exception:
                    pass  # nosec B110

    def get_theme_families(self) -> list[ThemeFamily]:
        """Retourne la liste des 12 familles de thèmes bivalentes."""
        return get_theme_families()

    def get_family_for_theme(self, theme_id: str) -> ThemeFamily | None:
        """Retrouve la famille d'un thème."""
        return get_family_for_theme(theme_id)

    def set_color_mode(self, mode: str, app: QApplication | None = None) -> ThemeProfile:
        """Définit le mode 'dark' ou 'light' pour la famille de thème active."""
        current = self._current_theme
        family = get_family_for_theme(current.id)
        target = (family.light_theme if family else self.get_theme("jetbrains_light")) if mode == "light" else family.dark_theme if family else self.get_theme("ide")

        self.apply_theme(target, app=app)
        return target

    def toggle_color_mode(self, app: QApplication | None = None) -> ThemeProfile:
        """Bascule intelligemment entre le mode Sombre et le mode Clair pour la famille active."""
        current = self._current_theme
        family = get_family_for_theme(current.id)
        target = (family.light_theme if family else self.get_theme("jetbrains_light")) if current.is_dark else family.dark_theme if family else self.get_theme("ide")

        self.apply_theme(target, app=app)
        return target

    def save_theme_preference(self, profile_name: str, theme_id: str) -> None:
        """Enregistre le thème sélectionné dans la BDD SQLite (SettingModel) et QSettings par profil."""
        try:
            from ankiforge.database.models import SettingModel

            SettingModel.set_value(f"profiles/{profile_name}/theme_id", theme_id, category="appearance")
        except Exception:
            pass  # nosec B110

        settings = QSettings("AnkiForgeOrg", "ankiforge_obsidian")
        settings.setValue(f"profiles/{profile_name}/theme_id", theme_id)

    def get_saved_theme_id(self, profile_name: str) -> str:
        """Récupère le thème enregistré pour le profil depuis la BDD SQLite (ou QSettings)."""
        try:
            from ankiforge.database.models import SettingModel

            val = SettingModel.get_value(f"profiles/{profile_name}/theme_id")
            if val:
                return str(val)
        except Exception:
            pass  # nosec B110

        settings = QSettings("AnkiForgeOrg", "ankiforge_obsidian")
        return str(settings.value(f"profiles/{profile_name}/theme_id", "ide"))


def get_style_engine() -> StyleEngine:
    """Fonction utilitaire pour obtenir le StyleEngine singleton."""
    return StyleEngine.instance()
