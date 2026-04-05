# src/ankiforge/ui/theme.py
from PySide6.QtGui import QPalette, QColor, Qt
from PySide6.QtWidgets import QApplication

def apply_dark_theme(app: QApplication) -> None:
    """Applique une QPalette globale sombre."""
    app.setStyle("Fusion")
    palette = QPalette()

    bg_color = QColor(18, 18, 18)
    surface_color = QColor(30, 30, 30)
    text_primary = QColor(224, 224, 224)
    text_disabled = QColor(110, 110, 110)
    accent_color = QColor(63, 81, 181)

    palette.setColor(QPalette.ColorRole.Window, bg_color)
    palette.setColor(QPalette.ColorRole.Base, surface_color)
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(24, 24, 24))
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


def apply_light_theme(app: QApplication) -> None:
    """Applique une QPalette globale claire et lisible."""
    app.setStyle("Fusion")
    palette = QPalette()

    bg_color = QColor(240, 240, 240)       # Fond gris très clair
    surface_color = QColor(255, 255, 255)  # Fond blanc pur pour les zones de texte/listes
    text_primary = QColor(30, 30, 30)      # Texte presque noir
    text_disabled = QColor(150, 150, 150)
    accent_color = QColor(63, 81, 181)     # On garde l'indigo, il ressort très bien sur le blanc

    palette.setColor(QPalette.ColorRole.Window, bg_color)
    palette.setColor(QPalette.ColorRole.Base, surface_color)
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(245, 245, 245))
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


def setup_dynamic_theme(app: QApplication) -> None:
    """Détecte le thème de l'OS, l'applique, et écoute les changements."""

    # 1. Fonction interne pour appliquer le bon thème selon le ColorScheme de l'OS
    def update_theme(scheme: Qt.ColorScheme):
        if scheme == Qt.ColorScheme.Dark:
            apply_dark_theme(app)
        else:
            apply_light_theme(app)

    # 2. On récupère le thème actuel au lancement et on l'applique
    current_scheme = app.styleHints().colorScheme()
    update_theme(current_scheme)

    # 3. On connecte le signal pour détecter si l'utilisateur change le thème de son OS plus tard
    app.styleHints().colorSchemeChanged.connect(update_theme)