"""Modèles Peewee des paramètres utilisateur."""

import datetime
import json
import logging
from typing import Any

from peewee import (
    CharField,
    DateTimeField,
    TextField,
)

from ankidraft.database.base import BaseModel, db

logger = logging.getLogger(__name__)


class SettingModel(BaseModel):
    """Stocke les paramètres et préférences utilisateur du profil en base de données SQLite.

    Fournit des méthodes utilitaires avec sérialisation/désérialisation JSON automatique.
    """

    key = CharField(unique=True, index=True)
    value = TextField()
    category = CharField(default="general", index=True)
    updated_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "settings"

    @classmethod
    def get_value(cls, key: str, default: Any = None) -> Any:
        """Récupère la valeur d'un paramètre avec conversion JSON si applicable."""
        try:
            record = cls.get_or_none(cls.key == key)
            if record is None:
                return default
            try:
                return json.loads(record.value)
            except (json.JSONDecodeError, TypeError):
                return record.value
        except Exception as e:
            logger.debug("Remarque sur la récupération du paramètre '%s': %s", key, e)
            return default

    @classmethod
    @db.atomic()
    def set_value(cls, key: str, value: Any, category: str = "general") -> "SettingModel":
        """Enregistre ou met à jour un paramètre en BDD.

        Si la valeur et la catégorie sont déjà identiques à celles persistées,
        aucune écriture n'est déclenchée (ni mise à jour de ``updated_at``).
        """
        value_str = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

        record = cls.get_or_none(cls.key == key)
        if record:
            if record.value == value_str and record.category == category:
                return record
            record.value = value_str
            record.category = category
            record.updated_at = datetime.datetime.now()
            record.save()
            return record
        else:
            return cls.create(
                key=key,
                value=value_str,
                category=category,
                updated_at=datetime.datetime.now(),
            )

    @classmethod
    def get_category(cls, category: str) -> dict[str, Any]:
        """Récupère tous les paramètres d'une catégorie donnée sous forme de dictionnaire."""
        results: dict[str, Any] = {}
        try:
            for record in cls.select().where(cls.category == category):
                try:
                    results[record.key] = json.loads(record.value)
                except (json.JSONDecodeError, TypeError):
                    results[record.key] = record.value
        except Exception as e:
            logger.debug("Remarque sur la récupération de la catégorie de paramètres '%s': %s", category, e)
        return results

    @classmethod
    @db.atomic()
    def set_many(cls, settings_dict: dict[str, Any], category: str = "general") -> None:
        """Enregistre un lot de paramètres dans une transaction atomique."""
        for k, v in settings_dict.items():
            cls.set_value(k, v, category=category)

    @classmethod
    @db.atomic()
    def delete_value(cls, key: str) -> bool:
        """Supprime un paramètre de la BDD."""
        try:
            deleted = cls.delete().where(cls.key == key).execute()
            return bool(deleted > 0)
        except Exception as e:
            logger.debug("Remarque sur la suppression du paramètre '%s': %s", key, e)
            return False

    @classmethod
    @db.atomic()
    def delete_category(cls, category: str) -> int:
        """Supprime tous les paramètres d'une catégorie."""
        try:
            deleted = cls.delete().where(cls.category == category).execute()
            return int(deleted)
        except Exception as e:
            logger.debug("Remarque sur la suppression de la catégorie '%s': %s", category, e)
            return 0
