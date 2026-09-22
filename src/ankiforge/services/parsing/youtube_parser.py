"""Extraction et structuration de contenu YouTube pour AnkiForge."""

import json
import logging
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

from ankiforge.services.cards.media_manager import MediaManager
from ankiforge.services.parsing.audio_parser import AudioParser, format_seconds_to_timestamp
from ankiforge.services.parsing.yt_dlp_service import YtDlpService, YtDlpUnavailableError

if TYPE_CHECKING:
    from ankiforge.services.ai.flexible_service import AIManager

logger = logging.getLogger(__name__)


def format_timestamp(seconds: float) -> str:
    """Convertit un temps en secondes en format [MM:SS] ou [HH:MM:SS]."""
    total_sec = max(0, int(seconds))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class YouTubeParser:
    """Extraction et pré-structuration de contenu YouTube pour génération de cartes."""

    def __init__(
        self,
        media_manager: MediaManager | None = None,
        audio_parser: AudioParser | None = None,
    ) -> None:
        """Initialise le parseur YouTube avec support optionnel des médias et audio."""
        self.media_manager = media_manager or MediaManager()
        self.audio_parser = audio_parser or AudioParser(media_manager=self.media_manager)

    @staticmethod
    def format_time(seconds: float) -> str:
        """Alias de format_timestamp pour rétrocompatibilité."""
        return format_timestamp(seconds)

    def _extract_video_id(self, url: str) -> str | None:
        """Extrait l'ID de la vidéo depuis une URL YouTube."""
        parsed = urlparse(url)
        video_id: str | None = None
        if parsed.hostname == "youtu.be":
            video_id = parsed.path.lstrip("/")
        elif parsed.hostname in ("www.youtube.com", "youtube.com", "m.youtube.com"):
            if parsed.path == "/watch":
                qs = parse_qs(parsed.query)
                video_id = qs.get("v", [None])[0]
            elif parsed.path.startswith(("/embed/", "/v/", "/shorts/")):
                parts = [p for p in parsed.path.split("/") if p]
                if len(parts) >= 2:
                    video_id = parts[1]

        logger.debug("Extraction ID YouTube depuis '%s' -> %s", url, video_id)
        return video_id

    def fetch_video_metadata(self, url: str) -> dict[str, str]:
        """Récupère les métadonnées publiques de la vidéo (titre, auteur) via oEmbed."""
        import os
        import sys

        if "pytest" in sys.modules or os.environ.get("ANKIFORGE_ENV") == "testing":
            return {}

        try:
            oembed_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(url)}&format=json"
            req = urllib.request.Request(
                oembed_url,
                headers={"User-Agent": "AnkiForge/1.0 (Desktop App)"},
            )
            with urllib.request.urlopen(req, timeout=4) as response:  # nosec B310
                raw_data = response.read().decode("utf-8")
                data = json.loads(raw_data)
                return {
                    "title": str(data.get("title", "")),
                    "author_name": str(data.get("author_name", "")),
                }
        except Exception as e:
            logger.debug("Impossible de récupérer les métadonnées oEmbed YouTube pour %s : %s", url, e)
            return {}

    def extract_subtitles(
        self,
        url: str,
        language: str = "fr",
        preserve_timestamps: bool = False,
    ) -> str | None:
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
            data = cast(Any, YouTubeTranscriptApi).get_transcript(video_id, languages=[language, "en"])
            if not data:
                return None

            has_timestamps = any(isinstance(item, dict) and "start" in item for item in data)

            if not preserve_timestamps or not has_timestamps:
                raw_text = " ".join([item["text"] if isinstance(item, dict) else getattr(item, "text", str(item)) for item in data])
                logger.info("Sous-titres YouTube extraits sans timestamps (%d mots) pour %s", len(raw_text.split()), video_id)
                return raw_text.strip()

            metadata = self.fetch_video_metadata(url)
            meta_header = ""
            if metadata.get("title"):
                author_str = f" • {metadata['author_name']}" if metadata.get("author_name") else ""
                meta_header = f"# {metadata['title']}\n\n**Source :** Vidéo YouTube{author_str}\n\n"

            grouped_markdown = self._group_transcript_segments(data)
            full_content = f"{meta_header}{grouped_markdown}".strip()
            logger.info("Sous-titres YouTube structurés extraits (%d mots) pour %s", len(full_content.split()), video_id)
            return full_content

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

    def _group_transcript_segments(
        self,
        items: list[dict[str, Any]],
        target_duration: float = 90.0,
    ) -> str:
        """Regroupe les sous-titres en blocs chronologiques cohérents de ~60-120 secondes."""
        if not items:
            return ""

        sections: list[str] = []
        current_texts: list[str] = []
        chunk_start = float(items[0].get("start", 0.0))
        current_end = chunk_start

        for item in items:
            text = str(item.get("text", "")).strip()
            if not text:
                continue

            start = float(item.get("start", 0.0))
            duration = float(item.get("duration", 0.0))
            current_end = start + duration

            current_texts.append(text)

            # Si le bloc dépasse la durée cible ou ~200 mots, on crée un nouveau chapitre
            words_in_chunk = sum(len(t.split()) for t in current_texts)
            if (current_end - chunk_start >= target_duration and words_in_chunk >= 80) or words_in_chunk >= 250:
                time_tag = f"<!-- TIME: {chunk_start:.1f} - {current_end:.1f} -->"
                heading = f"## [{format_timestamp(chunk_start)}] Chapitre {format_timestamp(chunk_start)}"
                body = " ".join(current_texts)
                sections.append(f"{time_tag}\n{heading}\n\n{body}\n")

                current_texts = []
                chunk_start = current_end

        if current_texts:
            time_tag = f"<!-- TIME: {chunk_start:.1f} - {current_end:.1f} -->"
            heading = f"## [{format_timestamp(chunk_start)}] Chapitre {format_timestamp(chunk_start)}"
            body = " ".join(current_texts)
            sections.append(f"{time_tag}\n{heading}\n\n{body}\n")

        return "\n".join(sections)

    def download_and_transcribe(
        self,
        url: str,
        ai_manager: "AIManager | None" = None,
        progress_callback: Callable[[str], None] | None = None,
        check_cancel: Callable[[], bool] | None = None,
        save_audio: bool = True,
    ) -> str:
        """Fallback : téléchargement audio vidéo à la demande (yt-dlp) + transcription Whisper."""
        logger.info("Démarrage du téléchargement audio / transcription de secours pour : %s", url)

        if check_cancel and check_cancel():
            logger.warning("Téléchargement/transcription YouTube annulé avant le démarrage.")
            return ""

        # 1. Vérification de la disponibilité de yt-dlp
        if not YtDlpService.is_available():
            logger.error("yt-dlp est introuvable pour transcrire l'audio de %s", url)
            raise YtDlpUnavailableError()

        # 2. Métadonnées de la vidéo (oEmbed)
        metadata = self.fetch_video_metadata(url)
        title = metadata.get("title", "")
        author = metadata.get("author_name", "")
        meta_header = ""
        if title:
            author_str = f" • {author}" if author else ""
            meta_header = f"# {title}\n\n**Source :** Vidéo YouTube{author_str}\n\n"

        # 3. Téléchargement du flux audio
        if progress_callback:
            progress_callback("Téléchargement du flux audio YouTube via yt-dlp...")

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            try:
                audio_file = YtDlpService.download_audio(
                    url=url,
                    output_dir=output_dir,
                    progress_callback=progress_callback,
                    check_cancel=check_cancel,
                )
            except Exception as e:
                logger.error("Échec du téléchargement audio YouTube pour %s : %s", url, e)
                raise

            if check_cancel and check_cancel():
                logger.warning("Opération YouTube interrompue après téléchargement audio.")
                return ""

            # 4. Stockage du média dans MediaManager (si activé)
            if save_audio:
                try:
                    self.media_manager.store_document_source(str(audio_file))
                except Exception as e:
                    logger.debug("Stockage du fichier audio YouTube dans MediaManager ignoré : %s", e)

            # 5. Transcription audio via Whisper
            if progress_callback:
                progress_callback("Transcription de l'enregistrement sonore avec Whisper...")

            segments = self.audio_parser._transcribe_audio(
                audio_path=audio_file,
                check_cancel=check_cancel,
                raise_if_unavailable=True,
            )

            if check_cancel and check_cancel():
                logger.warning("Opération YouTube interrompue pendant la transcription.")
                return ""

            if not segments:
                logger.warning("Aucun segment de transcription retourné pour la vidéo %s", url)
                return f"{meta_header}*Aucune parole détectée dans cette vidéo.*".strip()

            # 6. Regroupement sémantique et mise en forme Markdown paginée et horodatée
            if progress_callback:
                progress_callback(f"Structuration sémantique de {len(segments)} fragments...")

            grouped_chunks = self.audio_parser._group_segments(segments, target_duration_secs=50.0)

            chunk_outputs: list[str] = []
            for idx, chunk in enumerate(grouped_chunks, start=1):
                if check_cancel and check_cancel():
                    logger.warning("Mise en forme interrompue au fragment %d.", idx)
                    break

                start_t = float(chunk["start"])
                end_t = float(chunk["end"])
                text = str(chunk["text"]).strip()
                start_str = format_seconds_to_timestamp(start_t)
                end_str = format_seconds_to_timestamp(end_t)

                page_marker = f"<!-- PAGE: {idx} -->"
                time_marker = f"<!-- TIME: {start_t:.2f} - {end_t:.2f} -->"
                heading = f"### [{start_str} - {end_str}] Vidéo YouTube - Extrait #{idx}"

                chunk_content = f"{page_marker}\n{time_marker}\n\n{heading}\n\n{text}"
                chunk_outputs.append(chunk_content)

            body = "\n\n[SPLIT]\n\n".join(chunk_outputs)
            full_content = f"{meta_header}{body}".strip()

            logger.info(
                "Transcription YouTube terminée avec succès : %d fragments pour '%s'",
                len(chunk_outputs),
                title or url,
            )
            return full_content

    def parse(
        self,
        url: str,
        ai_manager: "AIManager | None" = None,
        preserve_timestamps: bool = True,
        progress_callback: Callable[[str], None] | None = None,
        check_cancel: Callable[[], bool] | None = None,
    ) -> str:
        """Pipeline complet : sous-titres d'abord, repli transcription."""
        if progress_callback:
            progress_callback("Recherche des sous-titres de la vidéo...")

        result = self.extract_subtitles(url, preserve_timestamps=preserve_timestamps)
        if result is None:
            if check_cancel and check_cancel():
                return ""
            if progress_callback:
                progress_callback("Sous-titres indisponibles. Téléchargement et transcription avec yt-dlp + Whisper...")
            result = self.download_and_transcribe(
                url,
                ai_manager=ai_manager,
                progress_callback=progress_callback,
                check_cancel=check_cancel,
            )
        return result or ""
