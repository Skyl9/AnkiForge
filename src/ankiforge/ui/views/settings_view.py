import qtawesome as qta
from PySide6.QtCore import Slot, QSettings, Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QComboBox, QLineEdit, QFileDialog, QGroupBox, QFormLayout)
from pathlib import Path

from ankiforge.ui.components.components import HeaderLabel, ActionButton, PrimaryButton
from ankiforge.ui.widgets.toast import show_toast


class SettingsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        # On récupère l'instance QSettings (identique à celle de MainWindow)
        self.settings = QSettings("AnkiForgeOrg", "AnkiForge")

        layout = QVBoxLayout(self)
        title = HeaderLabel("Paramètres Généraux")
        layout.addWidget(title)

        # ==========================================
        # SECTION 1 : APPARENCE
        # ==========================================
        appearance_group = QGroupBox("Apparence et Interface")
        appearance_layout = QFormLayout(appearance_group)

        self.cb_theme = QComboBox()
        self.cb_theme.addItems(["Système (Par défaut)", "Sombre (Dark)", "Clair (Light)"])

        # Charger la valeur sauvegardée
        saved_theme = self.settings.value("ui/theme", "Système (Par défaut)")
        self.cb_theme.setCurrentText(saved_theme)

        appearance_layout.addRow("Thème de l'application :", self.cb_theme)
        layout.addWidget(appearance_group)

        # ==========================================
        # SECTION 2 : EXPORTATION
        # ==========================================
        export_group = QGroupBox("Exportation et Fichiers")
        export_layout = QFormLayout(export_group)

        path_layout = QHBoxLayout()
        self.le_export_path = QLineEdit()
        self.le_export_path.setPlaceholderText("Sélectionnez un dossier pour vos .apkg")

        # Charger le chemin sauvegardé ou mettre le dossier 'Downloads' par défaut
        default_path = str(Path.home() / "Downloads")
        saved_path = self.settings.value("export/default_directory", default_path)
        self.le_export_path.setText(saved_path)

        self.btn_browse = ActionButton(qta.icon('fa5s.folder-open'), "")
        self.btn_browse.clicked.connect(self.browse_export_path)

        path_layout.addWidget(self.le_export_path)
        path_layout.addWidget(self.btn_browse)

        export_layout.addRow("Dossier d'export par défaut :", path_layout)
        layout.addWidget(export_group)

        # ==========================================
        # SECTION 3 : COMPORTEMENT
        # ==========================================
        behavior_group = QGroupBox("Comportement")
        behavior_layout = QFormLayout(behavior_group)

        self.cb_auto_save = QComboBox()
        self.cb_auto_save.addItems(["Activé", "Désactivé"])
        self.cb_auto_save.setCurrentText(self.settings.value("behavior/auto_save", "Activé"))
        behavior_layout.addRow("Sauvegarde automatique des notes :", self.cb_auto_save)

        layout.addWidget(behavior_group)

        layout.addStretch()

        # Bouton de sauvegarde global
        self.btn_save_all = PrimaryButton(qta.icon('fa5s.save', color='white'), " Enregistrer les préférences")
        self.btn_save_all.clicked.connect(self.save_all_settings)
        layout.addWidget(self.btn_save_all, alignment=Qt.AlignmentFlag.AlignRight)

    @Slot()
    def browse_export_path(self):
        """Ouvre une boîte de dialogue pour choisir le dossier d'export."""
        directory = QFileDialog.getExistingDirectory(self, "Choisir le dossier d'exportation",
                                                     self.le_export_path.text())
        if directory:
            self.le_export_path.setText(directory)

    @Slot()
    def save_all_settings(self):
        """Sauvegarde toutes les options dans QSettings."""
        self.settings.setValue("ui/theme", self.cb_theme.currentText())
        self.settings.setValue("export/default_directory", self.le_export_path.text())
        self.settings.setValue("behavior/auto_save", self.cb_auto_save.currentText())

        show_toast(self, "Préférences enregistrées !")

        # Optionnel : Si tu veux appliquer le thème immédiatement,
        # il faudra émettre un signal vers la MainWindow ici.

    @Slot()
    def refresh_data(self) -> None:
        """Contrat MainWindow."""
        pass