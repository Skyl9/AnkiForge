from typing import cast

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QPalette, QColor, QFontDatabase, QFont
from PySide6.QtWidgets import QApplication, QWidget, QGraphicsDropShadowEffect


class DesignTokens:
    """Point unique de vérité — toutes les valeurs visuelles."""

    # Backgrounds (dark)
    BG_MAIN = "#0f1115"
    BG_SIDEBAR = "#16181d"
    BG_PANEL = "#1e2128"
    BG_INPUT = "#1a1d24"
    BG_HOVER = "#2d313a"
    BG_ACTIVE = "rgba(99, 102, 241, 0.1)"

    # Accent
    ACCENT_PRIMARY = "#6366f1"  # Indigo-500
    ACCENT_HOVER = "#4f46e5"  # Indigo-600

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
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(DesignTokens.BG_MAIN))
    palette.setColor(QPalette.ColorRole.Base, QColor(DesignTokens.BG_INPUT))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(DesignTokens.BG_PANEL))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(DesignTokens.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Text, QColor(DesignTokens.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(DesignTokens.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(DesignTokens.TEXT_MUTED))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(DesignTokens.TEXT_MUTED))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(DesignTokens.TEXT_MUTED))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(DesignTokens.TEXT_MUTED))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(DesignTokens.ACCENT_PRIMARY))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(DesignTokens.BG_PANEL))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(DesignTokens.TEXT_PRIMARY))
    return palette


def create_light_palette() -> QPalette:
    # Fallback to dark palette as light mode specific tokens aren't provided yet
    return create_dark_palette()


def get_global_stylesheet(is_dark: bool) -> str:
    return f"""
    QMainWindow {{
        background-color: {DesignTokens.BG_MAIN};
    }}
    
    QScrollBar:vertical {{ border: none; background: transparent; width: 10px; }}
    QScrollBar::handle:vertical {{ background: {DesignTokens.BORDER_COLOR}; border-radius: 5px; }}
    QScrollBar::handle:vertical:hover {{ background: {DesignTokens.TEXT_MUTED}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    
    QScrollBar:horizontal {{ border: none; background: transparent; height: 10px; }}
    QScrollBar::handle:horizontal {{ background: {DesignTokens.BORDER_COLOR}; border-radius: 5px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {{
        background-color: {DesignTokens.BG_INPUT};
        color: {DesignTokens.TEXT_PRIMARY};
        border: 1px solid {DesignTokens.BORDER_COLOR};
        border-radius: {DesignTokens.RADIUS_SM}px;
        selection-background-color: {DesignTokens.ACCENT_PRIMARY};
    }}
    
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: 1px solid {DesignTokens.ACCENT_PRIMARY};
    }}

    QTableWidget, QTreeWidget {{
        background-color: {DesignTokens.BG_PANEL};
        border: 1px solid {DesignTokens.BORDER_COLOR};
        border-radius: {DesignTokens.RADIUS_MD}px;
        gridline-color: {DesignTokens.BORDER_COLOR};
        outline: none;
    }}
    
    QTableWidget::item:selected, QTreeWidget::item:selected {{
        background-color: {DesignTokens.BG_ACTIVE};
        color: {DesignTokens.TEXT_PRIMARY};
    }}

    QHeaderView::section {{
        background-color: {DesignTokens.BG_PANEL};
        color: {DesignTokens.TEXT_SECONDARY};
        border: none;
        border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
    }}
    """


def setup_dynamic_theme(app: QApplication) -> None:
    app.setStyle("Fusion")

    # Tente de charger la police Inter
    QFontDatabase.addApplicationFont(":/fonts/Inter-Regular.ttf")
    font = QFont(DesignTokens.FONT_MAIN, DesignTokens.FONT_SIZE_BASE)
    app.setFont(font)

    settings = QSettings("AnkiForgeOrg", "AnkiForge")
    saved_theme = settings.value("ui/theme", "Système (Par défaut)")

    def apply_theme(is_dark: bool):
        palette = create_dark_palette() if is_dark else create_light_palette()
        app.setPalette(palette)
        app.setStyleSheet(get_global_stylesheet(is_dark))

    if saved_theme == "Sombre (Dark)":
        apply_theme(True)
    elif saved_theme == "Clair (Light)":
        apply_theme(False)
    else:
        current_scheme = app.styleHints().colorScheme()
        apply_theme(current_scheme == Qt.ColorScheme.Dark)

    def os_theme_changed(scheme):
        if settings.value("ui/theme", "Système (Par défaut)") == "Système (Par défaut)":
            apply_theme(scheme == Qt.ColorScheme.Dark)

    app.styleHints().colorSchemeChanged.connect(os_theme_changed)


def refresh_theme_live() -> None:
    app = cast(QApplication, QApplication.instance())
    if app:
        setup_dynamic_theme(app)


def is_dark_mode() -> bool:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return False
    bg_color = app.palette().color(QPalette.ColorRole.Window)
    return bg_color.lightness() < 128


def get_icon_color() -> str:
    app = QApplication.instance()
    if isinstance(app, QApplication):
        return app.palette().color(QPalette.ColorRole.WindowText).name()
    return DesignTokens.TEXT_PRIMARY


def apply_shadow(widget: QWidget, blur: int = 12, offset_y: int = 4, color: str = "rgba(0,0,0,0.5)") -> None:
    """Applique QGraphicsDropShadowEffect — JAMAIS de CSS box-shadow."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, offset_y)

    if color.startswith("rgba"):
        parts = color.strip("rgba() ").split(",")
        if len(parts) == 4:
            qcolor = QColor(int(parts[0]), int(parts[1]), int(parts[2]), int(float(parts[3]) * 255))
            shadow.setColor(qcolor)
    else:
        shadow.setColor(QColor(color))

    widget.setGraphicsEffect(shadow)
