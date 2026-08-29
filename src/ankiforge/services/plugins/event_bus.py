"""
Bus d'événements découplé et typé pour AnkiForge.
Permet aux addons et au cœur de l'application de communiquer sans dépendance circulaire.
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

EventHandler = Callable[..., Any]


class EventBus:
    """
    Gestionnaire centralisé de publication/souscription d'événements pour AnkiForge.
    Chaque callback est exécuté de manière sécurisée (try/catch individuel).
    """

    _instance: EventBus | None = None

    def __init__(self) -> None:
        self._listeners: dict[str, list[EventHandler]] = {}

    @classmethod
    def get_instance(cls) -> EventBus:
        """Accès singleton au bus d'événements."""
        if cls._instance is None:
            cls._instance = EventBus()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Réinitialise l'instance (utilisé pour les tests unitaires)."""
        cls._instance = None

    def on(self, event_name: str, handler: EventHandler) -> EventHandler:
        """
        Abonne une fonction ou méthode à un événement.
        Peut être utilisé comme décorateur.
        """
        event_name = event_name.lower().strip()
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        if handler not in self._listeners[event_name]:
            self._listeners[event_name].append(handler)
        return handler

    def off(self, event_name: str, handler: EventHandler) -> bool:
        """Désabonne une fonction d'un événement."""
        event_name = event_name.lower().strip()
        if event_name in self._listeners and handler in self._listeners[event_name]:
            self._listeners[event_name].remove(handler)
            return True
        return False

    def emit(self, event_name: str, *args: Any, **kwargs: Any) -> list[Any]:
        """
        Déclenche un événement et exécute tous les écouteurs enregistrés.
        Chaque écouteur est exécuté avec protection d'exception pour ne pas bloquer les autres.
        Retourne la liste des résultats renvoyés par les gestionnaires.
        """
        event_name = event_name.lower().strip()
        listeners = list(self._listeners.get(event_name, []))
        results: list[Any] = []

        for listener in listeners:
            try:
                res = listener(*args, **kwargs)
                results.append(res)
            except Exception as e:
                logger.error(f"Erreur dans l'écouteur d'événement '{event_name}' ({listener.__name__ if hasattr(listener, '__name__') else listener}): {e}\n{traceback.format_exc()}")

        return results

    def clear(self, event_name: str | None = None) -> None:
        """Efface les écouteurs pour un événement donné ou pour tous les événements."""
        if event_name:
            self._listeners.pop(event_name.lower().strip(), None)
        else:
            self._listeners.clear()

    def get_listener_count(self, event_name: str) -> int:
        """Retourne le nombre d'écouteurs pour un événement donné."""
        return len(self._listeners.get(event_name.lower().strip(), []))


# Singleton instance helper
event_bus = EventBus.get_instance()
