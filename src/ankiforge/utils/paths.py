import logging
import os
import sys
from pathlib import Path

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
    Retourne le chemin vers le dossier de données persistant de l'application selon l'environnement actif :
    - Production : ~/.ankiforge (ou ANKIFORGE_DATA_DIR)
    - Développement : ~/.ankiforge-dev (ou ANKIFORGE_DATA_DIR)
    - Test : ~/.ankiforge-test (ou ANKIFORGE_DATA_DIR)

    Garantit que le dossier existe sur le disque avant de le retourner.
    Conforme à la règle 9 de GEMINI.md.

    Returns:
        Path: Objet Path représentant le dossier de données.
    """
    custom_dir = os.environ.get("ANKIFORGE_DATA_DIR")
    if custom_dir:
        app_dir = Path(custom_dir)
    else:
        from ankiforge.utils.environment import AppEnvironment, get_current_environment

        env = get_current_environment()
        if env == AppEnvironment.DEVELOPMENT:
            app_dir = Path.home() / ".ankiforge-dev"
        elif env == AppEnvironment.TESTING:
            app_dir = Path.home() / ".ankiforge-test"
        else:
            app_dir = Path.home() / ".ankiforge"

    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_tools_search_dirs() -> list[Path]:
    """
    Retourne la liste ordonnée des répertoires de recherche d'outils et modèles d'IA déportés (Piper TTS, Kokoro, Marker).
    En mode développement, cherche d'abord dans ~/.ankiforge-dev/tools, puis en repli dans ~/.ankiforge/tools
    pour éviter d'avoir à re-télécharger les modèles volumineux (300 Mo+).
    En mode test, on n'ajoute pas le repli ~/.ankiforge/tools afin de garantir l'isolation des tests.
    """
    from ankiforge.utils.environment import is_testing

    current_tools = get_app_data_dir() / "tools"
    dirs = [current_tools]
    if not is_testing():
        prod_tools = Path.home() / ".ankiforge" / "tools"
        if prod_tools != current_tools:
            dirs.append(prod_tools)
    return dirs


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


def resolve_media_path(filename: str, profile_name: str | None = None) -> Path:
    """
    Résout le chemin absolu d'un média physique de façon robuste et bidirectionnelle.
    1. Recherche directe dans le profil actif, le profil par défaut et le dossier global.
    2. En cas d'échec, interroge MediaModel pour résoudre les correspondances entre nom d'origine
       (ex: CM entier.pdf, _page_1.jpeg) et nom de stockage haché (ex: 33c6d32...pdf).
    3. Recherche en repli dans les dossiers médias des autres profils existants.
    """
    if not filename:
        return get_media_dir(profile_name) / "empty"

    # 1. Candidats standards immédiats
    candidates = [
        get_media_dir(profile_name) / filename,
        get_app_data_dir() / "profiles" / "default" / "media" / filename,
        get_app_data_dir() / "media" / filename,
    ]
    for p in candidates:
        if p.exists():
            return p

    # 2. Résolution bidirectionnelle via MediaModel (original_name <-> filename haché)
    resolved_alt_names: list[str] = []
    try:
        from ankiforge.database.models.cards import MediaModel

        # Cas A : filename fourni est le nom original, on cherche le filename haché
        media_by_orig = MediaModel.get_or_none(MediaModel.original_name == filename)
        if media_by_orig and media_by_orig.filename:
            resolved_alt_names.append(media_by_orig.filename)

        # Cas B : filename fourni est le nom haché, on cherche le nom original si stocké tel quel
        media_by_fn = MediaModel.get_or_none(MediaModel.filename == filename)
        if media_by_fn and media_by_fn.original_name:
            resolved_alt_names.append(media_by_fn.original_name)

        for alt_name in resolved_alt_names:
            for base_folder in (get_media_dir(profile_name), get_app_data_dir() / "profiles" / "default" / "media", get_app_data_dir() / "media"):
                alt_p = base_folder / alt_name
                if alt_p.exists():
                    return alt_p
    except Exception as err:
        logger.debug("Résolution via MediaModel impossible ou échouée pour '%s': %s", filename, err)

    # 3. Repli dans les dossiers médias des autres profils enregistrés
    try:
        profiles_dir = get_app_data_dir() / "profiles"
        if profiles_dir.exists():
            target_prof = profile_name if profile_name is not None else get_active_profile()
            for p_dir in profiles_dir.iterdir():
                if p_dir.is_dir() and p_dir.name not in (target_prof, "default"):
                    cand = p_dir / "media" / filename
                    if cand.exists():
                        return cand
                    for alt_name in resolved_alt_names:
                        cand_alt = p_dir / "media" / alt_name
                        if cand_alt.exists():
                            return cand_alt
    except Exception as err:
        logger.debug("Recherche de média inter-profils échouée: %s", err)

    return candidates[0]
