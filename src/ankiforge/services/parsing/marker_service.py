"""Installation et résolution du moteur Marker OCR hors du binaire Nuitka."""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess  # nosec B404
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ankiforge.utils.paths import get_tools_search_dirs

logger = logging.getLogger(__name__)


def _detect_torch_device() -> str | None:
    """Tente de détecter un accélérateur via PyTorch si le module est présent."""
    try:
        import sys

        torch_mod = sys.modules.get("torch")
        if torch_mod is None:
            import importlib

            torch_mod = importlib.import_module("torch")

        cuda_mod = getattr(torch_mod, "cuda", None)
        if cuda_mod is not None and callable(getattr(cuda_mod, "is_available", None)) and cuda_mod.is_available():
            return "cuda"
        backends = getattr(torch_mod, "backends", None)
        mps_mod = getattr(backends, "mps", None) if backends is not None else None
        if mps_mod is not None and callable(getattr(mps_mod, "is_available", None)) and mps_mod.is_available():
            return "mps"
    except (ImportError, Exception):
        pass
    return None


def detect_default_device() -> str:
    """Détecte le périphérique d'accélération matérielle par défaut (mps, cuda ou cpu)."""
    torch_device = _detect_torch_device()
    if torch_device is not None:
        return torch_device

    # Détection déterministe selon la plateforme et le matériel hôte pour le sous-processus
    if platform.system() == "Darwin" and platform.machine() in ("arm64", "aarch64"):
        return "mps"
    if shutil.which("nvidia-smi") is not None:
        return "cuda"
    return "cpu"


