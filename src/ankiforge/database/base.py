# ruff: noqa: E501
import logging
import uuid
from typing import Any

from peewee import Model, SqliteDatabase

from ankiforge.utils.paths import get_app_data_dir

logger = logging.getLogger(__name__)

# Chemin par défaut de la base de données SQLite du profil
DEFAULT_DB_PATH = get_app_data_dir() / "ankiforge.db"
DB_PATH = DEFAULT_DB_PATH

# Base de données SQLite (initialisation différée possible pour le multi-profils)
db = SqliteDatabase(
    None,
    timeout=30,
    pragmas={
        "journal_mode": "wal",  # Permet la lecture et l'écriture simultanées
        "cache_size": -1024 * 64,  # Alloue 64MB de RAM pour accélérer les requêtes
        "foreign_keys": 1,  # Force le respect des clés étrangères (sécurité des suppressions en cascade)
        "synchronous": 1,  # Équilibre parfait entre sécurité en cas de crash et vitesse d'écriture
    },
)
db.init(str(DEFAULT_DB_PATH))


class BaseModel(Model):
    """Classe de base pour tous les modèles Peewee d'AnkiForge."""

    id: Any
    delete: Any

    class Meta:
        database = db


def generate_guid() -> str:
    """Génère un identifiant unique universel hexadécimal pour les notes."""
    return uuid.uuid4().hex


def init_db() -> None:
    """Initialise la connexion à la base de données active."""
    db.connect(reuse_if_open=True)
    logger.info("Connexion établie à la base de données SQLite : %s", db.database)
