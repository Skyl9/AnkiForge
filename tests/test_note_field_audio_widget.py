"""
Tests UI (pytest-qt headless) pour les fonctionnalités audio & TTS dans NoteFieldEditorWidget.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from ankiforge.ui.widgets.note_editor_widget import NoteFieldEditorWidget


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

    with patch("ankiforge.services.cards.tts_service.get_tts_service", return_value=mock_svc):
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
