"""
Design System and Theme definitions for AnkiForge.
Single point of truth for all visual values and multi-layout theme profiles.
"""

import re
import sys
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QMenu, QWidget

if sys.platform == "darwin":
    DEFAULT_FONT_MAIN = ".AppleSystemUIFont"
    DEFAULT_FONT_CODE = "Menlo"
elif sys.platform == "win32":
    DEFAULT_FONT_MAIN = "Segoe UI"
    DEFAULT_FONT_CODE = "Consolas"
else:
    DEFAULT_FONT_MAIN = "DejaVu Sans"
    DEFAULT_FONT_CODE = "DejaVu Sans Mono"


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
    TEXT_ON_ACCENT = "#ffffff"  # icônes / texte posés sur un fond accent (boutons primaires, badges, handles)

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

    # Semantic tinted backgrounds (alpha variants dérivés de color_* à l'application du profil)
    ACCENT_BG = "rgba(99, 102, 241, 0.15)"
    COLOR_RED_BG = "rgba(239, 68, 68, 0.15)"
    COLOR_GREEN_BG = "rgba(16, 185, 129, 0.15)"
    COLOR_YELLOW_BG = "rgba(245, 158, 11, 0.15)"
    COLOR_BLUE_BG = "rgba(59, 130, 246, 0.15)"
    COLOR_PURPLE_BG = "rgba(99, 102, 241, 0.12)"

    # Semantic tinted borders (bordure teintée par alpha, dérivées comme les *_BG)
    ACCENT_BORDER = "rgba(99, 102, 241, 0.3)"
    COLOR_RED_BORDER = "rgba(239, 68, 68, 0.3)"
    COLOR_GREEN_BORDER = "rgba(16, 185, 129, 0.3)"
    COLOR_YELLOW_BORDER = "rgba(245, 158, 11, 0.3)"
    COLOR_BLUE_BORDER = "rgba(59, 130, 246, 0.3)"
    COLOR_PURPLE_BORDER = "rgba(168, 85, 247, 0.3)"

    # Semantic text-on-tint (texte lisible sur fond teinté ; sombre → teinte claire, claire → couleur de base)
    COLOR_RED_TEXT = "#f87171"
    COLOR_GREEN_TEXT = "#6ee7b7"
    COLOR_YELLOW_TEXT = "#fcd34d"
    COLOR_BLUE_TEXT = "#93c5fd"
    COLOR_PURPLE_TEXT = "#a5b4fc"

    # Anki Card Flags (1..7)
    FLAG_NONE = 0
    FLAG_RED = "#ef4444"
    FLAG_ORANGE = "#f97316"
    FLAG_GREEN = "#10b981"
    FLAG_BLUE = "#3b82f6"
    FLAG_PINK = "#ec4899"
    FLAG_TURQUOISE = "#06b6d4"
    FLAG_PURPLE = "#a855f7"

    # A/B Testing branches
    BRANCH_A = "#8b5cf6"
    BRANCH_B = "#06b6d4"
    BRANCH_A_BG = "rgba(139, 92, 246, 0.12)"
    BRANCH_B_BG = "rgba(6, 182, 212, 0.12)"
    BRANCH_A_BORDER = "rgba(139, 92, 246, 0.45)"
    BRANCH_B_BORDER = "rgba(6, 182, 212, 0.45)"

    FLAG_COLORS: dict[int, str] = {
        1: "#ef4444",
        2: "#f97316",
        3: "#10b981",
        4: "#3b82f6",
        5: "#ec4899",
        6: "#06b6d4",
        7: "#a855f7",
    }

    FLAG_NAMES: dict[int, str] = {
        0: "Aucun",
        1: "Rouge",
        2: "Orange",
        3: "Vert",
        4: "Bleu",
        5: "Rose",
        6: "Turquoise",
        7: "Violet",
    }

    FLAG_SEARCH_MAP: dict[str, int] = {
        "0": 0,
        "none": 0,
        "aucun": 0,
        "1": 1,
        "red": 1,
        "rouge": 1,
        "2": 2,
        "orange": 2,
        "3": 3,
        "green": 3,
        "vert": 3,
        "4": 4,
        "blue": 4,
        "bleu": 4,
        "5": 5,
        "pink": 5,
        "rose": 5,
        "6": 6,
        "turquoise": 6,
        "cyan": 6,
        "7": 7,
        "purple": 7,
        "violet": 7,
    }

    # Tokens de coloration syntaxique (Syntax Highlighting)
    SYNTAX_TAG = "#38bdf8"
    SYNTAX_ATTR = "#fbbf24"
    SYNTAX_STRING = "#4ade80"
    SYNTAX_KEYWORD = "#c084fc"
    SYNTAX_VARIABLE = "#f97316"
    SYNTAX_COMMENT = "#64748b"
    SYNTAX_NUMBER = "#22d3ee"

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
    FONT_MAIN = DEFAULT_FONT_MAIN
    FONT_CODE = DEFAULT_FONT_CODE
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
        cls.TEXT_ON_ACCENT = getattr(profile, "text_on_accent", "") or ("#ffffff" if cls.IS_DARK else "#0f1115")

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

        # Semantic tinted backgrounds — dérivés des couleurs sémantiques actives (réassignés à chaud)
        cls.ACCENT_BG = profile.accent_bg or cls._with_alpha(profile.accent_primary, 0.15)
        cls.COLOR_RED_BG = profile.color_red_bg or cls._with_alpha(profile.color_red, 0.15)
        cls.COLOR_GREEN_BG = profile.color_green_bg or cls._with_alpha(profile.color_green, 0.15)
        cls.COLOR_YELLOW_BG = profile.color_yellow_bg or cls._with_alpha(profile.color_yellow, 0.15)
        cls.COLOR_BLUE_BG = profile.color_blue_bg or cls._with_alpha(profile.color_blue, 0.15)
        cls.COLOR_PURPLE_BG = profile.color_purple_bg or cls._with_alpha(profile.color_purple, 0.12)

        # Semantic tinted borders — dérivées des couleurs sémantiques actives
        cls.ACCENT_BORDER = profile.accent_border or cls._with_alpha(profile.accent_primary, 0.3)
        cls.COLOR_RED_BORDER = profile.color_red_border or cls._with_alpha(profile.color_red, 0.3)
        cls.COLOR_GREEN_BORDER = profile.color_green_border or cls._with_alpha(profile.color_green, 0.3)
        cls.COLOR_YELLOW_BORDER = profile.color_yellow_border or cls._with_alpha(profile.color_yellow, 0.3)
        cls.COLOR_BLUE_BORDER = profile.color_blue_border or cls._with_alpha(profile.color_blue, 0.3)
        cls.COLOR_PURPLE_BORDER = profile.color_purple_border or cls._with_alpha(profile.color_purple, 0.3)

        # Branch A/B — couleurs fixes du design system, teintes alpha dérivées
        cls.BRANCH_A_BG = cls._with_alpha(cls.BRANCH_A, 0.12)
        cls.BRANCH_B_BG = cls._with_alpha(cls.BRANCH_B, 0.12)
        cls.BRANCH_A_BORDER = cls._with_alpha(cls.BRANCH_A, 0.45)
        cls.BRANCH_B_BORDER = cls._with_alpha(cls.BRANCH_B, 0.45)

        # Semantic text-on-tint — teinte claire en mode sombre, couleur de base en clair
        cls.COLOR_RED_TEXT = profile.color_red_text or ("#f87171" if cls.IS_DARK else profile.color_red)
        cls.COLOR_GREEN_TEXT = profile.color_green_text or ("#6ee7b7" if cls.IS_DARK else profile.color_green)
        cls.COLOR_YELLOW_TEXT = profile.color_yellow_text or ("#fcd34d" if cls.IS_DARK else profile.color_yellow)
        cls.COLOR_BLUE_TEXT = profile.color_blue_text or ("#93c5fd" if cls.IS_DARK else profile.color_blue)
        cls.COLOR_PURPLE_TEXT = profile.color_purple_text or ("#a5b4fc" if cls.IS_DARK else profile.color_purple)

        # Syntax Highlighting Tokens
        cls.SYNTAX_TAG = getattr(profile, "syntax_tag", "#38bdf8" if cls.IS_DARK else "#0284c7")
        cls.SYNTAX_ATTR = getattr(profile, "syntax_attr", "#fbbf24" if cls.IS_DARK else "#d97706")
        cls.SYNTAX_STRING = getattr(profile, "syntax_string", "#4ade80" if cls.IS_DARK else "#16a34a")
        cls.SYNTAX_KEYWORD = getattr(profile, "syntax_keyword", "#c084fc" if cls.IS_DARK else "#7c3aed")
        cls.SYNTAX_VARIABLE = getattr(profile, "syntax_variable", "#f97316" if cls.IS_DARK else "#ea580c")
        cls.SYNTAX_COMMENT = getattr(profile, "syntax_comment", "#64748b" if cls.IS_DARK else "#94a3b8")
        cls.SYNTAX_NUMBER = getattr(profile, "syntax_number", "#22d3ee" if cls.IS_DARK else "#0891b2")

        cls.RADIUS_SM = profile.radius_sm
        cls.RADIUS_MD = profile.radius_md
        cls.RADIUS_LG = profile.radius_lg

        cls.FONT_MAIN = getattr(profile, "font_main", DEFAULT_FONT_MAIN)
        cls.FONT_CODE = getattr(profile, "font_code", DEFAULT_FONT_CODE)
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
    def _with_alpha(cls, color: str, alpha: float) -> str:
        """Convertit une couleur hex (ou rgba existante) en rgba avec l'alpha demandée."""
        c = QColor(color)
        if not c.isValid():
            return color
        return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"

    @classmethod
    def is_dark_mode(cls) -> bool:
        """Indique si le thème actif actuel est en mode sombre."""
        return cls.IS_DARK


def setup_dynamic_theme(app: QApplication) -> None:
    """Configures the theme, fonts, and palette for the given QApplication."""
    from ankiforge.ui.style_engine.engine import StyleEngine

    app.setStyle("Fusion")
    default_font = QFont(DesignTokens.FONT_MAIN, DesignTokens.FONT_SIZE_BASE)
    app.setFont(default_font)
    StyleEngine.instance().apply_theme(DesignTokens.ACTIVE_THEME_ID, app)


def is_dark_mode() -> bool:
    """Returns whether the application is in dark mode."""
    return True


def apply_shadow(widget: QWidget, blur: int = 12, offset_y: int = 4, color: str | QColor = "rgba(0,0,0,0.5)") -> None:
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

    def __init__(self, parent: QWidget | None = None):
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
