# src/ankiforge/ui/widgets/components.py
from typing import cast

import qtawesome
from PySide6.QtWidgets import QPushButton, QFrame, QLabel, QVBoxLayout, QComboBox
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtCore import Qt, QEvent, Slot

from ankiforge.ui.theme import get_icon_color


class PrimaryButton(QPushButton):
    """Bouton principal pour les actions positives (Sauvegarder, Exporter)."""

    def __init__(self, icon_or_text, text=None, parent=None):
        if text is not None:
            super().__init__(icon_or_text, text, parent)
        else:
            super().__init__(icon_or_text, parent)

        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        # Les couleurs sémantiques (Vert) restent codées en dur car elles sont universelles
        self.setStyleSheet("""
            PrimaryButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
            }
            PrimaryButton:hover { background-color: #45a049; }
            PrimaryButton:pressed { background-color: #388E3C; }
            PrimaryButton:disabled { background-color: palette(alternate-base); color: palette(placeholder-text); }
        """)


class DangerButton(QPushButton):
    """Bouton pour les actions destructrices (Supprimer, Rejeter)."""

    def __init__(self, icon_or_text, text=None, parent=None):
        if text is not None:
            super().__init__(icon_or_text, text, parent)
        else:
            super().__init__(icon_or_text, parent)

        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        # Rouge universel
        self.setStyleSheet("""
            DangerButton {
                background-color: #F44336;
                color: white;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            DangerButton:hover { background-color: #E53935; }
            DangerButton:pressed { background-color: #D32F2F; }
            DangerButton:disabled { background-color: palette(alternate-base); color: palette(placeholder-text); }
        """)


class ActionButton(QPushButton):
    """Bouton neutre pour les outils (Historique, Scan, etc.). S'adapte au thème !"""

    def __init__(self, icon_name: str = "", text: str = "", parent=None):
        self.icon_name = icon_name  # On mémorise l'icône demandée

        # 1. On utilise le bon constructeur Qt selon la présence d'une icône
        if self.icon_name:
            icon = cast(QIcon, qtawesome.icon(self.icon_name, color=get_icon_color()))
            super().__init__(icon, text, parent)
        else:
            super().__init__(text, parent)

        # 2. Styles
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setStyleSheet("""
            ActionButton {
                background-color: palette(alternate-base);
                color: palette(text);
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                border: 1px solid palette(window);
            }
            ActionButton:hover { 
                background-color: palette(highlight); 
                color: palette(highlighted-text); 
            }
            ActionButton:pressed { background-color: palette(base); }
            ActionButton:disabled { 
                background-color: palette(window);
                color: palette(placeholder-text); 
            }
        """)

    def changeEvent(self, event):
        """Écoute les changements système. Si le thème change, on redessine l'icône !"""
        if event.type() == QEvent.Type.PaletteChange and self.icon_name:
            # ✨ CORRECTION : On caste également l'icône lors du rafraîchissement
            new_icon = cast(QIcon, qtawesome.icon(self.icon_name, color=get_icon_color()))
            self.setIcon(new_icon)

        super().changeEvent(event)


class RoundedPanel(QFrame):
    """Un conteneur avec des bords arrondis pour regrouper visuellement des éléments."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # 👇 Utilise "base" (blanc en light, gris foncé en dark)
        self.setStyleSheet("""
            RoundedPanel {
                background-color: palette(base);
                border-radius: 8px;
                border: 1px solid palette(alternate-base);
            }
        """)


class HeaderLabel(QLabel):
    """Titre standardisé pour les en-têtes d'onglets."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        # Pas besoin de couleur ici, il hérite automatiquement du WindowText
        self.setStyleSheet("""
            font-size: 20px; 
            font-weight: bold; 
            margin-bottom: 20px;
        """)


class MetricCard(RoundedPanel):
    """Carte de statistique prête à l'emploi (titre + grosse valeur)."""

    def __init__(self, title: str, initial_value: str = "0", parent=None):
        super().__init__(parent)
        vbox = QVBoxLayout(self)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_title = QLabel(title)
        # 👇 Utilise placeholder-text pour avoir un effet grisé/atténué naturel
        self.lbl_title.setStyleSheet("color: palette(placeholder-text); font-size: 14px;")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_value = QLabel(initial_value)
        # On garde le vert Anki pour la valeur, car c'est la marque de fabrique
        self.lbl_value.setStyleSheet("color: #4CAF50; font-size: 32px; font-weight: bold;")
        self.lbl_value.setAlignment(Qt.AlignmentFlag.AlignCenter)

        vbox.addWidget(self.lbl_title)
        vbox.addWidget(self.lbl_value)

    def set_value(self, value: str) -> None:
        """Met à jour le gros chiffre."""
        self.lbl_value.setText(value)


class DBComboBox(QComboBox):
    """
    Liste déroulante intelligente qui s'auto-peuple depuis la base de données Peewee.
    Maintient la sélection de l'utilisateur lors du rafraîchissement.
    """

    def __init__(self, model_class, display_field: str = "name", sort_field: str = "name", parent=None):
        """
        Args:
            model_class: La classe du modèle Peewee (ex: DeckModel).
            display_field: Le nom de l'attribut à afficher (ex: "name" ou "display_name").
            sort_field: Le nom de l'attribut servant au tri alphabétique.
        """
        super().__init__(parent)
        self.model_class = model_class
        self.display_field = display_field
        self.sort_field = sort_field

        # Style par défaut
        self.setMinimumSize(100, 32)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)

        self.refresh_data()

    @Slot()
    def refresh_data(self) -> None:
        """Recharge les données depuis SQLite en conservant la sélection active."""
        self.blockSignals(True)
        current_data = self.currentData()
        self.clear()

        # Requête dynamique
        query = self.model_class.select().order_by(getattr(self.model_class, self.sort_field))

        for item in query:
            display_text = getattr(item, self.display_field)
            self.addItem(display_text, userData=item.id)

        # Restauration de la sélection
        if current_data:
            idx = self.findData(current_data)
            if idx >= 0:
                self.setCurrentIndex(idx)

        self.blockSignals(False)
