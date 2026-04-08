import qtawesome as qta
from PySide6.QtCore import Slot, QSettings, Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QComboBox, QLineEdit, QFileDialog, QFormLayout, QSpinBox, QMessageBox)
from pathlib import Path

from ankiforge.database.models import NoteModel
from ankiforge.services.cards.media_manager import MediaManager
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

        # ==========================================
        # SECTION 4 : MAINTENANCE ET NETTOYAGE
        # ==========================================
        maint_panel = RoundedPanel()
        maint_layout = QVBoxLayout(maint_panel)
        maint_layout.setContentsMargins(15, 15, 15, 15)

        lbl_maint = QLabel("4. MAINTENANCE ET NETTOYAGE")
        lbl_maint.setStyleSheet(
            "font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 10px;"
        )
        maint_layout.addWidget(lbl_maint)

        # --- Sous-section : Médias ---
        media_layout = QHBoxLayout()
        self.btn_clean_media = ActionButton('fa5s.broom', " Nettoyer les images orphelines")
        self.btn_clean_media.clicked.connect(self.clean_orphaned_media)

        lbl_media_desc = QLabel("Libère de l'espace disque en supprimant les images non utilisées.")
        lbl_media_desc.setStyleSheet("color: palette(placeholder-text); font-style: italic; font-size: 11px;")

        media_layout.addWidget(self.btn_clean_media)
        media_layout.addWidget(lbl_media_desc)
        media_layout.addStretch()
        maint_layout.addLayout(media_layout)

        # --- Sous-section : Historique des notes ---
        hist_layout = QHBoxLayout()

        self.spin_keep_versions = QSpinBox()
        self.spin_keep_versions.setRange(1, 50)
        # On charge la préférence utilisateur ou on garde 5 par défaut
        self.spin_keep_versions.setValue(self.settings.value("maintenance/keep_versions", 5, type=int))
        self.spin_keep_versions.setPrefix("Garder ")
        self.spin_keep_versions.setSuffix(" versions")

        self.btn_purge_hist = ActionButton('fa5s.history', " Purger l'historique")
        self.btn_purge_hist.clicked.connect(self.purge_history)

        lbl_hist_desc = QLabel("Allège la base de données en supprimant les anciennes sauvegardes.")
        lbl_hist_desc.setStyleSheet("color: palette(placeholder-text); font-style: italic; font-size: 11px;")

        hist_layout.addWidget(self.spin_keep_versions)
        hist_layout.addWidget(self.btn_purge_hist)
        hist_layout.addWidget(lbl_hist_desc)
        hist_layout.addStretch()
        maint_layout.addLayout(hist_layout)
        layout.addWidget(maint_panel)



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

    @Slot()
    def save_all_settings(self):
        """Sauvegarde toutes les options dans QSettings."""
        self.settings.setValue("ui/theme", self.cb_theme.currentText())
        self.settings.setValue("export/default_directory", self.le_export_path.text())
        self.settings.setValue("behavior/auto_save", self.cb_auto_save.currentText())
        # 👇 NOUVELLE LIGNE 👇
        self.settings.setValue("maintenance/keep_versions", self.spin_keep_versions.value())

        self.settings.sync()
        refresh_theme_live()

        show_toast(self, "Préférences enregistrées et appliquées !")

    @Slot()
    def clean_orphaned_media(self) -> None:
        """Déclenche le nettoyage des images orphelines avec confirmation."""
        reply = QMessageBox.question(
            self, "Nettoyage des médias",
            "Voulez-vous rechercher et supprimer définitivement du disque les images qui ne sont plus associées à aucune note ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            manager = MediaManager()
            deleted_count = manager.clean_orphaned_media()
            if deleted_count > 0:
                show_toast(self, f"Nettoyage terminé : {deleted_count} fichier(s) supprimé(s) !")
            else:
                show_toast(self, "Votre dossier média est déjà parfaitement propre.")

    @Slot()
    def purge_history(self) -> None:
        """Déclenche la purge de l'historique des notes avec confirmation."""
        keep_last = self.spin_keep_versions.value()

        reply = QMessageBox.question(
            self, "Purge de l'historique",
            f"Voulez-vous vraiment supprimer définitivement les anciennes versions de vos notes pour n'en garder que {keep_last} par note ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # On enregistre la valeur choisie par sécurité
            self.settings.setValue("maintenance/keep_versions", keep_last)

            deleted_count = NoteModel.purge_old_versions(keep_last=keep_last)
            if deleted_count > 0:
                show_toast(self, f"Purge terminée : {deleted_count} ancienne(s) version(s) supprimée(s) !")
            else:
                show_toast(self, "Aucune version obsolète à purger.")
