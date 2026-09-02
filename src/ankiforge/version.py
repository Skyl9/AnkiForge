"""Module centralisé et dynamique de gestion des versions et métadonnées de build pour AnkiForge.

Fournit une Source Unique de Vérité (SSOT) pour :
1. La version sémantique de l'application (SemVer).
2. Le hash Git du commit de compilation.
3. L'horodatage de build UTC.
4. Le canal de distribution (stable, nightly, dev).
5. La plateforme et architecture d'exécution.
"""

from __future__ import annotations

import datetime
import logging
import os
import platform
import subprocess  # nosec: B404
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Version par défaut du projet
DEFAULT_VERSION = "1.0.5"


def _is_standalone() -> bool:
    """Détecte si l'application s'exécute en binaire autonome gelé."""
    if "__compiled__" in globals() or "__compiled__" in sys.modules:
        return True
    if getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"):
        return True
    if "APPIMAGE" in os.environ:
        return True
    exe_path = Path(sys.executable).resolve()
    if sys.platform == "darwin" and "Contents/MacOS" in str(exe_path):
        return True
    return False


def _get_platform_string() -> str:
    """Retourne une chaîne lisible représentant le système et l'architecture."""
    sys_name = platform.system()
    machine = platform.machine().lower()

    if sys_name == "Darwin":
        arch = "arm64" if "arm" in machine or "aarch" in machine else "x86_64"
        return f"macOS {arch}"
    elif sys_name == "Windows":
        arch = "x64" if "64" in machine else "x86"
        return f"Windows {arch}"
    elif sys_name == "Linux":
        arch = "x86_64" if "64" in machine or "x86_64" in machine else machine
        return f"Linux {arch}"
    return f"{sys_name} ({machine})"


def _read_git_commit(project_root: Path) -> str:
    """Tente de récupérer le hash Git court en mode développement."""
    try:
        git_dir = project_root / ".git"
        if not git_dir.exists():
            return "dev"
        res = subprocess.run(  # nosec: B603, B607
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return "dev"


def _read_pyproject_version(project_root: Path) -> str:
    """Tente de lire la version dans pyproject.toml."""
    try:
        pyproject_file = project_root / "pyproject.toml"
        if pyproject_file.is_file():
            with open(pyproject_file, encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith("version") and "=" in stripped:
                        return stripped.split("=")[1].strip().strip("\"'")
    except Exception:
        pass
    return DEFAULT_VERSION


@dataclass(frozen=True)
class AppVersionInfo:
    """Structure immuable des métadonnées de version d'AnkiForge."""

    version: str
    commit_hash: str
    build_date: str
    build_channel: str
    platform_str: str
    is_standalone: bool

    @property
    def full_display_version(self) -> str:
        """Version complète formatée pour les diagnostics et logs (ex: 'v1.0.5 (c673440a) · macOS arm64')."""
        channel_suffix = f" [{self.build_channel.upper()}]" if self.build_channel != "stable" else ""
        return f"v{self.version}{channel_suffix} ({self.commit_hash}) · {self.platform_str}"

    @property
    def short_display_version(self) -> str:
        """Version courte formatée (ex: 'v1.0.5' ou 'v1.0.5-nightly')."""
        return f"v{self.version}"


def get_version_info() -> AppVersionInfo:
    """Résout et retourne l'objet AppVersionInfo de l'instance en cours d'exécution."""
    is_standalone_env = _is_standalone()
    platform_info = _get_platform_string()

    # 1. Tentative de lecture du fichier généré statiquement au build (_version.py)
    try:
        from ankiforge import _version  # type: ignore[attr-defined]

        return AppVersionInfo(
            version=str(getattr(_version, "VERSION", DEFAULT_VERSION)),
            commit_hash=str(getattr(_version, "COMMIT_HASH", "standalone")),
            build_date=str(getattr(_version, "BUILD_DATE", "")),
            build_channel=str(getattr(_version, "BUILD_CHANNEL", "stable")),
            platform_str=platform_info,
            is_standalone=is_standalone_env,
        )
    except ImportError:
        pass

    # 2. Mode Développement source : Résolution dynamique
    root = Path(__file__).resolve().parent.parent.parent
    ver = _read_pyproject_version(root)
    commit = _read_git_commit(root)
    date_str = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    return AppVersionInfo(
        version=ver,
        commit_hash=commit,
        build_date=date_str,
        build_channel="dev",
        platform_str=platform_info,
        is_standalone=is_standalone_env,
    )


# Constantes globales exportées
VERSION_INFO: AppVersionInfo = get_version_info()
__version__: str = VERSION_INFO.version
