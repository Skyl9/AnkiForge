from typing import Optional, TYPE_CHECKING
from urllib.parse import urlparse, parse_qs
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

if TYPE_CHECKING:
    from ankiforge.services.ai.ai_manager import AIManager


class YouTubeParser:
    """Extraction de contenu YouTube pour génération de cartes."""

    def _extract_video_id(self, url: str) -> str | None:
        """Extracts the video ID from a YouTube URL."""
        parsed = urlparse(url)
        if parsed.hostname == "youtu.be":
            return parsed.path[1:]
        if parsed.hostname in ("www.youtube.com", "youtube.com"):
            if parsed.path == "/watch":
                qs = parse_qs(parsed.query)
                return qs.get("v", [None])[0]
            if parsed.path.startswith("/embed/"):
                return parsed.path.split("/")[2]
            if parsed.path.startswith("/v/"):
                return parsed.path.split("/")[2]
        return None

    def extract_subtitles(self, url: str, language: str = "fr") -> str | None:
        """Tente de récupérer les sous-titres via youtube_transcript_api."""
        video_id = self._extract_video_id(url)
        if not video_id:
            return None

        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[language, "en"])
            return " ".join([item["text"] for item in transcript])
        except (NoTranscriptFound, TranscriptsDisabled, Exception):
            return None

    def download_and_transcribe(self, url: str, ai_manager: "AIManager") -> str:
        """Fallback : yt-dlp audio download + transcription IA (Whisper/Gemini)."""
        # Pour l'instant, on n'a pas yt-dlp en dependance obligatoire.
        # Implémentation future ou via sous-process yt-dlp.
        return ""

    def parse(self, url: str, ai_manager: Optional["AIManager"] = None) -> str:
        """Pipeline complet : subtitles d'abord, fallback transcription."""
        result = self.extract_subtitles(url)
        if result is None and ai_manager:
            result = self.download_and_transcribe(url, ai_manager)
        return result or ""
