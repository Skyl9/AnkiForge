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
from ankiforge.ui.components.components import HeaderLabel, ActionButton, PrimaryButton, RoundedPanel
from ankiforge.ui.theme import refresh_theme_live
from ankiforge.ui.widgets.toast import show_toast

logger = logging.getLogger(__name__)


class SettingsTab(QWidget):
    """
    Global configuration view for the AnkiForge application.
    Allows managing appearance, language, export folders, automatic behaviors
    as well as database maintenance (purge, media cleaning).
    """

    def __init__(self) -> None:
        """Initializes the settings tab."""
        super().__init__()
        self.settings = QSettings("AnkiForgeOrg", "AnkiForge")
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Initializes and organizes main layouts and widgets."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)

        title = HeaderLabel(self.tr("General Settings"))
        self.main_layout.addWidget(title)

        self._build_appearance_section()
        self._build_export_section()
        self._build_behavior_section()
        self._build_maintenance_section()

        self.main_layout.addStretch()

        self._build_documentation_section()
        self._build_bottom_actions()

    def _build_appearance_section(self) -> None:
        """Builds the appearance management panel (Light/Dark theme)."""
        app_panel = RoundedPanel()
        app_layout = QVBoxLayout(app_panel)
        app_layout.setContentsMargins(15, 15, 15, 15)

        lbl_app = QLabel(self.tr("1. APPEARANCE AND INTERFACE"))
        lbl_app.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 10px;")
        app_layout.addWidget(lbl_app)

        form_app = QFormLayout()
        form_app.setHorizontalSpacing(20)

        # THEME
        self.cb_theme = QComboBox()
        self.cb_theme.addItems([self.tr("System (Default)"), self.tr("Dark"), self.tr("Light")])
        saved_theme = self.settings.value("ui/theme", self.tr("System (Default)"))
        self.cb_theme.setCurrentText(str(saved_theme))
        form_app.addRow(self._make_bold_label(self.tr("Application theme:")), self.cb_theme)

        # Language
        self.cb_language = QComboBox()
        self.cb_language.addItems(["English", "Français"])  # On ne traduit pas les noms des langues
        saved_lang = self.settings.value("ui/language", "English")
        self.cb_language.setCurrentText(str(saved_lang))
        form_app.addRow(self._make_bold_label(self.tr("Application language:")), self.cb_language)

        app_layout.addLayout(form_app)
        self.main_layout.addWidget(app_panel)

    def _build_export_section(self) -> None:
        exp_panel = RoundedPanel()
        exp_layout = QVBoxLayout(exp_panel)
        exp_layout.setContentsMargins(15, 15, 15, 15)

        lbl_exp = QLabel(self.tr("2. EXPORT AND FILES"))
        lbl_exp.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 10px;")
        exp_layout.addWidget(lbl_exp)

        form_exp = QFormLayout()
        form_exp.setHorizontalSpacing(20)

        path_layout = QHBoxLayout()
        self.le_export_path = QLineEdit()
        self.le_export_path.setPlaceholderText(self.tr("Select a folder for your .apkg"))

        default_path = str(Path.home() / "Downloads")
        saved_path = self.settings.value("export/default_directory", default_path)
        self.le_export_path.setText(str(saved_path))

        self.btn_browse = ActionButton("fa5s.folder-open", "")

        path_layout.addWidget(self.le_export_path)
        path_layout.addWidget(self.btn_browse)

        form_exp.addRow(self._make_bold_label(self.tr("Default export folder:")), path_layout)
        exp_layout.addLayout(form_exp)
        self.main_layout.addWidget(exp_panel)

    def _build_behavior_section(self) -> None:
        """Builds the automatic behaviors configuration panel."""
        beh_panel = RoundedPanel()
        beh_layout = QVBoxLayout(beh_panel)
        beh_layout.setContentsMargins(15, 15, 15, 15)

        lbl_beh = QLabel(self.tr("3. BEHAVIOR"))
        lbl_beh.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 10px;")
        beh_layout.addWidget(lbl_beh)

        form_beh = QFormLayout()
        form_beh.setHorizontalSpacing(20)

        self.cb_auto_save = QComboBox()
        self.cb_auto_save.addItems([self.tr("Enabled"), self.tr("Disabled")])
        self.cb_auto_save.setCurrentText(str(self.settings.value("behavior/auto_save", self.tr("Enabled"))))

        form_beh.addRow(self._make_bold_label(self.tr("Automatic note saving:")), self.cb_auto_save)
        beh_layout.addLayout(form_beh)
        self.main_layout.addWidget(beh_panel)

    def _build_maintenance_section(self) -> None:
        """Builds the database cleaning and maintenance tools panel."""
        maint_panel = RoundedPanel()
        maint_layout = QVBoxLayout(maint_panel)
        maint_layout.setContentsMargins(15, 15, 15, 15)

        lbl_maint = QLabel(self.tr("4. MAINTENANCE AND CLEANING"))
        lbl_maint.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 10px;")
        maint_layout.addWidget(lbl_maint)

        # Sub-section: Media
        media_layout = QHBoxLayout()
        self.btn_clean_media = ActionButton("fa5s.broom", self.tr(" Clean orphaned media"))
        lbl_media_desc = QLabel(self.tr("Frees disk space by deleting unused images."))
        lbl_media_desc.setStyleSheet("color: palette(placeholder-text); font-style: italic; font-size: 11px;")

        media_layout.addWidget(self.btn_clean_media)
        media_layout.addWidget(lbl_media_desc)
        media_layout.addStretch()
        maint_layout.addLayout(media_layout)

        # Sub-section: Note history
        hist_layout = QHBoxLayout()
        self.spin_keep_versions = QSpinBox()
        self.spin_keep_versions.setRange(1, 50)
        self.spin_keep_versions.setValue(cast(int, self.settings.value("maintenance/keep_versions", 5, type=int)))
        self.spin_keep_versions.setPrefix(self.tr("Keep "))
        self.spin_keep_versions.setSuffix(self.tr(" versions"))

        self.btn_purge_hist = ActionButton("fa5s.history", self.tr(" Purge history"))
        lbl_hist_desc = QLabel(self.tr("Lightens the database by deleting old backups."))
        lbl_hist_desc.setStyleSheet("color: palette(placeholder-text); font-style: italic; font-size: 11px;")

        hist_layout.addWidget(self.spin_keep_versions)
        hist_layout.addWidget(self.btn_purge_hist)
        hist_layout.addWidget(lbl_hist_desc)
        hist_layout.addStretch()

        maint_layout.addLayout(hist_layout)
        self.main_layout.addWidget(maint_panel)

    def _build_documentation_section(self) -> None:
        """Builds the documentation section panel."""
        doc_panel = RoundedPanel()
        doc_layout = QVBoxLayout(doc_panel)
        doc_layout.setContentsMargins(15, 15, 15, 15)

        lbl_doc = QLabel(self.tr("5. HELP AND DOCUMENTATION"))
        lbl_doc.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 10px;")
        doc_layout.addWidget(lbl_doc)

        help_layout = QHBoxLayout()
        self.btn_open_doc = ActionButton("fa5s.book", self.tr(" Open user guide"))
        lbl_doc_desc = QLabel(self.tr("Check tutorials on Agent creation and Markdown/LaTeX formatting."))
        lbl_doc_desc.setStyleSheet("color: palette(placeholder-text); font-style: italic; font-size: 11px;")

        help_layout.addWidget(self.btn_open_doc)
        help_layout.addWidget(lbl_doc_desc)
        help_layout.addStretch()

        doc_layout.addLayout(help_layout)
        self.main_layout.addWidget(doc_panel)

    def _build_bottom_actions(self) -> None:
        """Builds the bottom action bar containing the save button."""
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_save_all = PrimaryButton(qta.icon("fa5s.save", color="white"), self.tr(" Save preferences"))
        self.btn_save_all.setMinimumWidth(250)

        btn_layout.addWidget(self.btn_save_all)
        self.main_layout.addLayout(btn_layout)

    def _connect_signals(self) -> None:
        """Centralizes UI signal connections."""
        self.btn_browse.clicked.connect(self.browse_export_path)
        self.btn_save_all.clicked.connect(self.save_all_settings)
        self.btn_clean_media.clicked.connect(self.clean_orphaned_media)
        self.btn_purge_hist.clicked.connect(self.purge_history)
        self.btn_open_doc.clicked.connect(self.open_documentation)

    @staticmethod
    def _make_bold_label(text: str) -> QLabel:
        """Internal utility to quickly format form labels."""
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; color: palette(text); font-size: 11px;")
        return lbl

    @Slot()
    def browse_export_path(self) -> None:
        """Opens a native dialog to select a destination folder."""
        directory = QFileDialog.getExistingDirectory(self, self.tr("Choose export directory"), self.le_export_path.text())
        if directory:
            self.le_export_path.setText(directory)

    @Slot()
    def refresh_data(self) -> None:
        """MainWindow contract: Entry point to refresh the tab (not used here)."""
        pass

    @Slot()
    def save_all_settings(self) -> None:
        """Saves all modified settings in QSettings and applies them."""
        old_lang = str(self.settings.value("ui/language", "English"))
        new_lang = self.cb_language.currentText()

        self.settings.setValue("ui/theme", self.cb_theme.currentText())
        self.settings.setValue("ui/language", new_lang)
        self.settings.setValue("export/default_directory", self.le_export_path.text())
        self.settings.setValue("behavior/auto_save", self.cb_auto_save.currentText())
        self.settings.setValue("maintenance/keep_versions", self.spin_keep_versions.value())

        self.settings.sync()
        refresh_theme_live()

        logger.info("User preferences saved and applied.")
        show_toast(self, self.tr("Preferences saved and applied!"))

        if old_lang != new_lang:
            QMessageBox.information(self, self.tr("Restart Required"), self.tr("Please restart AnkiForge to apply the new language."))

    @Slot()
    def clean_orphaned_media(self) -> None:
        """Finds and permanently deletes unused media files."""
        reply = QMessageBox.question(
            self,
            self.tr("Media cleaning"),
            self.tr("Do you want to find and permanently delete images that are no longer associated with any note?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            manager = MediaManager()
            deleted_count = manager.clean_orphaned_media()
            if deleted_count > 0:
                logger.info(f"Media cleaning finished: {deleted_count} files deleted.")
                show_toast(self, self.tr("Cleaning finished: {0} file(s) deleted!").format(deleted_count))
            else:
                logger.info("Media cleaning: no orphaned files found.")
                show_toast(self, self.tr("Your media folder is already perfectly clean."))

    @Slot()
    def purge_history(self) -> None:
        """Deletes obsolete note versions to free database space."""
        keep_last = self.spin_keep_versions.value()

        reply = QMessageBox.question(
            self,
            self.tr("History purge"),
            self.tr("Do you really want to permanently delete old versions of your notes to keep only {0} per note?").format(keep_last),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.settings.setValue("maintenance/keep_versions", keep_last)

            deleted_count = NoteModel.purge_old_versions(keep_last=keep_last)
            if deleted_count > 0:
                logger.info(f"History purge finished: {deleted_count} old versions deleted.")
                show_toast(self, self.tr("Purge finished: {0} old version(s) deleted!").format(deleted_count))
            else:
                logger.info("History purge: no obsolete versions to purge.")
                show_toast(self, self.tr("No obsolete versions to purge."))

    @Slot()
    def open_documentation(self) -> None:
        """Ouvre la documentation officielle en ligne via le navigateur web par défaut."""
        QDesktopServices.openUrl(QUrl("https://github.com/votre-compte/AnkiForge/wiki"))
