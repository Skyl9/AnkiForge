"""Tests UI headless pour le widget de lecteur audio AudioPlayerWidget."""

import pytest

from ankiforge.ui.views.documents_view.widgets.audio_player import (
    AudioPlayerWidget,
    format_duration,
)


def test_format_duration():
    """Vérifie la conversion millisecondes vers chaîne formattée."""
    assert format_duration(0) == "00:00"
    assert format_duration(5000) == "00:05"
    assert format_duration(65000) == "01:05"
    assert format_duration(3605000) == "01:00:05"


@pytest.mark.ui
def test_audio_player_widget_init(qtbot):
    """Vérifie l'initialisation des composants du lecteur audio."""
    widget = AudioPlayerWidget()
    qtbot.addWidget(widget)

    assert widget.lbl_title.text() == "Aucun enregistrement audio chargé"
    assert widget.combo_speed.currentText() == "1.0x"
    assert widget.slider_volume.value() == 80
    assert widget.slider_timeline.value() == 0


@pytest.mark.ui
def test_audio_player_load_audio_file(qtbot, tmp_path):
    """Vérifie le chargement d'un fichier audio et la mise à jour des labels."""
    fake_audio = tmp_path / "cours_biochimie.mp3"
    fake_audio.write_bytes(b"\xff\xfb\x90\x44" * 50)

    widget = AudioPlayerWidget()
    qtbot.addWidget(widget)

    success = widget.load_audio(fake_audio)
    assert success is True
    assert widget.lbl_title.text() == "cours_biochimie.mp3"


@pytest.mark.ui
def test_audio_player_load_missing_file(qtbot):
    """Vérifie le comportement gracieux si le fichier n'existe pas."""
    widget = AudioPlayerWidget()
    qtbot.addWidget(widget)

    success = widget.load_audio("fichier_introuvable.mp3")
    assert success is False


@pytest.mark.ui
def test_audio_player_seek_and_signals(qtbot, tmp_path):
    """Vérifie que seek_seconds émet le signal time_jumped."""
    fake_audio = tmp_path / "cours_seek.mp3"
    fake_audio.write_bytes(b"\xff\xfb\x90\x44" * 50)

    widget = AudioPlayerWidget()
    qtbot.addWidget(widget)
    widget.load_audio(fake_audio)

    with qtbot.waitSignal(widget.time_jumped, timeout=1000) as blocker:
        widget.seek_seconds(12.5)

    assert blocker.args == [12.5]


@pytest.mark.ui
def test_audio_player_controls(qtbot):
    """Vérifie les interactions sur la vitesse, le volume et la sourdine."""
    widget = AudioPlayerWidget()
    qtbot.addWidget(widget)

    # Vitesse
    widget.combo_speed.setCurrentText("1.5x")
    # Volume
    widget.slider_volume.setValue(50)
    # Sourdine
    widget.btn_mute.click()
    assert widget._audio_output.isMuted() is True
    widget.btn_mute.click()
    assert widget._audio_output.isMuted() is False
