"""
Service de Synthèse Vocale (TTS) & Génération Audio pour AnkiForge.
Architecture multi-moteurs découplée et 100% compatible Nuitka (Règle GEMINI.md n°10) :
- Edge-TTS : Moteur en-processus pur Python asynchrone (zéro C++, ultra-léger)
- Piper TTS : Moteur local hors-ligne autonome en sidecar déporté dans ~/.ankiforge/tools/tts/
- Kokoro-82M : Runner optionnel externe déporté
- Moteur Système : Fallback natif OS sans réseau ni téléchargement (macOS say / Windows SAPI5 / Linux spd-say)
"""

import abc
import asyncio
import concurrent.futures
import hashlib
import logging
import os
import platform
import re
import shutil
import subprocess  # nosec B404  # appels en liste de binaires système, jamais shell=True
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ankiforge.services.cards.media_manager import MediaManager
from ankiforge.services.settings_service import SettingsService
from ankiforge.utils.archive_utils import safe_extract_tar, safe_extract_zip
from ankiforge.utils.paths import get_app_data_dir, resolve_media_path

logger = logging.getLogger(__name__)

# =========================================================================
# CONSTANTES DE SÉCURITÉ TÉLÉCHARGEMENT PIPER SIDECAR
# =========================================================================

# Plafonds de taille (les archives Piper pèsent ~20-26 Mo, la voix ~28 Mo).
_MAX_PIPER_ARCHIVE_BYTES = 150 * 1024 * 1024
_MAX_PIPER_VOICE_BYTES = 150 * 1024 * 1024
_PIPER_DOWNLOAD_TIMEOUT_SECONDS = 30.0

# Release GitHub épinglée (tag immuable). SHA-256 officiels des assets vérifiés
# le 2026-09-15 depuis github.com/rhasspy/piper/releases/tag/2023.11.14-2.
# Mapping (système, architecture) -> (nom_asset, sha256, est_une_archive_tar).
_PIPER_ASSETS: dict[tuple[str, str], tuple[str, str, bool]] = {
    ("Darwin", "arm64"): (
        "piper_macos_aarch64.tar.gz",
        "6b1eb03b3735946cb35216e063e7eebcc33a6bbf5dd96ec0217959bf1cdcb0cc",
        True,
    ),
    ("Darwin", "x86_64"): (
        "piper_macos_x64.tar.gz",
        "ced85c0a3df13945b1e623b878a48fdc2854d5c485b4b67f62857cf551deaf8b",
        True,
    ),
    ("Linux", "arm64"): (
        "piper_linux_aarch64.tar.gz",
        "fea0fd2d87c54dbc7078d0f878289f404bd4d6eea6e7444a77835d1537ab88eb",
        True,
    ),
    ("Linux", "x86_64"): (
        "piper_linux_x86_64.tar.gz",
        "a50cb45f355b7af1f6d758c1b360717877ba0a398cc8cbe6d2a7a3a26e225992",
        True,
    ),
    ("Windows", "amd64"): (
        "piper_windows_amd64.zip",
        "f3c58906402b24f3a96d92145f58acba6d86c9b5db896d207f78dc80811efcea",
        False,
    ),
}
_PIPER_RELEASE_BASE_URL = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2"

# Voix française par défaut (siwis-low) — SHA-256 officiels vérifiés le 2026-09-15
# depuis huggingface.co/rhasspy/piper-voices (résolution main).
_PIPER_VOICE_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/low"
_PIPER_VOICE_SHA256: dict[str, str] = {
    "fr_FR-siwis-low.onnx": "a7b7dcaf87229b32af8275cb1a719371234ea677bc0313d2289d5c50ab0ac53d",
    "fr_FR-siwis-low.onnx.json": "9722527d748c284f6dd7639c4b4e661853d4f7d4514079571f67d6a97a652b69",
}


