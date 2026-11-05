"""Onglet Paramètres Synthèse Vocale (TTS) & Gestionnaire de Moteurs Découplés.

Permet de choisir le moteur de voix par défaut, d'auditionner les voix,
et d'installer/mettre à jour le binaire autonome Piper TTS en local.
"""

import logging
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal

from ankiforge.utils.i18n import tr

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer

    HAS_QTMULTIMEDIA = True
except (ImportError, OSError):
    QAudioOutput = None  # type: ignore[misc]  # PySide6 QtMultimedia indisponible : repli sur None
    QMediaDevices = None  # type: ignore[misc]
    QMediaPlayer = None  # type: ignore[misc]
    HAS_QTMULTIMEDIA = False
from PySide6.QtWidgets import (
    QDoubleSpinBox,
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
from ankiforge.ui.widgets.settings_modal.components.collapsible_section import CollapsibleSection
from ankiforge.ui.widgets.settings_modal.components.settings_card import SettingsCard
from ankiforge.ui.widgets.settings_modal.dirty import SettingsDirtyMixin
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon
from ankiforge.utils.paths import get_app_data_dir

logger = logging.getLogger(__name__)


class TTSDiscoverySignals(QObject):
    """Signaux pour la détection asynchrone des sidecars et périphériques audio."""

    finished = Signal(dict)


class TTSDiscoveryWorker(QThread):
    """Worker d'arrière-plan pour la détection non bloquante des sidecars et sorties audio."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.signals = TTSDiscoverySignals()

    def run(self) -> None:
        is_piper_ok, piper_msg = PiperSidecarProvider.is_functional()
        is_kokoro_ok, kokoro_msg = KokoroSidecarProvider.is_functional()
        has_kokoro_runner = KokoroSidecarProvider.has_runner()
        has_kokoro_models = KokoroSidecarProvider.has_models()

        audio_devices_data: list[dict[str, Any]] = []
        default_dev_id: Any = None
        if HAS_QTMULTIMEDIA and QMediaDevices is not None:
            try:
                def_dev = QMediaDevices.defaultAudioOutput()
                default_dev_id = def_dev.id()
                for dev in QMediaDevices.audioOutputs():
                    audio_devices_data.append(
                        {
                            "id": dev.id(),
                            "name": dev.description(),
                            "is_default": dev.id() == default_dev_id,
                        }
                    )
            except Exception as err:
                logger.debug("Échec d'énumération des périphériques audio en tâche de fond : %s", err)

        self.signals.finished.emit(
            {
                "is_piper_ok": is_piper_ok,
                "piper_msg": piper_msg,
                "is_kokoro_ok": is_kokoro_ok,
                "kokoro_msg": kokoro_msg,
                "has_kokoro_runner": has_kokoro_runner,
                "has_kokoro_models": has_kokoro_models,
                "audio_devices": audio_devices_data,
                "default_dev_id": default_dev_id,
            }
        )


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


class PiperVoiceInstallerWorker(QThread):
    """Worker asynchrone pour le téléchargement d'une voix Piper depuis le catalogue HuggingFace."""

    progress = Signal(str)
    finished_success = Signal(str)
    failed = Signal(str)

    def __init__(self, voice_id: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.voice_id = voice_id

    def run(self) -> None:
        try:
            get_tts_service().download_piper_voice(self.voice_id, progress_callback=self.progress.emit)
            self.finished_success.emit(self.voice_id)
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

        # Lecteur audio instancié à la demande (lazy) pour un chargement instantané de l'onglet
        self._player: Any = None
        self._audio_output: Any = None

        self._installer_worker: PiperInstallerWorker | None = None
        self._voice_installer_worker: PiperVoiceInstallerWorker | None = None
        self._kokoro_worker: KokoroInstallerWorker | None = None
        self._discovery_worker: TTSDiscoveryWorker | None = None
        # Référence du périphérique audio actif au chargement (évite un faux « modifié »).
        self._initial_device_desc: str | None = None

        self._setup_ui()
        self._load_settings()
        # Référence des valeurs chargées : évite de marquer « modifié » un réglage auto-sélectionné.
        self._initial_engine: Any = self.cb_engine.currentData()
        self._initial_voice: Any = self.cb_voice.currentData()
        self._initial_rate: Any = self.cb_rate.currentData()
        self._initial_speed: float = self.spn_tts_default_speed.value()
        self._initial_voice_fr: str | None = self.cb_tts_default_voice_fr.currentData()
        self._initial_voice_en: str | None = self.cb_tts_default_voice_en.currentData()

        # Lancement de la détection asynchrone non bloquante
        self._start_discovery_worker()

    def _setup_ui(self) -> None:
        from PySide6.QtWidgets import QFrame, QScrollArea

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.content_widget = QWidget()
        layout = QVBoxLayout(self.content_widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # ── SECTION 1 : CONFIGURATION GÉNÉRALE TTS ──────────────────────────
        self.lbl_sec_general = QLabel(self.tr("CONFIGURATION DU MOTEUR VOCAL"))
        self.lbl_sec_general.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(self.lbl_sec_general)

        self.card_general = SettingsCard()
        card_gen_layout = QVBoxLayout(self.card_general)
        card_gen_layout.setContentsMargins(14, 12, 14, 12)
        card_gen_layout.setSpacing(10)

        # 1. Choix du Moteur
        row_engine = QHBoxLayout()
        lbl_engine = QLabel(self.tr("Moteur de synthèse :"))
        lbl_engine.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_engine.addWidget(lbl_engine)
        row_engine.addStretch()

        self.cb_engine = StyledComboBox()
        self.cb_engine.setFixedWidth(280)
        self.cb_engine.setFixedHeight(28)
        if self.cb_engine.view() is not None:
            self.cb_engine.view().setTextElideMode(Qt.TextElideMode.ElideRight)
        self._populate_engines()
        self.cb_engine.currentIndexChanged.connect(self._on_engine_changed)
        row_engine.addWidget(self.cb_engine)
        card_gen_layout.addLayout(row_engine)

        # 2. Choix de la Voix
        row_voice = QHBoxLayout()
        lbl_voice = QLabel(self.tr("Voix par défaut :"))
        lbl_voice.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_voice.addWidget(lbl_voice)
        row_voice.addStretch()

        self.cb_voice = StyledComboBox()
        self.cb_voice.setFixedWidth(280)
        self.cb_voice.setFixedHeight(28)
        if self.cb_voice.view() is not None:
            self.cb_voice.view().setTextElideMode(Qt.TextElideMode.ElideRight)
        row_voice.addWidget(self.cb_voice)
        card_gen_layout.addLayout(row_voice)

        # 3. Vitesse et Tonalité
        row_params = QHBoxLayout()
        lbl_rate = QLabel(self.tr("Vitesse d'élocution :"))
        lbl_rate.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_params.addWidget(lbl_rate)
        row_params.addStretch()

        self.cb_rate = StyledComboBox()
        self.cb_rate.setFixedWidth(280)
        self.cb_rate.setFixedHeight(28)
        if self.cb_rate.view() is not None:
            self.cb_rate.view().setTextElideMode(Qt.TextElideMode.ElideRight)
        self.cb_rate.addItem(self.tr("Normale (100%)"), "+0%")
        self.cb_rate.addItem(self.tr("Lente (85%)"), "-15%")
        self.cb_rate.addItem(self.tr("Rapide (115%)"), "+15%")
        self.cb_rate.addItem(self.tr("Très rapide (130%)"), "+30%")
        row_params.addWidget(self.cb_rate)
        card_gen_layout.addLayout(row_params)

        # 4. Périphérique de Sortie Audio
        row_device = QHBoxLayout()
        lbl_device = QLabel(self.tr("Sortie audio :"))
        lbl_device.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_device.addWidget(lbl_device)
        row_device.addStretch()

        self.cb_device = StyledComboBox()
        self.cb_device.setFixedWidth(280)
        self.cb_device.setFixedHeight(28)
        if self.cb_device.view() is not None:
            self.cb_device.view().setTextElideMode(Qt.TextElideMode.ElideRight)
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

        # ── SECTION 1b : PARAMÈTRES PAR DÉFAUT TTS ───────────────────────────
        self.lbl_sec_tts_defaults = QLabel(self.tr("PARAMÈTRES PAR DÉFAUT TTS"))
        self.lbl_sec_tts_defaults.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 4px;")
        layout.addWidget(self.lbl_sec_tts_defaults)

        self.card_tts_defaults = SettingsCard()
        card_tts_defaults_layout = QVBoxLayout(self.card_tts_defaults)
        card_tts_defaults_layout.setContentsMargins(14, 12, 14, 12)
        card_tts_defaults_layout.setSpacing(12)

        # Vitesse par défaut (0.5x à 2.0x, pas 0.05, défaut 1.0x)
        row_speed = QHBoxLayout()
        lbl_speed = QLabel(self.tr("Vitesse par défaut :"))
        lbl_speed.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_speed.addWidget(lbl_speed)
        row_speed.addStretch()
        self.spn_tts_default_speed = QDoubleSpinBox()
        self.spn_tts_default_speed.setRange(0.5, 2.0)
        self.spn_tts_default_speed.setSingleStep(0.05)
        self.spn_tts_default_speed.setDecimals(2)
        self.spn_tts_default_speed.setValue(float(SettingsService.get("tts/default_speed", 1.0)))
        self.spn_tts_default_speed.setSuffix(" x")
        self.spn_tts_default_speed.setFixedHeight(28)
        row_speed.addWidget(self.spn_tts_default_speed)
        card_tts_defaults_layout.addLayout(row_speed)

        # Voix par défaut français
        row_voice_fr = QHBoxLayout()
        lbl_voice_fr = QLabel(self.tr("Voix par défaut (français) :"))
        lbl_voice_fr.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_voice_fr.addWidget(lbl_voice_fr)
        row_voice_fr.addStretch()
        self.cb_tts_default_voice_fr = StyledComboBox()
        self.cb_tts_default_voice_fr.setFixedWidth(280)
        self.cb_tts_default_voice_fr.setFixedHeight(28)
        self._populate_voice_combo(self.cb_tts_default_voice_fr, "fr")
        saved_voice_fr = SettingsService.get("tts/voice_fr", "fr-FR-Standard")
        idx_voice_fr = self.cb_tts_default_voice_fr.findData(saved_voice_fr)
        if idx_voice_fr >= 0:
            self.cb_tts_default_voice_fr.setCurrentIndex(idx_voice_fr)
        row_voice_fr.addWidget(self.cb_tts_default_voice_fr)
        card_tts_defaults_layout.addLayout(row_voice_fr)

        # Voix par défaut anglais
        row_voice_en = QHBoxLayout()
        lbl_voice_en = QLabel(self.tr("Voix par défaut (anglais) :"))
        lbl_voice_en.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_voice_en.addWidget(lbl_voice_en)
        row_voice_en.addStretch()
        self.cb_tts_default_voice_en = StyledComboBox()
        self.cb_tts_default_voice_en.setFixedWidth(280)
        self.cb_tts_default_voice_en.setFixedHeight(28)
        self._populate_voice_combo(self.cb_tts_default_voice_en, "en")
        saved_voice_en = SettingsService.get("tts/voice_en", "en-US-Standard")
        idx_voice_en = self.cb_tts_default_voice_en.findData(saved_voice_en)
        if idx_voice_en >= 0:
            self.cb_tts_default_voice_en.setCurrentIndex(idx_voice_en)
        row_voice_en.addWidget(self.cb_tts_default_voice_en)
        card_tts_defaults_layout.addLayout(row_voice_en)

        layout.addWidget(self.card_tts_defaults)

        # ── SECTION 2 : GESTIONNAIRE LOCAL PIPER (COLLAPSIBLE SECTION) ───────
        self.sec_piper = CollapsibleSection(self.tr("MOTEUR LOCAL PIPER"), parent=self, collapsed=True)
        self.card_piper = self.sec_piper  # Alias de rétrocompatibilité

        # Statut de Piper
        row_status = QHBoxLayout()
        lbl_status_title = QLabel(self.tr("Statut de Piper CLI :"))
        lbl_status_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_status.addWidget(lbl_status_title)

        self.lbl_piper_status = QLabel()
        self.lbl_piper_status.setWordWrap(True)
        self.lbl_piper_status.setStyleSheet("font-size: 11px; font-weight: bold;")
        row_status.addWidget(self.lbl_piper_status)
        row_status.addStretch()
        self.sec_piper.add_layout(row_status)

        # Emplacement
        lbl_location = QLabel(tr("Emplacement : %1", get_app_data_dir() / "tools" / "tts" / "piper"))
        lbl_location.setWordWrap(True)
        lbl_location.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        self.sec_piper.add_widget(lbl_location)

        # Bouton Télécharger / Installer
        row_install = QHBoxLayout()
        self.lbl_install_progress = QLabel("")
        self.lbl_install_progress.setWordWrap(True)
        self.lbl_install_progress.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 11px;")
        row_install.addWidget(self.lbl_install_progress, 1)

        self.btn_install_piper = PrimaryButton(" Télécharger Piper CLI (1-Clic)")
        self.btn_install_piper.setIcon(load_on_accent_icon("ph.download-simple"))
        self.btn_install_piper.setFixedHeight(30)
        self.btn_install_piper.clicked.connect(self._on_install_piper)
        row_install.addWidget(self.btn_install_piper)
        self.sec_piper.add_layout(row_install)

        # Voix supplémentaires du catalogue Piper (HuggingFace)
        row_voice_cat = QHBoxLayout()
        lbl_cat_title = QLabel(self.tr("Voix additionnelles :"))
        lbl_cat_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_voice_cat.addWidget(lbl_cat_title)

        self.cb_piper_catalog_voices = StyledComboBox()
        self.cb_piper_catalog_voices.setMaximumWidth(280)
        row_voice_cat.addWidget(self.cb_piper_catalog_voices, 1)

        self.btn_download_piper_voice = SecondaryButton(self.tr(" Télécharger"))
        self.btn_download_piper_voice.setIcon(load_phosphor_icon("ph.download-simple", color=DesignTokens.ACCENT_PRIMARY))
        self.btn_download_piper_voice.setFixedHeight(30)
        self.btn_download_piper_voice.clicked.connect(self._on_download_piper_voice)
        row_voice_cat.addWidget(self.btn_download_piper_voice)
        self.sec_piper.add_layout(row_voice_cat)

        self.lbl_voice_install_progress = QLabel("")
        self.lbl_voice_install_progress.setWordWrap(True)
        self.lbl_voice_install_progress.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 11px;")
        self.sec_piper.add_widget(self.lbl_voice_install_progress)
        self._populate_piper_catalog_voices()

        layout.addWidget(self.sec_piper)
        self._update_piper_status_ui()

        # ── SECTION 3 : GESTIONNAIRE LOCAL KOKORO-82M (COLLAPSIBLE SECTION) ──
        self.sec_kokoro = CollapsibleSection(self.tr("MOTEUR LOCAL KOKORO-82M (OPTIONNEL)"), parent=self, collapsed=True)
        self.card_kokoro = self.sec_kokoro  # Alias de rétrocompatibilité

        # Statut de Kokoro
        row_kokoro_status = QHBoxLayout()
        lbl_kokoro_title = QLabel(self.tr("Statut du Runner Kokoro :"))
        lbl_kokoro_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_kokoro_status.addWidget(lbl_kokoro_title)

        self.lbl_kokoro_status = QLabel()
        self.lbl_kokoro_status.setWordWrap(True)
        self.lbl_kokoro_status.setStyleSheet("font-size: 11px; font-weight: bold;")
        row_kokoro_status.addWidget(self.lbl_kokoro_status)
        row_kokoro_status.addStretch()
        self.sec_kokoro.add_layout(row_kokoro_status)

        # Emplacement
        lbl_kokoro_loc = QLabel(tr("Emplacement : %1", get_app_data_dir() / "tools" / "tts" / "kokoro"))
        lbl_kokoro_loc.setWordWrap(True)
        lbl_kokoro_loc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        self.sec_kokoro.add_widget(lbl_kokoro_loc)

        # Description / Guide
        lbl_kokoro_guide = QLabel(
            self.tr("Kokoro-82M est un modèle local compact haute fidélité. Le runner s'exécute en processus déporté via ~/.ankiforge/tools/tts/kokoro/run.py ou un binaire 'kokoro' dans le PATH.")
        )
        lbl_kokoro_guide.setWordWrap(True)
        lbl_kokoro_guide.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        self.sec_kokoro.add_widget(lbl_kokoro_guide)

        # Bouton Installer / Configurer
        row_kokoro_install = QHBoxLayout()
        self.lbl_kokoro_install_progress = QLabel("")
        self.lbl_kokoro_install_progress.setWordWrap(True)
        self.lbl_kokoro_install_progress.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 11px;")
        row_kokoro_install.addWidget(self.lbl_kokoro_install_progress, 1)

        self.btn_install_kokoro = PrimaryButton(" Installer Kokoro (1-Clic)")
        self.btn_install_kokoro.setIcon(load_on_accent_icon("ph.download-simple"))
        self.btn_install_kokoro.setFixedHeight(30)
        self.btn_install_kokoro.clicked.connect(self._on_install_kokoro)
        row_kokoro_install.addWidget(self.btn_install_kokoro)
        self.sec_kokoro.add_layout(row_kokoro_install)

        layout.addWidget(self.sec_kokoro)
        self._update_kokoro_status_ui()

        layout.addStretch()

        self.scroll.setWidget(self.content_widget)
        root_layout.addWidget(self.scroll)

    def _start_discovery_worker(self) -> None:
        """Démarre le worker d'arrière-plan pour sonder les moteurs et sorties audio."""
        self._discovery_worker = TTSDiscoveryWorker(self)
        self._discovery_worker.signals.finished.connect(self._on_discovery_finished)
        self._discovery_worker.start()

    def _on_discovery_finished(self, results: dict[str, Any]) -> None:
        """Applique les résultats de la détection asynchrone à l'interface."""
        is_piper_ok = results.get("is_piper_ok", False)
        piper_msg = results.get("piper_msg", "")
        is_kokoro_ok = results.get("is_kokoro_ok", False)
        kokoro_msg = results.get("kokoro_msg", "")
        has_kokoro_runner = results.get("has_kokoro_runner")
        has_kokoro_models = results.get("has_kokoro_models")
        audio_devs = results.get("audio_devices", [])

        self._update_piper_status_ui(is_piper_ok, piper_msg)
        self._update_kokoro_status_ui(
            is_kokoro_ok,
            kokoro_msg,
            has_runner_val=has_kokoro_runner,
            has_models_val=has_kokoro_models,
        )

        if is_kokoro_ok and self.cb_engine.findData("kokoro") == -1:
            self.cb_engine.addItem(self.tr("Kokoro-82M (Runner Local Déporté)"), "kokoro")

        if audio_devs:
            self._populate_audio_devices(audio_devs)

    def _populate_engines(self) -> None:
        """Remplit le sélecteur des moteurs TTS avec vérification rapide de disponibilité."""
        current_data = self.cb_engine.currentData()
        self.cb_engine.blockSignals(True)
        self.cb_engine.clear()
        self.cb_engine.addItem(self.tr("Edge-TTS (Voix Neuronales Cloud Gratuit)"), "edge-tts")
        self.cb_engine.addItem(self.tr("Piper TTS (Local Hors-Ligne Standalone)"), "piper")
        self.cb_engine.addItem(self.tr("Moteur Système OS (Fallback Natif)"), "system")

        is_kokoro_ok, _ = KokoroSidecarProvider.is_functional()
        saved_engine = SettingsService.get("tts.engine")
        if is_kokoro_ok or saved_engine == "kokoro" or current_data == "kokoro":
            self.cb_engine.addItem(self.tr("Kokoro-82M (Runner Local Déporté)"), "kokoro")

        if current_data:
            idx = self.cb_engine.findData(current_data)
            if idx >= 0:
                self.cb_engine.setCurrentIndex(idx)
        self.cb_engine.blockSignals(False)

    def _populate_voice_combo(self, combo: StyledComboBox, lang: str) -> None:
        """Remplit un sélecteur de voix par défaut avec un jeu représentatif pour la langue donnée."""
        voices: list[tuple[str, str]] = {
            "fr": [
                (self.tr("fr-FR-Standard (Standard)"), "fr-FR-Standard"),
                (self.tr("fr-FR-Wavenet (Wavenet)"), "fr-FR-Wavenet"),
                (self.tr("fr-CA-Standard (Canada)"), "fr-CA-Standard"),
            ],
            "en": [
                (self.tr("en-US-Standard (Standard)"), "en-US-Standard"),
                (self.tr("en-US-Wavenet (Wavenet)"), "en-US-Wavenet"),
                (self.tr("en-GB-Standard (Royaume-Uni)"), "en-GB-Standard"),
            ],
        }.get(lang, [])
        combo.blockSignals(True)
        combo.clear()
        for label, voice_id in voices:
            combo.addItem(label, voice_id)
        combo.blockSignals(False)

    def _sync_sections(self, engine_id: str | None = None) -> None:
        """Déplie la section du moteur sélectionné et replie les autres."""
        if engine_id is None:
            engine_id = self.cb_engine.currentData()
        if engine_id == "piper":
            self.sec_piper.set_collapsed(False)
            self.sec_kokoro.set_collapsed(True)
        elif engine_id == "kokoro":
            self.sec_kokoro.set_collapsed(False)
            self.sec_piper.set_collapsed(True)
        else:
            self.sec_piper.set_collapsed(True)
            self.sec_kokoro.set_collapsed(True)

    def _update_piper_status_ui(self, is_functional_val: bool | None = None, msg_val: str | None = None) -> None:
        """Met à jour le libellé et la couleur du statut d'installation de Piper."""
        is_installed = PiperSidecarProvider.get_piper_executable() is not None
        if is_installed:
            if is_functional_val is not None:
                is_functional, msg = is_functional_val, msg_val or ""
            else:
                is_functional, msg = PiperSidecarProvider.is_functional()
            if is_functional:
                self.lbl_piper_status.setText(self.tr("● Installé et opérationnel"))
                self.lbl_piper_status.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 11px; font-weight: bold;")
                self.lbl_piper_status.setToolTip(self.tr("Binaire ou runner Piper opérationnel."))
                if hasattr(self, "btn_install_piper"):
                    self.btn_install_piper.setText(self.tr(" Réinstaller Piper CLI (1-Clic)"))
            else:
                if "Rosetta 2" in msg or "Bad CPU type" in msg or "[Errno 86]" in msg:
                    self.lbl_piper_status.setText(self.tr("○ Inopérationnel (Rosetta 2 requis)"))
                    self.lbl_piper_status.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; font-weight: bold;")
                    rosetta_help_msg = (
                        "Incompatibilité d'architecture Mac Apple Silicon :\n%1\n\n"
                        "Pour activer Rosetta 2, lancez dans le Terminal :\n  softwareupdate --install-rosetta\n"
                        "Ou réinstallez Piper pour déployer le runner natif piper-tts."
                    )
                    self.lbl_piper_status.setToolTip(tr(rosetta_help_msg, msg))
                else:
                    self.lbl_piper_status.setText(self.tr("○ Inopérationnel (dépendance requise)"))
                    self.lbl_piper_status.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; font-weight: bold;")
                    self.lbl_piper_status.setToolTip(tr("Dépendance manquante ou non fonctionnelle :\n%1", msg))
                if hasattr(self, "btn_install_piper"):
                    self.btn_install_piper.setText(self.tr(" Réinstaller Piper CLI (1-Clic)"))
        else:
            self.lbl_piper_status.setText(self.tr("○ Non installé (binaire absent)"))
            self.lbl_piper_status.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; font-weight: bold;")
            if hasattr(self, "btn_install_piper"):
                self.btn_install_piper.setText(self.tr(" Télécharger Piper CLI (1-Clic)"))

    def _populate_piper_catalog_voices(self) -> None:
        """Remplit le sélecteur de voix additionnelles Piper du catalogue officiel."""
        if not hasattr(self, "cb_piper_catalog_voices"):
            return
        self.cb_piper_catalog_voices.blockSignals(True)
        self.cb_piper_catalog_voices.clear()
        catalog = PiperSidecarProvider.get_catalog_voices()
        for v in catalog:
            suffix = self.tr(" (Déjà installée)") if v["is_downloaded"] else self.tr(" (À télécharger)")
            self.cb_piper_catalog_voices.addItem(f"{v['name']} [{v['lang']}]{suffix}", v["id"])
        self.cb_piper_catalog_voices.blockSignals(False)

    def _on_download_piper_voice(self) -> None:
        """Télécharge la voix Piper sélectionnée depuis le catalogue HuggingFace."""
        if not hasattr(self, "cb_piper_catalog_voices"):
            return
        voice_id = self.cb_piper_catalog_voices.currentData()
        if not voice_id:
            return

        self.btn_download_piper_voice.setEnabled(False)
        self.lbl_voice_install_progress.setText(self.tr("Téléchargement de la voix en cours..."))

        self._voice_installer_worker = PiperVoiceInstallerWorker(voice_id, parent=self)
        self._voice_installer_worker.progress.connect(self.lbl_voice_install_progress.setText)
        self._voice_installer_worker.finished_success.connect(self._on_voice_installer_success)
        self._voice_installer_worker.failed.connect(self._on_voice_installer_failed)
        self._voice_installer_worker.start()

    def _on_voice_installer_success(self, voice_id: str) -> None:
        self.btn_download_piper_voice.setEnabled(True)
        self.lbl_voice_install_progress.setText(self.tr("Voix installée avec succès !"))
        self._populate_piper_catalog_voices()
        if self.cb_engine.currentData() == "piper":
            self._on_engine_changed()
        show_toast(self, self.tr("La voix Piper a été téléchargée et ajoutée au catalogue local."))

    def _on_voice_installer_failed(self, err_msg: str) -> None:
        self.btn_download_piper_voice.setEnabled(True)
        self.lbl_voice_install_progress.setText(self.tr("Échec du téléchargement."))
        show_toast(self, tr("Échec du téléchargement de la voix Piper : %1", err_msg), is_error=True)

    def _update_kokoro_status_ui(
        self,
        is_functional_val: bool | None = None,
        msg_val: str | None = None,
        has_runner_val: bool | None = None,
        has_models_val: bool | None = None,
    ) -> None:
        """Met à jour le libellé et la couleur du statut d'installation de Kokoro."""
        if is_functional_val is not None:
            is_functional, msg = is_functional_val, msg_val or ""
        else:
            is_functional, msg = KokoroSidecarProvider.is_functional()

        has_runner = has_runner_val if has_runner_val is not None else KokoroSidecarProvider.has_runner()
        has_models = has_models_val if has_models_val is not None else KokoroSidecarProvider.has_models()

        if is_functional:
            self.lbl_kokoro_status.setText(self.tr("● Installé et opérationnel"))
            self.lbl_kokoro_status.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 11px; font-weight: bold;")
            if hasattr(self, "btn_install_kokoro"):
                self.btn_install_kokoro.setEnabled(False)
                self.btn_install_kokoro.setText(self.tr(" Kokoro déjà installé et prêt"))
                self.btn_install_kokoro.setToolTip(self.tr("Le modèle Kokoro-82M est opérationnel sans configuration requise."))
        elif has_runner and not has_models:
            self.lbl_kokoro_status.setText(self.tr("◐ Partiel (modèles ONNX manquants)"))
            self.lbl_kokoro_status.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; font-weight: bold;")
            self.lbl_kokoro_status.setToolTip(msg)
            if hasattr(self, "btn_install_kokoro"):
                self.btn_install_kokoro.setEnabled(True)
                self.btn_install_kokoro.setText(self.tr(" Télécharger les modèles Kokoro"))
                self.btn_install_kokoro.setToolTip(self.tr("Télécharger les poids ONNX (kokoro-v1.0.onnx et voices-v1.0.bin)"))
        else:
            self.lbl_kokoro_status.setText(self.tr("○ Non installé (runner absent)"))
            self.lbl_kokoro_status.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; font-weight: bold;")
            self.lbl_kokoro_status.setToolTip(msg)
            if hasattr(self, "btn_install_kokoro"):
                self.btn_install_kokoro.setEnabled(True)
                self.btn_install_kokoro.setText(self.tr(" Installer Kokoro (1-Clic)"))
                self.btn_install_kokoro.setToolTip(self.tr("Télécharger et installer le runner Kokoro local"))

    def _on_engine_changed(self) -> None:
        """Met à jour la liste des voix et synchronise les sections pliables lorsque le moteur change."""
        engine_id = self.cb_engine.currentData()
        self.cb_voice.clear()

        try:
            provider = self.tts_service.get_provider(engine_id)
            voices = provider.get_voices()
            for v in voices:
                self.cb_voice.addItem(tr("%1 (%2)", v["name"], v.get("lang", "")), v["id"])
        except Exception as e:
            self.cb_voice.addItem(tr("Erreur de chargement des voix : %1", e), "default")

        self._sync_sections(engine_id)

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
                    self.tr("Le moteur Kokoro-82M n'est pas opérationnel sur cette machine. Repli automatique sur Edge-TTS."),
                    is_error=False,
                )
            self.cb_engine.setCurrentIndex(0)

        # Toujours peupler la liste des voix du moteur sélectionné et synchroniser les sections
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
        SettingsService.set("tts/default_speed", float(self.spn_tts_default_speed.value()), category="multimedia")
        SettingsService.set("tts/voice_fr", self.cb_tts_default_voice_fr.currentData(), category="multimedia")
        SettingsService.set("tts/voice_en", self.cb_tts_default_voice_en.currentData(), category="multimedia")

        self._record_initial_state()
        if self._audio_output:
            dev_desc = self._audio_output.device().description()
            if dev_desc:
                SettingsService.set("tts.device_name", dev_desc, category="multimedia")
        elif hasattr(self, "cb_device") and self.cb_device.currentText():
            clean_name = self.cb_device.currentText().replace(" (Par défaut)", "")
            if clean_name and clean_name != self.tr("Sortie audio système par défaut"):
                SettingsService.set("tts.device_name", clean_name, category="multimedia")

    def has_pending_changes(self) -> bool:
        """True si un paramètre TTS diffère de sa valeur chargée (ou de la sortie audio active)."""
        if not values_equal(self.cb_engine.currentData(), self._initial_engine):
            return True
        if not values_equal(self.cb_voice.currentData(), self._initial_voice):
            return True
        if not values_equal(self.cb_rate.currentData(), self._initial_rate):
            return True
        if not values_equal(self.spn_tts_default_speed.value(), self._initial_speed):
            return True
        if not values_equal(self.cb_tts_default_voice_fr.currentData(), self._initial_voice_fr):
            return True
        if not values_equal(self.cb_tts_default_voice_en.currentData(), self._initial_voice_en):
            return True
        if self._audio_output:
            dev_desc = self._audio_output.device().description()
        elif hasattr(self, "cb_device") and self.cb_device.currentText():
            dev_desc = self.cb_device.currentText().replace(" (Par défaut)", "")
        else:
            dev_desc = None
        return not values_equal(dev_desc, self._initial_device_desc)

    def save_tab(self) -> None:
        """Alias conventionnel pour save_settings()."""
        self.save_settings()

    def _record_initial_state(self) -> None:
        """Capture l'état actuel des contrôles TTS pour la détection dirty à zéro coût BDD."""
        self._initial_engine = self.cb_engine.currentData()
        self._initial_voice = self.cb_voice.currentData()
        self._initial_rate = self.cb_rate.currentData()
        self._initial_speed = self.spn_tts_default_speed.value()
        self._initial_voice_fr = self.cb_tts_default_voice_fr.currentData()
        self._initial_voice_en = self.cb_tts_default_voice_en.currentData()

    def _populate_audio_devices(self, devices_data: list[dict[str, Any]] | None = None) -> None:
        """Remplit la liste des périphériques de sortie audio disponibles."""
        self.cb_device.blockSignals(True)
        self.cb_device.clear()

        if not HAS_QTMULTIMEDIA or (QMediaDevices is None and devices_data is None):
            self.cb_device.addItem(self.tr("Sortie audio système par défaut"), "")
            self.cb_device.setEnabled(False)
            self.cb_device.blockSignals(False)
            return

        saved_dev_name = SettingsService.get("tts.device_name")
        default_idx = 0
        saved_idx: int | None = None

        if devices_data:
            for idx, d in enumerate(devices_data):
                name = d["name"]
                is_def = d.get("is_default", False)
                label = f"{name} (Par défaut)" if is_def else name
                self.cb_device.addItem(label, d["id"])
                if is_def:
                    default_idx = idx
                if saved_dev_name and name == saved_dev_name:
                    saved_idx = idx
        else:
            try:
                default_device = QMediaDevices.defaultAudioOutput()
                self._audio_devices = list(QMediaDevices.audioOutputs())
                for idx, dev in enumerate(self._audio_devices):
                    name = dev.description()
                    is_def = dev.id() == default_device.id()
                    label = f"{name} (Par défaut)" if is_def else name
                    self.cb_device.addItem(label, dev.id())
                    if is_def:
                        default_idx = idx
                    if saved_dev_name and name == saved_dev_name:
                        saved_idx = idx
            except Exception as err:
                logger.debug("Échec de détection audio directe : %s", err)
                self.cb_device.addItem(self.tr("Sortie audio système par défaut"), "")

        if self.cb_device.count() == 0:
            self.cb_device.addItem(self.tr("Sortie audio système par défaut"), "")

        target_idx = saved_idx if saved_idx is not None else default_idx
        if 0 <= target_idx < self.cb_device.count():
            self.cb_device.setCurrentIndex(target_idx)

        self.cb_device.blockSignals(False)
        self._on_audio_device_changed()
        if self._initial_device_desc is None:
            if self._audio_output:
                self._initial_device_desc = self._audio_output.device().description()
            elif self.cb_device.currentText():
                self._initial_device_desc = self.cb_device.currentText().replace(" (Par défaut)", "")

    def _ensure_player_initialized(self) -> bool:
        """Initialise de façon paresseuse le lecteur audio QtMultimedia au premier besoin."""
        if self._player is not None:
            return True
        if not HAS_QTMULTIMEDIA or QMediaPlayer is None or QAudioOutput is None:
            return False
        try:
            self._player = QMediaPlayer(self)
            self._audio_output = QAudioOutput(self)
            self._audio_output.setVolume(1.0)
            self._audio_output.setMuted(False)
            self._player.setAudioOutput(self._audio_output)
            self._player.playbackStateChanged.connect(self._on_playback_state_changed)
            self._player.errorOccurred.connect(self._on_player_error)
            self._on_audio_device_changed()
            return True
        except Exception as e:
            logger.warning("Échec d'initialisation du lecteur audio : %s", e)
            self._player = None
            self._audio_output = None
            return False

    def _on_audio_device_changed(self) -> None:
        """Applique le périphérique audio sélectionné au lecteur s'il est initialisé."""
        if not self._audio_output:
            return
        selected_id = self.cb_device.currentData()
        for dev in getattr(self, "_audio_devices", []):
            if hasattr(dev, "id") and dev.id() == selected_id:
                self._audio_output.setDevice(dev)
                logger.info("Sortie audio changée vers : %s", dev.description())
                break

    def _on_playback_state_changed(self, state: Any) -> None:
        """Met à jour l'icône et l'intitulé du bouton de test selon la lecture."""
        is_playing = QMediaPlayer is not None and hasattr(QMediaPlayer, "PlaybackState") and state == QMediaPlayer.PlaybackState.PlayingState
        if is_playing:
            self.btn_test.setText(self.tr(" Arrêter la lecture"))
            self.btn_test.setIcon(load_phosphor_icon("ph.stop", color=DesignTokens.COLOR_RED))
        else:
            self.btn_test.setText(self.tr(" Tester la voix sélectionnée"))
            self.btn_test.setIcon(load_phosphor_icon("ph.speaker-high", color=DesignTokens.ACCENT_PRIMARY))

    def _on_test_voice(self) -> None:
        """Génère et lit un échantillon de voix avec les réglages actuels."""
        if not self._ensure_player_initialized():
            show_toast(self, self.tr("La lecture audio n'est pas supportée sur ce système (libpulse manquant)."), is_error=True)
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
            show_toast(self, tr("Lecture audio en cours sur '%1'...", dev_desc))
        except Exception as e:
            logger.exception("Erreur lors du test vocal : %s", e)
            show_toast(self, tr("Erreur lors du test vocal : %1", e), is_error=True)
        finally:
            self.btn_test.setEnabled(True)

    def _on_install_piper(self) -> None:
        """Lance le téléchargement de Piper CLI en tâche de fond."""
        self.btn_install_piper.setEnabled(False)
        self.lbl_install_progress.setText(self.tr("Téléchargement en cours..."))

        self._installer_worker = PiperInstallerWorker()
        self._installer_worker.progress.connect(self.lbl_install_progress.setText)
        self._installer_worker.finished_success.connect(self._on_installer_success)
        self._installer_worker.failed.connect(self._on_installer_failed)
        self._installer_worker.start()

    def _on_installer_success(self) -> None:
        self.btn_install_piper.setEnabled(True)
        self.lbl_install_progress.setText(self.tr("Piper installé avec succès !"))
        self._update_piper_status_ui(True, "Opérationnel")
        self._populate_piper_catalog_voices()
        self._populate_engines()
        self._on_engine_changed()
        show_toast(self, self.tr("Piper TTS a été installé avec succès."))

    def _on_installer_failed(self, err_msg: str) -> None:
        self.btn_install_piper.setEnabled(True)
        self.lbl_install_progress.setText(self.tr("Échec du téléchargement."))
        show_toast(self, tr("Installation de Piper échouée : %1", err_msg), is_error=True)

    def _on_install_kokoro(self) -> None:
        """Lance l'installation / configuration du runner Kokoro en tâche de fond."""
        self.btn_install_kokoro.setEnabled(False)
        self.lbl_kokoro_install_progress.setText(self.tr("Configuration en cours..."))

        self._kokoro_worker = KokoroInstallerWorker()
        self._kokoro_worker.progress.connect(self.lbl_kokoro_install_progress.setText)
        self._kokoro_worker.finished_success.connect(self._on_kokoro_installer_success)
        self._kokoro_worker.failed.connect(self._on_kokoro_installer_failed)
        self._kokoro_worker.start()

    def _on_kokoro_installer_success(self) -> None:
        self.lbl_kokoro_install_progress.setText(self.tr("Kokoro configuré avec succès !"))
        self._update_kokoro_status_ui(True, "Opérationnel")
        self._populate_engines()
        self._on_engine_changed()
        show_toast(self, self.tr("Le runner Kokoro-82M a été configuré avec succès."))

    def _on_kokoro_installer_failed(self, err_msg: str) -> None:
        self.btn_install_kokoro.setEnabled(True)
        self.lbl_kokoro_install_progress.setText(self.tr("Échec de la configuration."))
        show_toast(self, tr("Configuration de Kokoro échouée : %1", err_msg), is_error=True)

    def _on_player_error(self, error: Any, error_string: str) -> None:
        logger.warning("Erreur du lecteur audio : %s - %s", error, error_string)
        show_toast(self, tr("Erreur de lecture audio : %1", error_string), is_error=True)

    def refresh_theme(self, profile: Any) -> None:
        """Rafraîchit les styles et les cartes de l'onglet selon le profil de thème actif."""
        if hasattr(self, "card_general") and hasattr(self.card_general, "refresh_theme"):
            self.card_general.refresh_theme(profile)
        if hasattr(self, "card_tts_defaults") and hasattr(self.card_tts_defaults, "refresh_theme"):
            self.card_tts_defaults.refresh_theme(profile)
        if hasattr(self, "sec_piper") and hasattr(self.sec_piper, "refresh_theme"):
            self.sec_piper.refresh_theme(profile)
        if hasattr(self, "sec_kokoro") and hasattr(self.sec_kokoro, "refresh_theme"):
            self.sec_kokoro.refresh_theme(profile)
        self.lbl_sec_general.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        if hasattr(self, "lbl_sec_tts_defaults"):
            self.lbl_sec_tts_defaults.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 4px;")

    def closeEvent(self, event: Any) -> None:
        if self._player and QMediaPlayer is not None and hasattr(QMediaPlayer, "PlaybackState") and self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.stop()
        for w in (self._discovery_worker, self._installer_worker, self._voice_installer_worker, self._kokoro_worker):
            if w is not None and w.isRunning():
                w.quit()
                w.wait(500)
        super().closeEvent(event)
