"""Service de gestion et de personnalisation des drapeaux Anki par profil.

Permet d'associer un libellé métier personnalisé à chaque couleur de drapeau (1 à 7)
et maintient la compatibilité avec les valeurs numériques Anki.
"""

from __future__ import annotations

import logging
from typing import Any

from peewee import DoesNotExist

from ankiforge.database.models import FlagDefinitionModel, ProfileFlagLabelModel
from ankiforge.services.settings_service import SettingsService
from ankiforge.utils.event_bus import FlagLabelsUpdatedEvent, event_bus
from ankiforge.utils.paths import get_active_profile

logger = logging.getLogger(__name__)

SETTINGS_KEY = "anki/flag_labels"
SETTINGS_CATEGORY = "anki"

# Couleurs natives Anki (inchangées, figées par le format Anki)
NATIVE_FLAG_COLORS: dict[int, str] = {
    0: "transparent",
    1: "#ef4444",
    2: "#f97316",
    3: "#10b981",
    4: "#3b82f6",
    5: "#ec4899",
    6: "#06b6d4",
    7: "#a855f7",
}

# Noms natifs Anki (français) pour fallback
NATIVE_FLAG_NAMES: dict[int, str] = {
    0: "Aucun",
    1: "Rouge",
    2: "Orange",
    3: "Vert",
    4: "Bleu",
    5: "Rose",
    6: "Turquoise",
    7: "Violet",
}

# Alias de recherche par défaut (inchangés)
DEFAULT_FLAG_SEARCH_MAP: dict[str, int] = {
    "0": 0,
    "none": 0,
    "aucun": 0,
    "1": 1,
    "red": 1,
    "rouge": 1,
    "2": 2,
    "orange": 2,
    "3": 3,
    "green": 3,
    "vert": 3,
    "4": 4,
    "blue": 4,
    "bleu": 4,
    "5": 5,
    "pink": 5,
    "rose": 5,
    "6": 6,
    "turquoise": 6,
    "cyan": 6,
    "7": 7,
    "purple": 7,
    "violet": 7,
}


