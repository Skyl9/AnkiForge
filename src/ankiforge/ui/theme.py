# src/ankiforge/ui/theme.py
from PySide6.QtGui import QPalette, QColor, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings

GLOBAL_STYLESHEET = """
/* --- Scrollbars Modernes (Fines et sans flèches) --- */
QMainWindow {
    background-color: palette(window);
}
/* --- Scrollbars Modernes --- */
QScrollBar:vertical { border: none; background: transparent; width: 10px; margin: 0px; }
QScrollBar::handle:vertical { background: palette(alternate-base); min-height: 30px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: palette(placeholder-text); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar:horizontal { border: none; background: transparent; height: 10px; margin: 0px; }
QScrollBar::handle:horizontal { background: palette(alternate-base); min-width: 30px; border-radius: 5px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }

/* --- Champs de saisie et Menus déroulants --- */
QLineEdit, QTextEdit, QComboBox, QSpinBox {
    background-color: palette(base);
    color: palette(text);
    border: 1px solid palette(alternate-base);
    border-radius: 6px;
    padding: 8px 12px;
    selection-background-color: palette(highlight);
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid palette(highlight);
}
QComboBox::drop-down { border: none; padding-right: 10px; }
QComboBox QAbstractItemView {
    background-color: palette(base);
    border: 1px solid palette(alternate-base);
    border-radius: 6px;
    selection-background-color: palette(highlight);
    outline: none;
}

/* --- Tableaux et Arbres --- */
QTableWidget, QTreeWidget {
    background-color: palette(base);
    border: 1px solid palette(alternate-base);
    border-radius: 8px;
    gridline-color: palette(alternate-base);
    outline: none;
}
QTableWidget::item, QTreeWidget::item { padding: 5px; }
QTableWidget::item:selected, QTreeWidget::item:selected {
    background-color: palette(highlight);
    color: palette(highlighted-text);
}
QHeaderView::section {
    background-color: palette(alternate-base);
    color: palette(text);
    font-weight: bold;
    padding: 8px;
    border: none;
    border-right: 1px solid palette(window);
    border-bottom: 1px solid palette(window);
}

/* --- Menus contextuels --- */
QMenu { background-color: palette(base); border: 1px solid palette(alternate-base); border-radius: 6px; padding: 5px; }
QMenu::item { padding: 8px 25px 8px 20px; border-radius: 4px; }
QMenu::item:selected { background-color: palette(highlight); color: palette(highlighted-text); }

/* --- GroupBox --- */
QGroupBox { border: none; margin-top: 1.5em; font-weight: bold; color: palette(placeholder-text); }
QGroupBox::title { subcontrol-origin: margin; left: 0px; padding: 0px; }
"""

def apply_dark_theme(app: QApplication) -> None:
    """Applique une QPalette globale sombre."""
    app.setStyle("Fusion")
    palette = QPalette()

    bg_color = QColor(18, 18, 18)
    surface_color = QColor(30, 30, 30)
    alternate_base = QColor(45, 45, 45) # Contraste légèrement plus fort pour les bordures
    text_primary = QColor(224, 224, 224)
    text_disabled = QColor(110, 110, 110)
    accent_color = QColor(63, 81, 181)

    palette.setColor(QPalette.ColorRole.Window, bg_color)
    palette.setColor(QPalette.ColorRole.Base, surface_color)
    palette.setColor(QPalette.ColorRole.AlternateBase, alternate_base)
    palette.setColor(QPalette.ColorRole.WindowText, text_primary)
    palette.setColor(QPalette.ColorRole.Text, text_primary)
    palette.setColor(QPalette.ColorRole.ButtonText, text_primary)
    palette.setColor(QPalette.ColorRole.PlaceholderText, text_disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, text_disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, text_disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, text_disabled)
    palette.setColor(QPalette.ColorRole.Highlight, accent_color)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(40, 40, 40))
    palette.setColor(QPalette.ColorRole.ToolTipText, text_primary)

    app.setPalette(palette)
    app.setStyleSheet(GLOBAL_STYLESHEET)  # 👈 CRUCIAL : Le CSS vient APRÈS la palette !


def apply_light_theme(app: QApplication) -> None:
    """Applique une QPalette globale claire et reposante."""
    app.setStyle("Fusion")
    palette = QPalette()

    # Adoucissement global du thème clair
    bg_color = QColor(235, 235, 235)       # Fond légèrement plus sombre pour détacher les cartes
    surface_color = QColor(252, 252, 252)  # Blanc "cassé" moins agressif
    alternate_base = QColor(215, 215, 215) # Gris plus marqué pour bien délimiter les champs de saisie
    text_primary = QColor(40, 40, 40)
    text_disabled = QColor(140, 140, 140)
    accent_color = QColor(63, 81, 181)

    palette.setColor(QPalette.ColorRole.Window, bg_color)
    palette.setColor(QPalette.ColorRole.Base, surface_color)
    palette.setColor(QPalette.ColorRole.AlternateBase, alternate_base)
    palette.setColor(QPalette.ColorRole.WindowText, text_primary)
    palette.setColor(QPalette.ColorRole.Text, text_primary)
    palette.setColor(QPalette.ColorRole.ButtonText, text_primary)
    palette.setColor(QPalette.ColorRole.PlaceholderText, text_disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, text_disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, text_disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, text_disabled)
    palette.setColor(QPalette.ColorRole.Highlight, accent_color)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.ToolTipText, text_primary)

    app.setPalette(palette)
    app.setStyleSheet(GLOBAL_STYLESHEET)


def setup_dynamic_theme(app: QApplication) -> None:
    settings = QSettings("AnkiForgeOrg", "AnkiForge")
    saved_theme = settings.value("ui/theme", "Système (Par défaut)")

    if saved_theme == "Sombre (Dark)":
        apply_dark_theme(app)
    elif saved_theme == "Clair (Light)":
        apply_light_theme(app)
    else:
        current_scheme = app.styleHints().colorScheme()
        if current_scheme == Qt.ColorScheme.Dark:
            apply_dark_theme(app)
        else:
            apply_light_theme(app)

    # Écoute les changements OS uniquement si on est en mode "Système"
    def os_theme_changed(scheme):
        if settings.value("ui/theme", "Système (Par défaut)") == "Système (Par défaut)":
            if scheme == Qt.ColorScheme.Dark:
                apply_dark_theme(app)
            else:
                apply_light_theme(app)

    app.styleHints().colorSchemeChanged.connect(os_theme_changed)

def refresh_theme_live() -> None:
    """Fonction utilitaire pour appliquer le thème instantanément sans redémarrer."""
    app = QApplication.instance()
    if app:
        setup_dynamic_theme(app)

def get_icon_color() -> str:
    """Récupère la couleur du texte actif pour peindre les icônes dynamiquement."""
    app = QApplication.instance()
    if app:
        # Retourne la couleur hexadécimale (ex: '#e0e0e0' ou '#282828')
        return app.palette().color(QPalette.ColorRole.WindowText).name()
    return "#E0E0E0" # Fallback de sécurité