"""Installation et résolution du moteur Marker OCR hors du binaire Nuitka."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess  # nosec B404
import sys
from collections.abc import Callable
from pathlib import Path

from ankiforge.utils.paths import get_tools_search_dirs


class MarkerService:
    """Gère Marker dans un environnement Python persistant séparé de Nuitka."""

    PACKAGE_NAME = "marker-pdf"

    @classmethod
    def install(cls, progress_callback: Callable[[str], None] | None = None) -> Path:
        """Crée un venv persistant et installe marker-pdf avec pip."""
        python = cls._find_python()
        install_dir = get_tools_search_dirs()[0] / "marker"
        venv_dir = install_dir / "venv"
        install_dir.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback("Création de l'environnement Marker OCR...")
        if not (cls._venv_python(venv_dir)).exists():
            cls._run([python, "-m", "venv", str(venv_dir)], progress_callback)

        venv_python = cls._venv_python(venv_dir)
        if progress_callback:
            progress_callback("Installation de marker-pdf et de ses dépendances...")
        cls._run([str(venv_python), "-m", "pip", "install", "--upgrade", cls.PACKAGE_NAME], progress_callback)

        executable = cls._venv_executable(venv_dir)
        if not executable.exists():
            raise RuntimeError("L'installation est terminée mais marker_single est introuvable.")
        if platform.system() != "Windows":
            executable.chmod(executable.stat().st_mode | 0o111)
        return executable

    @classmethod
    def get_executable(cls) -> Path | None:
        for tools_dir in get_tools_search_dirs():
            for venv_dir in (tools_dir / "marker" / "venv", tools_dir / "marker"):
                executable = cls._venv_executable(venv_dir)
                if executable.exists() and (platform.system() == "Windows" or os.access(executable, os.X_OK)):
                    return executable
        return None

    @staticmethod
    def _venv_python(venv_dir: Path) -> Path:
        return venv_dir / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")

    @staticmethod
    def _venv_executable(venv_dir: Path) -> Path:
        return venv_dir / ("Scripts/marker_single.exe" if platform.system() == "Windows" else "bin/marker_single")

    @staticmethod
    def _find_python() -> str:
        candidates = []
        from ankiforge.utils.environment import is_standalone_runtime

        if not is_standalone_runtime():
            candidates.append(sys.executable)
        candidates.extend(filter(None, (shutil.which("python3"), shutil.which("python"))))
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
        raise RuntimeError("Python externe introuvable. Installez Python 3.12 pour installer Marker OCR.")

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
