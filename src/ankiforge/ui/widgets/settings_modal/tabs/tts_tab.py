"""
Onglet Paramètres Synthèse Vocale (TTS) & Gestionnaire de Moteurs Découplés.
Permet de choisir le moteur de voix par défaut, d'auditionner les voix,
et d'installer/mettre à jour le binaire autonome Piper TTS en local.
"""

import logging
from typing import Any

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.cards.tts_service import PiperSidecarProvider, get_tts_service
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.components import (
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.settings_modal.components.settings_card import SettingsCard
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.paths import get_app_data_dir

logger = logging.getLogger(__name__)


class PiperInstallerWorker(QThread):
    """Worker asynchrone pour le téléchargement et l'extraction de Piper CLI."""

    progress = Signal(str)
    finished_success = Signal()
    failed = Signal(str)

    def run(self) -> None:
        try:
            get_tts_service().download_and_install_piper(progress_callback=self.progress.emit)
            self.finished_success.emit()
        except Exception as e:
            self.failed.emit(str(e))


class TTSSettingsTab(QWidget):
    """Onglet Paramètres Synthèse Vocale (TTS)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tts_service = get_tts_service()

        # Lecteur audio pour les tests de voix
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(1.0)
        self._audio_output.setMuted(False)
        self._player.setAudioOutput(self._audio_output)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.errorOccurred.connect(self._on_player_error)

        self._installer_worker: PiperInstallerWorker | None = None

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # ── SECTION 1 : CONFIGURATION GÉNÉRALE TTS ──────────────────────────
        self.lbl_sec_general = QLabel("CONFIGURATION DU MOTEUR VOCAL")
        self.lbl_sec_general.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(self.lbl_sec_general)

        self.card_general = SettingsCard()
        card_gen_layout = QVBoxLayout(self.card_general)
        card_gen_layout.setContentsMargins(14, 12, 14, 12)
        card_gen_layout.setSpacing(10)

        # 1. Choix du Moteur
        row_engine = QHBoxLayout()
        lbl_engine = QLabel("Moteur de synthèse :")
        lbl_engine.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_engine.addWidget(lbl_engine)

        self.cb_engine = StyledComboBox()
        self.cb_engine.setMinimumWidth(260)
        self.cb_engine.setFixedHeight(28)
        self.cb_engine.addItem("Edge-TTS (Voix Neuronales Cloud Gratuit)", "edge-tts")
        self.cb_engine.addItem("Piper TTS (Local Hors-Ligne Standalone)", "piper")
        self.cb_engine.addItem("Moteur Système OS (Fallback Natif)", "system")
        self.cb_engine.currentIndexChanged.connect(self._on_engine_changed)
        row_engine.addWidget(self.cb_engine)
        card_gen_layout.addLayout(row_engine)

        # 2. Choix de la Voix
        row_voice = QHBoxLayout()
        lbl_voice = QLabel("Voix par défaut :")
        lbl_voice.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_voice.addWidget(lbl_voice)

        self.cb_voice = StyledComboBox()
        self.cb_voice.setMinimumWidth(260)
        self.cb_voice.setFixedHeight(28)
        row_voice.addWidget(self.cb_voice)
        card_gen_layout.addLayout(row_voice)

        # 3. Vitesse et Tonalité
        row_params = QHBoxLayout()
        lbl_rate = QLabel("Vitesse d'élocution :")
        lbl_rate.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_params.addWidget(lbl_rate)

        self.cb_rate = StyledComboBox()
        self.cb_rate.setFixedHeight(28)
        self.cb_rate.addItem("Normale (100%)", "+0%")
        self.cb_rate.addItem("Lente (85%)", "-15%")
        self.cb_rate.addItem("Rapide (115%)", "+15%")
        self.cb_rate.addItem("Très rapide (130%)", "+30%")
        row_params.addWidget(self.cb_rate)
        card_gen_layout.addLayout(row_params)

        # 4. Périphérique de Sortie Audio
        row_device = QHBoxLayout()
        lbl_device = QLabel("Sortie audio :")
        lbl_device.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_device.addWidget(lbl_device)

        self.cb_device = StyledComboBox()
        self.cb_device.setFixedHeight(28)
        self._populate_audio_devices()
        self.cb_device.currentIndexChanged.connect(self._on_audio_device_changed)
        row_device.addWidget(self.cb_device)
        card_gen_layout.addLayout(row_device)

        # 5. Bouton Tester la Voix
        row_test = QHBoxLayout()
        row_test.addStretch()

        self.btn_test = SecondaryButton(" Tester la voix sélectionnée")
        self.btn_test.setIcon(load_phosphor_icon("ph.speaker-high", color=DesignTokens.ACCENT_PRIMARY))
        self.btn_test.setFixedHeight(30)
        self.btn_test.clicked.connect(self._on_test_voice)
        row_test.addWidget(self.btn_test)

        card_gen_layout.addLayout(row_test)
        layout.addWidget(self.card_general)

        # ── SECTION 2 : GESTIONNAIRE LOCAL PIPER (SIDECAR DÉCOUPLÉ) ──────────
        self.lbl_sec_piper = QLabel("MOTEUR LOCAL HORS-LIGNE (PIPER SIDECAR)")
        self.lbl_sec_piper.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(self.lbl_sec_piper)

        self.card_piper = SettingsCard()
        card_piper_layout = QVBoxLayout(self.card_piper)
        card_piper_layout.setContentsMargins(14, 12, 14, 12)
        card_piper_layout.setSpacing(10)

        # Statut de Piper
        row_status = QHBoxLayout()
        lbl_status_title = QLabel("Statut de Piper CLI :")
        lbl_status_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_status.addWidget(lbl_status_title)

        self.lbl_piper_status = QLabel()
        self.lbl_piper_status.setStyleSheet("font-size: 11px; font-weight: bold;")
        self._update_piper_status_ui()
        row_status.addWidget(self.lbl_piper_status)
        row_status.addStretch()

        card_piper_layout.addLayout(row_status)

        # Emplacement
        lbl_location = QLabel(f"Emplacement : {get_app_data_dir() / 'tools' / 'tts' / 'piper'}")
        lbl_location.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        card_piper_layout.addWidget(lbl_location)

        # Bouton Télécharger / Installer
        row_install = QHBoxLayout()
        self.lbl_install_progress = QLabel("")
        self.lbl_install_progress.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 11px;")
        row_install.addWidget(self.lbl_install_progress, 1)

        self.btn_install_piper = PrimaryButton(" Télécharger Piper CLI (1-Clic)")
        self.btn_install_piper.setIcon(load_phosphor_icon("ph.download-simple", color="white"))
        self.btn_install_piper.setFixedHeight(30)
        self.btn_install_piper.clicked.connect(self._on_install_piper)
        row_install.addWidget(self.btn_install_piper)

        card_piper_layout.addLayout(row_install)
        layout.addWidget(self.card_piper)

        layout.addStretch()

    def _update_piper_status_ui(self) -> None:
        """Met à jour le libellé et la couleur du statut d'installation de Piper."""
        is_installed = PiperSidecarProvider.get_piper_executable() is not None
        if is_installed:
            is_functional, msg = PiperSidecarProvider.is_functional()
            if is_functional:
                self.lbl_piper_status.setText("● Installé et opérationnel")
                self.lbl_piper_status.setStyleSheet("color: #10b981; font-size: 11px; font-weight: bold;")
            else:
                self.lbl_piper_status.setText(f"⚠️ Dépendance manquante ({msg})")
                self.lbl_piper_status.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; font-weight: bold;")
                self.lbl_piper_status.setToolTip(msg)
        else:
            self.lbl_piper_status.setText("○ Non installé (binaire absent)")
            self.lbl_piper_status.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; font-weight: bold;")

    def _on_engine_changed(self) -> None:
        """Met à jour la liste des voix lorsque le moteur change."""
        engine_id = self.cb_engine.currentData()
        self.cb_voice.clear()

        try:
            provider = self.tts_service.get_provider(engine_id)
            voices = provider.get_voices()
            for v in voices:
                self.cb_voice.addItem(f"{v['name']} ({v.get('lang', '')})", v["id"])
        except Exception as e:
            self.cb_voice.addItem(f"Erreur de chargement des voix : {e}", "default")

    def _load_settings(self) -> None:
        """Charge les paramètres enregistrés pour la synthèse vocale."""
        engine = SettingsService.get("tts.engine", "edge-tts")
        idx_engine = self.cb_engine.findData(engine)
        if idx_engine >= 0:
            self.cb_engine.blockSignals(True)
            self.cb_engine.setCurrentIndex(idx_engine)
            self.cb_engine.blockSignals(False)

        # Toujours peupler la liste des voix du moteur sélectionné
        self._on_engine_changed()

        saved_voice = SettingsService.get("tts.voice")
        if saved_voice:
            idx_voice = self.cb_voice.findData(saved_voice)
            if idx_voice >= 0:
                self.cb_voice.setCurrentIndex(idx_voice)

        rate = SettingsService.get("tts.rate", "+0%")
        idx_rate = self.cb_rate.findData(rate)
        if idx_rate >= 0:
            self.cb_rate.setCurrentIndex(idx_rate)

    def save_settings(self) -> None:
        """Enregistre les préférences TTS en BDD via SettingsService."""
        SettingsService.set("tts.engine", self.cb_engine.currentData(), category="multimedia")
        SettingsService.set("tts.voice", self.cb_voice.currentData(), category="multimedia")
        SettingsService.set("tts.rate", self.cb_rate.currentData(), category="multimedia")
        dev_desc = self._audio_output.device().description()
        if dev_desc:
            SettingsService.set("tts.device_name", dev_desc, category="multimedia")

    def save_tab(self) -> None:
        """Alias conventionnel pour save_settings()."""
        self.save_settings()

    def _populate_audio_devices(self) -> None:
        """Remplit la liste des périphériques de sortie audio disponibles."""
        self.cb_device.clear()
        default_device = QMediaDevices.defaultAudioOutput()
        self._audio_devices = list(QMediaDevices.audioOutputs())
        saved_dev_name = SettingsService.get("tts.device_name")

        default_idx = 0
        saved_idx: int | None = None

        for idx, dev in enumerate(self._audio_devices):
            name = dev.description()
            is_def = dev.id() == default_device.id()
            label = f"{name} (Par défaut)" if is_def else name
            self.cb_device.addItem(label, dev.id())
            if is_def:
                default_idx = idx
            if saved_dev_name and name == saved_dev_name:
                saved_idx = idx

        target_idx = saved_idx if saved_idx is not None else default_idx
        if self.cb_device.count() > 0:
            self.cb_device.setCurrentIndex(target_idx)
            self._on_audio_device_changed()

    def _on_audio_device_changed(self) -> None:
        """Applique le périphérique audio sélectionné au lecteur."""
        selected_id = self.cb_device.currentData()
        for dev in getattr(self, "_audio_devices", []):
            if dev.id() == selected_id:
                self._audio_output.setDevice(dev)
                logger.info("Sortie audio changée vers : %s", dev.description())
                break

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        """Met à jour l'icône et l'intitulé du bouton de test selon la lecture."""
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_test.setText(" Arrêter la lecture")
            self.btn_test.setIcon(load_phosphor_icon("ph.stop", color="#ef4444"))
        else:
            self.btn_test.setText(" Tester la voix sélectionnée")
            self.btn_test.setIcon(load_phosphor_icon("ph.speaker-high", color=DesignTokens.ACCENT_PRIMARY))

    def _on_test_voice(self) -> None:
        """Génère et lit un échantillon de voix avec les réglages actuels."""
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.stop()
            return

        engine = self.cb_engine.currentData()
        voice = self.cb_voice.currentData()
        rate = self.cb_rate.currentData()

        sample_text = "Bonjour ! Voici un extrait de la synthèse vocale pour vos cartes Anki."
        self.btn_test.setEnabled(False)

        try:
            _, audio_path = self.tts_service.synthesize(
                text=sample_text,
                engine=engine,
                voice=voice,
                rate=rate,
            )
            self._player.setSource(QUrl.fromLocalFile(str(audio_path)))
            self._player.play()
            dev_desc = self._audio_output.device().description() or "Sortie audio"
            show_toast(self, f"Lecture audio en cours sur '{dev_desc}'...")
        except Exception as e:
            logger.exception("Erreur lors du test vocal : %s", e)
            show_toast(self, f"Erreur lors du test vocal : {e}", is_error=True)
        finally:
            self.btn_test.setEnabled(True)

    def _on_install_piper(self) -> None:
        """Lance le téléchargement de Piper CLI en tâche de fond."""
        self.btn_install_piper.setEnabled(False)
        self.lbl_install_progress.setText("Téléchargement en cours...")

        self._installer_worker = PiperInstallerWorker()
        self._installer_worker.progress.connect(self.lbl_install_progress.setText)
        self._installer_worker.finished_success.connect(self._on_installer_success)
        self._installer_worker.failed.connect(self._on_installer_failed)
        self._installer_worker.start()

    def _on_installer_success(self) -> None:
        self.btn_install_piper.setEnabled(True)
        self.lbl_install_progress.setText("Piper installé avec succès !")
        self._update_piper_status_ui()
        show_toast(self, "Piper TTS a été installé avec succès.")

    def _on_installer_failed(self, err_msg: str) -> None:
        self.btn_install_piper.setEnabled(True)
        self.lbl_install_progress.setText("Échec du téléchargement.")
        show_toast(self, f"Installation de Piper échouée : {err_msg}", is_error=True)

    def _on_player_error(self, error: QMediaPlayer.Error, error_string: str) -> None:
        logger.warning("Erreur du lecteur audio : %s - %s", error, error_string)
        show_toast(self, f"Erreur de lecture audio : {error_string}", is_error=True)

    def closeEvent(self, event: Any) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.stop()
        super().closeEvent(event)
