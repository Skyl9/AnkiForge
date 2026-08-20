"""
Design System and Theme definitions for AnkiForge.
Single point of truth for all visual values and multi-layout theme profiles.
"""

import re
from typing import Any, Optional, Union
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QMenu, QWidget


class DesignTokens:
    """Point unique de vérité — toutes les valeurs visuelles et thèmes dynamiques."""

    ACTIVE_THEME_ID = "ide"
    IS_DARK = True

    # Backgrounds
    BG_MAIN = "#0f1115"
    BG_SIDEBAR = "#16181d"
    BG_PANEL = "#1e2128"
    BG_INPUT = "#1a1d24"
    BG_HOVER = "#2d313a"
    BG_ACTIVE = "rgba(99, 102, 241, 0.12)"

    SURFACE_SECONDARY = "#1e2128"
    SURFACE_HOVER = "#2d313a"

    # Accent
    ACCENT_PRIMARY = "#6366f1"  # Indigo-Violet
    ACCENT_HOVER = "#4f46e5"
    ACCENT_GLOW = "rgba(99, 102, 241, 0.4)"

    # Text
    TEXT_PRIMARY = "#f8fafc"
    TEXT_SECONDARY = "#94a3b8"
    TEXT_MUTED = "#64748b"

    # Borders
    BORDER_COLOR = "#2d313a"
    BORDER_LIGHT = "rgba(255, 255, 255, 0.04)"
    BORDER_FOCUS = "#6366f1"

    # Semantic
    COLOR_BLUE = "#3b82f6"
    COLOR_GREEN = "#10b981"
    COLOR_YELLOW = "#f59e0b"
    COLOR_RED = "#ef4444"
    COLOR_PURPLE = "#6366f1"

    # Radius
    RADIUS_SM = 6  # buttons, inputs
    RADIUS_MD = 10  # panels, cards
    RADIUS_LG = 16  # modals, hero sections

    # Shadows
    SHADOW_SM_BLUR = 2
    SHADOW_MD_BLUR = 12
    SHADOW_GLASS_BLUR = 32
    SHADOW_COLOR = "rgba(0, 0, 0, 0.45)"

    # Typography
    FONT_MAIN = ".AppleSystemUIFont"
    FONT_CODE = "Menlo"
    FONT_SIZE_BASE = 13
    FONT_SIZE_SMALL = 11
    FONT_SIZE_SM = 11
    FONT_SIZE_XS = 11
    FONT_SIZE_CODE = 12

    # Sidebar
    SIDEBAR_WIDTH_EXPANDED = 260
    SIDEBAR_WIDTH_COLLAPSED = 68
    TOPBAR_HEIGHT = 60
    GLOBAL_TOPBAR_HEIGHT = 28

    @classmethod
    def apply_theme_profile(cls, profile: Any) -> None:
        """Applique l'intégralité d'un ThemeProfile aux variables de classe DesignTokens."""
        cls.ACTIVE_THEME_ID = profile.id
        cls.IS_DARK = getattr(profile, "is_dark", True)

        cls.BG_MAIN = profile.bg_main
        cls.BG_SIDEBAR = profile.bg_sidebar
        cls.BG_PANEL = profile.bg_panel
        cls.BG_INPUT = profile.bg_input
        cls.BG_HOVER = profile.bg_hover
        cls.BG_ACTIVE = profile.bg_active
        cls.SURFACE_SECONDARY = profile.bg_panel
        cls.SURFACE_HOVER = profile.bg_hover

        cls.ACCENT_PRIMARY = profile.accent_primary
        cls.ACCENT_HOVER = profile.accent_hover
        cls.ACCENT_GLOW = getattr(profile, "accent_glow", "rgba(99, 102, 241, 0.4)")

        cls.TEXT_PRIMARY = profile.text_primary
        cls.TEXT_SECONDARY = profile.text_secondary
        cls.TEXT_MUTED = profile.text_muted

        cls.BORDER_COLOR = profile.border_color
        cls.BORDER_LIGHT = profile.border_light
        cls.BORDER_FOCUS = getattr(profile, "border_focus", profile.accent_primary)

        cls.COLOR_BLUE = profile.color_blue
        cls.COLOR_GREEN = profile.color_green
        cls.COLOR_YELLOW = profile.color_yellow
        cls.COLOR_RED = profile.color_red
        cls.COLOR_PURPLE = profile.color_purple

        cls.RADIUS_SM = profile.radius_sm
        cls.RADIUS_MD = profile.radius_md
        cls.RADIUS_LG = profile.radius_lg

        cls.FONT_MAIN = getattr(profile, "font_main", ".AppleSystemUIFont")
        cls.FONT_CODE = getattr(profile, "font_code", "Menlo")
        cls.FONT_SIZE_BASE = getattr(profile, "font_size_base", 13)
        cls.FONT_SIZE_SMALL = getattr(profile, "font_size_sm", 11)
        cls.FONT_SIZE_SM = getattr(profile, "font_size_sm", 11)

        cls.SHADOW_COLOR = "rgba(0, 0, 0, 0.45)" if cls.IS_DARK else "rgba(0, 0, 0, 0.12)"

    @classmethod
    def set_layout_theme(cls, layout_or_theme_id: str) -> None:
        """Adapte l'ensemble des design tokens selon le thème ou concept/layout actif."""
        from ankiforge.ui.style_engine.themes import BUILTIN_THEMES, JETBRAINS_DARK

        theme = BUILTIN_THEMES.get(layout_or_theme_id, JETBRAINS_DARK)
        cls.apply_theme_profile(theme)

    @classmethod
    def is_dark_mode(cls) -> bool:
        """Indique si le thème actif actuel est en mode sombre."""
        return cls.IS_DARK


