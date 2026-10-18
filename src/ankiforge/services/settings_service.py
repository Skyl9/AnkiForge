"""Service de Gestion des Paramètres et Préférences Utilisateur pour AnkiForge.

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
        """Récupère la valeur d'un paramètre depuis la BDD Peewee (avec repli sur QSettings si non défini)."""
        try:
            val = SettingModel.get_value(key, default=None)
            if val is not None:
                return val
        except Exception as e:
            logger.debug("Lecture SettingModel '%s' échouée: %s", key, e)

        try:
            q_settings = get_app_qsettings()
            if q_settings.contains(key):
                return q_settings.value(key, default)
        except Exception as q_err:
            logger.debug("Lecture QSettings fallback pour '%s' échouée: %s", key, q_err)

        return default

    @staticmethod
    def set(key: str, value: Any, category: str = "general", sync_qsettings: bool = True) -> None:
        """Enregistre un paramètre en BDD Peewee et synchronise optionnellement QSettings.

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

    @staticmethod
    def delete(key: str, sync_qsettings: bool = True) -> bool:
        """Supprime un paramètre de la BDD Peewee et synchronise optionnellement QSettings."""
        deleted = False
        try:
            deleted = SettingModel.delete_value(key)
            if deleted:
                logger.debug("Paramètre '%s' supprimé de la BDD", key)
        except Exception as e:
            logger.debug("Suppression SettingModel '%s' échouée: %s", key, e)

        if sync_qsettings:
            try:
                q_settings = get_app_qsettings()
                if q_settings.contains(key):
                    q_settings.remove(key)
            except Exception as q_err:
                logger.debug("Suppression QSettings '%s' échouée: %s", key, q_err)

        return deleted

    @classmethod
    def get_shortcut_override(cls, shortcut_id: str) -> str | None:
        """Récupère la séquence surchargée pour un identifiant d'action, ou None si non surchargé."""
        val = cls.get(f"shortcuts/{shortcut_id}", default=None, category="shortcuts")
        if isinstance(val, str) and val.strip():
            return val.strip()
        return None

    @classmethod
    def set_shortcut_override(cls, shortcut_id: str, sequence: str, default_sequence: str | None = None) -> None:
        """Enregistre une surcharge de raccourci.

        Conformément à la spécification, aucune écriture n'est effectuée si la valeur
        est égale à la valeur par défaut ; dans ce cas, toute surcharge existante est supprimée.
        """
        key = f"shortcuts/{shortcut_id}"
        seq_clean = sequence.strip()
        if default_sequence is not None and seq_clean.upper() == default_sequence.strip().upper():
            cls.remove_shortcut_override(shortcut_id)
            return

        cls.set(key, seq_clean, category="shortcuts")

    @classmethod
    def remove_shortcut_override(cls, shortcut_id: str) -> None:
        """Supprime la surcharge d'un raccourci pour restaurer son comportement d'usine."""
        cls.delete(f"shortcuts/{shortcut_id}")

    @classmethod
    def get_all_shortcut_overrides(cls) -> dict[str, str]:
        """Récupère l'ensemble des surcharges de raccourcis définies."""
        raw = cls.get_category("shortcuts")
        prefix = "shortcuts/"
        overrides: dict[str, str] = {}
        for k, v in raw.items():
            sc_id = k[len(prefix) :] if k.startswith(prefix) else k
            if isinstance(v, str) and v.strip():
                overrides[sc_id] = v.strip()
        return overrides

    @classmethod
    def clear_all_shortcut_overrides(cls) -> None:
        """Supprime l'intégralité des surcharges de raccourcis configurées."""
        try:
            SettingModel.delete_category("shortcuts")
            logger.info("Toutes les surcharges de raccourcis ont été réinitialisées en BDD")
        except Exception as e:
            logger.debug("Suppression catégorie shortcuts échouée: %s", e)

        try:
            q_settings = get_app_qsettings()
            for key in list(q_settings.allKeys()):
                if key.startswith("shortcuts/"):
                    q_settings.remove(key)
        except Exception as q_err:
            logger.debug("Nettoyage QSettings shortcuts échoué: %s", q_err)
