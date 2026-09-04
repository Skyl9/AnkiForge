"""Widget de lecture audio interactif et synchronisé pour AnkiForge.

Permet d'écouter les enregistrements de cours, podcasts et amphis tout en suivant
la transcription textuelle, avec navigation par clic sur les fragments horodatés.
"""

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTime, QUrl, Signal, Slot

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    HAS_QTMULTIMEDIA = True
except (ImportError, OSError):
    QAudioOutput = None  # type: ignore[assignment, misc]
    QMediaPlayer = None  # type: ignore[assignment, misc]
    HAS_QTMULTIMEDIA = False
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
)

from ankiforge.ui.components.buttons import IconButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


def format_duration(milliseconds: int) -> str:
    """Formate une durée en millisecondes en chaîne mm:ss ou hh:mm:ss."""
    seconds = max(0, milliseconds // 1000)
    time = QTime(0, 0, 0).addSecs(seconds)
    if seconds >= 3600:
        return time.toString("hh:mm:ss")
    return time.toString("mm:ss")


class AudioPlayerWidget(QFrame):
    """Lecteur audio compact et ergonomique intégré à l'éditeur de documents.

    Fonctionnalités :
    - Lecture / Pause / Stop avec raccourcis et boutons Phosphor.
    - Saut rapide avant / arrière (+10s / -10s).
    - Curseur temporel interactif avec mise à jour continue sans à-coups.
    - Vitesse de lecture ajustable (0.75x, 1.0x, 1.25x, 1.5x, 2.0x).
    - Contrôle du volume et sourdine.
    - Émission de signaux pour synchronisation avec le texte.
    """

    time_jumped = Signal(float)  # en secondes
    position_changed = Signal(int)  # en millisecondes

    def __init__(self, parent: QFrame | None = None) -> None:
        super().__init__(parent)
        self._duration_ms = 0
        self._is_slider_dragging = False
        self._current_file: str | None = None

        self._setup_audio_engine()
        self._setup_ui()
        self._apply_styling()

    def _setup_audio_engine(self) -> None:
        """Initialise le moteur audio Qt (sécurisé contre absence de libpulse)."""
        if HAS_QTMULTIMEDIA and QMediaPlayer is not None and QAudioOutput is not None:
            self._player: Any = QMediaPlayer(self)
            self._audio_output: Any = QAudioOutput(self)
            self._player.setAudioOutput(self._audio_output)
            self._audio_output.setVolume(0.8)

            self._player.positionChanged.connect(self._on_player_position_changed)
            self._player.durationChanged.connect(self._on_player_duration_changed)
            self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        else:
            self._player = None
            self._audio_output = None

    def _setup_ui(self) -> None:
        """Construit l'interface du lecteur."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(6)

        # 1. Ligne Supérieure : Titre du fichier, Badge de statut et Vitesse
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.lbl_icon = QLabel()
        self.lbl_icon.setPixmap(load_phosphor_icon("ph.waveform", color=DesignTokens.COLOR_GREEN).pixmap(18, 18))
        top_row.addWidget(self.lbl_icon)

        self.lbl_title = QLabel("Aucun enregistrement audio chargé")
        self.lbl_title.setStyleSheet(f"font-weight: 600; color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;")
        top_row.addWidget(self.lbl_title, 1)

        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: '{DesignTokens.FONT_CODE}'; font-size: 11px;")
        top_row.addWidget(self.lbl_time)

        self.combo_speed = QComboBox()
        self.combo_speed.addItems(["0.75x", "1.0x", "1.25x", "1.5x", "2.0x"])
        self.combo_speed.setCurrentIndex(1)  # 1.0x
        self.combo_speed.setFixedWidth(70)
        self.combo_speed.currentTextChanged.connect(self._on_speed_changed)
        top_row.addWidget(self.combo_speed)

        main_layout.addLayout(top_row)

        # 2. Ligne Inférieure : Contrôles, Barre de progression et Volume
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)

        self.btn_prev_10 = IconButton("ph.arrow-counter-clockwise", tooltip="Reculer de 10 secondes", size=24)
        self.btn_prev_10.clicked.connect(self._on_skip_backward)
        ctrl_row.addWidget(self.btn_prev_10)

        self.btn_play = IconButton("ph.play", tooltip="Lecture / Pause", size=26)
        self.btn_play.clicked.connect(self.toggle_play)
        ctrl_row.addWidget(self.btn_play)

        self.btn_next_10 = IconButton("ph.arrow-clockwise", tooltip="Avancer de 10 secondes", size=24)
        self.btn_next_10.clicked.connect(self._on_skip_forward)
        ctrl_row.addWidget(self.btn_next_10)

        # Curseur de position temporelle
        self.slider_timeline = QSlider()
        self.slider_timeline.setOrientation(self.slider_timeline.orientation().Horizontal)
        self.slider_timeline.setRange(0, 0)
        self.slider_timeline.sliderPressed.connect(self._on_slider_pressed)
        self.slider_timeline.sliderReleased.connect(self._on_slider_released)
        self.slider_timeline.sliderMoved.connect(self._on_slider_moved)
        ctrl_row.addWidget(self.slider_timeline, 1)

        # Contrôle du volume
        self.btn_mute = IconButton("ph.speaker-high", tooltip="Couper / Rétablir le son", size=22)
        self.btn_mute.clicked.connect(self._on_toggle_mute)
        ctrl_row.addWidget(self.btn_mute)

        self.slider_volume = QSlider()
        self.slider_volume.setOrientation(self.slider_volume.orientation().Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(80)
        self.slider_volume.setFixedWidth(70)
        self.slider_volume.valueChanged.connect(self._on_volume_changed)
        ctrl_row.addWidget(self.slider_volume)

        main_layout.addLayout(ctrl_row)

    def _apply_styling(self) -> None:
        """Applique les styles conformes au Design System."""
        self.setObjectName("AudioPlayerWidget")
        self.setStyleSheet(f"""
            QFrame#AudioPlayerWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 2px 6px;
                font-size: 11px;
            }}
            QSlider::groove:horizontal {{
                border: 1px solid {DesignTokens.BORDER_COLOR};
                height: 4px;
                background: {DesignTokens.BG_INPUT};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {DesignTokens.COLOR_GREEN};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                width: 12px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 6px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {DesignTokens.COLOR_GREEN};
            }}
        """)

    def load_audio(self, file_path: str | Path) -> bool:
        """Charge un fichier audio dans le lecteur."""
        path_obj = Path(file_path)
        if not path_obj.exists():
            logger.warning("Fichier audio introuvable : %s", file_path)
            return False

        self._current_file = str(path_obj)
        self.stop()
        if self._player:
            self._player.setSource(QUrl.fromLocalFile(str(path_obj.resolve())))
            self.lbl_title.setText(path_obj.name)
        else:
            self.lbl_title.setText(f"{path_obj.name} (Audio non supporté)")
        self.lbl_time.setText("00:00 / 00:00")
        self.slider_timeline.setValue(0)
        logger.info("Fichier audio chargé dans le lecteur : %s", path_obj.name)
        return True

    @Slot()
    def toggle_play(self) -> None:
        """Alterne entre lecture et pause."""
        if not self._player or QMediaPlayer is None:
            return
        is_playing = hasattr(QMediaPlayer, "PlaybackState") and self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        if is_playing:
            self._player.pause()
        else:
            self._player.play()

    def play(self) -> None:
        """Démarre la lecture."""
        if self._player:
            self._player.play()

    def pause(self) -> None:
        """Met en pause la lecture."""
        if self._player:
            self._player.pause()

    def stop(self) -> None:
        """Arrête la lecture et revient au début."""
        if self._player:
            self._player.stop()
        self.slider_timeline.setValue(0)

    def seek_seconds(self, seconds: float) -> None:
        """Saute à un temps précis (en secondes) et démarre la lecture."""
        if not self._player:
            return
        ms = int(max(0.0, seconds) * 1000)
        self._player.setPosition(ms)
        self.slider_timeline.setValue(ms)
        self.play()
        self.time_jumped.emit(seconds)
        logger.debug("Saut audio vers %.2f secondes (%d ms)", seconds, ms)

    @Slot(int)
    def _on_player_position_changed(self, position_ms: int) -> None:
        """Met à jour l'affichage et le curseur si l'utilisateur ne le déplace pas."""
        if not self._is_slider_dragging:
            self.slider_timeline.setValue(position_ms)
        current_str = format_duration(position_ms)
        total_str = format_duration(self._duration_ms)
        self.lbl_time.setText(f"{current_str} / {total_str}")
        self.position_changed.emit(position_ms)

    @Slot(int)
    def _on_player_duration_changed(self, duration_ms: int) -> None:
        """Met à jour la durée totale du fichier."""
        self._duration_ms = duration_ms
        self.slider_timeline.setRange(0, duration_ms)
        pos = self._player.position() if self._player else 0
        current_str = format_duration(pos)
        total_str = format_duration(duration_ms)
        self.lbl_time.setText(f"{current_str} / {total_str}")

    @Slot(object)
    def _on_playback_state_changed(self, state: Any) -> None:
        """Met à jour l'icône du bouton play/pause."""
        is_playing = QMediaPlayer is not None and hasattr(QMediaPlayer, "PlaybackState") and state == QMediaPlayer.PlaybackState.PlayingState
        if is_playing:
            self.btn_play.setIcon(load_phosphor_icon("ph.pause", color=DesignTokens.TEXT_PRIMARY))
            self.btn_play.setToolTip("Mettre en pause")
        else:
            self.btn_play.setIcon(load_phosphor_icon("ph.play", color=DesignTokens.TEXT_PRIMARY))
            self.btn_play.setToolTip("Lancer la lecture")

    @Slot()
    def _on_slider_pressed(self) -> None:
        self._is_slider_dragging = True

    @Slot()
    def _on_slider_released(self) -> None:
        self._is_slider_dragging = False
        new_ms = self.slider_timeline.value()
        if self._player:
            self._player.setPosition(new_ms)
        self.time_jumped.emit(new_ms / 1000.0)

    @Slot(int)
    def _on_slider_moved(self, value_ms: int) -> None:
        current_str = format_duration(value_ms)
        total_str = format_duration(self._duration_ms)
        self.lbl_time.setText(f"{current_str} / {total_str}")

    @Slot()
    def _on_skip_backward(self) -> None:
        """Recule de 10 secondes."""
        if not self._player:
            return
        new_ms = max(0, self._player.position() - 10000)
        self._player.setPosition(new_ms)

    @Slot()
    def _on_skip_forward(self) -> None:
        """Avance de 10 secondes."""
        if not self._player:
            return
        new_ms = min(self._duration_ms, self._player.position() + 10000)
        self._player.setPosition(new_ms)

    @Slot(str)
    def _on_speed_changed(self, speed_text: str) -> None:
        """Modifie la vitesse de lecture."""
        if not self._player:
            return
        try:
            factor = float(speed_text.replace("x", ""))
            self._player.setPlaybackRate(factor)
            logger.debug("Vitesse de lecture audio ajustée : %.2fx", factor)
        except ValueError:
            pass

    @Slot(int)
    def _on_volume_changed(self, value: int) -> None:
        """Ajuste le volume sonore (0.0 à 1.0)."""
        if not self._audio_output:
            return
        vol = max(0.0, min(1.0, value / 100.0))
        self._audio_output.setVolume(vol)
        if vol > 0 and self._audio_output.isMuted():
            self._audio_output.setMuted(False)
            self.btn_mute.setIcon(load_phosphor_icon("ph.speaker-high", color=DesignTokens.TEXT_PRIMARY))

    @Slot()
    def _on_toggle_mute(self) -> None:
        """Active ou désactive la sourdine."""
        if not self._audio_output:
            return
        is_muted = not self._audio_output.isMuted()
        self._audio_output.setMuted(is_muted)
        icon_name = "ph.speaker-slash" if is_muted else "ph.speaker-high"
        self.btn_mute.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_PRIMARY))
