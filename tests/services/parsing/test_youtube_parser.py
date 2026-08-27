from unittest.mock import patch
from ankiforge.services.parsing.youtube_parser import YouTubeParser


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
    with patch.object(parser, "extract_subtitles", return_value=None):
        with patch.object(parser, "download_and_transcribe", return_value="fallback audio"):
            assert parser.parse("https://youtu.be/test", None) == "fallback audio"