def _download_verified(
    url: str,
    dest: Path,
    expected_sha256: str,
    *,
    max_bytes: int,
    timeout: float = _PIPER_DOWNLOAD_TIMEOUT_SECONDS,
    progress_callback: Callable[[str], None] | None = None,
    progress_label: str = "Téléchargement",
) -> None:
    """Télécharge un fichier HTTPS en streaming avec plafond de taille et vérification SHA-256.

    Raises:
        ValueError: si la taille annoncée ou reçue dépasse le plafond, ou si
            l'empreinte SHA-256 ne correspond pas à la valeur attendue.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "AnkiForge/1.0"})
    hasher = hashlib.sha256()
    downloaded = 0
    chunk_size = 1024 * 64

    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as out_file:  # nosec B310  # HTTPS + certificats par défaut, timeout borné
        total_size = int(resp.headers.get("Content-Length", 0))
        if total_size > max_bytes:
            raise ValueError(f"Taille annoncée ({total_size} octets) supérieure au plafond autorisé ({max_bytes}).")

        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            out_file.write(chunk)
            hasher.update(chunk)
            downloaded += len(chunk)
            if downloaded > max_bytes:
                raise ValueError(f"Taille téléchargée ({downloaded} octets) supérieure au plafond autorisé ({max_bytes}).")
            if progress_callback and total_size > 0:
                percent = int((downloaded / total_size) * 100)
                mb = downloaded / (1024 * 1024)
                total_mb = total_size / (1024 * 1024)
                progress_callback(f"{progress_label} : {mb:.1f}/{total_mb:.1f} Mo ({percent}%)")

    computed = hasher.hexdigest()
    if computed != expected_sha256:
        dest.unlink(missing_ok=True)
        raise ValueError(f"Échec de la vérification SHA-256 de '{url}'. Le fichier est corrompu ou non authentique (attendu {expected_sha256[:16]}…, reçu {computed[:16]}…).")


class TextNormalizer:
    """Nettoie et normalise le texte pour la synthèse vocale."""

    @staticmethod
    def strip_html(text: str) -> str:
        """Supprime toutes les balises HTML tout en préservant le texte lisible."""
        if not text:
            return ""
        # Remplacer les retours à la ligne HTML par des espaces
        cleaned = re.sub(r"<(br|p|div|tr|li)[^>]*>", " ", text, flags=re.IGNORECASE)
        # Supprimer le reste des balises
        cleaned = re.sub(r"<[^>]+>", "", cleaned)
        return cleaned

    @staticmethod
    def expand_cloze(text: str) -> str:
        """
        Développe les occlusions Anki (Clozes) pour que le TTS prononce le mot masqué.
        Ex: 'La capitale est {{c1::Paris::Indice}}' -> 'La capitale est Paris'
        """
        if not text:
            return ""
        # Capture {{c1::texte::indice}} ou {{c1::texte}}
        return re.sub(r"\{\{c\d+::(.*?)(?:::.*?)?\}\}", r"\1", text)

    @staticmethod
    def remove_audio_tags(text: str) -> str:
        """Supprime les balises son existantes [sound:xxx.mp3] pour éviter les réinjections."""
        if not text:
            return ""
        return re.sub(r"\[sound:[^\]]+\]", "", text)

    @staticmethod
    def clean_markdown_and_math(text: str) -> str:
        """Supprime les éléments de formatage Markdown et délimiteurs mathématiques."""
        if not text:
            return ""
        # Liens markdown [Texte](url) -> Texte
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        # Images markdown ![alt](url) -> ""
        cleaned = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", cleaned)
        # Gras et italique **texte**, *texte*, __texte__, _texte_
        cleaned = re.sub(r"(\*\*|__|\*|_)(.*?)\1", r"\2", cleaned)
        # Équations LaTeX \( ... \) ou \[ ... \] ou $ ... $
        cleaned = re.sub(r"\\\(|\\\)|\\\[|\\\]", " ", cleaned)
        cleaned = re.sub(r"\${1,2}(.*?)\${1,2}", r"\1", cleaned)
        return cleaned

    @classmethod
    def clean_for_tts(cls, text: str, strip_cloze: bool = True) -> str:
        """Pipeline complet de nettoyage du texte pour le moteur vocal."""
        if not text:
            return ""
        t = cls.remove_audio_tags(text)
        if strip_cloze:
            t = cls.expand_cloze(t)
        t = cls.strip_html(t)
        t = cls.clean_markdown_and_math(t)
        # Réduction des espaces multiples
        t = re.sub(r"\s+", " ", t).strip()
        return t


class TTSProvider(abc.ABC):
    """Interface de base pour tout moteur de synthèse vocale."""

    id: str
    display_name: str

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Indique si le moteur est utilisable sur la machine."""
        pass

    @abc.abstractmethod
    def get_voices(self) -> list[dict[str, str]]:
        """Retourne la liste des voix disponibles : [{'id': '...', 'name': '...', 'lang': '...'}]."""
        pass

    @abc.abstractmethod
    def synthesize(
        self,
        text: str,
        voice: str | None = None,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> bytes:
        """Génère l'audio brut (format MP3 ou WAV) à partir du texte normalisé."""
        pass


def _run_async(coro: Any) -> Any:
    """Exécute une coroutine asyncio de manière sécurisée quel que soit le thread appelant."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


class EdgeTTSProvider(TTSProvider):
    """
    Fournisseur Edge-TTS : Pur Python, asynchrone, 100% Nuitka-compatible.
    Utilise le service neural gratuit de Microsoft Edge (100+ langues, voix naturelles).
    """

    id = "edge-tts"
    display_name = "Edge-TTS (Voix Neuronales Cloud Gratuit)"

    DEFAULT_VOICES: list[dict[str, str]] = [
        {"id": "fr-FR-VivienneMultilingualNeural", "name": "Français - Vivienne (Naturelle)", "lang": "fr-FR", "gender": "Female"},
        {"id": "fr-FR-HenriNeural", "name": "Français - Henri (Naturel)", "lang": "fr-FR", "gender": "Male"},
        {"id": "fr-FR-DeniseNeural", "name": "Français - Denise", "lang": "fr-FR", "gender": "Female"},
        {"id": "fr-CA-AntoineNeural", "name": "Français (Canada) - Antoine", "lang": "fr-CA", "gender": "Male"},
        {"id": "en-US-JennyNeural", "name": "English (US) - Jenny", "lang": "en-US", "gender": "Female"},
        {"id": "en-US-GuyNeural", "name": "English (US) - Guy", "lang": "en-US", "gender": "Male"},
        {"id": "en-GB-SoniaNeural", "name": "English (UK) - Sonia", "lang": "en-GB", "gender": "Female"},
        {"id": "es-ES-AlvaroNeural", "name": "Español - Alvaro", "lang": "es-ES", "gender": "Male"},
        {"id": "es-ES-ElviraNeural", "name": "Español - Elvira", "lang": "es-ES", "gender": "Female"},
        {"id": "de-DE-KillianNeural", "name": "Deutsch - Killian", "lang": "de-DE", "gender": "Male"},
        {"id": "de-DE-KatjaNeural", "name": "Deutsch - Katja", "lang": "de-DE", "gender": "Female"},
        {"id": "it-IT-DiegoNeural", "name": "Italiano - Diego", "lang": "it-IT", "gender": "Male"},
        {"id": "ja-JP-NanamiNeural", "name": "日本語 - Nanami", "lang": "ja-JP", "gender": "Female"},
        {"id": "zh-CN-XiaoxiaoNeural", "name": "中文 - Xiaoxiao", "lang": "zh-CN", "gender": "Female"},
    ]

    def is_available(self) -> bool:
        try:
            import edge_tts  # noqa: F401

            return True
        except ImportError:
            return False

    def get_voices(self) -> list[dict[str, str]]:
        """Retourne la liste des voix neuronales disponibles avec mise en cache paresseuse."""
        return self.DEFAULT_VOICES

    def synthesize(
        self,
        text: str,
        voice: str | None = None,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> bytes:
        if not self.is_available():
            raise RuntimeError("Le module 'edge-tts' n'est pas disponible.")

        import edge_tts

        selected_voice = voice or "fr-FR-VivienneMultilingualNeural"

        async def _synth() -> bytes:
            communicate = edge_tts.Communicate(text, selected_voice, rate=rate, pitch=pitch)
            audio_data = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.extend(chunk["data"])
            return bytes(audio_data)

        return _run_async(_synth())


class PiperSidecarProvider(TTSProvider):
    """
    Fournisseur Piper TTS en Sidecar Local : Exécutable précompilé autonome
    situé dans ~/.ankiforge/tools/tts/piper (sans dépendances Python/PyTorch).
    """

    id = "piper"
    display_name = "Piper TTS (Local Hors-Ligne Standalone)"

    @staticmethod
    def get_piper_executable() -> Path | None:
        """Localise l'exécutable piper dans les dossiers d'outils AnkiForge ou dans le PATH."""
        # 1. Dossiers tools AnkiForge (environnement actif + repli prod si non test)
        from ankiforge.utils.environment import is_testing
        from ankiforge.utils.paths import get_tools_search_dirs

        search_dirs = [get_app_data_dir() / "tools"]
        if not is_testing():
            for d in get_tools_search_dirs():
                if d not in search_dirs:
                    search_dirs.append(d)

        for tools_dir in search_dirs:
            app_tools = tools_dir / "tts"
            candidates = [
                app_tools / "piper" / "piper",
                app_tools / "piper" / "piper.exe",
                app_tools / "piper",
                app_tools / "piper.exe",
                app_tools / "bin" / "piper",
                app_tools / "bin" / "piper.exe",
                tools_dir / "bin" / "piper",
            ]
            for c in candidates:
                if c.is_file() and os.access(c, os.X_OK):
                    return c

        # 2. PATH système (ignoré en mode test pour garantir l'isolation)
        if not is_testing():
            system_exe = shutil.which("piper")
            if system_exe:
                return Path(system_exe)

        return None

    @staticmethod
    def get_voices_dir() -> Path:
        """Retourne le dossier hébergeant les modèles de voix ONNX de Piper."""
        voices_dir = get_app_data_dir() / "tools" / "tts" / "voices"
        voices_dir.mkdir(parents=True, exist_ok=True)
        return voices_dir

    @classmethod
    def is_functional(cls) -> tuple[bool, str]:
        """Vérifie que le binaire piper existe ET s'exécute sans erreur de dépendance dynamique."""
        exe = cls.get_piper_executable()
        if not exe:
            return False, "Binaire Piper introuvable."
        try:
            res = subprocess.run(
                [str(exe), "--version"],
                capture_output=True,
                check=False,
                timeout=2,
                cwd=str(exe.parent),
            )  # nosec B603  # argv fixe [exe, "--version"], binaire vérifié SHA-256, aucun shell
            if res.returncode == 0:
                return True, "Opérationnel"
            err = res.stderr.decode("utf-8", errors="ignore").strip()
            if "Library not loaded" in err or "libespeak-ng" in err:
                return False, "Dépendance système requise (libespeak-ng)"
            return False, f"Erreur ({res.returncode}) : {err}"
        except Exception as e:
            return False, str(e)

    def is_available(self) -> bool:
        """Vérifie la présence et le bon fonctionnement du binaire piper."""
        ok, _ = self.is_functional()
        return ok

    def get_voices(self) -> list[dict[str, str]]:
        """Liste les modèles .onnx présents dans le dossier des voix Piper (avec repli prod si vide en dev)."""
        from ankiforge.utils.paths import get_tools_search_dirs

        voices: list[dict[str, str]] = []
        seen_ids: set[str] = set()

        for tools_dir in get_tools_search_dirs():
            v_dir = tools_dir / "tts" / "voices"
            if v_dir.exists() and v_dir.is_dir():
                for model_file in v_dir.glob("*.onnx"):
                    voice_id = model_file.stem
                    if voice_id not in seen_ids:
                        seen_ids.add(voice_id)
                        voices.append(
                            {
                                "id": str(model_file),
                                "name": f"Piper - {voice_id}",
                                "lang": voice_id.split("-")[0] if "-" in voice_id else "local",
                            }
                        )
        if not voices:
            voices.append(
                {
                    "id": "default",
                    "name": "Piper (Aucune voix téléchargée - voir Paramètres)",
                    "lang": "fr-FR",
                }
            )
        return voices

    def synthesize(
        self,
        text: str,
        voice: str | None = None,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> bytes:
        piper_exe = self.get_piper_executable()
        if not piper_exe:
            raise RuntimeError("Le binaire Piper est introuvable. Téléchargez-le dans les Paramètres d'AnkiForge ou installez-le dans ~/.ankiforge/tools/tts/piper.")

        ok, reason = self.is_functional()
        if not ok:
            raise RuntimeError(f"Le moteur Piper ne peut pas s'exécuter sur cette machine : {reason}. Sélectionnez Edge-TTS ou le Moteur Système dans les Paramètres.")

        voices_dir = self.get_voices_dir()
        model_path: Path | None = None

        if voice and Path(voice).exists():
            model_path = Path(voice)
        else:
            # Recherche du premier modèle ONNX disponible
            available_models = list(voices_dir.glob("*.onnx"))
            if available_models:
                model_path = available_models[0]

        if not model_path or not model_path.exists():
            raise RuntimeError("Aucun modèle de voix Piper (.onnx) n'a été trouvé dans ~/.ankiforge/tools/tts/voices/. Téléchargez une voix dans les Paramètres.")

        # Création d'un fichier WAV temporaire
        temp_wav = voices_dir / f"temp_{hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()[:8]}.wav"
        try:
            cmd = [str(piper_exe), "--model", str(model_path), "--output_file", str(temp_wav)]
            proc = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                capture_output=True,
                check=False,
                cwd=str(piper_exe.parent),
            )  # nosec B603  # argv liste fixe, chemins vérifiés + SHA-256, input via stdin (pas shell)
            if proc.returncode != 0:
                err_msg = proc.stderr.decode("utf-8", errors="ignore")
                raise RuntimeError(f"Piper a échoué (code {proc.returncode}) : {err_msg}")

            if not temp_wav.exists() or temp_wav.stat().st_size == 0:
                raise RuntimeError("Piper n'a pas produit de fichier audio valide.")

            return temp_wav.read_bytes()
        finally:
            temp_wav.unlink(missing_ok=True)


class KokoroSidecarProvider(TTSProvider):
    """Fournisseur Kokoro-82M déporté (optionnel)."""

    id = "kokoro"
    display_name = "Kokoro-82M (Runner Local Déporté)"

    def is_available(self) -> bool:
        runner = get_app_data_dir() / "tools" / "tts" / "kokoro" / "run.py"
        return runner.exists() or shutil.which("kokoro") is not None

    def get_voices(self) -> list[dict[str, str]]:
        return [
            {"id": "af_heart", "name": "Kokoro - Heart (US Female)", "lang": "en-US"},
            {"id": "af_bella", "name": "Kokoro - Bella (US Female)", "lang": "en-US"},
            {"id": "am_adam", "name": "Kokoro - Adam (US Male)", "lang": "en-US"},
            {"id": "bf_emma", "name": "Kokoro - Emma (UK Female)", "lang": "en-GB"},
        ]

    def synthesize(
        self,
        text: str,
        voice: str | None = None,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> bytes:
        raise NotImplementedError("Le runner Kokoro déporté n'est pas encore configuré sur cette machine.")


class SystemSpeechProvider(TTSProvider):
    """
    Fournisseur Système OS : Zéro réseau, zéro téléchargement.
    Exploite les synthétiseurs natifs :
    - macOS : /usr/bin/say + afconvert
    - Windows : PowerShell SAPI5
    - Linux : espeak-ng / spd-say
    """

    id = "system"
    display_name = "Moteur Système OS (Fallback Natif Sans Réseau)"

    def is_available(self) -> bool:
        sys_name = platform.system()
        if sys_name == "Darwin":
            return Path("/usr/bin/say").exists()
        elif sys_name == "Windows":
            return shutil.which("powershell.exe") is not None
        elif sys_name == "Linux":
            return shutil.which("spd-say") is not None or shutil.which("espeak-ng") is not None
        return False

    def get_voices(self) -> list[dict[str, str]]:
        sys_name = platform.system()
        if sys_name == "Darwin":
            try:
                out = subprocess.check_output(["/usr/bin/say", "-v", "?"], text=True)  # nosec B603  # argv fixe, binaire système macOS (existance vérifiée)
                voices = []
                for line in out.strip().splitlines()[:15]:
                    parts = line.split()
                    if len(parts) >= 2:
                        v_name = parts[0]
                        lang = parts[1]
                        voices.append({"id": v_name, "name": f"Système ({v_name})", "lang": lang})
                return voices or [{"id": "Thomas", "name": "Système (Thomas)", "lang": "fr_FR"}]
            except Exception:
                return [{"id": "Thomas", "name": "Système (Thomas)", "lang": "fr_FR"}]
        return [{"id": "default", "name": "Voix Système par Défaut", "lang": "fr-FR"}]

    def synthesize(
        self,
        text: str,
        voice: str | None = None,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> bytes:
        sys_name = platform.system()
        temp_dir = get_app_data_dir() / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        h = hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()[:10]

        if sys_name == "Darwin":
            aiff_path = temp_dir / f"sys_{h}.aiff"
            m4a_path = temp_dir / f"sys_{h}.m4a"
            try:
                cmd = ["/usr/bin/say"]
                if voice and voice != "default":
                    cmd.extend(["-v", voice])
                cmd.extend(["-o", str(aiff_path), text])
                subprocess.run(cmd, check=True)  # nosec B603  # argv liste fixe [binaire système, -v, voix, -o, wav, texte]

                # Conversion en AAC/m4a si afconvert est disponible
                if Path("/usr/bin/afconvert").exists():
                    subprocess.run(
                        ["/usr/bin/afconvert", "-f", "mp4f", "-d", "aac", str(aiff_path), str(m4a_path)],
                        check=True,
                    )  # nosec B603  # argv fixe, chemins temporaires ~/.ankiforge/tmp, aucun shell
                    if m4a_path.exists():
                        return m4a_path.read_bytes()

                return aiff_path.read_bytes()
            finally:
                aiff_path.unlink(missing_ok=True)
                m4a_path.unlink(missing_ok=True)

        elif sys_name == "Windows":
            wav_path = temp_dir / f"sys_{h}.wav"
            ps_script = f"""
            Add-Type -AssemblyName System.Speech;
            $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer;
            $synth.SetOutputToWaveFile('{str(wav_path).replace("'", "''")}');
            $synth.Speak('{text.replace("'", "''")}');
            $synth.Dispose();
            """
            try:
                subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps_script], check=True)  # nosec B603 B607  # pas de shell=True ; texte échappé des guillemets simples, chemins temporaires dédiés
                if wav_path.exists():
                    return wav_path.read_bytes()
                raise RuntimeError("PowerShell SAPI5 n'a pas pu créer de fichier audio.")
            finally:
                wav_path.unlink(missing_ok=True)

        elif sys_name == "Linux":
            wav_path = temp_dir / f"sys_{h}.wav"
            if shutil.which("espeak-ng"):
                subprocess.run(["espeak-ng", "-w", str(wav_path), text], check=True)  # nosec B603 B607  # argv liste fixe, texte passé en argument (jamais shell)
                if wav_path.exists():
                    data = wav_path.read_bytes()
                    wav_path.unlink()
                    return data

        raise RuntimeError("Aucun moteur vocal système n'a pu synthétiser le texte.")


class TTSService:
    """
    Façade centrale pour la synthèse vocale et la gestion du stockage média AnkiForge.
    Gère la sélection du moteur, la normalisation, le cache MD5 et l'archivage via MediaManager.
    """

    def __init__(self, media_manager: MediaManager | None = None) -> None:
        self.media_manager = media_manager or MediaManager()
        self.normalizer = TextNormalizer()

        # Registre des moteurs disponibles
        self._providers: dict[str, TTSProvider] = {
            "edge-tts": EdgeTTSProvider(),
            "piper": PiperSidecarProvider(),
            "kokoro": KokoroSidecarProvider(),
            "system": SystemSpeechProvider(),
        }

    def get_provider(self, engine: str) -> TTSProvider:
        """Retourne le fournisseur correspondant au nom demandé avec repli si indisponible."""
        p = self._providers.get(engine.lower())
        if p and p.is_available():
            return p

        # Stratégie de repli ordonnée : Edge-TTS -> Piper -> Système
        for fallback_id in ("edge-tts", "piper", "system"):
            candidate = self._providers.get(fallback_id)
            if candidate and candidate.is_available():
                logger.warning(
                    "Moteur TTS '%s' non disponible, utilisation du repli : '%s'",
                    engine,
                    candidate.display_name,
                )
                return candidate

        raise RuntimeError("Aucun moteur de synthèse vocale (TTS) n'est disponible sur cette machine.")

    def get_available_engines(self) -> list[dict[str, Any]]:
        """Liste les moteurs TTS avec leur statut de disponibilité."""
        return [
            {
                "id": p_id,
                "display_name": p.display_name,
                "is_available": p.is_available(),
            }
            for p_id, p in self._providers.items()
        ]

    def synthesize(
        self,
        text: str,
        engine: str | None = None,
        voice: str | None = None,
        rate: str | None = None,
        pitch: str | None = None,
        strip_cloze: bool = True,
    ) -> tuple[str, Path]:
        """
        Synthétise un texte en fichier audio et l'intègre au dossier média AnkiForge.

        Returns:
            tuple[str, Path]:
                - str : La balise Anki [sound:nom_fichier.mp3]
                - Path : Le chemin d'accès absolu vers le fichier audio généré
        """
        clean_text = self.normalizer.clean_for_tts(text, strip_cloze=strip_cloze)
        if not clean_text:
            raise ValueError("Le texte à synthétiser est vide après normalisation.")

        # Récupération des paramètres par défaut si omis
        actual_engine = engine or SettingsService.get("tts.engine", "edge-tts")
        actual_voice = voice or SettingsService.get("tts.voice", "fr-FR-VivienneMultilingualNeural")
        actual_rate = rate or SettingsService.get("tts.rate", "+0%")
        actual_pitch = pitch or SettingsService.get("tts.pitch", "+0Hz")

        provider = self.get_provider(actual_engine)

        # 1. Calcul du hash d'identification unique pour le cache
        cache_key = f"{provider.id}:{actual_voice}:{actual_rate}:{actual_pitch}:{clean_text}"
        audio_hash = hashlib.md5(cache_key.encode("utf-8"), usedforsecurity=False).hexdigest()

        # Déterminer l'extension cible
        ext = ".mp3" if provider.id == "edge-tts" else ".wav"
        if provider.id == "system" and platform.system() == "Darwin":
            ext = ".m4a"

        target_filename = f"tts_{audio_hash}{ext}"
        candidate_path = self.media_manager.media_dir / target_filename
        if candidate_path.exists() and candidate_path.stat().st_size > 0:
            logger.debug("Audio déjà présent dans le cache média : %s", target_filename)
            return f"[sound:{target_filename}]", candidate_path

        existing_path = resolve_media_path(target_filename)
        if existing_path.exists() and existing_path.stat().st_size > 0:
            logger.debug("Audio déjà présent dans le cache média : %s", target_filename)
            return f"[sound:{target_filename}]", existing_path

        # 2. Génération des données audio brutes
        logger.info(
            "Synthèse vocale en cours [%s / %s] : '%s' (%d caractères)",
            provider.id,
            actual_voice,
            clean_text[:40],
            len(clean_text),
        )
        raw_bytes = provider.synthesize(clean_text, voice=actual_voice, rate=actual_rate, pitch=actual_pitch)

        # 3. Sauvegarde directe sous target_filename dans media_dir
        dest_path = self.media_manager.media_dir / target_filename
        dest_path.write_bytes(raw_bytes)

        # Enregistrement en base de données MediaModel pour la traçabilité
        try:
            from ankiforge.database.models import MediaModel

            MediaModel.get_or_create(
                checksum=audio_hash,
                defaults={
                    "filename": target_filename,
                    "original_name": target_filename,
                    "mime_type": "audio/mpeg" if ext == ".mp3" else "audio/wav",
                },
            )
        except Exception as err:
            logger.debug("Remarque sur l'enregistrement MediaModel : %s", err)

        logger.info("Audio TTS généré avec succès : %s", target_filename)
        return f"[sound:{target_filename}]", dest_path

    # =========================================================================
    # GESTIONNAIRE DE TÉLÉCHARGEMENT PIPER SIDECAR (1-CLIC)
    # =========================================================================

    @staticmethod
    def is_piper_installed() -> bool:
        """Vérifie si Piper est déjà installé dans tools/tts/piper."""
        return PiperSidecarProvider.get_piper_executable() is not None

    @staticmethod
    def download_and_install_piper(progress_callback: Callable[[str], None] | None = None) -> bool:
        """
        Télécharge et décompresse automatiquement l'exécutable officiel Piper
        correspondant à la plateforme courante dans ~/.ankiforge/tools/tts/.

        Intégrité : chaque asset est épinglé en SHA-256 (source officielle GitHub)
        et le téléchargement est soumis à un plafond de taille et un timeout.
        """
        sys_name = platform.system()
        arch = platform.machine().lower()

        # Résolution de l'asset officiel correspondant à la plateforme
        key = (sys_name, "amd64") if sys_name == "Windows" else (sys_name, "arm64" if "arm" in arch or "aarch64" in arch else "x86_64")
        if key not in _PIPER_ASSETS:
            raise RuntimeError(f"Plateforme non supportée pour Piper automatique : {sys_name} {arch}")
        asset_name, expected_sha256, is_tar = _PIPER_ASSETS[key]

        tools_dir = get_app_data_dir() / "tools" / "tts"
        tools_dir.mkdir(parents=True, exist_ok=True)

        url = f"{_PIPER_RELEASE_BASE_URL}/{asset_name}"
        archive_path = tools_dir / ("piper_archive.tar.gz" if is_tar else "piper_archive.zip")

        if progress_callback:
            progress_callback("Téléchargement de Piper depuis GitHub (vérification SHA-256)...")

        try:
            _download_verified(
                url,
                archive_path,
                expected_sha256,
                max_bytes=_MAX_PIPER_ARCHIVE_BYTES,
                progress_callback=progress_callback,
                progress_label="Téléchargement de Piper",
            )

            if progress_callback:
                progress_callback("Extraction de l'archive...")

            if is_tar:
                safe_extract_tar(archive_path, tools_dir, max_total_size=_MAX_PIPER_ARCHIVE_BYTES)
            else:
                safe_extract_zip(archive_path, tools_dir, max_total_size=_MAX_PIPER_ARCHIVE_BYTES)

            archive_path.unlink(missing_ok=True)

            # S'assurer des permissions d'exécution (fichiers téléchargés dans le
            # profil utilisateur ~/.ankiforge/tools, mode 0755 requis pour s'exécuter)
            exe = PiperSidecarProvider.get_piper_executable()
            if exe and sys_name != "Windows":
                os.chmod(exe, 0o755)  # nosec B103  # propriété de l'utilisateur, nécessaire à l'exécution
                for helper_name in ("piper_phonemize", "espeak-ng"):
                    helper = exe.parent / helper_name
                    if helper.exists():
                        os.chmod(helper, 0o755)  # nosec B103  # idem

            # Télécharger une voix française par défaut si aucune voix n'est présente
            voices_dir = PiperSidecarProvider.get_voices_dir()
            if not list(voices_dir.glob("*.onnx")):
                if progress_callback:
                    progress_callback("Téléchargement de la voix française (fr_FR-siwis-low)...")
                for ext in (".onnx", ".onnx.json"):
                    fname = f"fr_FR-siwis-low{ext}"
                    v_url = f"{_PIPER_VOICE_BASE_URL}/{fname}"
                    v_dest = voices_dir / fname
                    _download_verified(
                        v_url,
                        v_dest,
                        _PIPER_VOICE_SHA256[fname],
                        max_bytes=_MAX_PIPER_VOICE_BYTES,
                    )

            if progress_callback:
                progress_callback("Piper installé avec succès !")
            return True

        except Exception as e:
            logger.exception("Échec du téléchargement/installation de Piper : %s", e)
            if archive_path.exists():
                archive_path.unlink(missing_ok=True)
            raise


# Instance singleton paresseuse
_tts_service_instance: TTSService | None = None


def get_tts_service() -> TTSService:
    """Retourne l'instance singleton du service TTS."""
    global _tts_service_instance
    if _tts_service_instance is None:
        _tts_service_instance = TTSService()
    return _tts_service_instance
