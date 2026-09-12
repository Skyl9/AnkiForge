"""Tests unitaires pour YouTubeParser avec préservation des timestamps."""

from unittest.mock import patch

from ankiforge.services.parsing.youtube_parser import YouTubeParser, format_timestamp


def test_format_timestamp() -> None:
    assert format_timestamp(0) == "00:00"
    assert format_timestamp(45.6) == "00:45"
    assert format_timestamp(75.0) == "01:15"
    assert format_timestamp(615.0) == "10:15"
    assert format_timestamp(3665.0) == "01:01:05"


def test_group_transcript_segments() -> None:
    parser = YouTubeParser()
    mock_items = [
        {"text": "Bonjour à tous,", "start": 0.0, "duration": 2.0},
        {"text": "bienvenue dans ce cours.", "start": 2.0, "duration": 3.0},
        {"text": "Aujourd'hui nous étudions l'entropie.", "start": 5.0, "duration": 4.0},
    ]

    res = parser._group_transcript_segments(mock_items, target_duration=5.0)
    assert "<!-- TIME: 0.0 -" in res
    assert "## [00:00] Chapitre 00:00" in res
    assert "Bonjour à tous," in res


@patch("ankiforge.services.parsing.youtube_parser.YouTubeTranscriptApi")
@patch.object(YouTubeParser, "fetch_video_metadata")
def test_extract_subtitles_with_timestamps(mock_meta: object, mock_api: object) -> None:
    mock_meta.return_value = {"title": "Physique Quantique 101", "author_name": "Dr. Smith"}  # type: ignore[attr-defined]
    mock_api.get_transcript.return_value = [  # type: ignore[attr-defined]
        {"text": "Bienvenue dans cette leçon.", "start": 0.0, "duration": 3.0},
        {"text": "Les particules se comportent comme des ondes.", "start": 3.0, "duration": 4.0},
    ]

    parser = YouTubeParser()
    res = parser.extract_subtitles("https://www.youtube.com/watch?v=mock123", preserve_timestamps=True)

    assert res is not None
    assert "# Physique Quantique 101" in res
    assert "Dr. Smith" in res
    assert "<!-- TIME: 0.0 -" in res
    assert "## [00:00]" in res
    assert "particules se comportent" in res


@patch("ankiforge.services.parsing.youtube_parser.YouTubeTranscriptApi")
@patch.object(YouTubeParser, "fetch_video_metadata")
def test_extract_subtitles_without_timestamps(mock_meta: object, mock_api: object) -> None:
    mock_meta.return_value = {}  # type: ignore[attr-defined]
    mock_api.get_transcript.return_value = [  # type: ignore[attr-defined]
        {"text": "Première phrase.", "start": 0.0, "duration": 2.0},
        {"text": "Seconde phrase.", "start": 2.0, "duration": 2.0},
    ]

    parser = YouTubeParser()
    res = parser.extract_subtitles("https://www.youtube.com/watch?v=mock123", preserve_timestamps=False)

    assert res is not None
    assert "<!-- TIME:" not in res
    assert "Première phrase. Seconde phrase." in res
