"""Service de Détection et Validation de l'Environnement LaTeX Local pour AnkiForge.

Détecte automatiquement les exécutables nécessaires (latex, dvisvgm, dvipng)
sur les plateformes courantes (macOS, Linux, Windows) et certifie leur version.
"""

import logging
import shutil
import subprocess  # nosec B404 - intentional subprocess usage for version detection
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LatexBinaryInfo:
    """Informations sur un binaire LaTeX détecté."""

    name: str
    path: str
    version: str | None = None
    is_available: bool = True


@dataclass(frozen=True)
class LatexEnvironmentStatus:
    """Statut global de l'environnement LaTeX."""

    latex: LatexBinaryInfo | None
    dvisvgm: LatexBinaryInfo | None
    dvipng: LatexBinaryInfo | None
    is_fully_available: bool
    message: str


class LatexEnvironmentService:
    """Détecte et valide la chaîne d'outils LaTeX locale de l'utilisateur."""

    KNOWN_MAC_PATHS: list[str] = [
        "/Library/TeX/texbin",
        "/usr/local/bin",
        "/opt/homebrew/bin",
    ]

    KNOWN_LINUX_PATHS: list[str] = [
        "/usr/bin",
        "/usr/local/bin",
    ]

    KNOWN_WIN_PATHS: list[str] = [
        r"C:\Program Files\MiKTeX\miktex\bin\x64",
        r"C:\Program Files\texlive\2024\bin\windows",
        r"C:\Program Files\texlive\2023\bin\windows",
        r"C:\Program Files\texlive\2022\bin\windows",
    ]

    def __init__(self) -> None:
        self._cache: dict[str, LatexBinaryInfo | None] = {}

    def detect_latex_binary(self) -> LatexBinaryInfo | None:
        """Localise l'exécutable 'latex' ou 'pdflatex'."""
        return self._detect_binary("latex", fallback_names=["pdflatex"])

    def detect_dvisvgm_binary(self) -> LatexBinaryInfo | None:
        """Localise l'exécutable 'dvisvgm'."""
        return self._detect_binary("dvisvgm")

    def detect_dvipng_binary(self) -> LatexBinaryInfo | None:
        """Localise l'exécutable 'dvipng'."""
        return self._detect_binary("dvipng")

    def _detect_binary(self, name: str, fallback_names: list[str] | None = None) -> LatexBinaryInfo | None:
        """Recherche un binaire dans le PATH puis dans les chemins connus selon la plateforme."""
        cache_key = name
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 1. Recherche via shutil.which (respecte le PATH du processus)
        path = shutil.which(name)
        if path:
            info = self._get_binary_info(name, path)
            self._cache[cache_key] = info
            return info

        # 2. Essayer les noms de secours
        if fallback_names:
            for fallback in fallback_names:
                path = shutil.which(fallback)
                if path:
                    info = self._get_binary_info(fallback, path)
                    self._cache[cache_key] = info
                    return info

        # 3. Recherche dans les chemins connus selon la plateforme
        known_paths = self._get_known_paths_for_platform()
        for base_path in known_paths:
            candidate = Path(base_path) / name
            if sys.platform == "win32":
                candidate = candidate.with_suffix(".exe")
            if candidate.exists() and candidate.is_file():
                info = self._get_binary_info(name, str(candidate))
                self._cache[cache_key] = info
                return info

                # Essayer aussi les noms de secours dans les chemins connus
                if fallback_names:
                    for fallback in fallback_names:
                        candidate_fb = Path(base_path) / fallback
                        if sys.platform == "win32":
                            candidate_fb = candidate_fb.with_suffix(".exe")
                        if candidate_fb.exists() and candidate_fb.is_file():
                            info = self._get_binary_info(fallback, str(candidate_fb))
                            self._cache[cache_key] = info
                            return info

        self._cache[cache_key] = None
        return None

    def _get_known_paths_for_platform(self) -> list[str]:
        """Retourne les chemins connus selon la plateforme courante."""
        if sys.platform == "darwin":
            return self.KNOWN_MAC_PATHS
        elif sys.platform == "win32":
            return self.KNOWN_WIN_PATHS
        else:
            return self.KNOWN_LINUX_PATHS

    def _get_binary_info(self, name: str, path: str) -> LatexBinaryInfo:
        """Récupère la version d'un binaire s'il est disponible."""
        version = self._get_version(path)
        return LatexBinaryInfo(name=name, path=path, version=version, is_available=True)

    def _get_version(self, binary_path: str) -> str | None:
        """Exécute le binaire avec --version et extrait la version."""
        try:
            result = subprocess.run(  # nosec B603 - trusted binary path, no user input
                [binary_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0 and result.stdout:
                # Extraire la première ligne non vide
                lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
                if lines:
                    return lines[0]
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError) as e:
            logger.debug("Impossible de récupérer la version de %s : %s", binary_path, e)
        return None

    def get_latex_version(self) -> str | None:
        """Retourne la version de latex/pdflatex si disponible."""
        info = self.detect_latex_binary()
        return info.version if info else None

    def get_dvisvgm_version(self) -> str | None:
        """Retourne la version de dvisvgm si disponible."""
        info = self.detect_dvisvgm_binary()
        return info.version if info else None

    def get_dvipng_version(self) -> str | None:
        """Retourne la version de dvipng si disponible."""
        info = self.detect_dvipng_binary()
        return info.version if info else None

    def is_latex_available(self) -> bool:
        """Certifie que la chaîne minimale (latex + dvisvgm) est fonctionnelle."""
        return bool(self.detect_latex_binary() and self.detect_dvisvgm_binary())

    def get_full_status(self) -> LatexEnvironmentStatus:
        """Retourne un diagnostic complet de l'environnement LaTeX."""
        latex = self.detect_latex_binary()
        dvisvgm = self.detect_dvisvgm_binary()
        dvipng = self.detect_dvipng_binary()

        is_fully = bool(latex and dvisvgm)

        if is_fully:
            parts = []
            if latex:
                parts.append(f"latex ({latex.version or 'version inconnue'})")
            if dvisvgm:
                parts.append(f"dvisvgm ({dvisvgm.version or 'version inconnue'})")
            if dvipng:
                parts.append(f"dvipng ({dvipng.version or 'version inconnue'})")
            message = "Environnement LaTeX détecté : " + ", ".join(parts)
        elif latex and not dvisvgm:
            message = "latex détecté mais dvisvgm introuvable — compilation SVG impossible"
        elif dvisvgm and not latex:
            message = "dvisvgm détecté mais latex introuvable — compilation impossible"
        else:
            message = "Aucun compilateur LaTeX détecté — installez MacTeX/TeX Live/MiKTeX"

        return LatexEnvironmentStatus(
            latex=latex,
            dvisvgm=dvisvgm,
            dvipng=dvipng,
            is_fully_available=is_fully,
            message=message,
        )

    def clear_cache(self) -> None:
        """Vide le cache de détection pour forcer une nouvelle recherche."""
        self._cache.clear()

    def get_custom_paths_from_settings(self) -> dict[str, str]:
        """Récupère les chemins personnalisés depuis les paramètres utilisateur."""
        from ankidraft.services.settings_service import SettingsService

        return {
            "latex": SettingsService.get("latex/binary_path", ""),
            "dvisvgm": SettingsService.get("latex/dvisvgm_path", ""),
            "dvipng": SettingsService.get("latex/dvipng_path", ""),
        }

    def validate_custom_paths(self, paths: dict[str, str]) -> dict[str, bool]:
        """Valide que les chemins personnalisés pointent vers des exécutables valides."""
        results = {}
        for name, path in paths.items():
            if not path:
                results[name] = False
                continue
            p = Path(path)
            if sys.platform == "win32" and not p.suffix:
                p = p.with_suffix(".exe")
            results[name] = p.exists() and p.is_file()
        return results
