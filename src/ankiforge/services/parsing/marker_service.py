"""Installation et résolution du moteur Marker OCR hors du binaire Nuitka."""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess  # nosec B404
import sys
from collections.abc import Callable
from pathlib import Path

from ankiforge.utils.paths import get_tools_search_dirs

logger = logging.getLogger(__name__)


class MarkerService:
    """Gère Marker dans un environnement Python persistant séparé de Nuitka."""

    PACKAGE_NAME = "marker-pdf>=1.8.0,<2.0.0"
    MIN_PYTHON_VERSION = (3, 10)
    MAX_PYTHON_VERSION = (3, 14)  # Exclusif : 3.10, 3.11, 3.12, 3.13 supportés

    @classmethod
    def install(cls, progress_callback: Callable[[str], None] | None = None) -> Path:
        """Crée un venv persistant et installe marker-pdf avec pip ou uv."""
        python = cls._find_python()
        install_dir = get_tools_search_dirs()[0] / "marker"
        venv_dir = install_dir / "venv"
        install_dir.mkdir(parents=True, exist_ok=True)

        # Si le venv existe déjà mais n'est pas basé sur une version de Python compatible, on le purge
        if venv_dir.exists() and not cls._is_venv_compatible(venv_dir):
            if progress_callback:
                progress_callback("Environnement Marker incompatible ou obsolète détecté. Réinitialisation...")
            logger.info("Purge de l'environnement Marker obsolète : %s", venv_dir)
            shutil.rmtree(venv_dir, ignore_errors=True)

        if not cls._is_venv_compatible(venv_dir):
            if progress_callback:
                progress_callback("Création de l'environnement Marker OCR (Python compatible)...")
            uv_exe = cls._find_uv()
            if uv_exe:
                cls._run([uv_exe, "venv", str(venv_dir), "--python", python], progress_callback)
            else:
                cls._run([python, "-m", "venv", str(venv_dir)], progress_callback)

        venv_python = cls._venv_python(venv_dir)
        if not cls._is_python_compatible(venv_python):
            raise RuntimeError(f"L'environnement virtuel créé à {venv_dir} n'est pas valide ou utilise un Python incompatible.")

        if progress_callback:
            progress_callback("Installation de marker-pdf et de ses dépendances...")

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
            raise RuntimeError("L'installation est terminée mais marker_single est introuvable.")
        if platform.system() != "Windows":
            executable.chmod(executable.stat().st_mode | 0o111)
        return executable

    @classmethod
    def get_executable(cls) -> Path | None:
        """Retourne le chemin vers marker_single s'il existe et est basé sur un environnement compatible."""
        for tools_dir in get_tools_search_dirs():
            for venv_dir in (tools_dir / "marker" / "venv", tools_dir / "marker"):
                executable = cls._venv_executable(venv_dir)
                if executable.exists() and (platform.system() == "Windows" or os.access(executable, os.X_OK)):
                    if cls._is_venv_compatible(venv_dir):
                        return executable
                    logger.warning(
                        "L'exécutable Marker à %s utilise un environnement incompatible (Python < 3.10 ou Marker >= 2.0.0 requérant llama-server). Réinstallation requise.",
                        executable,
                    )
        return None

    @classmethod
    def _is_venv_compatible(cls, venv_dir: Path) -> bool:
        """Vérifie si le venv contient un interpréteur Python fonctionnel et une version autonome de Marker (< 2.0.0)."""
        venv_python = cls._venv_python(venv_dir)
        if not (venv_python.exists() and cls._is_python_compatible(venv_python)):
            return False

        executable = cls._venv_executable(venv_dir)
        if executable.exists():
            # Si marker est installé, vérifier qu'il ne s'agit pas de la v2+ qui impose llama-server
            try:
                res = subprocess.run(  # nosec B603
                    [
                        str(venv_python),
                        "-c",
                        "import importlib.metadata, sys; v = importlib.metadata.version('marker-pdf'); major = int(v.split('.')[0]); sys.exit(0 if major < 2 else 1)",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=5,
                )
                if res.returncode != 0:
                    return False
            except Exception:
                pass
        return True

    @classmethod
    def _is_python_compatible(cls, candidate: str | Path) -> bool:
        """Vérifie si l'interpréteur Python satisfait 3.10 <= version < 3.14."""
        candidate_path = Path(candidate)
        if not candidate_path.exists():
            return False
        try:
            res = subprocess.run(  # nosec B603
                [
                    str(candidate),
                    "-c",
                    "import sys; min_v = (3, 10); max_v = (3, 14); sys.exit(0 if min_v <= sys.version_info < max_v else 1)",
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
        """Détecte un interpréteur Python compatible (>= 3.10 et < 3.14)."""
        from ankiforge.utils.environment import is_standalone_runtime

        candidates: list[str] = []

        # 1. sys.executable si l'application s'exécute depuis les sources Python
        if not is_standalone_runtime() and cls._is_python_compatible(sys.executable):
            return sys.executable

        # 2. Recherche via uv si présent
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
            except Exception:
                pass

        # 3. Commandes versionnées dans le PATH
        for cmd in ("python3.12", "python3.11", "python3.10", "python3", "python"):
            which_path = shutil.which(cmd)
            if which_path and which_path not in candidates:
                candidates.append(which_path)

        # 4. Chemins système typiques par plateforme
        system_paths: list[Path] = []
        if platform.system() == "Darwin":
            for ver in ("3.12", "3.11", "3.10"):
                system_paths.extend(
                    [
                        Path(f"/opt/homebrew/bin/python{ver}"),
                        Path(f"/usr/local/bin/python{ver}"),
                        Path(f"/Library/Frameworks/Python.framework/Versions/{ver}/bin/python3"),
                        Path(f"/opt/local/bin/python{ver}"),
                    ]
                )
            uv_python_dir = Path.home() / ".local" / "share" / "uv" / "python"
            if uv_python_dir.is_dir():
                system_paths.extend(sorted(uv_python_dir.glob("cpython-3.1[0-2]*/bin/python3"), reverse=True))
        elif platform.system() == "Linux":
            for ver in ("3.12", "3.11", "3.10"):
                system_paths.extend(
                    [
                        Path(f"/usr/bin/python{ver}"),
                        Path(f"/usr/local/bin/python{ver}"),
                    ]
                )
            uv_python_dir = Path.home() / ".local" / "share" / "uv" / "python"
            if uv_python_dir.is_dir():
                system_paths.extend(sorted(uv_python_dir.glob("cpython-3.1[0-2]*/bin/python3"), reverse=True))
        elif platform.system() == "Windows":
            for ver in ("312", "311", "310"):
                system_paths.extend(
                    [
                        Path.home() / f"AppData/Local/Programs/Python/Python{ver}/python.exe",
                        Path(f"C:/Python{ver}/python.exe"),
                    ]
                )

        for p in system_paths:
            if p.is_file() and str(p) not in candidates:
                candidates.append(str(p))

        # 5. Test et sélection du premier candidat compatible
        for candidate in candidates:
            if cls._is_python_compatible(candidate):
                logger.info("Interpréteur Python compatible sélectionné pour Marker OCR : %s", candidate)
                return candidate

        raise RuntimeError(
            "Aucun interpréteur Python compatible (3.10, 3.11 ou 3.12) n'a été trouvé.\n"
            "Marker OCR nécessite Python 3.10 ou supérieur (Python 3.9 n'est pas supporté).\n"
            "Veuillez installer Python 3.12 via Homebrew ('brew install python@3.12') ou depuis https://www.python.org."
        )

    @staticmethod
    def _venv_python(venv_dir: Path) -> Path:
        return venv_dir / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")

    @staticmethod
    def _venv_executable(venv_dir: Path) -> Path:
        return venv_dir / ("Scripts/marker_single.exe" if platform.system() == "Windows" else "bin/marker_single")

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
