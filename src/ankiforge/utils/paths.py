import sys
from pathlib import Path

import platformdirs

APP_NAME = "ankiforge_obsidian"


def get_project_root() -> Path:
    """
    Localise dynamiquement la racine du projet sur le disque.

    Remonte l'arborescence depuis le fichier actuel jusqu'à trouver le fichier pyproject.toml.

    Returns:
        Path: Chemin absolu vers la racine du projet.

    Raises:
        RuntimeError: Si le projet n'est pas trouvé.
    """
    current_path = Path(__file__).resolve().parent

    # On remonte les dossiers un par un
    for parent in [current_path, *current_path.parents]:
        if (parent / "pyproject.toml").exists():
            return parent

    # Fallback si le fichier n'est pas trouvé (utile en cas de structure exotique)
    raise RuntimeError("Impossible de trouver la racine du projet (pyproject.toml manquant).")


def get_app_data_dir() -> Path:
    """
    Retourne le chemin vers le dossier de données de l'application selon l'environnement.

    Returns:
        Path: Objet Path représentant le dossier de données.
    """
    if getattr(sys, "frozen", False):
        # 📦 MODE PRODUCTION (App empaquetée via PyInstaller/cx_Freeze)
        # Windows : C:\Users\<User>\AppData\Local\ankiforge_obsidian
        # macOS   : ~/Library/Application Support/ankiforge_obsidian
        # Linux   : ~/.local/share/ankiforge_obsidian
        app_dir = platformdirs.user_data_path(appname=APP_NAME, appauthor=False)
    else:
        # 🛠️ MODE DÉVELOPPEMENT
        # Crée un dossier .ankiforge proprement à la racine du projet
        app_dir = get_project_root() / ".ankiforge"

    # S'assure que le dossier existe avant de le renvoyer
    app_dir.mkdir(parents=True, exist_ok=True)

    return app_dir


_active_profile = "default"


def get_active_profile() -> str:
    """Retourne le nom du profil actif."""
    return _active_profile


def set_active_profile(name: str) -> None:
    """Modifie le profil actif."""
    global _active_profile
    _active_profile = name


def get_profile_dir(name: str) -> Path:
    """Retourne le chemin vers le dossier d'un profil spécifique."""
    profile_dir = get_app_data_dir() / "profiles" / name
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def get_media_dir() -> Path:
    """Retourne le chemin vers le dossier media du profil actif."""
    media_dir = get_profile_dir(get_active_profile()) / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    return media_dir
