import logging
from pathlib import Path
import sys

logger = logging.getLogger(__name__)

APP_NAME = "ankiforge"


def get_project_root() -> Path:
    """
    Localise dynamiquement la racine du projet ou du bundle sur le disque.
    Ne lève jamais d'exception pour garantir le démarrage en binaire autonome.

    Returns:
        Path: Chemin absolu vers la racine du projet ou du bundle.
    """
    # 1. PyInstaller
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)

    # 2. Nuitka standalone ou exécutable gelé
    if getattr(sys, "frozen", False) or "__compiled__" in globals() or "__compiled__" in sys.modules:
        exe_path = Path(sys.executable).resolve()
        return exe_path.parent

    # 3. Recherche de pyproject.toml en remontant l'arborescence (Mode Dev)
    try:
        current_path = Path(__file__).resolve().parent
        for parent in [current_path, *current_path.parents]:
            if (parent / "pyproject.toml").exists():
                return parent
    except Exception as e:
        logger.debug("Recherche de pyproject.toml échouée: %s", e)

    # 4. Fallback safe vers le répertoire parent du package
    try:
        return Path(__file__).resolve().parent.parent.parent
    except Exception as e:
        logger.debug("Fallback racine échoué: %s", e)
        return Path.cwd()


def get_resource_path(*subpaths: str) -> Path:
    """
    Localise un fichier de ressource (icône SVG, traduction .qm, prompt Jinja2, extension C)
    de manière robuste selon le mode d'exécution (Dev, Nuitka, PyInstaller, macOS App Bundle).

    Args:
        *subpaths: Segments du chemin relatif (ex: "src", "ressources", "icons", "logo.svg").

    Returns:
        Path: Le chemin absolu vers la ressource existante ou candidate.
    """
    rel = Path(*subpaths)
    candidates: list[Path] = []

    # 1. PyInstaller _MEIPASS
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
        candidates.append(base / rel)
        if rel.parts and rel.parts[0] == "src":
            candidates.append(base / Path(*rel.parts[1:]))

    # 2. Nuitka standalone ou exécutable gelé
    if getattr(sys, "frozen", False) or "__compiled__" in globals() or "__compiled__" in sys.modules:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / rel)
        if rel.parts and rel.parts[0] == "src":
            candidates.append(exe_dir / Path(*rel.parts[1:]))
        # macOS App Bundle : Contents/Resources
        resources_dir = exe_dir.parent / "Resources"
        candidates.append(resources_dir / rel)
        if rel.parts and rel.parts[0] == "src":
            candidates.append(resources_dir / Path(*rel.parts[1:]))

    # 3. Racine du projet (Mode Dev)
    try:
        root = get_project_root()
        candidates.append(root / rel)
        if rel.parts and rel.parts[0] == "src":
            candidates.append(root / Path(*rel.parts[1:]))
    except Exception as e:
        logger.debug("Résolution ressource racine impossible: %s", e)

    # 4. Relatif au module python ankiforge
    try:
        pkg_dir = Path(__file__).resolve().parent.parent  # src/ankiforge
        candidates.append(pkg_dir.parent / rel)  # src / ...
        candidates.append(pkg_dir / rel)  # src/ankiforge / ...
        if rel.parts and rel.parts[0] == "src":
            candidates.append(pkg_dir.parent / Path(*rel.parts[1:]))
            candidates.append(pkg_dir / Path(*rel.parts[1:]))
    except Exception as e:
        logger.debug("Résolution ressource package impossible: %s", e)

    # Renvoie la première candidate existante
    for c in candidates:
        if c.exists():
            return c

    # Fallback par défaut
    return candidates[0] if candidates else rel


def get_app_data_dir() -> Path:
    """
    Retourne le chemin vers le dossier de données persistant de l'application (~/.ankiforge).
    Garantit que le dossier existe sur le disque avant de le retourner.
    Conforme à la règle 9 de GEMINI.md.

    Returns:
        Path: Objet Path représentant le dossier de données.
    """
    app_dir = Path.home() / ".ankiforge"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


_active_profile = "default"


def get_active_profile() -> str:
    """Retourne le nom du profil actif."""
    return _active_profile


def set_active_profile(name: str) -> None:
    """Modifie le profil actif."""
    global _active_profile
    if _active_profile != name:
        logger.info("Basculement du profil actif vers : '%s'", name)
    _active_profile = name


def get_profile_dir(name: str) -> Path:
    """Retourne le chemin vers le dossier d'un profil spécifique."""
    profile_dir = get_app_data_dir() / "profiles" / name
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def get_media_dir(profile_name: str | None = None) -> Path:
    """Retourne le chemin vers le dossier des médias d'un profil."""
    target_prof = profile_name if profile_name is not None else get_active_profile()
    media_dir = get_profile_dir(target_prof) / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    return media_dir