@dataclass(frozen=True)
class MarkerOptions:
    """Options d'extraction et configuration d'exécution de Marker OCR."""

    page_range: str | None = None
    force_ocr: bool = False
    disable_ocr: bool = False
    strip_existing_ocr: bool = False
    disable_ocr_math: bool = False
    extract_images: bool = True
    filter_blank_pages: bool = False
    highres_image_dpi: int = 192
    lowres_image_dpi: int = 96
    pdftext_workers: int = 1
    debug: bool = False
    device: str | None = None
    extra_cli_args: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Valide les options et interdit formellement les options LLM non supervisées."""
        for arg in self.extra_cli_args:
            if arg == "--use_llm" or arg.startswith("--use_llm"):
                raise ValueError("L'option '--use_llm' est strictement interdite dans MarkerOptions. L'enrichissement IA relève exclusivement des pipelines supervisés d'AnkiForge.")
        if self.force_ocr and self.disable_ocr:
            raise ValueError("Les options 'force_ocr' et 'disable_ocr' sont mutuellement exclusives.")

    @staticmethod
    def detect_default_device() -> str:
        """Détecte le périphérique d'exécution par défaut (délégation vers detect_default_device)."""
        return detect_default_device()

    def to_cli_args(self, output_dir: Path) -> list[str]:
        """Génère la liste ordonnée d'arguments CLI pour marker_single."""
        args: list[str] = [
            "--output_dir",
            str(output_dir),
            "--paginate_output",
        ]

        if self.page_range:
            args.extend(["--page_range", self.page_range])
        if self.force_ocr:
            args.append("--force_ocr")
        if self.disable_ocr:
            args.append("--disable_ocr")
        if self.strip_existing_ocr:
            args.append("--strip_existing_ocr")
        if self.disable_ocr_math:
            args.append("--disable_ocr_math")
        if self.extract_images:
            args.append("--extract_images")
        if self.filter_blank_pages:
            args.append("--filter_blank_pages")
        if self.highres_image_dpi != 192:
            args.extend(["--highres_image_dpi", str(self.highres_image_dpi)])
        if self.lowres_image_dpi != 96:
            args.extend(["--lowres_image_dpi", str(self.lowres_image_dpi)])
        if self.pdftext_workers != 1:
            args.extend(["--pdftext_workers", str(self.pdftext_workers)])
        if self.debug:
            args.append("--debug")

        if self.extra_cli_args:
            for arg in self.extra_cli_args:
                if arg == "--use_llm" or arg.startswith("--use_llm"):
                    raise ValueError("L'option '--use_llm' est strictement interdite.")
            args.extend(self.extra_cli_args)

        return args

    def get_process_env(self, base_env: dict[str, str] | None = None) -> dict[str, str]:
        """Retourne l'environnement du sous-processus injectant la consigne matérielle TORCH_DEVICE."""
        env = dict(os.environ if base_env is None else base_env)
        target_device = self.device if self.device is not None else self.detect_default_device()
        env["TORCH_DEVICE"] = target_device
        return env

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> MarkerOptions:
        """Instancie MarkerOptions en lisant les surcharges des variables ANKIFORGE_MARKER_*."""
        source = os.environ if env is None else env

        def _bool_val(key: str, default: bool) -> bool:
            if key not in source:
                return default
            return source[key].strip().lower() in ("1", "true", "yes", "on")

        def _int_val(key: str, default: int) -> int:
            if key not in source:
                return default
            try:
                return int(source[key].strip())
            except ValueError:
                return default

        page_range = source.get("ANKIFORGE_MARKER_PAGE_RANGE") or None
        device = source.get("ANKIFORGE_MARKER_DEVICE") or None

        return cls(
            page_range=page_range,
            force_ocr=_bool_val("ANKIFORGE_MARKER_FORCE_OCR", False),
            disable_ocr=_bool_val("ANKIFORGE_MARKER_DISABLE_OCR", False),
            strip_existing_ocr=_bool_val("ANKIFORGE_MARKER_STRIP_EXISTING_OCR", False),
            disable_ocr_math=_bool_val("ANKIFORGE_MARKER_DISABLE_OCR_MATH", False),
            extract_images=_bool_val("ANKIFORGE_MARKER_EXTRACT_IMAGES", True),
            filter_blank_pages=_bool_val("ANKIFORGE_MARKER_FILTER_BLANK_PAGES", False),
            highres_image_dpi=_int_val("ANKIFORGE_MARKER_HIGHRES_IMAGE_DPI", 192),
            lowres_image_dpi=_int_val("ANKIFORGE_MARKER_LOWRES_IMAGE_DPI", 96),
            pdftext_workers=_int_val("ANKIFORGE_MARKER_PDFTEXT_WORKERS", 1),
            debug=_bool_val("ANKIFORGE_MARKER_DEBUG", False),
            device=device,
        )


