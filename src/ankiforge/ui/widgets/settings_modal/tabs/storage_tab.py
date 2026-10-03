import datetime
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import ankiforge.ui.widgets.settings_modal as settings_pkg
from ankiforge.database.backup import (
    list_profile_backups,
    restart_application,
    restore_granular_backup,
)
from ankiforge.database.maintenance import optimize_database
from ankiforge.database.models import (
    CardModel,
    NoteModel,
    NoteVersionModel,
)
from ankiforge.services.profile_manager import ProfileManager
from ankiforge.ui.components import (
    DangerButton,
    PrimaryButton,
    SecondaryButton,
)
from ankiforge.ui.components.buttons import apply_compact_style
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.settings_modal.components.settings_card import SettingsCard
from ankiforge.ui.widgets.settings_modal.components.storage_metric_card import StorageMetricCard
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon
from ankiforge.utils.paths import get_active_profile, get_app_data_dir, get_media_dir

logger = logging.getLogger(__name__)


class _MaintenanceSignals(QObject):
    finished = Signal()
    failed = Signal(str)


class _DatabaseMaintenanceWorker(QRunnable):
    def __init__(self, db_path: str) -> None:
        super().__init__()
        self.db_path = db_path
        self.signals = _MaintenanceSignals()

    def run(self) -> None:
        try:
            optimize_database(Path(self.db_path))
        except Exception as error:
            logger.error("Échec de la maintenance SQLite : %s", error, exc_info=True)
            self.signals.failed.emit(str(error))
            return
        self.signals.finished.emit()


