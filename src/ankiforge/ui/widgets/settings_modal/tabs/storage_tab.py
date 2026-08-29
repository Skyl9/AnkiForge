import datetime
import logging
from typing import Any, Optional

from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

import ankiforge.ui.widgets.settings_modal as settings_pkg
from ankiforge.database.base import db
from ankiforge.database.models import (
    CardModel,
    MediaModel,
    NoteModel,
    NoteVersionMediaModel,
    NoteVersionModel,
)
from ankiforge.services.profile_manager import ProfileManager
from ankiforge.ui.components import (
    DangerButton,
    PrimaryButton,
    SecondaryButton,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.settings_modal.components.settings_card import SettingsCard
from ankiforge.ui.widgets.settings_modal.components.storage_metric_card import StorageMetricCard
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.paths import get_active_profile, get_app_data_dir

logger = logging.getLogger(__name__)


class StorageMaintenanceTab(QWidget):
    """Onglet Métrologie Réelle, Optimisation SQLite, Nettoyage Médias et Backups."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self.refresh_metrics()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # ── SECTION 1 : COCKPIT DU STOCKAGE RÉEL ─────────────────────────────
        self.lbl_sec_stat = QLabel("ÉTAT DU STOCKAGE ET DE LA BASE DE DONNÉES")
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
        self.btn_snapshot.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
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

        self.lbl_recent_backups = QLabel("Dernières sauvegardes : Aucune pour le moment.")
        self.lbl_recent_backups.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11.5px; font-family: monospace;")
        bku_layout.addWidget(self.lbl_recent_backups)

        layout.addWidget(self.card_bku)
        layout.addStretch()

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
            media_dir = pm.PROFILES_DIR / profile_name / "media"
            if not media_dir.exists():
                media_dir = get_app_data_dir() / "media"

            media_count = 0
            media_size_bytes = 0
            if media_dir.exists():
                for f in media_dir.glob("*"):
                    if f.is_file():
                        media_count += 1
                        media_size_bytes += f.stat().st_size

            media_size_mb = media_size_bytes / (1024 * 1024)
            self.c_media.update_metric(f"{media_size_mb:.2f} Mo", f"{media_count} fichier{'s' if media_count > 1 else ''} média")

            # Time Machine
            versions_count = NoteVersionModel.select().count()
            self.c_tm.update_metric(f"{versions_count} versions", f"{notes_count} notes actives")

            # Backups
            backup_dir = pm.PROFILES_DIR / profile_name / "backups"
            if backup_dir.exists():
                backups = sorted(backup_dir.glob("ankiforge_backup_*.db"), reverse=True)
                if backups:
                    b_texts = [f"• {b.name} ({b.stat().st_size / 1024:.0f} Ko)" for b in backups[:3]]
                    self.lbl_recent_backups.setText("\n".join(b_texts))
                else:
                    self.lbl_recent_backups.setText("Aucune sauvegarde enregistrée dans ce profil.")
            else:
                self.lbl_recent_backups.setText("Dossier de sauvegarde non initialisé.")

        except Exception as e:
            logger.warning("Erreur refresh_metrics StorageMaintenanceTab: %s", e)

    def _run_vacuum(self) -> None:
        try:
            db.execute_sql("VACUUM;")
            db.execute_sql("PRAGMA optimize;")
            self.refresh_metrics()
            show_toast(self, "Optimisation SQLite (VACUUM & PRAGMA) terminée avec succès !")
        except Exception as e:
            show_toast(self, f"Erreur lors de l'optimisation : {e}", is_error=True)

    def _clean_orphan_media(self) -> None:
        try:
            pm = ProfileManager()
            profile_name = get_active_profile()
            media_dir = pm.PROFILES_DIR / profile_name / "media"
            if not media_dir.exists():
                media_dir = get_app_data_dir() / "media"

            used_media_ids = {m.media_id for m in NoteVersionMediaModel.select(NoteVersionMediaModel.media)}
            orphan_records = list(MediaModel.select().where(~(MediaModel.id.in_(used_media_ids)))) if used_media_ids else list(MediaModel.select())

            cleaned_count = 0
            freed_bytes = 0
            for record in orphan_records:
                target_f = media_dir / record.filename
                if target_f.exists():
                    freed_bytes += target_f.stat().st_size
                    target_f.unlink()
                record.delete_instance()
                cleaned_count += 1

            self.refresh_metrics()
            freed_kb = freed_bytes / 1024
            show_toast(self, f"Nettoyage terminé : {cleaned_count} médias orphelins supprimés ({freed_kb:.1f} Ko libérés) !")
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
            show_toast(self, f"Cache et fichiers temporaires nettoyés ({deleted_count} fichiers supprimés) !")
        except Exception as e:
            show_toast(self, f"Erreur nettoyage cache : {e}", is_error=True)

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

    def save_tab(self) -> None:
        pass

    def refresh_theme(self, profile: Any) -> None:
        self.lbl_sec_stat.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        self.lbl_sec_act.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        self.lbl_sec_bku.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        self.c_db.refresh_theme(profile)
        self.c_media.refresh_theme(profile)
        self.c_tm.refresh_theme(profile)
        self.card_act.refresh_theme(profile)
        self.card_bku.refresh_theme(profile)
        self.lbl_recent_backups.setStyleSheet(f"color: {profile.text_secondary}; font-size: 11.5px; font-family: monospace;")
