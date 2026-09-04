"""
Central typed event bus for AnkiForge.
Provides decoupled, publish-subscribe messaging across the application lifecycle.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Typed Event Classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AppEvent:
    """Base class for all typed application events."""

    timestamp: datetime = field(default_factory=datetime.now)


# Deck Events
@dataclass(frozen=True)
class DeckCreatedEvent(AppEvent):
    deck_id: int = 0
    deck_name: str = ""


@dataclass(frozen=True)
class DeckRenamedEvent(AppEvent):
    deck_id: int = 0
    old_name: str = ""
    new_name: str = ""


@dataclass(frozen=True)
class DeckDeletedEvent(AppEvent):
    deck_id: int = 0
    deck_name: str = ""


# Note & Card Events
@dataclass(frozen=True)
class NoteCreatedEvent(AppEvent):
    note_id: int = 0
    deck_name: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NoteUpdatedEvent(AppEvent):
    note_id: int = 0
    version_number: int = 1


@dataclass(frozen=True)
class NoteDeletedEvent(AppEvent):
    note_id: int = 0


@dataclass(frozen=True)
class CardCreatedEvent(AppEvent):
    card_id: int = 0
    note_id: int = 0
    deck_name: str = ""


@dataclass(frozen=True)
class CardUpdatedEvent(AppEvent):
    card_id: int = 0
    note_id: int = 0


@dataclass(frozen=True)
class CardDeletedEvent(AppEvent):
    card_id: int = 0


# Profile & Theme Events
@dataclass(frozen=True)
class ProfileSwitchedEvent(AppEvent):
    profile_name: str = ""


@dataclass(frozen=True)
class ThemeChangedEvent(AppEvent):
    theme_name: str = ""
    layout_name: str = ""


# Pipeline Events
@dataclass(frozen=True)
class PipelineCreatedEvent(AppEvent):
    pipeline_id: int = 0
    pipeline_name: str = ""


@dataclass(frozen=True)
class PipelineUpdatedEvent(AppEvent):
    pipeline_id: int = 0
    pipeline_name: str = ""


@dataclass(frozen=True)
class PipelineDeletedEvent(AppEvent):
    pipeline_id: int = 0


@dataclass(frozen=True)
class PipelineRunStartedEvent(AppEvent):
    pipeline_id: int = 0
    pipeline_name: str = ""
    run_id: str = ""


@dataclass(frozen=True)
class PipelineRunFinishedEvent(AppEvent):
    pipeline_id: int = 0
    pipeline_name: str = ""
    success: bool = True
    error: str = ""
    generated_cards_count: int = 0


# Document & RAG Events
@dataclass(frozen=True)
class DocumentAddedEvent(AppEvent):
    doc_id: int = 0
    title: str = ""
    doc_type: str = "text"


@dataclass(frozen=True)
class DocumentUpdatedEvent(AppEvent):
    doc_id: int = 0
    title: str = ""


@dataclass(frozen=True)
class DocumentDeletedEvent(AppEvent):
    doc_id: int = 0


@dataclass(frozen=True)
class DocumentIndexedEvent(AppEvent):
    doc_id: int = 0
    chunks_count: int = 0


# Audit & Linter Events
@dataclass(frozen=True)
class AuditStartedEvent(AppEvent):
    deck_id: int | None = None


@dataclass(frozen=True)
class AuditCompletedEvent(AppEvent):
    total_notes: int = 0
    anomalies_count: int = 0
    deck_id: int | None = None


@dataclass(frozen=True)
class LinterRuleToggledEvent(AppEvent):
    rule_id: int = 0
    is_active: bool = True


# Persona Events
@dataclass(frozen=True)
class PersonaCreatedEvent(AppEvent):
    persona_id: int = 0
    name: str = ""


@dataclass(frozen=True)
class PersonaUpdatedEvent(AppEvent):
    persona_id: int = 0
    name: str = ""


@dataclass(frozen=True)
class PersonaDeletedEvent(AppEvent):
    persona_id: int = 0


# Setting Events
@dataclass(frozen=True)
class SettingChangedEvent(AppEvent):
    key: str = ""
    value: Any = None


# Consultant AI Events
@dataclass(frozen=True)
class OpenConsultantRequestedEvent(AppEvent):
    context_item: str = ""
    initial_prompt: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# AppEventBus Singleton & Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

E = TypeVar("E", bound=AppEvent)
EventHandler = Callable[..., Any]


class AppEventBus:
    """
    Centralized event bus supporting both strongly typed events and string names.
    Thread-safe and exception-isolated.
    """

    _instance: AppEventBus | None = None
    _lock = threading.RLock()

    def __init__(self) -> None:
        self._listeners: dict[type[AppEvent] | str, list[EventHandler]] = {}
        self._rw_lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> AppEventBus:
        """Singleton accessor for the event bus."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = AppEventBus()
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (useful for test isolation)."""
        with cls._lock:
            cls._instance = None

    def subscribe(self, event_type: type[E] | str, handler: Callable[[E], Any] | EventHandler | None = None) -> Any:
        """
        Subscribe a callback handler to a specific event type or string key.
        Can be used as a decorator when handler is omitted.
        """
        if handler is None:

            def decorator(fn: EventHandler) -> EventHandler:
                self.subscribe(event_type, fn)
                return fn

            return decorator

        key: type[AppEvent] | str = event_type.lower().strip() if isinstance(event_type, str) else event_type

        with self._rw_lock:
            if key not in self._listeners:
                self._listeners[key] = []
            if handler not in self._listeners[key]:
                self._listeners[key].append(handler)
        return handler

    def unsubscribe(self, event_type: type[E] | str, handler: EventHandler) -> bool:
        """Unsubscribe a callback handler from an event type or string key."""
        key: type[AppEvent] | str = event_type.lower().strip() if isinstance(event_type, str) else event_type

        with self._rw_lock:
            if key in self._listeners and handler in self._listeners[key]:
                self._listeners[key].remove(handler)
                return True
        return False

    def publish(self, event: AppEvent | str, *args: Any, **kwargs: Any) -> list[Any]:
        """
        Publish an event to all subscribed listeners.
        Catches and logs exceptions for individual handlers to avoid cascading failures.
        """
        results: list[Any] = []
        matching_handlers: list[EventHandler] = []

        with self._rw_lock:
            if isinstance(event, str):
                str_key = event.lower().strip()
                matching_handlers.extend(self._listeners.get(str_key, []))
            elif isinstance(event, AppEvent):
                # Specific event class handlers
                event_cls = type(event)
                matching_handlers.extend(self._listeners.get(event_cls, []))
                # Also generic AppEvent handlers
                if event_cls is not AppEvent:
                    matching_handlers.extend(self._listeners.get(AppEvent, []))

        for handler in matching_handlers:
            try:
                res = handler(event) if isinstance(event, AppEvent) else handler(*args, **kwargs)
                results.append(res)
            except Exception as e:
                try:
                    handler_name = getattr(handler, "__qualname__", "unknown_handler")
                except Exception:
                    handler_name = "deleted_shiboken_handler"

                logger.debug(
                    "Error executing event handler %s for event %s: %s",
                    handler_name,
                    event,
                    e,
                )
                if "already deleted" in str(e):
                    with self._rw_lock:
                        for listeners in self._listeners.values():
                            if handler in listeners:
                                listeners.remove(handler)

        return results

    # Backward compatibility aliases for legacy plugins
    def on(self, event_name: str, handler: EventHandler | None = None) -> Any:
        return self.subscribe(event_name, handler)

    def off(self, event_name: str, handler: EventHandler) -> bool:
        return self.unsubscribe(event_name, handler)

    def emit(self, event_name: str, *args: Any, **kwargs: Any) -> list[Any]:
        return self.publish(event_name, *args, **kwargs)

    def clear(self, event_type: type[E] | str | None = None) -> None:
        """Clear listeners for a specific event type or all events."""
        with self._rw_lock:
            if event_type is None:
                self._listeners.clear()
            else:
                key = event_type.lower().strip() if isinstance(event_type, str) else event_type
                self._listeners.pop(key, None)

    def listener_count(self, event_type: type[E] | str) -> int:
        """Return the number of registered listeners for an event."""
        key = event_type.lower().strip() if isinstance(event_type, str) else event_type
        with self._rw_lock:
            return len(self._listeners.get(key, []))


# Global default instance
event_bus = AppEventBus.get_instance()
