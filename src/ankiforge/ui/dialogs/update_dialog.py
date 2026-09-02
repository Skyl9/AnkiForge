"""Boîte de dialogue moderne de mise à jour 1-clic pour AnkiForge.

Permet le téléchargement en tâche de fond avec jauge de progression,
la vérification d'intégrité SHA-256 et le redémarrage sécurisé multi-OS.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

from PySide6.QtCore import QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.auto_updater import (
    UpdateDownloaderWorker,
    apply_update_and_restart,
    find_asset_for_current_platform,
    is_standalone_app,
)
from ankiforge.services.update_checker import UpdateInfo
from ankiforge.ui.components.badges import Badge
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.version import VERSION_INFO

logger = logging.getLogger(__name__)


class UpdateDialog(QDialog):
    """Boîte de dialogue de mise à jour avec téléchargement intégré et swap sécurisé."""

    def __init__(self, update_info: UpdateInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.update_info = update_info
        self._downloaded_file: Path | None = None
        self._downloader_worker: UpdateDownloaderWorker | None = None

        self.setWindowTitle(f"Mise à jour disponible — v{self.update_info.version}")
        self.setMinimumSize(580, 520)
        self.resize(620, 560)

        self._setup_ui()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 24, 24, 20)
        root_layout.setSpacing(14)

        # ── 1. En-tête avec Icône et Titre ──
        header_layout = QHBoxLayout()
        header_layout.setSpacing(14)

        icon_lbl = QLabel()
        spark_icon = load_phosphor_icon("sparkle", color=DesignTokens.ACCENT_PRIMARY)
        if not spark_icon.isNull():
            icon_lbl.setPixmap(spark_icon.pixmap(32, 32))
        header_layout.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        main_title = QLabel(self.update_info.title or f"AnkiForge v{self.update_info.version}")
        main_title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {DesignTokens.TEXT_PRIMARY};")
        title_col.addWidget(main_title)

        sub_title = QLabel("Une nouvelle version optimisée d'AnkiForge est disponible au téléchargement.")
        sub_title.setStyleSheet(f"font-size: 13px; color: {DesignTokens.TEXT_MUTED};")
        title_col.addWidget(sub_title)

        header_layout.addLayout(title_col, stretch=1)
        root_layout.addLayout(header_layout)

        # ── 2. Badges de Versions Comparatives ──
        badge_card = QFrame()
        badge_card.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL};border: 1px solid {DesignTokens.BORDER_COLOR};border-radius: {DesignTokens.RADIUS_MD};padding: 8px;")
        badge_layout = QHBoxLayout(badge_card)
        badge_layout.setContentsMargins(12, 6, 12, 6)
        badge_layout.setSpacing(12)

        curr_lbl = QLabel(f"Version installée : <b>v{VERSION_INFO.version}</b>")
        curr_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 13px;")
        badge_layout.addWidget(curr_lbl)

        badge_layout.addStretch(1)

        arrow_lbl = QLabel("➔")
        arrow_lbl.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-weight: bold; font-size: 14px;")
        badge_layout.addWidget(arrow_lbl)

        badge_layout.addStretch(1)

        channel_label = f" [{self.update_info.channel.upper()}]" if self.update_info.channel != "stable" else ""
        new_badge = Badge(f"Disponible : v{self.update_info.version}{channel_label}", variant="success")
        badge_layout.addWidget(new_badge)

        root_layout.addWidget(badge_card)

        # ── 3. Visualiseur des Notes de Version (Markdown) ──
        notes_lbl = QLabel("Notes de Version & Nouveautés :")
        notes_lbl.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {DesignTokens.TEXT_PRIMARY};")
        root_layout.addWidget(notes_lbl)

        self.notes_browser = QTextBrowser()
        self.notes_browser.setOpenExternalLinks(True)
        self.notes_browser.setMarkdown(self.update_info.release_notes or "_Aucune note de version détaillée._")
        self.notes_browser.setStyleSheet(
            f"background-color: {DesignTokens.BG_INPUT};"
            f"border: 1px solid {DesignTokens.BORDER_COLOR};"
            f"border-radius: {DesignTokens.RADIUS_SM};"
            f"color: {DesignTokens.TEXT_PRIMARY};"
            "font-size: 13px;"
            "padding: 12px;"
        )
        root_layout.addWidget(self.notes_browser, stretch=1)

        # ── 4. Section de Progression du Téléchargement (Masquée initialement) ──
        self.progress_container = QWidget()
        self.progress_container.setVisible(False)
        progress_layout = QVBoxLayout(self.progress_container)
        progress_layout.setContentsMargins(0, 4, 0, 4)
        progress_layout.setSpacing(6)

        self.progress_status_lbl = QLabel("Téléchargement de la mise à jour...")
        self.progress_status_lbl.setStyleSheet(f"font-size: 12px; font-weight: 500; color: {DesignTokens.TEXT_PRIMARY};")
        progress_layout.addWidget(self.progress_status_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setStyleSheet(
            f"QProgressBar {{ background-color: {DesignTokens.BG_INPUT}; "
            f"border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 9px; "
            "text-align: center; color: #ffffff; font-size: 11px; font-weight: 600; }\n"
            f"QProgressBar::chunk {{ background-color: {DesignTokens.ACCENT_PRIMARY}; border-radius: 8px; }}"
        )
        progress_layout.addWidget(self.progress_bar)

        root_layout.addWidget(self.progress_container)

        # ── 5. Barre d'Actions Inférieure ──
        self.btn_layout = QHBoxLayout()
        self.btn_layout.setSpacing(10)

        self.web_btn = SecondaryButton("Lien web GitHub")
        self.web_btn.clicked.connect(self._on_web_clicked)
        self.btn_layout.addWidget(self.web_btn)

        self.btn_layout.addStretch(1)

        self.cancel_btn = SecondaryButton("Plus tard")
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        self.btn_layout.addWidget(self.cancel_btn)

        self.action_btn = PrimaryButton("📥 Télécharger et Installer")
        self.action_btn.clicked.connect(self._on_start_download)
        self.btn_layout.addWidget(self.action_btn)

        root_layout.addLayout(self.btn_layout)

    def _on_web_clicked(self) -> None:
        """Ouvre la page de la release GitHub."""
        QDesktopServices.openUrl(QUrl(self.update_info.html_url))

    def _on_cancel_clicked(self) -> None:
        """Annule le téléchargement en cours ou ferme la modale."""
        if self._downloader_worker:
            self._downloader_worker.cancel()
        self.reject()

    def _on_start_download(self) -> None:
        """Démarre le téléchargement asynchrone du binaire de mise à jour."""
        asset = find_asset_for_current_platform(self.update_info.assets)

        if not asset or "browser_download_url" not in asset:
            logger.warning("Aucun asset direct trouvé. Redirection vers la page GitHub.")
            self._on_web_clicked()
            self.accept()
            return

        download_url = str(asset["browser_download_url"])
        filename = str(asset.get("name", f"AnkiForge-v{self.update_info.version}"))

        # Transition visuelle vers l'état DOWNLOADING
        self.progress_container.setVisible(True)
        self.action_btn.setEnabled(False)
        self.action_btn.setText("Téléchargement...")
        self.cancel_btn.setText("Annuler")

        self._downloader_worker = UpdateDownloaderWorker(download_url, filename)
        self._downloader_worker.signals.progress.connect(self._on_download_progress)
        self._downloader_worker.signals.download_complete.connect(self._on_download_finished)
        self._downloader_worker.signals.download_error.connect(self._on_download_failed)

        QThreadPool.globalInstance().start(self._downloader_worker)

    def _on_download_progress(self, percentage: int, downloaded: int, total: int) -> None:
        """Met à jour la jauge et le libellé de progression en temps réel."""
        self.progress_bar.setValue(percentage)
        down_mb = downloaded / (1024 * 1024)
        total_mb = total / (1024 * 1024) if total > 0 else 0
        if total_mb > 0:
            self.progress_status_lbl.setText(f"Téléchargement : {down_mb:.1f} Mo / {total_mb:.1f} Mo ({percentage}%)")
        else:
            self.progress_status_lbl.setText(f"Téléchargement : {down_mb:.1f} Mo...")

    def _on_download_finished(self, dest_path: object, sha256_hash: str) -> None:
        """Gestionnaire de fin de téléchargement avec vérification d'intégrité."""
        self._downloaded_file = cast(Path, dest_path)
        self.progress_bar.setValue(100)
        self.progress_status_lbl.setText(f"✅ Téléchargement vérifié (SHA-256 : {sha256_hash[:12]}...)")
        self.progress_status_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #10b981;")

        self.action_btn.setEnabled(True)
        self.cancel_btn.setText("Fermer")

        if is_standalone_app():
            self.action_btn.setText("🔄 Redémarrer et Installer")
            self.action_btn.clicked.disconnect()
            self.action_btn.clicked.connect(self._on_apply_and_restart)
        else:
            self.action_btn.setText("Prêt (Mode Dev)")
            self.action_btn.setEnabled(False)
            self.progress_status_lbl.setText("✅ Téléchargé avec succès.\nℹ️ Mode Développement détecté : Le remplacement automatique est désactivé pour protéger le code source.")

    def _on_download_failed(self, error_msg: str) -> None:
        """Gestionnaire d'erreur de téléchargement."""
        self.progress_status_lbl.setText(f"❌ Échec du téléchargement : {error_msg}")
        self.progress_status_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #ef4444;")
        self.action_btn.setEnabled(True)
        self.action_btn.setText("Réessayer")
        self.cancel_btn.setText("Fermer")

    def _on_apply_and_restart(self) -> None:
        """Applique la mise à jour et quitte l'application active pour le swap."""
        if not self._downloaded_file:
            return

        success, msg = apply_update_and_restart(self._downloaded_file)
        if success:
            logger.info("Fermeture d'AnkiForge pour application de la mise à jour : %s", msg)
            self.accept()
            QApplication.quit()
        else:
            self._on_download_failed(msg)
