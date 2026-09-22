"""Installation, détection et exécution sécurisée de yt-dlp hors du binaire Nuitka."""

from __future__ import annotations

import importlib.util
import logging
import os
import platform
import shutil
import subprocess  # nosec B404
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ankiforge.utils.paths import get_tools_search_dirs

logger = logging.getLogger(__name__)


class YtDlpUnavailableError(RuntimeError):
    """Exception levée lorsque yt-dlp n'est pas disponible et requis pour l'opération."""

    def __init__(self, message: str | None = None) -> None:
        default_msg = "yt-dlp est introuvable. Pour transcrire des vidéos YouTube sans sous-titres, veuillez installer yt-dlp (ex: 'uv add yt-dlp' ou via les outils déportés AnkiForge)."
        super().__init__(message or default_msg)


class YtDlpService:
    """Gère yt-dlp en tant qu'outil déporté dans un environnement isolé ou binaire système."""

    PACKAGE_NAME = "yt-dlp>=2024.1.1"
    MIN_PYTHON_VERSION = (3, 10)
    MAX_PYTHON_VERSION = (3, 14)

    @classmethod
    def get_executable(cls) -> Path | None:
        """Retourne le chemin vers le binaire yt-dlp s'il existe dans les dossiers tools ou le PATH."""
        from ankiforge.utils.environment import is_testing

        # 1. Recherche dans les répertoires d'outils déportés d'AnkiForge
        for tools_dir in get_tools_search_dirs():
            for venv_dir in (tools_dir / "yt-dlp" / "venv", tools_dir / "yt-dlp"):
                executable = cls._venv_executable(venv_dir)
                if executable.exists() and (platform.system() == "Windows" or os.access(executable, os.X_OK)):
                    return executable

            bin_candidate = tools_dir / "bin" / ("yt-dlp.exe" if platform.system() == "Windows" else "yt-dlp")
            if bin_candidate.is_file() and (platform.system() == "Windows" or os.access(bin_candidate, os.X_OK)):
                return bin_candidate

        # 2. Recherche dans le PATH système (ignoré en tests unitaires pour isolation)
        if not is_testing():
            sys_path = shutil.which("yt-dlp")
            if sys_path:
                candidate = Path(sys_path)
                if candidate.is_file() and (platform.system() == "Windows" or os.access(candidate, os.X_OK)):
                    return candidate

        return None

    @classmethod
    def is_available(cls) -> bool:
        """Indique si yt-dlp est disponible (binaire local ou module python)."""
        if cls.get_executable() is not None:
            return True
        try:
            return importlib.util.find_spec("yt_dlp") is not None
        except Exception:
            return False

    @classmethod
    def install(cls, progress_callback: Callable[[str], None] | None = None) -> Path:
        """Crée un venv persistant et installe yt-dlp avec pip ou uv."""
        python = cls._find_python()
        install_dir = get_tools_search_dirs()[0] / "yt-dlp"
        venv_dir = install_dir / "venv"
        install_dir.mkdir(parents=True, exist_ok=True)

        if venv_dir.exists() and not cls._is_venv_compatible(venv_dir):
            if progress_callback:
                progress_callback("Environnement yt-dlp incompatible ou obsolète détecté. Réinitialisation...")
            logger.info("Purge de l'environnement yt-dlp obsolète : %s", venv_dir)
            shutil.rmtree(venv_dir, ignore_errors=True)

        if not cls._is_venv_compatible(venv_dir):
            if progress_callback:
                progress_callback("Création de l'environnement yt-dlp...")
            uv_exe = cls._find_uv()
            if uv_exe:
                cls._run([uv_exe, "venv", str(venv_dir), "--python", python], progress_callback)
            else:
                cls._run([python, "-m", "venv", str(venv_dir)], progress_callback)

        venv_python = cls._venv_python(venv_dir)
        if not cls._is_python_compatible(venv_python):
            raise RuntimeError(f"L'environnement virtuel créé à {venv_dir} n'est pas valide ou utilise un Python incompatible.")

        if progress_callback:
            progress_callback("Installation de yt-dlp...")

        uv_exe = cls._find_uv()
        if uv_exe:
            cls._run(
                [uv_exe, "pip", "install", "--upgrade", cls.PACKAGE_NAME, "--python", str(venv_python)],
                progress_callback,
            )
        else:
            cls._run([str(venv_python), "-m", "pip", "install", "--upgrade", cls.PACKAGE_NAME], progress_callback)

        executable = cls._venv_executable(venv_dir)
        if not executable.exists():
            raise RuntimeError("L'installation est terminée mais yt-dlp est introuvable.")
        if platform.system() != "Windows":
            executable.chmod(executable.stat().st_mode | 0o111)
        return executable

    @classmethod
    def download_audio(
        cls,
        url: str,
        output_dir: Path,
        progress_callback: Callable[[str], None] | None = None,
        check_cancel: Callable[[], bool] | None = None,
    ) -> Path:
        """Télécharge le flux audio natif de la vidéo YouTube (format M4A / AAC sans conversion).

        Args:
            url: URL de la vidéo YouTube.
            output_dir: Dossier où enregistrer le flux audio temporaire.
            progress_callback: Callback optionnel de suivi d'avancement.
            check_cancel: Callback optionnel vérifiant si l'annulation est demandée.

        Returns:
            Path: Chemin absolu vers le fichier audio téléchargé.

        Raises:
            YtDlpUnavailableError: Si yt-dlp n'est pas installé.
            RuntimeError: En cas d'erreur de téléchargement ou d'annulation.
        """
        if check_cancel and check_cancel():
            raise RuntimeError("Téléchargement annulé avant le démarrage.")

        output_dir.mkdir(parents=True, exist_ok=True)
        out_tmpl = output_dir / "%(id)s.%(ext)s"

        executable = cls.get_executable()

        if executable is not None:
            # Mode A : Binaire autonome yt-dlp via subprocess
            if progress_callback:
                progress_callback("Téléchargement du flux audio avec yt-dlp...")

            cmd = [
                str(executable),
                "-f",
                "ba[ext=m4a]/ba/b",
                "-o",
                str(out_tmpl),
                "--no-playlist",
                "--no-warnings",
                url,
            ]

            process = subprocess.Popen(  # nosec B603
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
            )

            try:
                if process.stdout is not None:
                    for line in process.stdout:
                        if check_cancel and check_cancel():
                            process.terminate()
                            try:
                                process.wait(timeout=2)
                            except subprocess.TimeoutExpired:
                                process.kill()
                            raise RuntimeError("Téléchargement audio annulé par l'utilisateur.")
                        clean_line = line.strip()
                        if progress_callback and clean_line and "[download]" in clean_line:
                            progress_callback(clean_line)
                return_code = process.wait()
                if return_code != 0:
                    raise RuntimeError(f"yt-dlp a échoué avec le code d'erreur {return_code}.")
            except Exception:
                if process.poll() is None:
                    process.kill()
                raise

        elif importlib.util.find_spec("yt_dlp") is not None:
            # Mode B : Module Python yt_dlp
            if progress_callback:
                progress_callback("Téléchargement du flux audio via le module yt_dlp...")

            import yt_dlp

            def _hook(d: dict[str, Any]) -> None:
                if check_cancel and check_cancel():
                    raise RuntimeError("Téléchargement audio annulé par l'utilisateur.")
                if progress_callback and d.get("status") == "downloading":
                    pct = str(d.get("_percent_str", "")).strip()
                    if pct:
                        progress_callback(f"Téléchargement audio : {pct}")

            ydl_opts = {
                "format": "ba[ext=m4a]/ba/b",
                "outtmpl": str(out_tmpl),
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "progress_hooks": [_hook],
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        else:
            raise YtDlpUnavailableError()

        # Localisation du fichier téléchargé dans output_dir
        audio_candidates = sorted(
            [f for f in output_dir.iterdir() if f.is_file() and f.suffix.lower() in (".m4a", ".webm", ".opus", ".mp3", ".wav", ".aac")],
            key=lambda p: p.stat().st_size,
            reverse=True,
        )

        if not audio_candidates:
            raise RuntimeError(f"yt-dlp s'est exécuté mais aucun fichier audio n'a été produit dans {output_dir}.")

        selected_audio = audio_candidates[0]
        logger.info("Flux audio YouTube téléchargé avec succès : %s (%d octets)", selected_audio.name, selected_audio.stat().st_size)
        return selected_audio

    # ── Méthodes utilitaires d'environnement ────────────────────────────────────

    @classmethod
    def _is_venv_compatible(cls, venv_dir: Path) -> bool:
        """Vérifie si le venv contient un interpréteur Python fonctionnel."""
        venv_python = cls._venv_python(venv_dir)
        return venv_python.exists() and cls._is_python_compatible(venv_python)

    @classmethod
    def _is_python_compatible(cls, candidate: str | Path) -> bool:
        """Vérifie si l'interpréteur Python satisfait MIN_PYTHON_VERSION <= version < MAX_PYTHON_VERSION."""
        candidate_path = Path(candidate)
        if not candidate_path.exists():
            return False
        try:
            res = subprocess.run(  # nosec B603
                [
                    str(candidate),
                    "-c",
                    f"import sys; min_v = {cls.MIN_PYTHON_VERSION}; max_v = {cls.MAX_PYTHON_VERSION}; sys.exit(0 if min_v <= sys.version_info < max_v else 1)",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
            return res.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _find_uv() -> str | None:
        """Localise l'exécutable uv pour une installation rapide si disponible."""
        exe = shutil.which("uv")
        if exe and os.access(exe, os.X_OK):
            return exe
        for candidate in (
            Path.home() / ".local" / "bin" / "uv",
            Path.home() / ".cargo" / "bin" / "uv",
            Path("/opt/homebrew/bin/uv"),
            Path("/usr/local/bin/uv"),
        ):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        return None

    @classmethod
    def _find_python(cls) -> str:
        """Détecte un interpréteur Python compatible."""
        from ankiforge.utils.environment import is_standalone_runtime

        candidates: list[str] = []

        if not is_standalone_runtime() and cls._is_python_compatible(sys.executable):
            return sys.executable

        uv_exe = cls._find_uv()
        if uv_exe:
            try:
                res = subprocess.run(  # nosec B603
                    [uv_exe, "python", "find", ">=3.10,<3.14"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if res.returncode == 0:
                    found = res.stdout.strip()
                    if found and cls._is_python_compatible(found):
                        return found
            except Exception as err:
                logger.debug("Découverte de l'interpréteur Python via uv ignorée : %s", err)

        for cmd in ("python3.12", "python3.11", "python3.10", "python3", "python"):
            which_path = shutil.which(cmd)
            if which_path and which_path not in candidates:
                candidates.append(which_path)

        for candidate in candidates:
            if cls._is_python_compatible(candidate):
                return candidate

        raise RuntimeError("Aucun interpréteur Python compatible trouvé pour installer yt-dlp.")

    @staticmethod
    def _venv_python(venv_dir: Path) -> Path:
        return venv_dir / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")

    @staticmethod
    def _venv_executable(venv_dir: Path) -> Path:
        return venv_dir / ("Scripts/yt-dlp.exe" if platform.system() == "Windows" else "bin/yt-dlp")

    @staticmethod
    def _run(command: list[str], progress_callback: Callable[[str], None] | None) -> None:
        process = subprocess.Popen(  # nosec B603
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
        if process.stdout is not None:
            for line in process.stdout:
                if progress_callback and line.strip():
                    progress_callback(line.strip())
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"Commande d'installation échouée (code {return_code}) : {' '.join(command[:4])}")
