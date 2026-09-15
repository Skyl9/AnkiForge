"""Tests unitaires pour le parseur audio (AudioParser) et l'intégration des horodatages."""

from unittest.mock import MagicMock, patch

import pytest

from ankiforge.services.parsing.audio_parser import (
    AudioParser,
    format_seconds_to_timestamp,
)
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.services.parsing.document_parser import DocumentParser


def test_format_seconds_to_timestamp():
    """Vérifie le formatage des secondes en chaînes mm:ss et hh:mm:ss."""
    assert format_seconds_to_timestamp(0) == "00:00"
    assert format_seconds_to_timestamp(45.6) == "00:45"
    assert format_seconds_to_timestamp(125) == "02:05"
    assert format_seconds_to_timestamp(3665) == "01:01:05"


def test_audio_parser_unsupported_format(tmp_path):
    """Vérifie qu'un format audio non supporté lève un ValueError."""
    fake_txt = tmp_path / "audio.txt"
    fake_txt.write_text("not an audio file")

    parser = AudioParser()
    with pytest.raises(ValueError) as exc:
        parser.parse(fake_txt)
    assert "Format audio non supporté" in str(exc.value)


def test_audio_parser_file_not_found():
    """Vérifie qu'un fichier inexistant lève un FileNotFoundError."""
    parser = AudioParser()
    with pytest.raises(FileNotFoundError):
        parser.parse("inexistant.mp3")


def test_audio_parser_with_whisper_mock(tmp_path):
    """Vérifie la transcription et le regroupement en blocs horodatés avec un mock de Whisper."""
    fake_mp3 = tmp_path / "cours_cardiologie.mp3"
    fake_mp3.write_bytes(b"\xff\xfb\x90\x44" * 100)

    # Simulation de la réponse Whisper verbose_json avec segments
    mock_segments = [
        MagicMock(start=0.0, end=15.0, text="Bonjour à tous."),
        MagicMock(start=15.0, end=35.0, text="Aujourd'hui nous étudions le cycle cardiaque."),
        MagicMock(start=35.0, end=55.0, text="La première étape est la systole auriculaire."),
        MagicMock(start=55.0, end=80.0, text="Puis vient la systole ventriculaire."),
        MagicMock(start=80.0, end=110.0, text="Enfin la diastole générale permet le remplissage."),
    ]

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = MagicMock(segments=mock_segments)

    mock_media = MagicMock()

    with patch("openai.OpenAI", return_value=mock_client):
        parser = AudioParser(
            media_manager=mock_media,
            api_key="fake_key",
            provider="openai",
        )
        result = parser.parse(fake_mp3)

    assert mock_media.store_document_source.called
    assert "<!-- PAGE: 1 -->" in result
    assert "<!-- TIME: 0.00 -" in result
    assert "cycle cardiaque" in result
    assert "systole auriculaire" in result
    assert "[SPLIT]" in result


def test_chunking_service_audio_timestamps():
    """Vérifie que ChunkingService extrait fidèlement start_time et end_time pour chaque chunk."""
    raw_md = """
<!-- PAGE: 1 -->
<!-- TIME: 0.00 - 55.00 -->
### [00:00 - 00:55] Enregistrement - Extrait #1

Bonjour à tous. Aujourd'hui nous étudions le cycle cardiaque et la systole auriculaire.

[SPLIT]

<!-- PAGE: 2 -->
<!-- TIME: 55.00 - 110.00 -->
### [00:55 - 01:50] Enregistrement - Extrait #2

Puis vient la systole ventriculaire et enfin la diastole générale pour le remplissage.
"""

    chunks = ChunkingService.extract_chunks(raw_md, file_type="audio")
    assert len(chunks) == 2

    # Premier chunk
    assert chunks[0]["page_number"] == 1
    assert chunks[0]["start_time"] == 0.0
    assert chunks[0]["end_time"] == 55.0
    assert "cycle cardiaque" in chunks[0]["content"]

    # Deuxième chunk
    assert chunks[1]["page_number"] == 2
    assert chunks[1]["start_time"] == 55.0
    assert chunks[1]["end_time"] == 110.0
    assert "systole ventriculaire" in chunks[1]["content"]


def test_audio_parser_cancellation(tmp_path):
    """Vérifie que le check_cancel interrompt la génération."""
    fake_mp3 = tmp_path / "cours_cancel.mp3"
    fake_mp3.write_bytes(b"\xff\xfb\x90\x44" * 100)

    parser = AudioParser(media_manager=MagicMock())
    result = parser.parse(fake_mp3, check_cancel=lambda: True)

    assert "Transcription annulée" in result


def test_document_parser_audio_delegation(tmp_path):
    """Vérifie que DocumentParser route les fichiers audio vers AudioParser."""
    fake_mp3 = tmp_path / "amphi.wav"
    fake_mp3.write_bytes(b"RIFF\x24\x00\x00\x00WAVE" + b"\x00" * 100)

    doc_parser = DocumentParser()

    with patch.object(AudioParser, "parse", return_value="<!-- PAGE: 1 -->\n\n### Extrait\n\nTexte transcrit"):
        result = doc_parser.parse_document(str(fake_mp3))

    assert "Texte transcrit" in result
