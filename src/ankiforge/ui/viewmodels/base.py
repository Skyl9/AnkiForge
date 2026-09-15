"""
Base ViewModel for AnkiForge MVVM architecture.
Inherits from QObject to provide reactive Signal emissions while keeping business state testable.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, Signal

from ankiforge.utils.event_bus import AppEvent, AppEventBus
from ankiforge.utils.event_bus import event_bus as global_event_bus

logger = logging.getLogger(__name__)


class BaseViewModel(QObject):
    """
    Base ViewModel providing reactive state properties, error handling,
    busy indicator signalling, and decoupled EventBus integration.
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
        """Update busy status and emit signal if changed."""
        if self._is_busy != busy:
            self._is_busy = busy
            self.busy_changed.emit(busy)

    def set_error(self, message: str | None) -> None:
        """Update error status and emit error signal if present."""
        self._error_message = message
        if message:
            logger.error("[%s] Error: %s", self.__class__.__name__, message)
            self.error_occurred.emit(message)

    def emit_message(self, message: str) -> None:
        """Emit a user-facing informational message."""
        self.message_emitted.emit(message)

    def subscribe_event(self, event_type: type[AppEvent] | str, handler: Any) -> None:
        """Subscribe to an AppEvent and track it for clean disposal."""
        self._event_bus.subscribe(event_type, handler)
        self._subscriptions.append((event_type, handler))

    def publish_event(self, event: AppEvent | str, *args: Any, **kwargs: Any) -> list[Any]:
        """Publish an event through the EventBus."""
        return self._event_bus.publish(event, *args, **kwargs)

    def dispose(self) -> None:
        """Unsubscribe all active event handlers and reset state."""
        for event_type, handler in self._subscriptions:
            self._event_bus.unsubscribe(event_type, handler)
        self._subscriptions.clear()
