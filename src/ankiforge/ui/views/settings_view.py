from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Slot

from ankiforge.ui.components.components import HeaderLabel


class SettingsTab(QWidget):
    def __init__(self, main_manager=None) -> None:
        super().__init__()

        # main_manager est là au cas où l'app l'injecte, mais on ne l'utilise pas pour l'IA
        self.manager = main_manager

        layout = QVBoxLayout(self)

        title = HeaderLabel("Paramètres Généraux")
        layout.addWidget(title)

        subtitle = QLabel(
            "Les paramètres globaux de l'application (Dossier d'export par défaut, Thème visuel, Options d'affichage) apparaîtront ici prochainement.")
        subtitle.setStyleSheet("color: palette(placeholder-text); margin-top: 20px; font-style: italic;")
        subtitle.setWordWrap(True)

        layout.addWidget(subtitle)
        layout.addStretch()

    @Slot()
    def refresh_data(self) -> None:
        """Contrat MainWindow : rien à rafraîchir pour l'instant."""
        pass