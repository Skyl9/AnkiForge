"""
Design System and Theme definitions for AnkiForge.
Single point of truth for all visual values.
"""

import re
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QWidget, QMenu


class DesignTokens:
    """Point unique de vérité — toutes les valeurs visuelles."""

    # Backgrounds (dark)
    BG_MAIN = "#0f1115"
    BG_SIDEBAR = "#16181d"
    BG_PANEL = "#1e2128"
    BG_INPUT = "#1a1d24"
    BG_HOVER = "#2d313a"
    BG_ACTIVE = "rgba(139, 92, 246, 0.1)"

    SURFACE_SECONDARY = "#1e2128"
    SURFACE_HOVER = "#2d313a"

    # Accent
    ACCENT_PRIMARY = "#8b5cf6"  # Purple-500 (Violet)
    ACCENT_HOVER = "#7c3aed"  # Purple-600

    # Text
    TEXT_PRIMARY = "#f8fafc"
    TEXT_SECONDARY = "#94a3b8"
    TEXT_MUTED = "#64748b"

    # Borders
    BORDER_COLOR = "#2d313a"
    BORDER_LIGHT = "rgba(255, 255, 255, 0.04)"

    # Semantic
    COLOR_BLUE = "#3b82f6"
    COLOR_GREEN = "#10b981"
    COLOR_YELLOW = "#f59e0b"
    COLOR_RED = "#ef4444"
    COLOR_PURPLE = "#8b5cf6"

    # Radius
    RADIUS_SM = 6  # buttons, inputs
    RADIUS_MD = 10  # panels, cards
    RADIUS_LG = 16  # modals, hero sections

    # Shadows (pour QGraphicsDropShadowEffect — natif Qt, pas CSS)
    SHADOW_SM_BLUR = 2
    SHADOW_MD_BLUR = 12
    SHADOW_GLASS_BLUR = 32

    # Typography
    FONT_MAIN = "Inter"
    FONT_CODE = "Fira Code"
    FONT_SIZE_BASE = 13
    FONT_SIZE_SMALL = 11
    FONT_SIZE_CODE = 12

    # Sidebar
    SIDEBAR_WIDTH_EXPANDED = 260
    SIDEBAR_WIDTH_COLLAPSED = 68
    TOPBAR_HEIGHT = 60
    GLOBAL_TOPBAR_HEIGHT = 28


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
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(DesignTokens.TEXT_PRIMARY))
    return palette


def create_light_palette() -> QPalette:
    """Creates the light theme QPalette (currently returning dark as default)."""
    return create_dark_palette()


def get_global_stylesheet(is_dark: bool) -> str:
    """Generates the global QSS."""
    return f"""
    QWidget {{
        font-family: "{DesignTokens.FONT_MAIN}";
        font-size: {DesignTokens.FONT_SIZE_BASE}px;
        color: {DesignTokens.TEXT_PRIMARY};
    }}
    
    QScrollBar:vertical {{
        border: none;
        background: transparent;
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background-color: {DesignTokens.BORDER_COLOR};
        min-height: 20px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {DesignTokens.TEXT_MUTED};
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
        background-color: {DesignTokens.BORDER_COLOR};
        min-width: 20px;
        border-radius: 5px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {DesignTokens.TEXT_MUTED};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}
    
    QMenu {{
        background-color: {DesignTokens.BG_SIDEBAR};
        border: 1px solid {DesignTokens.BORDER_COLOR};
        border-radius: {DesignTokens.RADIUS_MD}px;
        padding: 6px;
    }}
    QMenu::item {{
        color: {DesignTokens.TEXT_SECONDARY};
        padding: 8px 16px 8px 36px;
        border-radius: {DesignTokens.RADIUS_SM}px;
        margin: 2px 0px;
    }}
    QMenu::item:selected {{
        background-color: {DesignTokens.BG_HOVER};
        color: {DesignTokens.TEXT_PRIMARY};
    }}
    QMenu::icon {{
        left: 12px;
    }}
    QMenu::indicator {{
        width: 16px;
        height: 16px;
        left: 4px;
    }}
    """


def setup_dynamic_theme(app: QApplication) -> None:
    """Configures the theme, fonts, and palette for the given QApplication."""
    app.setStyle("Fusion")

    # Load fonts
    QFontDatabase.addApplicationFont(":/fonts/Inter-Regular.ttf")
    QFontDatabase.addApplicationFont(":/fonts/FiraCode-Regular.ttf")

    default_font = QFont(DesignTokens.FONT_MAIN, DesignTokens.FONT_SIZE_BASE)
    app.setFont(default_font)

    app.setPalette(create_dark_palette())
    app.setStyleSheet(get_global_stylesheet(True))


def refresh_theme_live() -> None:
    """Refreshes the theme for the currently running QApplication."""
    app = QApplication.instance()
    if isinstance(app, QApplication):
        app.setPalette(create_dark_palette())
        app.setStyleSheet(get_global_stylesheet(True))


def is_dark_mode() -> bool:
    """Returns whether the application is in dark mode."""
    return True


def get_icon_color() -> str:
    """Returns the default color for icons based on the current theme."""
    return DesignTokens.TEXT_PRIMARY


def apply_shadow(widget: QWidget, blur: int = 12, offset_y: int = 4, color: str = "rgba(0,0,0,0.5)") -> None:
    """Applique QGraphicsDropShadowEffect — JAMAIS de CSS box-shadow."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setXOffset(0)
    shadow.setYOffset(offset_y)

    # Parse color
    if color.startswith("rgba"):
        match = re.match(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", color)
        if match:
            r, g, b, a = match.groups()
            c = QColor(int(r), int(g), int(b), int(float(a) * 255))
        else:
            c = QColor(0, 0, 0, 127)
    else:
        c = QColor(color)

    shadow.setColor(c)
    widget.setGraphicsEffect(shadow)


class StyledMenu(QMenu):
    """A premium custom QMenu with drop shadows and uniform styling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)

        # Apply local style sheet to force background painting on translucent window under macOS
        self.setStyleSheet(f"""
            QMenu {{
                background-color: {DesignTokens.BG_SIDEBAR};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 6px;
            }}
            QMenu::item {{
                color: {DesignTokens.TEXT_SECONDARY};
                padding: 8px 16px 8px 36px;
                border-radius: {DesignTokens.RADIUS_SM}px;
                margin: 2px 0px;
            }}
            QMenu::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QMenu::icon {{
                left: 12px;
            }}
        """)

        # Apply drop shadow
        apply_shadow(self, blur=DesignTokens.SHADOW_MD_BLUR, offset_y=4, color="rgba(0, 0, 0, 0.5)")