class MarkerService:
    """Gère Marker dans un environnement Python persistant séparé de Nuitka."""

    PACKAGE_NAME = "marker-pdf>=1.8.0,<2.0.0"
    MIN_PYTHON_VERSION = (3, 10)
    MAX_PYTHON_VERSION = (3, 14)  # Exclusif : 3.10, 3.11, 3.12, 3.13 supportés
    ESTIMATED_DISK_SPACE_BYTES = 5 * 1024 * 1024 * 1024  # ~5.0 Go (dépendances PyTorch + modèles de vision)
    ESTIMATED_DOWNLOAD_BYTES = 2 * 1024 * 1024 * 1024  # ~2.0 Go
    MIN_FREE_SPACE_BYTES = 4 * 1024 * 1024 * 1024  # ~4.0 Go d'espace minimum recommandé
    ESTIMATED_DURATION_MINUTES = (3, 8)

    @classmethod
    def get_installation_target_dir(cls) -> Path:
        """Retourne le répertoire cible pour l'installation de Marker."""
        return get_tools_search_dirs()[0] / "marker"

    @classmethod
    def get_available_disk_space(cls, target_dir: Path | None = None) -> int:
        """Retourne l'espace disque disponible (en octets) sur le volume contenant le dossier cible."""
        path = (target_dir or cls.get_installation_target_dir()).resolve()
        while not path.exists() and path.parent != path:
            path = path.parent
        try:
            usage = shutil.disk_usage(path)
            return int(getattr(usage, "free", usage[2]))
        except (OSError, IndexError, AttributeError) as err:
            logger.warning("Impossible de mesurer l'espace disque disponible sur %s : %s", path, err)
            return 0

    @classmethod
    def has_sufficient_disk_space(cls, required_bytes: int | None = None, target_dir: Path | None = None) -> bool:
        """Indique si le volume cible dispose d'un espace libre suffisant pour installer Marker."""
        threshold = required_bytes if required_bytes is not None else cls.MIN_FREE_SPACE_BYTES
        return cls.get_available_disk_space(target_dir) >= threshold

    @classmethod
    def format_bytes(cls, size_bytes: int | float) -> str:
        """Formate une taille en octets en chaîne lisible (Go / Mo)."""
        gb = size_bytes / (1024 * 1024 * 1024)
        if gb >= 1.0:
            return f"{gb:.1f} Go"
        mb = size_bytes / (1024 * 1024)
        return f"{mb:.0f} Mo"

    @classmethod
    def purge_installation(cls) -> None:
        """Supprime complètement l'environnement Marker existant."""
        for tools_dir in get_tools_search_dirs():
            marker_dir = tools_dir / "marker"
            if marker_dir.exists():
                logger.info("Purge de l'environnement Marker : %s", marker_dir)
                shutil.rmtree(marker_dir, ignore_errors=True)

    @classmethod
    def install(cls, progress_callback: Callable[[str], None] | None = None) -> Path:
        """Crée un venv persistant et installe marker-pdf avec pip ou uv."""
        python = cls._find_python()
        install_dir = cls.get_installation_target_dir()
        venv_dir = install_dir / "venv"
        install_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Démarrage de l'installation de Marker OCR dans %s via Python %s", venv_dir, python)

        # Si le venv existe déjà mais n'est pas basé sur une version de Python compatible, on le purge
        if venv_dir.exists() and not cls._is_venv_compatible(venv_dir):
            if progress_callback:
                progress_callback("Environnement Marker incompatible ou obsolète détecté. Réinitialisation...")
            logger.info("Purge de l'environnement Marker obsolète : %s", venv_dir)
            shutil.rmtree(venv_dir, ignore_errors=True)

        try:
            if not cls._is_venv_compatible(venv_dir):
                if progress_callback:
                    progress_callback("Création de l'environnement Marker OCR (Python compatible)...")
                logger.info("Création de l'environnement virtuel pour Marker OCR : %s", venv_dir)
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
            logger.info("Installation du paquet %s dans %s", cls.PACKAGE_NAME, venv_dir)

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
            logger.info("Installation de Marker OCR réussie avec succès : %s", executable)
            return executable
        except Exception:
            logger.exception("Échec de l'installation de Marker OCR. Nettoyage de l'environnement incomplet...")
            if venv_dir.exists():
                shutil.rmtree(venv_dir, ignore_errors=True)
            raise

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
                )  # argv fixe [python, -c, code métier constant], jamais de shell
                if res.returncode != 0:
                    return False
            except Exception as err:
                logger.debug("Vérification de la version marker-pdf ignorée : %s", err)
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
            )  # argv fixe [python, -c, code métier constant], jamais de shell
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
                )  # argv fixe [uv, python, find, spec], exécutable localisé/validé, pas de shell
                if res.returncode == 0:
                    found = res.stdout.strip()
                    if found and cls._is_python_compatible(found):
                        return found
            except Exception as err:
                logger.debug("Découverte de l'interpréteur Python via uv ignorée : %s", err)

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
        )  # argv construit en interne (liste fixe, jamais shell), exécutables résolus par _find_uv/_find_python
        if process.stdout is not None:
            for line in process.stdout:
                if progress_callback and line.strip():
                    progress_callback(line.strip())
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"Commande d'installation échouée (code {return_code}) : {' '.join(command[:4])}")
