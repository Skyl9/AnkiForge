"""Service de parsage et de transcription d'enregistrements audio (.mp3, .m4a, .wav, .ogg, etc.).

Utilise Whisper pour générer une transcription textuelle horodatée précise,
découpée en fragments temporels exploitables par ChunkingService et synchronisés
avec le lecteur AudioPlayerWidget.
"""

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ankiforge.services.cards.media_manager import MediaManager

logger = logging.getLogger(__name__)

SUPPORTED_AUDIO_EXTENSIONS = frozenset({".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac", ".wma"})


def format_seconds_to_timestamp(seconds: float) -> str:
    """Convertit des secondes en format mm:ss ou hh:mm:ss."""
    s = int(max(0.0, seconds))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


class AudioParser:
    """Parseur et transcripteur pour les fichiers audio (cours, amphis, podcasts).

    Génère un Markdown paginé contenant pour chaque fragment :
    - Des marqueurs de page (<!-- PAGE: N -->) et d'horodatage (<!-- TIME: start - end -->).
    - Un en-tête lisible avec le créneau temporel : ### [01:23 - 02:45] Partie N.
    - Le texte fidèlement transcrit.
    """

    def __init__(
        self,
        media_manager: MediaManager | None = None,
        api_key: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
    ) -> None:
        """Initialise le parseur audio avec options de transcription Whisper."""
        self.media_manager = media_manager or MediaManager()
        self._custom_api_key = api_key
        self._custom_provider = provider
        self._custom_base_url = base_url

    def parse(
        self,
        audio_path: str | Path,
        progress_callback: Callable[[str], None] | None = None,
        check_cancel: Callable[[], bool] | None = None,
    ) -> str:
        """Transcrit le fichier audio et génère le Markdown paginé avec horodatages.

        Args:
            audio_path: Chemin vers le fichier sonore.
            progress_callback: Callback optionnel de rapport de progression.
            check_cancel: Callback optionnel de vérification d'annulation.

        Returns:
            str: Le texte Markdown complet paginé et horodaté.

        Raises:
            FileNotFoundError: Si le fichier audio n'existe pas.
            ValueError: Si le format audio n'est pas supporté.
        """
        path_obj = Path(audio_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Le fichier audio '{path_obj}' est introuvable.")

        ext = path_obj.suffix.lower()
        if ext not in SUPPORTED_AUDIO_EXTENSIONS:
            raise ValueError(f"Format audio non supporté : '{ext}'. Formats supportés : {', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}")

        logger.info("Début du traitement audio : %s (taille: %d octets)", path_obj.name, path_obj.stat().st_size)

        if progress_callback:
            progress_callback("Archivage du média source...")

        # 1. Sauvegarde du fichier audio dans le dossier des médias
        self.media_manager.store_document_source(str(path_obj))

        if check_cancel and check_cancel():
            logger.warning("Traitement audio interrompu avant transcription.")
            return f"# {path_obj.stem}\n\n*Transcription annulée.*"

        if progress_callback:
            progress_callback("Transcription de l'enregistrement sonore avec Whisper...")

        # 2. Transcription du fichier sonore
        segments = self._transcribe_audio(path_obj, check_cancel=check_cancel)

        if not segments:
            logger.warning("Aucun segment transcrit pour l'audio : %s", path_obj.name)
            return f"# {path_obj.stem}\n\n*Aucune parole détectée dans cet enregistrement.*"

        if progress_callback:
            progress_callback(f"Structuration sémantique de {len(segments)} fragments...")

        # 3. Regroupement des segments en blocs cohérents (~45-60s par fragment)
        grouped_chunks = self._group_segments(segments, target_duration_secs=50.0)

        # 4. Assemblage en Markdown avec marqueurs temporels
        chunk_outputs: list[str] = []
        for idx, chunk in enumerate(grouped_chunks, start=1):
            if check_cancel and check_cancel():
                logger.warning("Génération de transcription interrompue au fragment %d.", idx)
                break

            start_t = chunk["start"]
            end_t = chunk["end"]
            text = chunk["text"].strip()
            start_str = format_seconds_to_timestamp(start_t)
            end_str = format_seconds_to_timestamp(end_t)

            page_marker = f"<!-- PAGE: {idx} -->"
            time_marker = f"<!-- TIME: {start_t:.2f} - {end_t:.2f} -->"
            heading = f"### [{start_str} - {end_str}] Enregistrement - Extrait #{idx}"

            chunk_content = f"{page_marker}\n{time_marker}\n\n{heading}\n\n{text}"
            chunk_outputs.append(chunk_content)

        logger.info(
            "Transcription audio achevée avec succès : %d fragments générés pour '%s'",
            len(chunk_outputs),
            path_obj.name,
        )
        return "\n\n[SPLIT]\n\n".join(chunk_outputs)

    def _resolve_stt_credentials(self) -> tuple[str, str, str]:
        """Détermine la clé API, le fournisseur et le base_url pour Whisper."""
        if self._custom_api_key:
            return (
                self._custom_provider or "openai",
                self._custom_api_key,
                self._custom_base_url or "https://api.openai.com/v1",
            )

        # 1. Vérifier OpenAI dans l'environnement ou SettingsService
        openai_key = os.environ.get("OPENAI_API_KEY")
        if not openai_key:
            try:
                from peewee import PeeweeException

                from ankiforge.services.settings_service import SettingsService

                openai_key = str(SettingsService.get("keys/openai", ""))
            except (PeeweeException, KeyError, AttributeError):
                pass

        if not openai_key:
            try:
                from peewee import PeeweeException

                from ankiforge.database.models import LLMConfigModel

                cfg = LLMConfigModel.select().where(LLMConfigModel.provider == "openai").first()
                if cfg and cfg.api_key:
                    openai_key = str(cfg.api_key)
            except (PeeweeException, KeyError, AttributeError):
                pass

        if openai_key:
            return ("openai", openai_key, "https://api.openai.com/v1")

        # 2. Vérifier Groq
        groq_key = os.environ.get("GROQ_API_KEY")
        if not groq_key:
            try:
                from peewee import PeeweeException

                from ankiforge.services.settings_service import SettingsService

                groq_key = str(SettingsService.get("keys/groq", ""))
            except (PeeweeException, KeyError, AttributeError):
                pass

        if not groq_key:
            try:
                from peewee import PeeweeException

                from ankiforge.database.models import LLMConfigModel

                cfg = LLMConfigModel.select().where(LLMConfigModel.provider == "groq").first()
                if cfg and cfg.api_key:
                    groq_key = str(cfg.api_key)
            except (PeeweeException, KeyError, AttributeError):
                pass

        if groq_key:
            return ("groq", groq_key, "https://api.groq.com/openai/v1")

        return ("", "", "")

    def _transcribe_audio(
        self,
        audio_path: Path,
        check_cancel: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """Effectue la transcription via l'API Whisper OpenAI ou Groq."""
        provider, api_key, base_url = self._resolve_stt_credentials()

        if not api_key:
            logger.warning("Aucune clé API Whisper (OpenAI/Groq) configurée. Génération d'une transcription fictive.")
            # Mode dégradé si aucune clé n'est configurée
            return [
                {
                    "start": 0.0,
                    "end": 30.0,
                    "text": ("Enregistrement audio importé. Pour activer la transcription automatique complète avec Whisper, veuillez renseigner une clé API OpenAI ou Groq dans les Paramètres IA."),
                }
            ]

        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=base_url)
            model_name = "whisper-1" if provider == "openai" else "whisper-large-v3"

            logger.info("Appel de l'API Whisper (%s via %s)...", model_name, provider)
            with open(audio_path, "rb") as f:
                response = client.audio.transcriptions.create(
                    model=model_name,
                    file=f,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )

            raw_segments = getattr(response, "segments", None)
            if not raw_segments and isinstance(response, dict):
                raw_segments = response.get("segments")

            if not raw_segments:
                # Si l'API renvoie du texte global sans segments détaillés
                full_text = getattr(response, "text", "") or str(response)
                return [{"start": 0.0, "end": 60.0, "text": full_text}]

            segments: list[dict[str, Any]] = []
            for seg in raw_segments:
                if isinstance(seg, dict):
                    s_start = float(seg.get("start", 0.0))
                    s_end = float(seg.get("end", 0.0))
                    s_text = str(seg.get("text", "")).strip()
                else:
                    s_start = float(getattr(seg, "start", 0.0))
                    s_end = float(getattr(seg, "end", 0.0))
                    s_text = str(getattr(seg, "text", "")).strip()

                if s_text:
                    segments.append({"start": s_start, "end": s_end, "text": s_text})

            return segments

        except Exception as err:
            logger.error("Erreur lors de la transcription Whisper : %s", err, exc_info=True)
            # En cas d'erreur de clé invalide ou réseau
            return [
                {
                    "start": 0.0,
                    "end": 10.0,
                    "text": f"Erreur lors de la transcription : {err}",
                }
            ]

    @staticmethod
    def _group_segments(segments: list[dict[str, Any]], target_duration_secs: float = 50.0) -> list[dict[str, Any]]:
        """Regroupe les micro-segments de Whisper en fragments sémantiques plus longs."""
        if not segments:
            return []

        grouped: list[dict[str, Any]] = []
        current_texts: list[str] = []
        group_start = segments[0]["start"]
        group_end = segments[0]["end"]

        for seg in segments:
            current_texts.append(seg["text"])
            group_end = seg["end"]

            # Si le bloc dépasse la durée cible, on crée un chunk
            if (group_end - group_start) >= target_duration_secs:
                grouped.append(
                    {
                        "start": group_start,
                        "end": group_end,
                        "text": " ".join(current_texts),
                    }
                )
                current_texts = []
                group_start = group_end

        # Ajouter le reliquat restant
        if current_texts:
            grouped.append(
                {
                    "start": group_start,
                    "end": group_end,
                    "text": " ".join(current_texts),
                }
            )

        return grouped