class FlagService:
    """Service de consultation et de persistance des libellés de drapeaux Anki."""

    _cached_labels: dict[int, str] | None = None
    _cached_colors: dict[int, str] | None = None
    _cached_search_map: dict[str, int] | None = None

    @classmethod
    def _invalidate_cache(cls) -> None:
        """Invalide le cache mémoire des libellés, couleurs et map de recherche."""
        cls._cached_labels = None
        cls._cached_colors = None
        cls._cached_search_map = None
        # Rafraîchir aussi les DesignTokens pour l'UI
        try:
            from ankiforge.ui.theme import DesignTokens

            DesignTokens.refresh_flag_tokens()
        except Exception as e:
            logger.debug("Impossible de rafraîchir DesignTokens : %s", e)

    @classmethod
    def _get_active_profile_name(cls) -> str | None:
        """Retourne le nom du profil actif."""
        try:
            return get_active_profile()
        except Exception as e:
            logger.debug("Impossible de récupérer le profil actif : %s", e)
            return None

    @classmethod
    def _load_native_definitions(cls) -> dict[int, dict[str, Any]]:
        """Charge les définitions natives depuis la BDD ou fallback vers constantes."""
        definitions: dict[int, dict[str, Any]] = {}
        try:
            for fd in FlagDefinitionModel.select():
                definitions[fd.value] = {
                    "name": fd.name,
                    "color_hex": fd.color_hex,
                    "is_customizable": fd.is_customizable,
                    "id": fd.id,
                }
        except Exception as e:
            logger.debug("Fallback vers définitions natives : %s", e)
            for idx in range(8):
                definitions[idx] = {
                    "name": NATIVE_FLAG_NAMES.get(idx, f"Drapeau {idx}"),
                    "color_hex": NATIVE_FLAG_COLORS.get(idx, "#000000"),
                    "is_customizable": idx > 0,
                    "id": idx,
                }
        return definitions

    @classmethod
    def _load_profile_overrides(cls, profile_name: str | None) -> dict[int, str]:
        """Charge les libellés personnalisés pour un profil donné."""
        overrides: dict[int, str] = {}
        if profile_name is None:
            return overrides
        try:
            for pfl in ProfileFlagLabelModel.select().where(ProfileFlagLabelModel.profile_name == profile_name):
                if pfl.custom_label and pfl.custom_label.strip():
                    overrides[pfl.flag_definition.value] = pfl.custom_label.strip()
        except Exception as e:
            logger.debug("Erreur chargement overrides profil %s : %s", profile_name, e)
        return overrides

    @classmethod
    def get_flag_labels(cls) -> dict[int, str]:
        """Renvoie la table complète des 8 libellés (0..7) pour le profil actif.

        Drapeau 0 correspond à 'Aucun'.
        Les drapeaux 1..7 utilisent le libellé personnalisé s'il existe et est non vide,
        ou le nom natif de FlagDefinitionModel sinon.
        """
        if cls._cached_labels is not None:
            return dict(cls._cached_labels)

        profile_name = cls._get_active_profile_name()
        definitions = cls._load_native_definitions()
        overrides = cls._load_profile_overrides(profile_name)

        labels: dict[int, str] = {}
        for idx in range(8):
            if idx in overrides:
                labels[idx] = overrides[idx]
            else:
                labels[idx] = definitions.get(idx, {}).get("name", NATIVE_FLAG_NAMES.get(idx, f"Drapeau {idx}"))

        cls._cached_labels = dict(labels)
        return labels

    @classmethod
    def get_flag_colors(cls) -> dict[int, str]:
        """Renvoie la table complète des 8 couleurs (0..7) pour le profil actif."""
        if cls._cached_colors is not None:
            return dict(cls._cached_colors)

        definitions = cls._load_native_definitions()
        colors: dict[int, str] = {}
        for idx in range(8):
            colors[idx] = definitions.get(idx, {}).get("color_hex", NATIVE_FLAG_COLORS.get(idx, "#000000"))

        cls._cached_colors = dict(colors)
        return colors

    @classmethod
    def get_flag_name(cls, flag_idx: int) -> str:
        """Renvoie le libellé résolu d'un drapeau donné."""
        if flag_idx not in range(8):
            return "Aucun"
        labels = cls.get_flag_labels()
        return labels.get(flag_idx, "Aucun")

    @classmethod
    def get_flag_color(cls, flag_idx: int) -> str:
        """Renvoie la couleur hexadécimale d'un drapeau donné."""
        if flag_idx not in range(8):
            return "transparent"
        colors = cls.get_flag_colors()
        return colors.get(flag_idx, "transparent")

    @classmethod
    def get_flag_definition(cls, flag_idx: int) -> dict[str, Any] | None:
        """Renvoie la définition complète (id, name, color_hex, is_customizable) d'un drapeau."""
        if flag_idx not in range(8):
            return None
        definitions = cls._load_native_definitions()
        return definitions.get(flag_idx)

    @classmethod
    def set_flag_labels(cls, labels: dict[int, str]) -> None:
        """Enregistre les libellés personnalisés pour le profil actif et émet FlagLabelsUpdatedEvent.

        Seuls les drapeaux 1..7 sont modifiables. Une chaîne vide réinitialise le drapeau au nom natif.
        """
        profile_name = cls._get_active_profile_name()
        if profile_name is None:
            logger.warning("Impossible de définir les libellés : aucun profil actif")
            return

        # Lire les définitions natives pour connaître les noms par défaut
        definitions = cls._load_native_definitions()

        for flag_value, custom_label in labels.items():
            if flag_value not in range(1, 8):
                continue

            val = custom_label.strip() if isinstance(custom_label, str) else ""
            default_name = definitions.get(flag_value, {}).get("name", NATIVE_FLAG_NAMES.get(flag_value, ""))

            try:
                flag_def = FlagDefinitionModel.get(FlagDefinitionModel.value == flag_value)
            except DoesNotExist:
                logger.warning("Définition de drapeau introuvable pour la valeur %s", flag_value)
                continue

            if not val or val == default_name:
                # Supprimer l'override → revenir au natif
                ProfileFlagLabelModel.delete().where((ProfileFlagLabelModel.profile_name == profile_name) & (ProfileFlagLabelModel.flag_definition == flag_def)).execute()
            else:
                # Upsert l'override
                ProfileFlagLabelModel.insert(
                    profile_name=profile_name,
                    flag_definition=flag_def,
                    custom_label=val,
                ).on_conflict(
                    conflict_target=[ProfileFlagLabelModel.profile_name, ProfileFlagLabelModel.flag_definition],
                    preserve=[ProfileFlagLabelModel.custom_label],
                ).execute()

        logger.info("Libellés de drapeaux mis à jour pour le profil %s : %s", profile_name, labels)

        cls._invalidate_cache()
        resolved = cls.get_flag_labels()
        event_bus.publish(FlagLabelsUpdatedEvent(labels=resolved))

    @classmethod
    def reset_to_defaults(cls) -> None:
        """Réinitialise tous les drapeaux aux libellés natifs pour le profil actif."""
        profile_name = cls._get_active_profile_name()
        if profile_name is None:
            return

        ProfileFlagLabelModel.delete().where(ProfileFlagLabelModel.profile_name == profile_name).execute()

        cls._invalidate_cache()
        resolved = cls.get_flag_labels()
        event_bus.publish(FlagLabelsUpdatedEvent(labels=resolved))

    @classmethod
    def get_flag_search_map(cls) -> dict[str, int]:
        """Renvoie la table de correspondance complète pour la recherche de drapeaux.

        Combinant les alias par défaut (DEFAULT_FLAG_SEARCH_MAP) et les libellés personnalisés en minuscules.
        """
        if cls._cached_search_map is not None:
            return dict(cls._cached_search_map)

        search_map = dict(DEFAULT_FLAG_SEARCH_MAP)
        labels = cls.get_flag_labels()

        for idx in range(1, 8):
            label = labels.get(idx, "").strip().lower()
            if label:
                search_map[label] = idx
                if " " in label:
                    search_map[label.replace(" ", "_")] = idx
                    search_map[label.replace(" ", "-")] = idx

        cls._cached_search_map = dict(search_map)
        return search_map

    @classmethod
    def migrate_legacy_settings(cls) -> int:
        """Migre les libellés personnalisés depuis SettingsService (JSON) vers ProfileFlagLabelModel.

        Retourne le nombre de libellés migrés.
        """
        profile_name = cls._get_active_profile_name()
        if profile_name is None:
            return 0

        try:
            raw = SettingsService.get(SETTINGS_KEY, default={})
            if not isinstance(raw, dict) or not raw:
                return 0
        except Exception as e:
            logger.debug("Aucun paramètre legacy à migrer : %s", e)
            return 0

        migrated = 0
        definitions = cls._load_native_definitions()

        for flag_str, custom_label in raw.items():
            try:
                flag_value = int(flag_str)
            except (ValueError, TypeError):
                continue

            if flag_value not in range(1, 8):
                continue

            val = custom_label.strip() if isinstance(custom_label, str) else ""
            if not val:
                continue

            default_name = definitions.get(flag_value, {}).get("name", NATIVE_FLAG_NAMES.get(flag_value, ""))
            if val == default_name:
                continue

            try:
                flag_def = FlagDefinitionModel.get(FlagDefinitionModel.value == flag_value)
            except DoesNotExist:
                continue

            ProfileFlagLabelModel.insert(
                profile_name=profile_name,
                flag_definition=flag_def,
                custom_label=val,
            ).on_conflict(
                conflict_target=[ProfileFlagLabelModel.profile_name, ProfileFlagLabelModel.flag_definition],
                preserve=[ProfileFlagLabelModel.custom_label],
            ).execute()
            migrated += 1

        if migrated > 0:
            logger.info("Migration legacy : %d libellés de drapeaux migrés pour le profil %s", migrated, profile_name)
            # Nettoyer l'ancien paramètre
            SettingsService.set(SETTINGS_KEY, {}, category=SETTINGS_CATEGORY)
            cls._invalidate_cache()
            resolved = cls.get_flag_labels()
            event_bus.publish(FlagLabelsUpdatedEvent(labels=resolved))

        return migrated
