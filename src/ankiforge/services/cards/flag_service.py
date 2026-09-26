"""
Service de gestion et de personnalisation des drapeaux Anki par profil.
Permet d'associer un libellé métier personnalisé à chaque couleur de drapeau (1 à 7)
et maintient la compatibilité avec les valeurs numériques Anki.
"""

from __future__ import annotations

import logging
from typing import Any

from ankiforge.services.settings_service import SettingsService
from ankiforge.utils.event_bus import FlagLabelsUpdatedEvent, event_bus

logger = logging.getLogger(__name__)

SETTINGS_KEY = "anki/flag_labels"
SETTINGS_CATEGORY = "anki"

DEFAULT_FLAG_NAMES: dict[int, str] = {
    0: "Aucun",
    1: "Rouge",
    2: "Orange",
    3: "Vert",
    4: "Bleu",
    5: "Rose",
    6: "Turquoise",
    7: "Violet",
}

DEFAULT_FLAG_COLORS: dict[int, str] = {
    0: "transparent",
    1: "#ef4444",
    2: "#f97316",
    3: "#10b981",
    4: "#3b82f6",
    5: "#ec4899",
    6: "#06b6d4",
    7: "#a855f7",
}

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

    @classmethod
    def _invalidate_cache(cls) -> None:
        """Invalide le cache mémoire des libellés."""
        cls._cached_labels = None

    @classmethod
    def get_flag_labels(cls) -> dict[int, str]:
        """
        Renvoie la table complète des 8 libellés (0..7) pour le profil actif.
        Drapeau 0 correspond à 'Aucun'.
        Les drapeaux 1..7 utilisent le libellé personnalisé s'il existe et est non vide,
        ou le nom par défaut de DEFAULT_FLAG_NAMES sinon.
        """
        if cls._cached_labels is not None:
            return dict(cls._cached_labels)

        custom: dict[str, Any] = {}
        try:
            raw = SettingsService.get(SETTINGS_KEY, default={})
            if isinstance(raw, dict):
                custom = raw
        except Exception as e:
            logger.debug("Remarque sur la lecture des libellés de drapeaux : %s", e)

        labels: dict[int, str] = {0: DEFAULT_FLAG_NAMES.get(0, "Aucun")}
        for idx in range(1, 8):
            custom_val = custom.get(str(idx))
            if isinstance(custom_val, str) and custom_val.strip():
                labels[idx] = custom_val.strip()
            else:
                labels[idx] = DEFAULT_FLAG_NAMES.get(idx, f"Drapeau {idx}")

        cls._cached_labels = dict(labels)
        return labels

    @classmethod
    def get_flag_name(cls, flag_idx: int) -> str:
        """Renvoie le libellé résolu d'un drapeau donné."""
        if flag_idx not in range(8):
            return "Aucun"
        labels = cls.get_flag_labels()
        return labels.get(flag_idx, "Aucun")

    @classmethod
    def set_flag_labels(cls, labels: dict[int, str]) -> None:
        """
        Enregistre les libellés personnalisés pour le profil actif et émet FlagLabelsUpdatedEvent.
        Seuls les drapeaux 1..7 sont modifiables. Une chaîne vide réinitialise le drapeau au nom par défaut.
        """
        current_saved: dict[str, str] = {}
        try:
            raw = SettingsService.get(SETTINGS_KEY, default={})
            if isinstance(raw, dict):
                current_saved = {str(k): str(v) for k, v in raw.items()}
        except Exception:
            current_saved = {}

        for k, v in labels.items():
            if k in range(1, 8):
                val = v.strip() if isinstance(v, str) else ""
                default_name = DEFAULT_FLAG_NAMES.get(k, "")
                if not val or val == default_name:
                    current_saved.pop(str(k), None)
                else:
                    current_saved[str(k)] = val

        SettingsService.set(SETTINGS_KEY, current_saved, category=SETTINGS_CATEGORY)
        logger.info("Libellés de drapeaux mis à jour : %s", current_saved)

        cls._invalidate_cache()
        resolved = cls.get_flag_labels()
        event_bus.publish(FlagLabelsUpdatedEvent(labels=resolved))

    @classmethod
    def reset_to_defaults(cls) -> None:
        """Réinitialise tous les drapeaux aux libellés par défaut."""
        SettingsService.set(SETTINGS_KEY, {}, category=SETTINGS_CATEGORY)
        cls._invalidate_cache()
        resolved = cls.get_flag_labels()
        event_bus.publish(FlagLabelsUpdatedEvent(labels=resolved))

    @classmethod
    def get_flag_search_map(cls) -> dict[str, int]:
        """
        Renvoie la table de correspondance complète pour la recherche de drapeaux,
        combinant les alias par défaut (DEFAULT_FLAG_SEARCH_MAP)
        et les libellés personnalisés en minuscules.
        """
        search_map = dict(DEFAULT_FLAG_SEARCH_MAP)
        labels = cls.get_flag_labels()

        for idx in range(1, 8):
            label = labels.get(idx, "").strip().lower()
            if label:
                search_map[label] = idx
                if " " in label:
                    search_map[label.replace(" ", "_")] = idx
                    search_map[label.replace(" ", "-")] = idx

        return search_map