def create_dark_palette() -> QPalette:
    """Creates the dark theme QPalette based on DesignTokens."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(DesignTokens.BG_MAIN))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(DesignTokens.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base, QColor(DesignTokens.BG_INPUT))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(DesignTokens.BG_PANEL))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(DesignTokens.BG_PANEL))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(DesignTokens.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Text, QColor(DesignTokens.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Button, QColor(DesignTokens.BG_PANEL))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(DesignTokens.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(DesignTokens.COLOR_RED))
    palette.setColor(QPalette.ColorRole.Link, QColor(DesignTokens.ACCENT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(DesignTokens.ACCENT_PRIMARY))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    return palette


def create_light_palette() -> QPalette:
    """Creates the light theme QPalette based on DesignTokens."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(DesignTokens.BG_MAIN))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(DesignTokens.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base, QColor(DesignTokens.BG_INPUT))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(DesignTokens.BG_PANEL))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(DesignTokens.BG_PANEL))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(DesignTokens.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Text, QColor(DesignTokens.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Button, QColor(DesignTokens.BG_PANEL))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(DesignTokens.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(DesignTokens.COLOR_RED))
    palette.setColor(QPalette.ColorRole.Link, QColor(DesignTokens.ACCENT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(DesignTokens.ACCENT_PRIMARY))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    return palette


def get_global_stylesheet(is_dark: bool = True) -> str:
    """Génère la feuille de style QSS globale alignée sur les DesignTokens actifs via le StyleEngine."""
    from ankiforge.ui.style_engine.engine import StyleEngine

    return StyleEngine.instance().generate_stylesheet()


def setup_dynamic_theme(app: QApplication) -> None:
    """Configures the theme, fonts, and palette for the given QApplication."""
    from ankiforge.ui.style_engine.engine import StyleEngine

    app.setStyle("Fusion")
    default_font = QFont(DesignTokens.FONT_MAIN, DesignTokens.FONT_SIZE_BASE)
    app.setFont(default_font)
    StyleEngine.instance().apply_theme(DesignTokens.ACTIVE_THEME_ID, app)


def refresh_theme_live() -> None:
    """Refreshes the theme for the currently running QApplication."""
    from ankiforge.ui.style_engine.engine import StyleEngine

    StyleEngine.instance().apply_theme(DesignTokens.ACTIVE_THEME_ID)


def is_dark_mode() -> bool:
    """Returns whether the application is in dark mode."""
    return True


def get_icon_color() -> str:
    """Returns the default color for icons based on the current theme."""
    return DesignTokens.TEXT_PRIMARY


def apply_shadow(widget: QWidget, blur: int = 12, offset_y: int = 4, color: Union[str, QColor] = "rgba(0,0,0,0.5)") -> None:
    """Applique QGraphicsDropShadowEffect — JAMAIS de CSS box-shadow."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setXOffset(0)
    shadow.setYOffset(offset_y)

    if isinstance(color, QColor):
        c = color
    elif isinstance(color, str):
        if color.startswith("rgba"):
            match = re.match(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", color)
            if match:
                r, g, b, a = match.groups()
                c = QColor(int(r), int(g), int(b), int(float(a) * 255))
            else:
                c = QColor(0, 0, 0, 127)
        else:
            c = QColor(color)
    else:
        c = QColor(0, 0, 0, 127)

    shadow.setColor(c)
    widget.setGraphicsEffect(shadow)


class StyledMenu(QMenu):
    """A premium custom QMenu with drop shadows and uniform styling."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)

        self.setStyleSheet(f"""
            QMenu {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 6px;
            }}
            QMenu::item {{
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 7px 20px 7px 32px;
                border-radius: {DesignTokens.RADIUS_SM}px;
                margin: 2px 0px;
                font-family: "{DesignTokens.FONT_MAIN}";
                font-size: {DesignTokens.FONT_SIZE_BASE}px;
            }}
            QMenu::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.ACCENT_PRIMARY};
                font-weight: bold;
            }}
            QMenu::item:disabled {{
                color: {DesignTokens.TEXT_MUTED};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {DesignTokens.BORDER_COLOR};
                margin: 4px 6px;
            }}
            QMenu::icon {{
                left: 10px;
            }}
        """)

        apply_shadow(self, blur=DesignTokens.SHADOW_MD_BLUR, offset_y=4, color=DesignTokens.SHADOW_COLOR)
