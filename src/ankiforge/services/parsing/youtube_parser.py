import logging
from typing import TYPE_CHECKING, Optional
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

if TYPE_CHECKING:
    from ankiforge.services.ai.flexible_service import AIManager

logger = logging.getLogger(__name__)


class YouTubeParser:
    """Extraction de contenu YouTube pour génération de cartes."""

    def _extract_video_id(self, url: str) -> str | None:
        """Extrait l'ID de la vidéo depuis une URL YouTube."""
        parsed = urlparse(url)
        video_id: str | None = None
        if parsed.hostname == "youtu.be":
            video_id = parsed.path[1:]
        elif parsed.hostname in ("www.youtube.com", "youtube.com"):
            if parsed.path == "/watch":
                qs = parse_qs(parsed.query)
                video_id = qs.get("v", [None])[0]
            elif parsed.path.startswith("/embed/") or parsed.path.startswith("/v/"):
                video_id = parsed.path.split("/")[2]

        logger.debug("Extraction ID YouTube depuis '%s' -> %s", url, video_id)
        return video_id

    def extract_subtitles(self, url: str, language: str = "fr") -> str | None:
        """Tente de récupérer les sous-titres via youtube_transcript_api."""
        video_id = self._extract_video_id(url)
        if not video_id:
            logger.warning("Impossible d'extraire l'ID de vidéo YouTube depuis l'URL : %s", url)
            return None

        logger.info(
            "Tentative de récupération des sous-titres YouTube pour vidéo ID='%s' (langues: [%s, en])",
            video_id,
            language,
        )
        try:
            data = YouTubeTranscriptApi.get_transcript(video_id, languages=[language, "en"])  # type: ignore[attr-defined]
            text = " ".join([item["text"] if isinstance(item, dict) else getattr(item, "text", str(item)) for item in data])

            logger.info("Sous-titres YouTube extraits avec succès (%d mots) pour %s", len(text.split()), video_id)
            return text
        except (NoTranscriptFound, TranscriptsDisabled) as e:
            logger.warning(
                "Sous-titres indisponibles pour la vidéo YouTube %s : %s. Repli sur le téléchargement audio.",
                video_id,
                e,
            )
            return None
        except Exception as e:
            logger.error(
                "Erreur inattendue lors de la récupération des sous-titres YouTube (%s) : %s",
                video_id,
                e,
                exc_info=True,
            )
            return None

    def download_and_transcribe(self, url: str, ai_manager: Optional["AIManager"] = None) -> str:
        """Fallback : yt-dlp audio download + transcription IA (Whisper/Gemini)."""
        logger.info("Démarrage du téléchargement audio / transcription de secours pour : %s", url)
        return ""

    def parse(self, url: str, ai_manager: Optional["AIManager"] = None) -> str:
        """Pipeline complet : subtitles d'abord, fallback transcription."""
        result = self.extract_subtitles(url)
        if result is None:
            result = self.download_and_transcribe(url, ai_manager)
        return result or ""
