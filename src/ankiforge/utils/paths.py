import os
import sys
from pathlib import Path

import platformdirs

APP_NAME = "AnkiForge"

def get_project_root() -> str:
    """
        Cherche dynamiquement la racine du projet en remontant l'arborescence
        jusqu'à trouver 'pyproject.toml'.
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
    if getattr(sys, 'frozen', False):
        # 📦 MODE PRODUCTION (App empaquetée via PyInstaller/cx_Freeze)
        # Windows : C:\Users\<User>\AppData\Local\AnkiForge
        # macOS   : ~/Library/Application Support/AnkiForge
        # Linux   : ~/.local/share/AnkiForge
        app_dir = platformdirs.user_data_path(appname=APP_NAME, appauthor=False)
    else:
        # 🛠️ MODE DÉVELOPPEMENT
        # Crée un dossier .ankiforge proprement à la racine du projet
        app_dir = get_project_root() / ".ankiforge"

    # S'assure que le dossier existe avant de le renvoyer
    app_dir.mkdir(parents=True, exist_ok=True)

    return app_dir