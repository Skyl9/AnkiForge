import logging
from pathlib import Path
from typing import cast

import qtawesome as qta
from PySide6.QtCore import Slot, QSettings, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QFileDialog,
    QFormLayout,
    QSpinBox,
    QMessageBox,
)

from ankiforge.database.models import NoteModel
from ankiforge.services.cards.media_manager import MediaManager

# 👇 Ajout de RoundedPanel dans les imports
from ankiforge.ui.components.components import HeaderLabel, ActionButton, PrimaryButton, RoundedPanel
from ankiforge.ui.theme import refresh_theme_live
from ankiforge.ui.widgets.toast import show_toast

logger = logging.getLogger(__name__)


class SettingsTab(QWidget):
    """
    Vue de configuration globale de l'application AnkiForge.
    Permet de gérer l'apparence, les dossiers d'export, les comportements automatiques
    ainsi que la maintenance de la base de données (purge, nettoyage des médias).
    """

    def __init__(self) -> None:
        """Initialise l'onglet des paramètres."""
        super().__init__()
        self.settings = QSettings("AnkiForgeOrg", "AnkiForge")

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Initialise et organise les layouts et widgets principaux."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)

        title = HeaderLabel("Paramètres Généraux")
        self.main_layout.addWidget(title)

        self._build_appearance_section()
        self._build_export_section()
        self._build_behavior_section()
        self._build_maintenance_section()

        self.main_layout.addStretch()

        self._build_documentation_section()
        self._build_bottom_actions()

    def _build_appearance_section(self) -> None:
        """Construit le panneau de gestion de l'apparence (Thème clair/sombre)."""
        app_panel = RoundedPanel()
        app_layout = QVBoxLayout(app_panel)
        app_layout.setContentsMargins(15, 15, 15, 15)

        lbl_app = QLabel("1. APPARENCE ET INTERFACE")
        lbl_app.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 10px;")
        app_layout.addWidget(lbl_app)

        form_app = QFormLayout()
        form_app.setHorizontalSpacing(20)

        self.cb_theme = QComboBox()
        self.cb_theme.addItems(["Système (Par défaut)", "Sombre (Dark)", "Clair (Light)"])

        saved_theme = self.settings.value("ui/theme", "Système (Par défaut)")
        self.cb_theme.setCurrentText(str(saved_theme))

        form_app.addRow(self._make_bold_label("Thème de l'application :"), self.cb_theme)
        app_layout.addLayout(form_app)

        self.main_layout.addWidget(app_panel)

    def _build_export_section(self) -> None:
        """Construit le panneau de configuration des dossiers d'exportation."""
        exp_panel = RoundedPanel()
        exp_layout = QVBoxLayout(exp_panel)
        exp_layout.setContentsMargins(15, 15, 15, 15)

        lbl_exp = QLabel("2. EXPORTATION ET FICHIERS")
        lbl_exp.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 10px;")
        exp_layout.addWidget(lbl_exp)

        form_exp = QFormLayout()
        form_exp.setHorizontalSpacing(20)

        path_layout = QHBoxLayout()
        self.le_export_path = QLineEdit()
        self.le_export_path.setPlaceholderText("Sélectionnez un dossier pour vos .apkg")

        default_path = str(Path.home() / "Downloads")
        saved_path = self.settings.value("export/default_directory", default_path)
        self.le_export_path.setText(str(saved_path))

        self.btn_browse = ActionButton("fa5s.folder-open", "")

        path_layout.addWidget(self.le_export_path)
        path_layout.addWidget(self.btn_browse)

        form_exp.addRow(self._make_bold_label("Dossier d'export par défaut :"), path_layout)
        exp_layout.addLayout(form_exp)

        self.main_layout.addWidget(exp_panel)

    def _build_behavior_section(self) -> None:
        """Construit le panneau de configuration des comportements automatiques de l'application."""
        beh_panel = RoundedPanel()
        beh_layout = QVBoxLayout(beh_panel)
        beh_layout.setContentsMargins(15, 15, 15, 15)

        lbl_beh = QLabel("3. COMPORTEMENT")
        lbl_beh.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 10px;")
        beh_layout.addWidget(lbl_beh)

        form_beh = QFormLayout()
        form_beh.setHorizontalSpacing(20)

        self.cb_auto_save = QComboBox()
        self.cb_auto_save.addItems(["Activé", "Désactivé"])
        self.cb_auto_save.setCurrentText(str(self.settings.value("behavior/auto_save", "Activé")))

        form_beh.addRow(self._make_bold_label("Sauvegarde automatique des notes :"), self.cb_auto_save)
        beh_layout.addLayout(form_beh)

        self.main_layout.addWidget(beh_panel)

    def _build_maintenance_section(self) -> None:
        """Construit le panneau des outils de nettoyage et de maintenance de la base de données."""
        maint_panel = RoundedPanel()
        maint_layout = QVBoxLayout(maint_panel)
        maint_layout.setContentsMargins(15, 15, 15, 15)

        lbl_maint = QLabel("4. MAINTENANCE ET NETTOYAGE")
        lbl_maint.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 10px;")
        maint_layout.addWidget(lbl_maint)

        # Sous-section : Médias
        media_layout = QHBoxLayout()
        self.btn_clean_media = ActionButton("fa5s.broom", " Nettoyer les images orphelines")

        lbl_media_desc = QLabel("Libère de l'espace disque en supprimant les images non utilisées.")
        lbl_media_desc.setStyleSheet("color: palette(placeholder-text); font-style: italic; font-size: 11px;")

        media_layout.addWidget(self.btn_clean_media)
        media_layout.addWidget(lbl_media_desc)
        media_layout.addStretch()
        maint_layout.addLayout(media_layout)

        # Sous-section : Historique des notes
        hist_layout = QHBoxLayout()

        self.spin_keep_versions = QSpinBox()
        self.spin_keep_versions.setRange(1, 50)
        self.spin_keep_versions.setValue(cast(int, self.settings.value("maintenance/keep_versions", 5, type=int)))
        self.spin_keep_versions.setPrefix("Garder ")
        self.spin_keep_versions.setSuffix(" versions")

        self.btn_purge_hist = ActionButton("fa5s.history", " Purger l'historique")

        lbl_hist_desc = QLabel("Allège la base de données en supprimant les anciennes sauvegardes.")
        lbl_hist_desc.setStyleSheet("color: palette(placeholder-text); font-style: italic; font-size: 11px;")

        hist_layout.addWidget(self.spin_keep_versions)
        hist_layout.addWidget(self.btn_purge_hist)
        hist_layout.addWidget(lbl_hist_desc)
        hist_layout.addStretch()

        maint_layout.addLayout(hist_layout)
        self.main_layout.addWidget(maint_panel)

    def _build_documentation_section(self) -> None:
        """Construit le panneau de liens vers la documentation externe."""
        doc_panel = RoundedPanel()
        doc_layout = QVBoxLayout(doc_panel)
        doc_layout.setContentsMargins(15, 15, 15, 15)

        lbl_doc = QLabel("5. AIDE ET DOCUMENTATION")
        lbl_doc.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 10px;")
        doc_layout.addWidget(lbl_doc)

        help_layout = QHBoxLayout()
        self.btn_open_doc = ActionButton("fa5s.book", " Ouvrir le guide d'utilisation")

        lbl_doc_desc = QLabel("Consultez les tutoriels sur la création d'Agents et le formatage Markdown/LaTeX.")
        lbl_doc_desc.setStyleSheet("color: palette(placeholder-text); font-style: italic; font-size: 11px;")

        help_layout.addWidget(self.btn_open_doc)
        help_layout.addWidget(lbl_doc_desc)
        help_layout.addStretch()

        doc_layout.addLayout(help_layout)
        self.main_layout.addWidget(doc_panel)

    def _build_bottom_actions(self) -> None:
        """Construit la barre d'action inférieure contenant le bouton de sauvegarde."""
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_save_all = PrimaryButton(qta.icon("fa5s.save", color="white"), " Enregistrer les préférences")
        self.btn_save_all.setMinimumWidth(250)

        btn_layout.addWidget(self.btn_save_all)
        self.main_layout.addLayout(btn_layout)

    def _connect_signals(self) -> None:
        """Centralise le branchement des signaux de l'interface."""
        self.btn_browse.clicked.connect(self.browse_export_path)
        self.btn_save_all.clicked.connect(self.save_all_settings)
        self.btn_clean_media.clicked.connect(self.clean_orphaned_media)
        self.btn_purge_hist.clicked.connect(self.purge_history)
        self.btn_open_doc.clicked.connect(self.open_documentation)

    @staticmethod
    def _make_bold_label(text: str) -> QLabel:
        """Utilitaire interne pour formater rapidement les labels des formulaires."""
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; color: palette(text); font-size: 11px;")
        return lbl

    @Slot()
    def browse_export_path(self) -> None:
        """Ouvre une boîte de dialogue native pour sélectionner un dossier de destination."""
        directory = QFileDialog.getExistingDirectory(self, "Choisir le dossier d'exportation", self.le_export_path.text())
        if directory:
            self.le_export_path.setText(directory)

    @Slot()
    def refresh_data(self) -> None:
        """Contrat MainWindow : Point d'entrée pour rafraîchir l'onglet (non utilisé ici)."""
        pass

    @Slot()
    def save_all_settings(self) -> None:
        """Sauvegarde l'ensemble des paramètres modifiés dans les QSettings et les applique."""
        self.settings.setValue("ui/theme", self.cb_theme.currentText())
        self.settings.setValue("export/default_directory", self.le_export_path.text())
        self.settings.setValue("behavior/auto_save", self.cb_auto_save.currentText())
        self.settings.setValue("maintenance/keep_versions", self.spin_keep_versions.value())

        self.settings.sync()
        refresh_theme_live()

        logger.info("Préférences utilisateur enregistrées et appliquées.")
        show_toast(self, "Préférences enregistrées et appliquées !")

    @Slot()
    def clean_orphaned_media(self) -> None:
        """Recherche et supprime définitivement les fichiers médias non utilisés."""
        reply = QMessageBox.question(
            self,
            "Nettoyage des médias",
            "Voulez-vous rechercher et supprimer définitivement du disque les images qui ne sont plus associées à aucune note ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            manager = MediaManager()
            deleted_count = manager.clean_orphaned_media()
            if deleted_count > 0:
                logger.info(f"Nettoyage des médias terminé : {deleted_count} fichiers supprimés.")
                show_toast(self, f"Nettoyage terminé : {deleted_count} fichier(s) supprimé(s) !")
            else:
                logger.info("Nettoyage des médias : aucun fichier orphelin trouvé.")
                show_toast(self, "Votre dossier média est déjà parfaitement propre.")

    @Slot()
    def purge_history(self) -> None:
        """Supprime les versions obsolètes des notes pour libérer de l'espace en base de données."""
        keep_last = self.spin_keep_versions.value()

        reply = QMessageBox.question(
            self,
            "Purge de l'historique",
            f"Voulez-vous vraiment supprimer définitivement les anciennes versions de vos notes pour n'en garder que {keep_last} par note ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.settings.setValue("maintenance/keep_versions", keep_last)

            deleted_count = NoteModel.purge_old_versions(keep_last=keep_last)
            if deleted_count > 0:
                logger.info(f"Purge de l'historique terminée : {deleted_count} anciennes versions supprimées.")
                show_toast(self, f"Purge terminée : {deleted_count} ancienne(s) version(s) supprimée(s) !")
            else:
                logger.info("Purge de l'historique : aucune version obsolète à purger.")
                show_toast(self, "Aucune version obsolète à purger.")

    @Slot()
    def open_documentation(self) -> None:
        """Ouvre la documentation officielle en ligne via le navigateur web par défaut."""
        QDesktopServices.openUrl(QUrl("https://github.com/votre-compte/AnkiForge/wiki"))
