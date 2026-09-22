"""
Onglet Paramètres Synthèse Vocale (TTS) & Gestionnaire de Moteurs Découplés.
Permet de choisir le moteur de voix par défaut, d'auditionner les voix,
et d'installer/mettre à jour le binaire autonome Piper TTS en local.
"""

import logging
from typing import Any

from PySide6.QtCore import QThread, QUrl, Signal

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer

    HAS_QTMULTIMEDIA = True
except (ImportError, OSError):
    QAudioOutput = None  # type: ignore[misc]  # PySide6 QtMultimedia indisponible : repli sur None
    QMediaDevices = None  # type: ignore[misc]
    QMediaPlayer = None  # type: ignore[misc]
    HAS_QTMULTIMEDIA = False
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.cards.tts_service import (
    KokoroSidecarProvider,
    PiperSidecarProvider,
    get_tts_service,
)
from ankiforge.services.settings_service import SettingsService, values_equal
from ankiforge.ui.components import (
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.settings_modal.components.settings_card import SettingsCard
from ankiforge.ui.widgets.settings_modal.dirty import SettingsDirtyMixin
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon
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


class KokoroInstallerWorker(QThread):
    """Worker asynchrone pour l'installation / configuration de Kokoro-82M."""

    progress = Signal(str)
    finished_success = Signal()
    failed = Signal(str)

    def run(self) -> None:
        try:
            get_tts_service().download_and_install_kokoro(progress_callback=self.progress.emit)
            self.finished_success.emit()
        except Exception as e:
            self.failed.emit(str(e))


class TTSSettingsTab(SettingsDirtyMixin, QWidget):
    """Onglet Paramètres Synthèse Vocale (TTS)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tts_service = get_tts_service()

        # Lecteur audio pour les tests de voix (sécurisé contre absence de libpulse)
        if HAS_QTMULTIMEDIA and QMediaPlayer is not None and QAudioOutput is not None:
            self._player: Any = QMediaPlayer(self)
            self._audio_output: Any = QAudioOutput(self)
            self._audio_output.setVolume(1.0)
            self._audio_output.setMuted(False)
            self._player.setAudioOutput(self._audio_output)
            self._player.playbackStateChanged.connect(self._on_playback_state_changed)
            self._player.errorOccurred.connect(self._on_player_error)
        else:
            self._player = None
            self._audio_output = None

        self._installer_worker: PiperInstallerWorker | None = None
        self._kokoro_worker: KokoroInstallerWorker | None = None
        # Référence du périphérique audio actif au chargement (évite un faux « modifié »).
        self._initial_device_desc: str | None = None

        self._setup_ui()
        self._load_settings()
        # Référence des valeurs chargées : évite de marquer « modifié » un réglage auto-sélectionné.
        self._initial_engine: Any = self.cb_engine.currentData()
        self._initial_voice: Any = self.cb_voice.currentData()
        self._initial_rate: Any = self.cb_rate.currentData()

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
        self._populate_engines()
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
        self.lbl_sec_piper = QLabel("MOTEUR LOCAL PIPER")
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
        self.btn_install_piper.setIcon(load_on_accent_icon("ph.download-simple"))
        self.btn_install_piper.setFixedHeight(30)
        self.btn_install_piper.clicked.connect(self._on_install_piper)
        row_install.addWidget(self.btn_install_piper)

        card_piper_layout.addLayout(row_install)
        layout.addWidget(self.card_piper)

        # ── SECTION 3 : GESTIONNAIRE LOCAL KOKORO-82M (SIDECAR DÉPORTÉ) ──────
        self.lbl_sec_kokoro = QLabel("MOTEUR LOCAL KOKORO-82M (OPTIONNEL)")
        self.lbl_sec_kokoro.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(self.lbl_sec_kokoro)

        self.card_kokoro = SettingsCard()
        card_kokoro_layout = QVBoxLayout(self.card_kokoro)
        card_kokoro_layout.setContentsMargins(14, 12, 14, 12)
        card_kokoro_layout.setSpacing(10)

        # Statut de Kokoro
        row_kokoro_status = QHBoxLayout()
        lbl_kokoro_title = QLabel("Statut du Runner Kokoro :")
        lbl_kokoro_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_kokoro_status.addWidget(lbl_kokoro_title)

        self.lbl_kokoro_status = QLabel()
        self.lbl_kokoro_status.setStyleSheet("font-size: 11px; font-weight: bold;")
        self._update_kokoro_status_ui()
        row_kokoro_status.addWidget(self.lbl_kokoro_status)
        row_kokoro_status.addStretch()

        card_kokoro_layout.addLayout(row_kokoro_status)

        # Emplacement
        lbl_kokoro_loc = QLabel(f"Emplacement : {get_app_data_dir() / 'tools' / 'tts' / 'kokoro'}")
        lbl_kokoro_loc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        card_kokoro_layout.addWidget(lbl_kokoro_loc)

        # Description / Guide
        lbl_kokoro_guide = QLabel(
            "Kokoro-82M est un modèle local compact haute fidélité. Le runner s'exécute en processus déporté via ~/.ankiforge/tools/tts/kokoro/run.py ou un binaire 'kokoro' dans le PATH."
        )
        lbl_kokoro_guide.setWordWrap(True)
        lbl_kokoro_guide.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        card_kokoro_layout.addWidget(lbl_kokoro_guide)

        # Bouton Installer / Configurer
        row_kokoro_install = QHBoxLayout()
        self.lbl_kokoro_install_progress = QLabel("")
        self.lbl_kokoro_install_progress.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 11px;")
        row_kokoro_install.addWidget(self.lbl_kokoro_install_progress, 1)

        self.btn_install_kokoro = PrimaryButton(" Installer / Configurer Kokoro (1-Clic)")
        self.btn_install_kokoro.setIcon(load_on_accent_icon("ph.download-simple"))
        self.btn_install_kokoro.setFixedHeight(30)
        self.btn_install_kokoro.clicked.connect(self._on_install_kokoro)
        row_kokoro_install.addWidget(self.btn_install_kokoro)

        card_kokoro_layout.addLayout(row_kokoro_install)
        layout.addWidget(self.card_kokoro)

        layout.addStretch()

        self.scroll.setWidget(self.content_widget)
        root_layout.addWidget(self.scroll)

    def _populate_engines(self) -> None:
        """Remplit le sélecteur des moteurs TTS avec vérification de disponibilité pour Kokoro."""
        current_data = self.cb_engine.currentData()
        self.cb_engine.blockSignals(True)
        self.cb_engine.clear()
        self.cb_engine.addItem("Edge-TTS (Voix Neuronales Cloud Gratuit)", "edge-tts")
        self.cb_engine.addItem("Piper TTS (Local Hors-Ligne Standalone)", "piper")
        self.cb_engine.addItem("Moteur Système OS (Fallback Natif)", "system")

        is_kokoro_ok, _ = KokoroSidecarProvider.is_functional()
        if is_kokoro_ok:
            self.cb_engine.addItem("Kokoro-82M (Runner Local Déporté)", "kokoro")

        if current_data:
            idx = self.cb_engine.findData(current_data)
            if idx >= 0:
                self.cb_engine.setCurrentIndex(idx)
        self.cb_engine.blockSignals(False)

    def _update_piper_status_ui(self) -> None:
        """Met à jour le libellé et la couleur du statut d'installation de Piper."""
        is_installed = PiperSidecarProvider.get_piper_executable() is not None
        if is_installed:
            is_functional, msg = PiperSidecarProvider.is_functional()
            if is_functional:
                self.lbl_piper_status.setText("● Installé et opérationnel")
                self.lbl_piper_status.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 11px; font-weight: bold;")
            else:
                self.lbl_piper_status.setText(f"Dépendance manquante ({msg})")
                self.lbl_piper_status.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; font-weight: bold;")
                self.lbl_piper_status.setToolTip(msg)
        else:
            self.lbl_piper_status.setText("○ Non installé (binaire absent)")
            self.lbl_piper_status.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; font-weight: bold;")

    def _update_kokoro_status_ui(self) -> None:
        """Met à jour le libellé et la couleur du statut d'installation de Kokoro."""
        is_functional, msg = KokoroSidecarProvider.is_functional()
        if is_functional:
            self.lbl_kokoro_status.setText("● Installé et opérationnel")
            self.lbl_kokoro_status.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 11px; font-weight: bold;")
        else:
            self.lbl_kokoro_status.setText("○ Non installé (runner absent)")
            self.lbl_kokoro_status.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; font-weight: bold;")
            self.lbl_kokoro_status.setToolTip(msg)

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
        self._populate_engines()
        engine = SettingsService.get("tts.engine", "edge-tts")
        idx_engine = self.cb_engine.findData(engine)
        if idx_engine >= 0:
            self.cb_engine.blockSignals(True)
            self.cb_engine.setCurrentIndex(idx_engine)
            self.cb_engine.blockSignals(False)
        else:
            if engine == "kokoro":
                show_toast(
                    self,
                    "Le moteur Kokoro-82M n'est pas opérationnel sur cette machine. Repli automatique sur Edge-TTS.",
                    is_error=False,
                )
            self.cb_engine.setCurrentIndex(0)

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
        if self._audio_output:
            dev_desc = self._audio_output.device().description()
            if dev_desc:
                SettingsService.set("tts.device_name", dev_desc, category="multimedia")

    def has_pending_changes(self) -> bool:
        """True si un paramètre TTS diffère de sa valeur chargée (ou de la sortie audio active)."""
        if not values_equal(self.cb_engine.currentData(), self._initial_engine):
            return True
        if not values_equal(self.cb_voice.currentData(), self._initial_voice):
            return True
        if not values_equal(self.cb_rate.currentData(), self._initial_rate):
            return True
        dev_desc = self._audio_output.device().description() if self._audio_output else None
        return not values_equal(dev_desc, self._initial_device_desc)

    def save_tab(self) -> None:
        """Alias conventionnel pour save_settings()."""
        self.save_settings()

    def _populate_audio_devices(self) -> None:
        """Remplit la liste des périphériques de sortie audio disponibles."""
        self.cb_device.clear()
        if not HAS_QTMULTIMEDIA or QMediaDevices is None:
            self.cb_device.addItem("Sortie audio système par défaut", "")
            self.cb_device.setEnabled(False)
            return

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
        if self._audio_output:
            self._initial_device_desc = self._audio_output.device().description()

    def _on_audio_device_changed(self) -> None:
        """Applique le périphérique audio sélectionné au lecteur."""
        if not self._audio_output:
            return
        selected_id = self.cb_device.currentData()
        for dev in getattr(self, "_audio_devices", []):
            if dev.id() == selected_id:
                self._audio_output.setDevice(dev)
                logger.info("Sortie audio changée vers : %s", dev.description())
                break

    def _on_playback_state_changed(self, state: Any) -> None:
        """Met à jour l'icône et l'intitulé du bouton de test selon la lecture."""
        is_playing = QMediaPlayer is not None and hasattr(QMediaPlayer, "PlaybackState") and state == QMediaPlayer.PlaybackState.PlayingState
        if is_playing:
            self.btn_test.setText(" Arrêter la lecture")
            self.btn_test.setIcon(load_phosphor_icon("ph.stop", color=DesignTokens.COLOR_RED))
        else:
            self.btn_test.setText(" Tester la voix sélectionnée")
            self.btn_test.setIcon(load_phosphor_icon("ph.speaker-high", color=DesignTokens.ACCENT_PRIMARY))

    def _on_test_voice(self) -> None:
        """Génère et lit un échantillon de voix avec les réglages actuels."""
        if not self._player or QMediaPlayer is None:
            show_toast(self, "La lecture audio n'est pas supportée sur ce système (libpulse manquant).", is_error=True)
            return

        if hasattr(QMediaPlayer, "PlaybackState") and self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
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
            dev_desc = self._audio_output.device().description() if self._audio_output else "Sortie audio"
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

    def _on_install_kokoro(self) -> None:
        """Lance l'installation / configuration du runner Kokoro en tâche de fond."""
        self.btn_install_kokoro.setEnabled(False)
        self.lbl_kokoro_install_progress.setText("Configuration en cours...")

        self._kokoro_worker = KokoroInstallerWorker()
        self._kokoro_worker.progress.connect(self.lbl_kokoro_install_progress.setText)
        self._kokoro_worker.finished_success.connect(self._on_kokoro_installer_success)
        self._kokoro_worker.failed.connect(self._on_kokoro_installer_failed)
        self._kokoro_worker.start()

    def _on_kokoro_installer_success(self) -> None:
        self.btn_install_kokoro.setEnabled(True)
        self.lbl_kokoro_install_progress.setText("Kokoro configuré avec succès !")
        self._update_kokoro_status_ui()
        self._populate_engines()
        show_toast(self, "Le runner Kokoro-82M a été configuré avec succès.")

    def _on_kokoro_installer_failed(self, err_msg: str) -> None:
        self.btn_install_kokoro.setEnabled(True)
        self.lbl_kokoro_install_progress.setText("Échec de la configuration.")
        show_toast(self, f"Configuration de Kokoro échouée : {err_msg}", is_error=True)

    def _on_player_error(self, error: Any, error_string: str) -> None:
        logger.warning("Erreur du lecteur audio : %s - %s", error, error_string)
        show_toast(self, f"Erreur de lecture audio : {error_string}", is_error=True)

    def closeEvent(self, event: Any) -> None:
        if self._player and QMediaPlayer is not None and hasattr(QMediaPlayer, "PlaybackState") and self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.stop()
        super().closeEvent(event)
