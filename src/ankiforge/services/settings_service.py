"""
Service de Gestion des Paramètres et Préférences Utilisateur pour AnkiForge.
Persiste les réglages dans la BDD SQLite du profil via Peewee (SettingModel),
avec synchronisation transparente et fallback sur QSettings.
"""

import logging
from typing import Any

from ankiforge.database.models import SettingModel
from ankiforge.utils.environment import get_app_qsettings

logger = logging.getLogger(__name__)

_MISSING = object()


def values_equal(a: Any, b: Any) -> bool:
    """Compare deux valeurs en exigeant le même type (évite les faux positifs bool/int)."""
    if type(a) is not type(b):
        return False
    return a == b


class SettingsService:
    """Service d'accès et de persistance des préférences utilisateur par profil."""

    @staticmethod
    def get(key: str, default: Any = None, category: str | None = None) -> Any:
        """
        Récupère la valeur d'un paramètre depuis la BDD Peewee (avec repli sur QSettings si non défini).
        """
        try:
            val = SettingModel.get_value(key, default=None)
            if val is not None:
                return val
        except Exception as e:
            logger.debug("Lecture SettingModel '%s' échouée: %s", key, e)

        # Fallback sur QSettings
        try:
            q_settings = get_app_qsettings()
            if q_settings.contains(key):
                return q_settings.value(key, default)
        except Exception as q_err:
            logger.debug("Lecture QSettings fallback pour '%s' échouée: %s", key, q_err)

        return default

    @staticmethod
    def set(key: str, value: Any, category: str = "general", sync_qsettings: bool = True) -> None:
        """
        Enregistre un paramètre en BDD Peewee et synchronise optionnellement QSettings.

        Si la valeur est déjà identique en BDD, aucune écriture (BDD ou QSettings)
        n'est effectuée : on évite des UPDATEs inutiles et coûteux.
        """
        try:
            current = SettingModel.get_value(key, _MISSING)
            if current is not _MISSING and values_equal(current, value):
                return
            SettingModel.set_value(key, value, category=category)
            logger.debug("Paramètre '%s' mis à jour en BDD (catégorie: '%s')", key, category)
        except Exception as e:
            logger.warning("Écriture SettingModel '%s' échouée: %s", key, e)

        if sync_qsettings:
            try:
                q_settings = get_app_qsettings()
                if not values_equal(q_settings.value(key, _MISSING), value):
                    q_settings.setValue(key, value)
            except Exception as e:
                logger.debug("Synchronisation QSettings '%s' échouée: %s", key, e)

    @staticmethod
    def get_category(category: str) -> dict[str, Any]:
        """Récupère l'ensemble des paramètres d'une catégorie."""
        try:
            return SettingModel.get_category(category)
        except Exception as e:
            logger.debug("get_category '%s' échoué: %s", category, e)
            return {}

    @staticmethod
    def set_batch(settings_dict: dict[str, Any], category: str = "general") -> None:
        """Enregistre un lot de paramètres de manière atomique en BDD."""
        try:
            SettingModel.set_many(settings_dict, category=category)
            logger.info("Enregistrement par lot de %d paramètres (catégorie: '%s')", len(settings_dict), category)
        except Exception as e:
            logger.warning("set_batch échoué pour la catégorie '%s': %s", category, e)

        try:
            q_settings = get_app_qsettings()
            for k, v in settings_dict.items():
                q_settings.setValue(k, v)
        except Exception as q_err:
            logger.debug("Synchronisation QSettings en lot échouée: %s", q_err)
