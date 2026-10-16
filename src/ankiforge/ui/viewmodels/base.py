"""ViewModel de base pour l'architecture MVVM d'AnkiForge.

Hérite de QObject pour fournir des émissions de signaux réactives tout en maintenant l'état métier testable.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, Signal

from ankiforge.utils.event_bus import AppEvent, AppEventBus
from ankiforge.utils.event_bus import event_bus as global_event_bus

logger = logging.getLogger(__name__)


class BaseViewModel(QObject):
    """ViewModel de base pour l'état réactif et l'intégration à l'EventBus.

    Fournit les propriétés d'état réactives, la gestion des erreurs,
    les indicateurs d'occupation et l'intégration découplée avec l'EventBus.
    """

    busy_changed = Signal(bool)
    error_occurred = Signal(str)
    message_emitted = Signal(str)

    def __init__(
        self,
        bus: AppEventBus | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._event_bus = bus or global_event_bus
        self._is_busy: bool = False
        self._error_message: str | None = None
        self._subscriptions: list[tuple[type[AppEvent] | str, Any]] = []

    @property
    def event_bus(self) -> AppEventBus:
        return self._event_bus

    @property
    def is_busy(self) -> bool:
        return self._is_busy

    @property
    def error_message(self) -> str | None:
        return self._error_message

    def set_busy(self, busy: bool) -> None:
        """Met à jour le statut d'occupation et émet le signal si l'état a changé."""
        if self._is_busy != busy:
            self._is_busy = busy
            self.busy_changed.emit(busy)

    def set_error(self, message: str | None) -> None:
        """Met à jour le message d'erreur et émet le signal d'erreur correspondant."""
        self._error_message = message
        if message:
            logger.error("[%s] Error: %s", self.__class__.__name__, message)
            self.error_occurred.emit(message)

    def emit_message(self, message: str) -> None:
        """Émet un message d'information destiné à l'utilisateur."""
        self.message_emitted.emit(message)

    def subscribe_event(self, event_type: type[AppEvent] | str, handler: Any) -> None:
        """Abonne un gestionnaire à un événement AppEvent et l'enregistre pour un nettoyage propre."""
        self._event_bus.subscribe(event_type, handler)
        self._subscriptions.append((event_type, handler))

    def publish_event(self, event: AppEvent | str, *args: Any, **kwargs: Any) -> list[Any]:
        """Publie un événement via l'EventBus global ou local."""
        return self._event_bus.publish(event, *args, **kwargs)

    def dispose(self) -> None:
        """Désabonne tous les gestionnaires d'événements actifs et réinitialise l'état."""
        for event_type, handler in self._subscriptions:
            self._event_bus.unsubscribe(event_type, handler)
        self._subscriptions.clear()
