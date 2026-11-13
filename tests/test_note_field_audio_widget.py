"""Tests UI (pytest-qt headless) pour les fonctionnalités audio & TTS dans NoteFieldEditorWidget."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QToolButton
from pytestqt.qtbot import QtBot

from ankidraft.ui.widgets.note_editor_widget import NoteFieldEditorWidget

pytestmark = pytest.mark.ui


def test_note_field_audio_visibility_toggle(qtbot: QtBot) -> None:
    """Vérifie que le bouton de lecture audio s'affiche uniquement si [sound:...] est présent."""
    widget = NoteFieldEditorWidget(field_name="Front", initial_value="Texte sans audio")
    qtbot.addWidget(widget)
    widget.show()

    # Initialement pas de balise [sound:...] -> bouton masqué
    assert widget.btn_play_audio.isHidden()

    # Insertion d'une balise audio -> bouton devient visible
    widget.set_text("Texte enrichi [sound:test_voice.mp3]")
    assert not widget.btn_play_audio.isHidden()

    # Suppression de la balise audio -> bouton redevient masqué
    widget.set_text("Texte à nouveau sans audio")
    assert widget.btn_play_audio.isHidden()


def test_note_field_generate_tts_action(qtbot: QtBot) -> None:
    """Vérifie que le clic sur le bouton TTS génère et insère la balise sonore."""
    widget = NoteFieldEditorWidget(field_name="Front", initial_value="Bonjour le monde")
    qtbot.addWidget(widget)
    widget.show()

    changed_signals: list[str] = []
    widget.content_changed.connect(changed_signals.append)

    mock_svc = MagicMock()
    mock_svc.synthesize.return_value = ("[sound:tts_mock123.mp3]", Path("/fake/tts_mock123.mp3"))

    with patch("ankidraft.services.cards.tts_service.get_tts_service", return_value=mock_svc):
        # Clic sur le bouton de génération TTS
        qtbot.mouseClick(widget.btn_tts_generate, Qt.MouseButton.LeftButton)

    # La balise sonore a été injectée
    text = widget.get_text()
    assert "[sound:tts_mock123.mp3]" in text
    assert text.startswith("Bonjour le monde")

    # Le signal content_changed a été émis
    assert "Front" in changed_signals

    # Le bouton de lecture audio n'est plus masqué
    assert not widget.btn_play_audio.isHidden()


def test_note_field_audio_playback_trigger(qtbot: QtBot, tmp_path: Path) -> None:
    """Clic sur btn_play_audio résout le chemin, appelle setSource puis play ; gère les erreurs."""
    audio_file = tmp_path / "test_voice.mp3"
    audio_file.write_bytes(b"\x00\x01fake audio")

    mock_player = MagicMock()
    mock_player.errorOccurred = MagicMock()
    mock_output = MagicMock()
    mock_default_device = MagicMock()
    mock_devices = MagicMock()
    mock_devices.audioOutputs.return_value = []
    mock_devices.defaultAudioOutput.return_value = mock_default_device

    with (
        patch("ankidraft.ui.widgets.note_editor_widget.QMediaPlayer", return_value=mock_player),
        patch("ankidraft.ui.widgets.note_editor_widget.QAudioOutput", return_value=mock_output),
        patch("ankidraft.ui.widgets.note_editor_widget.QMediaDevices", mock_devices),
        patch(
            "ankidraft.ui.widgets.note_editor_widget.SettingsService.get",
            return_value=None,
        ),
        patch("ankidraft.utils.paths.resolve_media_path", return_value=audio_file),
    ):
        widget = NoteFieldEditorWidget(field_name="Front", initial_value="Texte [sound:test_voice.mp3]")
        qtbot.addWidget(widget)
        widget.show()

        # Le périphérique par défaut est affecté (aucun périphérique configuré)
        mock_output.setDevice.assert_called_once_with(mock_default_device)
        mock_output.setVolume.assert_called_with(1.0)
        mock_output.setMuted.assert_called_with(False)

        # Le signal errorOccurred est connecté au slot dédié
        mock_player.errorOccurred.connect.assert_called_once_with(widget._on_player_error)

        # Clic lecture -> setSource(chemin résolu absolu) puis play()
        qtbot.mouseClick(widget.btn_play_audio, Qt.MouseButton.LeftButton)

        mock_player.setSource.assert_called_once()
        source_url = mock_player.setSource.call_args[0][0]
        assert source_url.toLocalFile() == str(audio_file.resolve())
        mock_player.play.assert_called_once()

    # Gestion d'erreur : le slot consigne en log et notifie via un toast
    with patch("ankidraft.ui.widgets.note_editor_widget.logger") as mock_logger, patch("ankidraft.ui.widgets.note_editor_widget.show_toast") as mock_toast:
        widget._on_player_error(QMediaPlayer.Error.ResourceError, "codec manquant")
        mock_logger.error.assert_called_once()
        mock_toast.assert_called_once()
        args, _ = mock_toast.call_args
        assert isinstance(args[0], (QToolButton, NoteFieldEditorWidget))
        assert "Erreur audio" in str(args[1])
