import os
import sys
from pathlib import Path


def get_app_data_dir() -> str:
    """
    Retourne le chemin vers le dossier de données de l'application.
    Crée un dossier caché ~/.ankiforge dans le répertoire utilisateur si en mode app.
    """
    if getattr(sys, 'frozen', False):
        # PROD MOD
        app_dir = Path.home() / ".ankiforge"
    else:
        #  DEV MODE
        # On remonte à la racine du projet (src -> utils -> paths.py)
        app_dir = Path(__file__).resolve().parent.parent.parent.parent / ".ankiforge"

        # S'assure que le dossier de base existe
    app_dir.mkdir(parents=True, exist_ok=True)

    return str(app_dir)