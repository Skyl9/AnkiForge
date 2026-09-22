from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ankiforge.services.parsing.audio_parser import AudioParser, WhisperUnavailableError
from ankiforge.services.parsing.youtube_parser import YouTubeParser
from ankiforge.services.parsing.yt_dlp_service import YtDlpService, YtDlpUnavailableError

pytestmark = pytest.mark.unit


def test_extract_video_id():
    parser = YouTubeParser()
    assert parser._extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert parser._extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert parser._extract_video_id("https://notyoutube.com") is None


@patch("ankiforge.services.parsing.youtube_parser.YouTubeTranscriptApi")
def test_extract_subtitles_success(mock_api):
    mock_api.get_transcript.return_value = [{"text": "Hello"}, {"text": "world"}]
    parser = YouTubeParser()
    res = parser.extract_subtitles("https://youtu.be/dQw4w9WgXcQ")
    assert res == "Hello world"
    mock_api.get_transcript.assert_called_once_with("dQw4w9WgXcQ", languages=["fr", "en"])


@patch("ankiforge.services.parsing.youtube_parser.YouTubeTranscriptApi")
def test_extract_subtitles_failure(mock_api):
    mock_api.get_transcript.side_effect = Exception("No subs")
    parser = YouTubeParser()
    res = parser.extract_subtitles("https://youtu.be/dQw4w9WgXcQ")
    assert res is None


def test_parse_with_fallback():
    parser = YouTubeParser()
    with patch.object(parser, "extract_subtitles", return_value=None), patch.object(parser, "download_and_transcribe", return_value="fallback audio"):
        assert parser.parse("https://youtu.be/test", None) == "fallback audio"


def test_download_and_transcribe_success(tmp_path: Path) -> None:
    fake_audio = tmp_path / "lecture.m4a"
    fake_audio.write_bytes(b"audio content")

    mock_segments = [
        {"start": 0.0, "end": 25.0, "text": "Bienvenue au cours de neurobiologie."},
        {"start": 25.0, "end": 55.0, "text": "Nous abordons aujourd'hui les potentiels d'action."},
        {"start": 55.0, "end": 80.0, "text": "La dépolarisation membranaire est initiée par les canaux sodiques."},
    ]

    mock_media = MagicMock()
    mock_audio_parser = MagicMock(spec=AudioParser)
    mock_audio_parser._transcribe_audio.return_value = mock_segments
    mock_audio_parser._group_segments = AudioParser._group_segments

    parser = YouTubeParser(media_manager=mock_media, audio_parser=mock_audio_parser)

    with (
        patch.object(YtDlpService, "is_available", return_value=True),
        patch.object(YtDlpService, "download_audio", return_value=fake_audio),
        patch.object(parser, "fetch_video_metadata", return_value={"title": "Neurobiologie 101", "author_name": "Dr. House"}),
    ):
        progress_msgs: list[str] = []
        res = parser.download_and_transcribe(
            "https://youtu.be/neuro123",
            progress_callback=progress_msgs.append,
        )

    assert "# Neurobiologie 101" in res
    assert "Dr. House" in res
    assert "<!-- PAGE: 1 -->" in res
    assert "<!-- TIME: 0.00 -" in res
    assert "neurobiologie" in res
    assert "[SPLIT]" in res
    assert mock_media.store_document_source.called
    assert len(progress_msgs) > 0


def test_download_and_transcribe_ytdlp_unavailable() -> None:
    parser = YouTubeParser()
    with patch.object(YtDlpService, "is_available", return_value=False):
        with pytest.raises(YtDlpUnavailableError) as exc:
            parser.download_and_transcribe("https://youtu.be/no_ytdlp")
        assert "yt-dlp est introuvable" in str(exc.value)


def test_download_and_transcribe_whisper_unavailable(tmp_path: Path) -> None:
    fake_audio = tmp_path / "test.m4a"
    fake_audio.write_bytes(b"dummy")

    mock_audio_parser = MagicMock(spec=AudioParser)
    mock_audio_parser._transcribe_audio.side_effect = WhisperUnavailableError("Moteur Whisper absent")

    parser = YouTubeParser(audio_parser=mock_audio_parser)

    with (
        patch.object(YtDlpService, "is_available", return_value=True),
        patch.object(YtDlpService, "download_audio", return_value=fake_audio),
        patch.object(parser, "fetch_video_metadata", return_value={}),
        pytest.raises(WhisperUnavailableError) as exc,
    ):
        parser.download_and_transcribe("https://youtu.be/no_whisper")
    assert "Moteur Whisper absent" in str(exc.value)


def test_download_and_transcribe_cancellation_before_start() -> None:
    parser = YouTubeParser()
    res = parser.download_and_transcribe("https://youtu.be/cancel", check_cancel=lambda: True)
    assert res == ""


def test_download_and_transcribe_cancellation_after_download(tmp_path: Path) -> None:
    fake_audio = tmp_path / "test.m4a"
    fake_audio.write_bytes(b"dummy")

    cancel_flag = False

    def check_cancel_func() -> bool:
        return cancel_flag

    def download_side_effect(*args, **kwargs):
        nonlocal cancel_flag
        cancel_flag = True
        return fake_audio

    parser = YouTubeParser()

    with (
        patch.object(YtDlpService, "is_available", return_value=True),
        patch.object(YtDlpService, "download_audio", side_effect=download_side_effect),
        patch.object(parser, "fetch_video_metadata", return_value={}),
    ):
        res = parser.download_and_transcribe("https://youtu.be/cancel_mid", check_cancel=check_cancel_func)
        assert res == ""


def test_download_and_transcribe_no_segments_detected(tmp_path: Path) -> None:
    fake_audio = tmp_path / "silent.m4a"
    fake_audio.write_bytes(b"silent")

    mock_audio_parser = MagicMock(spec=AudioParser)
    mock_audio_parser._transcribe_audio.return_value = []

    parser = YouTubeParser(audio_parser=mock_audio_parser)

    with (
        patch.object(YtDlpService, "is_available", return_value=True),
        patch.object(YtDlpService, "download_audio", return_value=fake_audio),
        patch.object(parser, "fetch_video_metadata", return_value={"title": "Vidéo Muette"}),
    ):
        res = parser.download_and_transcribe("https://youtu.be/silent")
        assert "# Vidéo Muette" in res
        assert "Aucune parole détectée" in res


def test_parse_full_pipeline_subtitles_missing_calls_download_and_transcribe() -> None:
    parser = YouTubeParser()
    progress_calls: list[str] = []

    with patch.object(parser, "extract_subtitles", return_value=None) as mock_subs, patch.object(parser, "download_and_transcribe", return_value="# Titre\n\nContenu audio transcrit") as mock_dt:
        res = parser.parse("https://youtu.be/full_test", progress_callback=progress_calls.append)

    assert mock_subs.called
    assert mock_dt.called
    assert res == "# Titre\n\nContenu audio transcrit"
    assert any("Téléchargement et transcription" in msg for msg in progress_calls)
