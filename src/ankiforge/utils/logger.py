import logging
import sys
from logging.handlers import RotatingFileHandler

from ankiforge.utils.paths import get_app_data_dir


def setup_logging(level=logging.INFO):
    """
    Configure le système de log global pour AnkiForge.
    Branche un flux vers la console et un flux vers un fichier rotatif.
    """
    # 1. Définir l'emplacement du fichier de log
    log_dir = get_app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "ankiforge.log"

    # 2. Définir le format des messages (Standard industriel)
    # [Date] [Niveau] [Nom du fichier] : Message
    log_format = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    # 3. Handler pour la Console (pour vous en développement)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    console_handler.setLevel(logging.DEBUG)  # La console montre tout

    # 4. Handler pour le Fichier (pour la production / support utilisateur)
    # On garde 5 fichiers de 5 Mo chacun (rotation)
    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(log_format)
    file_handler.setLevel(logging.INFO)  # Le fichier ne stocke que l'important

    # 5. Configuration du Root Logger (le parent de tous les loggers)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # On nettoie les handlers existants pour éviter les doublons au redémarrage
    root_logger.handlers = []
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    logging.info("--- Démarrage de la session AnkiForge ---")
    logging.info(f"Fichier de log : {log_file}")
