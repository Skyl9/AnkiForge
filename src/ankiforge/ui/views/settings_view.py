import qtawesome as qta
from PySide6.QtCore import Slot, QSettings, Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QComboBox, QLineEdit, QFileDialog, QFormLayout)
from pathlib import Path

# 👇 Ajout de RoundedPanel dans les imports
from ankiforge.ui.components.components import HeaderLabel, ActionButton, PrimaryButton, RoundedPanel
from ankiforge.ui.theme import refresh_theme_live
from ankiforge.ui.widgets.toast import show_toast


class SettingsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        # On récupère l'instance QSettings (identique à celle de MainWindow)
        self.settings = QSettings("AnkiForgeOrg", "AnkiForge")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        title = HeaderLabel("Paramètres Généraux")
        layout.addWidget(title)

        # ==========================================
        # SECTION 1 : APPARENCE
        # ==========================================
        app_panel = RoundedPanel()
        app_layout = QVBoxLayout(app_panel)
        app_layout.setContentsMargins(15, 15, 15, 15)

        lbl_app = QLabel("1. APPARENCE ET INTERFACE")
        lbl_app.setStyleSheet(
            "font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 10px;")
        app_layout.addWidget(lbl_app)

        form_app = QFormLayout()
        form_app.setHorizontalSpacing(20)

        self.cb_theme = QComboBox()
        self.cb_theme.addItems(["Système (Par défaut)", "Sombre (Dark)", "Clair (Light)"])

        # Charger la valeur sauvegardée
        saved_theme = self.settings.value("ui/theme", "Système (Par défaut)")
        self.cb_theme.setCurrentText(saved_theme)

        form_app.addRow(self._make_bold_label("Thème de l'application :"), self.cb_theme)
        app_layout.addLayout(form_app)
        layout.addWidget(app_panel)

        # ==========================================
        # SECTION 2 : EXPORTATION
        # ==========================================
        exp_panel = RoundedPanel()
        exp_layout = QVBoxLayout(exp_panel)
        exp_layout.setContentsMargins(15, 15, 15, 15)

        lbl_exp = QLabel("2. EXPORTATION ET FICHIERS")
        lbl_exp.setStyleSheet(
            "font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 10px;")
        exp_layout.addWidget(lbl_exp)

        form_exp = QFormLayout()
        form_exp.setHorizontalSpacing(20)

        path_layout = QHBoxLayout()
        self.le_export_path = QLineEdit()
        self.le_export_path.setPlaceholderText("Sélectionnez un dossier pour vos .apkg")

        # Charger le chemin sauvegardé ou mettre le dossier 'Downloads' par défaut
        default_path = str(Path.home() / "Downloads")
        saved_path = self.settings.value("export/default_directory", default_path)
        self.le_export_path.setText(saved_path)

        self.btn_browse = ActionButton('fa5s.folder-open', "")
        self.btn_browse.clicked.connect(self.browse_export_path)

        path_layout.addWidget(self.le_export_path)
        path_layout.addWidget(self.btn_browse)

        form_exp.addRow(self._make_bold_label("Dossier d'export par défaut :"), path_layout)
        exp_layout.addLayout(form_exp)
        layout.addWidget(exp_panel)

        # ==========================================
        # SECTION 3 : COMPORTEMENT
        # ==========================================
        beh_panel = RoundedPanel()
        beh_layout = QVBoxLayout(beh_panel)
        beh_layout.setContentsMargins(15, 15, 15, 15)

        lbl_beh = QLabel("3. COMPORTEMENT")
        lbl_beh.setStyleSheet(
            "font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 10px;")
        beh_layout.addWidget(lbl_beh)

        form_beh = QFormLayout()
        form_beh.setHorizontalSpacing(20)

        self.cb_auto_save = QComboBox()
        self.cb_auto_save.addItems(["Activé", "Désactivé"])
        self.cb_auto_save.setCurrentText(self.settings.value("behavior/auto_save", "Activé"))

        form_beh.addRow(self._make_bold_label("Sauvegarde automatique des notes :"), self.cb_auto_save)
        beh_layout.addLayout(form_beh)
        layout.addWidget(beh_panel)

        layout.addStretch()

        # Bouton de sauvegarde global (aligné à droite)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_save_all = PrimaryButton(qta.icon('fa5s.save', color='white'), " Enregistrer les préférences")
        self.btn_save_all.clicked.connect(self.save_all_settings)
        self.btn_save_all.setMinimumWidth(250)
        btn_layout.addWidget(self.btn_save_all)

        layout.addLayout(btn_layout)

    def _make_bold_label(self, text: str) -> QLabel:
        """Utilitaire pour formater les labels des formulaires."""
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; color: palette(text); font-size: 11px;")
        return lbl

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
        self.settings.sync()
        refresh_theme_live()

        show_toast(self, "Préférences enregistrées et appliquées !")

    @Slot()
    def refresh_data(self) -> None:
        """Contrat MainWindow."""
        pass