class StorageMaintenanceTab(QWidget):
    """Onglet Métrologie Réelle, Optimisation SQLite, Nettoyage Médias et Backups."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._maintenance_worker: _DatabaseMaintenanceWorker | None = None
        self._setup_ui()
        QTimer.singleShot(0, self.refresh_metrics)

    def _setup_ui(self) -> None:
        from PySide6.QtWidgets import QFrame, QScrollArea

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background: transparent; border: none;")

        self.content_widget = QWidget()
        layout = QVBoxLayout(self.content_widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # ── SECTION 1 : COCKPIT DU STOCKAGE RÉEL ─────────────────────────────
        from ankiforge.utils.environment import get_environment_display_name

        self.lbl_sec_stat = QLabel(f"STOCKAGE & BDD — ENVIRONNEMENT : {get_environment_display_name().upper()} ({get_app_data_dir()})")
        self.lbl_sec_stat.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(self.lbl_sec_stat)

        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(10)

        self.c_db = StorageMetricCard("Base de données SQLite", "0 Ko", "ph.database", "WAL Actif • 0 notes")
        self.c_media = StorageMetricCard("Stockage Médias", "0 Mo", "ph.images", "0 fichiers médias")
        self.c_tm = StorageMetricCard("Time Machine", "0 versions", "ph.clock-counter-clockwise", "Historique actif")

        metrics_grid.addWidget(self.c_db, 0, 0)
        metrics_grid.addWidget(self.c_media, 0, 1)
        metrics_grid.addWidget(self.c_tm, 0, 2)
        layout.addLayout(metrics_grid)

        # ── SECTION 2 : ACTIONS D'ENTRETIEN RÉELLES ──────────────────────────
        self.lbl_sec_act = QLabel("ACTIONS D'ENTRETIEN ET D'OPTIMISATION")
        self.lbl_sec_act.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        layout.addWidget(self.lbl_sec_act)

        self.card_act = SettingsCard()
        act_layout = QVBoxLayout(self.card_act)
        act_layout.setContentsMargins(14, 12, 14, 12)
        act_layout.setSpacing(10)

        row_actions1 = QHBoxLayout()
        row_actions1.setSpacing(10)

        self.btn_vacuum = SecondaryButton("Optimiser la base de données (VACUUM)")
        self.btn_vacuum.setIcon(load_phosphor_icon("ph.lightning", color=DesignTokens.COLOR_YELLOW))
        self.btn_vacuum.clicked.connect(self._run_vacuum)
        row_actions1.addWidget(self.btn_vacuum, 1)

        self.btn_clean_media = SecondaryButton("Nettoyer les images orphelines")
        self.btn_clean_media.setIcon(load_phosphor_icon("ph.broom", color=DesignTokens.COLOR_BLUE))
        self.btn_clean_media.clicked.connect(self._clean_orphan_media)
        row_actions1.addWidget(self.btn_clean_media, 1)

        act_layout.addLayout(row_actions1)

        row_actions2 = QHBoxLayout()
        row_actions2.setSpacing(10)

        self.btn_purge_history = DangerButton("Purger l'historique (> 30 jours)", ghost=True)
        self.btn_purge_history.setIcon(load_phosphor_icon("ph.clock-counter-clockwise", color=DesignTokens.COLOR_RED))
        self.btn_purge_history.clicked.connect(self._purge_history)
        row_actions2.addWidget(self.btn_purge_history, 1)

        self.btn_clear_cache = SecondaryButton("Vider les fichiers temporaires et cache")
        self.btn_clear_cache.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.TEXT_MUTED))
        self.btn_clear_cache.clicked.connect(self._clear_cache)
        row_actions2.addWidget(self.btn_clear_cache, 1)

        act_layout.addLayout(row_actions2)

        row_actions3 = QHBoxLayout()
        row_actions3.setSpacing(10)

        self.btn_purge_tts = SecondaryButton("Purger le cache audio TTS")
        self.btn_purge_tts.setIcon(load_phosphor_icon("ph.speaker-high", color=DesignTokens.COLOR_PURPLE))
        self.btn_purge_tts.clicked.connect(self._purge_tts_cache)
        row_actions3.addWidget(self.btn_purge_tts, 1)

        self.btn_transfer = SecondaryButton("Transférer du contenu inter-profils...")
        self.btn_transfer.setIcon(load_phosphor_icon("ph.arrows-left-right", color=DesignTokens.ACCENT_PRIMARY))
        self.btn_transfer.clicked.connect(self._open_profile_transfer)
        row_actions3.addWidget(self.btn_transfer, 1)

        act_layout.addLayout(row_actions3)

        from ankiforge.utils.environment import get_app_qsettings

        settings = get_app_qsettings()
        clean_on_exit = settings.value("storage/clean_media_on_exit", False, type=bool)

        self.chk_clean_media_on_exit = QCheckBox("Nettoyer automatiquement les médias orphelins à la fermeture de l'application")
        self.chk_clean_media_on_exit.setChecked(bool(clean_on_exit))
        self.chk_clean_media_on_exit.toggled.connect(self._on_clean_media_on_exit_toggled)
        self.chk_clean_media_on_exit.setStyleSheet(f"""
            QCheckBox {{
                color: {DesignTokens.TEXT_SECONDARY};
                font-size: 11px;
                spacing: 8px;
                margin-top: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                background-color: {DesignTokens.BG_INPUT};
            }}
            QCheckBox::indicator:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QCheckBox::indicator:checked {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        act_layout.addWidget(self.chk_clean_media_on_exit)

        layout.addWidget(self.card_act)

        # ── SECTION 3 : SAUVEGARDES DE SÉCURITÉ (BACKUPS) ────────────────────
        self.lbl_sec_bku = QLabel("SAUVEGARDES DE SÉCURITÉ DU PROFIL (INSTANTANÉS)")
        self.lbl_sec_bku.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        layout.addWidget(self.lbl_sec_bku)

        self.card_bku = SettingsCard()
        bku_layout = QVBoxLayout(self.card_bku)
        bku_layout.setContentsMargins(14, 12, 14, 12)
        bku_layout.setSpacing(8)

        top_bku_row = QHBoxLayout()
        self.btn_snapshot = PrimaryButton("Créer un instantané immédiat (Backup)")
        self.btn_snapshot.setIcon(load_on_accent_icon("ph.floppy-disk"))
        self.btn_snapshot.setFixedHeight(28)
        self.btn_snapshot.clicked.connect(self._create_snapshot)
        top_bku_row.addWidget(self.btn_snapshot)

        top_bku_row.addStretch()

        self.btn_open_backup_folder = SecondaryButton("Ouvrir le dossier des sauvegardes")
        self.btn_open_backup_folder.setIcon(load_phosphor_icon("ph.folder", color=DesignTokens.TEXT_PRIMARY))
        self.btn_open_backup_folder.setFixedHeight(28)
        self.btn_open_backup_folder.clicked.connect(self._open_backup_folder)
        top_bku_row.addWidget(self.btn_open_backup_folder)

        bku_layout.addLayout(top_bku_row)

        self.lbl_recent_backups = QLabel("Historique des sauvegardes de sécurité")
        self.lbl_recent_backups.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; margin-top: 4px;")
        bku_layout.addWidget(self.lbl_recent_backups)

        self.table_backups = QTableWidget(0, 5)
        self.table_backups.setHorizontalHeaderLabels(["Date & Heure", "Type", "Taille", "Intégrité", "Action"])
        self.table_backups.horizontalHeader().setStretchLastSection(False)
        self.table_backups.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_backups.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_backups.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_backups.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_backups.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_backups.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_backups.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_backups.verticalHeader().setVisible(False)
        self.table_backups.verticalHeader().setDefaultSectionSize(36)
        self.table_backups.setMinimumHeight(150)
        self.table_backups.setMaximumHeight(220)
        self.table_backups.setStyleSheet(f"""
            QTableWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                gridline-color: {DesignTokens.BORDER_COLOR};
            }}
            QHeaderView::section {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_MUTED};
                font-size: 10px;
                font-weight: bold;
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                padding: 4px 8px;
            }}
        """)
        bku_layout.addWidget(self.table_backups)

        layout.addWidget(self.card_bku)
        layout.addStretch()

        self.scroll.setWidget(self.content_widget)
        root_layout.addWidget(self.scroll)

    def refresh_metrics(self) -> None:
        """Calcule les vraies valeurs sur le disque et en base SQLite."""
        try:
            pm = ProfileManager()
            profile_name = get_active_profile()
            db_path = pm.get_db_path(profile_name)

            db_size_kb = db_path.stat().st_size / 1024 if db_path.exists() else 0
            db_size_str = f"{db_size_kb / 1024:.1f} Mo" if db_size_kb > 1024 else f"{db_size_kb:.0f} Ko"

            notes_count = NoteModel.select().count()
            cards_count = CardModel.select().count()
            self.c_db.update_metric(db_size_str, f"WAL Actif • {notes_count} note{'s' if notes_count > 1 else ''}, {cards_count} carte{'s' if cards_count > 1 else ''}")

            # Médias
            media_dir = get_media_dir(profile_name)

            media_count = 0
            media_size_bytes = 0
            tts_count = 0
            tts_size_bytes = 0
            if media_dir.exists():
                for f in media_dir.glob("*"):
                    if f.is_file():
                        media_count += 1
                        sz = f.stat().st_size
                        media_size_bytes += sz
                        if f.name.startswith("tts_"):
                            tts_count += 1
                            tts_size_bytes += sz

            media_size_mb = media_size_bytes / (1024 * 1024)
            tts_size_mb = tts_size_bytes / (1024 * 1024)
            tts_info = f" • dont {tts_count} audio TTS ({tts_size_mb:.1f} Mo)" if tts_count > 0 else ""
            self.c_media.update_metric(
                f"{media_size_mb:.2f} Mo",
                f"{media_count} fichier{'s' if media_count > 1 else ''} média{tts_info}",
            )

            # Time Machine
            versions_count = NoteVersionModel.select().count()
            self.c_tm.update_metric(f"{versions_count} versions", f"{notes_count} notes actives")

            # Backups
            backups = list_profile_backups(profile_name)
            self.table_backups.setRowCount(len(backups))
            if backups:
                self.lbl_recent_backups.setText(f"Historique : {len(backups)} sauvegarde{'s' if len(backups) > 1 else ''} disponible{'s' if len(backups) > 1 else ''}.")
            else:
                self.lbl_recent_backups.setText("Aucune sauvegarde enregistrée dans ce profil.")

            for row, b in enumerate(backups):
                dt_str = b.created_at.strftime("%d/%m/%Y %H:%M:%S") if isinstance(b.created_at, datetime.datetime) else str(b.created_at)
                item_date = QTableWidgetItem(dt_str)
                self.table_backups.setItem(row, 0, item_date)

                type_str = "Sécurité" if b.is_prerestore else "Instantané"
                item_type = QTableWidgetItem(type_str)
                self.table_backups.setItem(row, 1, item_type)

                sz_kb = b.size_bytes / 1024
                sz_str = f"{sz_kb / 1024:.1f} Mo" if sz_kb > 1024 else f"{sz_kb:.0f} Ko"
                item_sz = QTableWidgetItem(sz_str)
                self.table_backups.setItem(row, 2, item_sz)

                valid_str = "Saine" if b.is_valid else "Corrompue"
                item_val = QTableWidgetItem(valid_str)
                item_val.setForeground(QColor(DesignTokens.COLOR_GREEN if b.is_valid else DesignTokens.COLOR_RED))
                self.table_backups.setItem(row, 3, item_val)

                btn_restore = SecondaryButton("Restaurer")
                apply_compact_style(btn_restore, height=28)
                btn_restore.setEnabled(b.is_valid)
                btn_restore.clicked.connect(lambda _=False, binfo=b: self._restore_backup(binfo))
                self.table_backups.setCellWidget(row, 4, btn_restore)

        except Exception as e:
            logger.warning("Erreur refresh_metrics StorageMaintenanceTab: %s", e)

    def _run_vacuum(self) -> None:
        if self._maintenance_worker is not None:
            return

        profile_name = get_active_profile()
        db_path = ProfileManager().get_db_path(profile_name)
        self.btn_vacuum.setEnabled(False)
        self._maintenance_worker = _DatabaseMaintenanceWorker(str(db_path))
        self._maintenance_worker.signals.finished.connect(self._on_vacuum_finished)
        self._maintenance_worker.signals.failed.connect(self._on_vacuum_failed)
        QThreadPool.globalInstance().start(self._maintenance_worker)

    def _on_vacuum_finished(self) -> None:
        self._maintenance_worker = None
        self.btn_vacuum.setEnabled(True)
        self.refresh_metrics()
        show_toast(self, "Optimisation SQLite (VACUUM & PRAGMA) terminée avec succès !")

    def _on_vacuum_failed(self, error: str) -> None:
        self._maintenance_worker = None
        self.btn_vacuum.setEnabled(True)
        show_toast(self, f"Erreur lors de l'optimisation : {error}", is_error=True)

    def _clean_orphan_media(self) -> None:
        try:
            from ankiforge.services.cards.media_manager import MediaManager

            manager = MediaManager()
            cleaned_count = manager.clean_orphaned_media()
            self.refresh_metrics()
            show_toast(self, f"Nettoyage terminé : {cleaned_count} médias orphelins supprimés !")
        except Exception as e:
            show_toast(self, f"Erreur lors du nettoyage : {e}", is_error=True)

    def _purge_history(self) -> None:
        reply = QMessageBox.question(
            self,
            "Confirmer la purge Time Machine",
            "Voulez-vous purger l'historique des modifications antérieur à 30 jours ?\n(Les versions actives actuelles ne seront pas affectées).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                cutoff = datetime.datetime.now() - datetime.timedelta(days=30)
                deleted = NoteVersionModel.delete().where((NoteVersionModel.created_at < cutoff) & (~NoteVersionModel.is_active)).execute()
                self.refresh_metrics()
                show_toast(self, f"Purge effectuée : {deleted} anciennes versions supprimées.")
            except Exception as e:
                show_toast(self, f"Erreur purge : {e}", is_error=True)

    def _clear_cache(self) -> None:
        try:
            temp_dir = get_app_data_dir() / "temp"
            deleted_count = 0
            if temp_dir.exists():
                for f in temp_dir.glob("*"):
                    if f.is_file():
                        f.unlink()
                        deleted_count += 1
            # Purger également le cache audio orphelin
            from ankiforge.services.cards.tts_service import get_tts_service

            tts_del, _ = get_tts_service().purge_audio_cache(only_orphans=True)
            self.refresh_metrics()
            show_toast(
                self,
                f"Cache nettoyé ({deleted_count} fichiers temporaires et {tts_del} audios orphelins supprimés) !",
            )
        except Exception as e:
            show_toast(self, f"Erreur nettoyage cache : {e}", is_error=True)

    def _purge_tts_cache(self) -> None:
        reply = QMessageBox.question(
            self,
            "Confirmer la purge du cache audio",
            "Voulez-vous supprimer tous les fichiers audio TTS générés en cache ?\n(Les audios pourront être régénérés à la demande dans l'éditeur de notes).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                from ankiforge.services.cards.tts_service import get_tts_service

                count, freed_bytes = get_tts_service().purge_audio_cache(only_orphans=False)
                self.refresh_metrics()
                freed_mb = freed_bytes / (1024 * 1024)
                show_toast(self, f"Purge terminée : {count} fichier(s) audio supprimé(s) ({freed_mb:.1f} Mo libérés).")
            except Exception as e:
                show_toast(self, f"Erreur lors de la purge : {e}", is_error=True)

    def _open_profile_transfer(self) -> None:
        """Ouvre la boîte de dialogue de transfert de contenu inter-profils."""
        from ankiforge.ui.dialogs.profile_transfer_dialog import ProfileTransferDialog

        dialog = ProfileTransferDialog(parent=self)
        dialog.exec()
        self.refresh_metrics()

    def _create_snapshot(self) -> None:
        try:
            settings_pkg.backup_database(keep_last=5)
            self.refresh_metrics()
            show_toast(self, "Instantané (Snapshot) créé avec succès !")
        except Exception as e:
            show_toast(self, f"Erreur lors de la sauvegarde : {e}", is_error=True)

    def _open_backup_folder(self) -> None:
        pm = ProfileManager()
        profile_name = get_active_profile()
        backup_dir = pm.PROFILES_DIR / profile_name / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        import webbrowser

        webbrowser.open(backup_dir.as_uri())

    def _restore_backup(self, backup_info: Any) -> None:
        """Confirme et restaure une sauvegarde sélectionnée avec redémarrage propre."""
        dt_str = backup_info.created_at.strftime("%d/%m/%Y à %H:%M:%S") if isinstance(backup_info.created_at, datetime.datetime) else str(backup_info.created_at)
        reply = QMessageBox.question(
            self,
            "Confirmer la restauration",
            f"Voulez-vous restaurer la sauvegarde du {dt_str} ({backup_info.filename}) ?\n\n"
            "• Une sauvegarde de sécurité pré-restauration de votre état actuel sera créée automatiquement.\n"
            "• L'application va redémarrer immédiatement pour finaliser la restauration.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            profile_name = get_active_profile()
            success = restore_granular_backup(profile_name, backup_info.filepath, create_safety_snapshot=True)
            if success:
                show_toast(self, "Restauration effectuée ! Redémarrage de l'application...")
                QTimer.singleShot(400, restart_application)
            else:
                QMessageBox.critical(
                    self,
                    "Échec de la restauration",
                    "Impossible de restaurer cette sauvegarde. Votre base actuelle est restée intacte.",
                )

    def save_tab(self) -> None:
        if hasattr(self, "chk_clean_media_on_exit"):
            from ankiforge.utils.environment import get_app_qsettings

            settings = get_app_qsettings()
            settings.setValue("storage/clean_media_on_exit", self.chk_clean_media_on_exit.isChecked())

    def _on_clean_media_on_exit_toggled(self, checked: bool) -> None:
        from ankiforge.utils.environment import get_app_qsettings

        settings = get_app_qsettings()
        settings.setValue("storage/clean_media_on_exit", checked)

    def refresh_theme(self, profile: Any) -> None:
        self.lbl_sec_stat.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        self.lbl_sec_act.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        self.lbl_sec_bku.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        self.c_db.refresh_theme(profile)
        self.c_media.refresh_theme(profile)
        self.c_tm.refresh_theme(profile)
        self.card_act.refresh_theme(profile)
        self.card_bku.refresh_theme(profile)
        self.lbl_recent_backups.setStyleSheet(f"color: {profile.text_secondary}; font-size: 11.5px; font-family: '{profile.font_code}';")
