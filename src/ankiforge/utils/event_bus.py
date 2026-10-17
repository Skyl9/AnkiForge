"""Bus d'événements typé central pour AnkiForge.

Assure une communication découplée de type publication/abonnement tout au long du cycle de vie de l'application.
"""

from __future__ import annotations

import logging
import re
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
    """Classe de base de tous les événements applicatifs typés."""

    timestamp: datetime = field(default_factory=datetime.now)


# Deck Events
@dataclass(frozen=True)
class DeckCreatedEvent(AppEvent):
    """Événement émis à la création d'un paquet."""

    deck_id: int = 0
    deck_name: str = ""


@dataclass(frozen=True)
class DeckRenamedEvent(AppEvent):
    """Événement émis lors du renommage d'un paquet."""

    deck_id: int = 0
    old_name: str = ""
    new_name: str = ""


@dataclass(frozen=True)
class DeckDeletedEvent(AppEvent):
    """Événement émis à la suppression d'un paquet."""

    deck_id: int = 0
    deck_name: str = ""


# Note & Card Events
@dataclass(frozen=True)
class NoteCreatedEvent(AppEvent):
    """Événement émis à la création d'une note."""

    note_id: int = 0
    deck_name: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NoteUpdatedEvent(AppEvent):
    """Événement émis à la mise à jour d'une note."""

    note_id: int = 0
    version_number: int = 1


@dataclass(frozen=True)
class NoteDeletedEvent(AppEvent):
    """Événement émis à la suppression d'une note."""

    note_id: int = 0


@dataclass(frozen=True)
class CardCreatedEvent(AppEvent):
    """Événement émis à la création d'une carte."""

    card_id: int = 0
    note_id: int = 0
    deck_name: str = ""


@dataclass(frozen=True)
class CardUpdatedEvent(AppEvent):
    """Événement émis à la mise à jour d'une carte."""

    card_id: int = 0
    note_id: int = 0


@dataclass(frozen=True)
class CardDeletedEvent(AppEvent):
    """Événement émis à la suppression d'une carte."""

    card_id: int = 0


# Profile & Theme Events
@dataclass(frozen=True)
class ProfileSwitchedEvent(AppEvent):
    """Événement émis lors du changement de profil utilisateur."""

    profile_name: str = ""


@dataclass(frozen=True)
class ThemeChangedEvent(AppEvent):
    """Événement émis lors du changement de thème ou de disposition d'interface."""

    theme_name: str = ""
    layout_name: str = ""


# Flag Events
@dataclass(frozen=True)
class FlagLabelsUpdatedEvent(AppEvent):
    """Événement émis lors de la mise à jour des libellés de drapeaux personnalisés."""

    labels: dict[int, str] = field(default_factory=dict)


# Pipeline Events
@dataclass(frozen=True)
class PipelineCreatedEvent(AppEvent):
    """Événement émis à la création d'un pipeline IA."""

    pipeline_id: int = 0
    pipeline_name: str = ""


@dataclass(frozen=True)
class PipelineUpdatedEvent(AppEvent):
    """Événement émis à la mise à jour d'un pipeline IA."""

    pipeline_id: int = 0
    pipeline_name: str = ""


@dataclass(frozen=True)
class PipelineDeletedEvent(AppEvent):
    """Événement émis à la suppression d'un pipeline IA."""

    pipeline_id: int = 0


@dataclass(frozen=True)
class PipelineRunStartedEvent(AppEvent):
    """Événement émis au démarrage de l'exécution d'un pipeline IA."""

    pipeline_id: int = 0
    pipeline_name: str = ""
    run_id: str = ""


@dataclass(frozen=True)
class PipelineRunFinishedEvent(AppEvent):
    """Événement émis à la fin de l'exécution d'un pipeline IA."""

    pipeline_id: int = 0
    pipeline_name: str = ""
    success: bool = True
    error: str = ""
    generated_cards_count: int = 0


# Document & RAG Events
@dataclass(frozen=True)
class DocumentAddedEvent(AppEvent):
    """Événement émis à l'ajout d'un document source."""

    doc_id: int = 0
    title: str = ""
    doc_type: str = "text"


@dataclass(frozen=True)
class DocumentUpdatedEvent(AppEvent):
    """Événement émis à la mise à jour d'un document source."""

    doc_id: int = 0
    title: str = ""


@dataclass(frozen=True)
class DocumentDeletedEvent(AppEvent):
    """Événement émis à la suppression d'un document source."""

    doc_id: int = 0


@dataclass(frozen=True)
class DocumentIndexedEvent(AppEvent):
    """Événement émis lorsque l'indexation vectorielle d'un document est terminée."""

    doc_id: int = 0
    chunks_count: int = 0


@dataclass(frozen=True)
class CoverageSyncedEvent(AppEvent):
    """Événement émis lors de la synchronisation de la couverture documentaire."""

    doc_id: int | None = None
    scope: str = "document"  # "document" | "all"


# Audit & Linter Events
@dataclass(frozen=True)
class AuditStartedEvent(AppEvent):
    """Événement émis au démarrage d'un audit de qualité des notes."""

    deck_id: int | None = None


@dataclass(frozen=True)
class AuditCompletedEvent(AppEvent):
    """Événement émis à l'achèvement d'un audit de qualité des notes."""

    total_notes: int = 0
    anomalies_count: int = 0
    deck_id: int | None = None


@dataclass(frozen=True)
class LinterRuleToggledEvent(AppEvent):
    """Événement émis lors de l'activation ou de la désactivation d'une règle du linter."""

    rule_id: int = 0
    is_active: bool = True


# Persona Events
@dataclass(frozen=True)
class PersonaCreatedEvent(AppEvent):
    """Événement émis à la création d'une persona."""

    persona_id: int = 0
    name: str = ""


@dataclass(frozen=True)
class PersonaUpdatedEvent(AppEvent):
    """Événement émis à la mise à jour d'une persona."""

    persona_id: int = 0
    name: str = ""


@dataclass(frozen=True)
class PersonaDeletedEvent(AppEvent):
    """Événement émis à la suppression d'une persona."""

    persona_id: int = 0


# Setting Events
@dataclass(frozen=True)
class SettingChangedEvent(AppEvent):
    """Événement émis lors de la modification d'un paramètre applicatif."""

    key: str = ""
    value: Any = None


# Consultant AI Events
@dataclass(frozen=True)
class OpenConsultantRequestedEvent(AppEvent):
    """Événement émis pour demander l'ouverture du consultant IA avec un contexte donné."""

    context_item: str = ""
    initial_prompt: str = ""


# Feedback & Support Events
@dataclass(frozen=True)
class OpenFeedbackRequestedEvent(AppEvent):
    """Événement émis pour demander l'ouverture du formulaire de retour utilisateur."""

    tab: str = "bug"  # "bug" ou "feature"
    initial_title: str = ""
    context_error: str = ""


# MCP Server Events
@dataclass(frozen=True)
class MCPDataMutatedEvent(AppEvent):
    """Événement émis lors d'une mutation de données par un agent externe via le protocole MCP."""

    mutation_type: str = ""  # "card", "split", "model", "css"
    target_id: int = 0
    target_name: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPPatchStagedEvent(AppEvent):
    """Événement émis lors de la proposition d'un patch en attente par un agent MCP (Two-Phase Commit)."""

    patch_id: str = ""
    patch_type: str = ""  # "card", "split", "note_create", "batch_note_create", "model", "css"
    target_id: int = 0
    title: str = ""
    details: dict[str, Any] = field(default_factory=dict)


# LLM Model Catalog Events
@dataclass(frozen=True)
class LLMModelsChangedEvent(AppEvent):
    """Événement émis lors de l'ajout, modification ou suppression d'un modèle IA dans le catalogue."""

    action: str = ""  # "created", "updated", "deleted"
    model_id: str = ""
    provider: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# AppEventBus Singleton & Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

E = TypeVar("E", bound=AppEvent)
EventHandler = Callable[..., Any]

_EVENT_NAME_ALIASES: dict[str, type[AppEvent]] = {
    "deck_created": DeckCreatedEvent,
    "deck_renamed": DeckRenamedEvent,
    "deck_deleted": DeckDeletedEvent,
    "note_created": NoteCreatedEvent,
    "note_updated": NoteUpdatedEvent,
    "note_deleted": NoteDeletedEvent,
    "card_created": CardCreatedEvent,
    "card_updated": CardUpdatedEvent,
    "card_deleted": CardDeletedEvent,
    "profile_switched": ProfileSwitchedEvent,
    "theme_changed": ThemeChangedEvent,
    "pipeline_created": PipelineCreatedEvent,
    "pipeline_updated": PipelineUpdatedEvent,
    "pipeline_deleted": PipelineDeletedEvent,
    "pipeline_run_started": PipelineRunStartedEvent,
    "pipeline_run_finished": PipelineRunFinishedEvent,
    "document_added": DocumentAddedEvent,
    "document_updated": DocumentUpdatedEvent,
    "document_deleted": DocumentDeletedEvent,
    "document_indexed": DocumentIndexedEvent,
    "coverage_synced": CoverageSyncedEvent,
    "audit_started": AuditStartedEvent,
    "audit_completed": AuditCompletedEvent,
    "linter_rule_toggled": LinterRuleToggledEvent,
    "persona_created": PersonaCreatedEvent,
    "persona_updated": PersonaUpdatedEvent,
    "persona_deleted": PersonaDeletedEvent,
    "setting_changed": SettingChangedEvent,
    "flag_labels_updated": FlagLabelsUpdatedEvent,
    "mcp_data_mutated": MCPDataMutatedEvent,
    "mcp_patch_staged": MCPPatchStagedEvent,
    "llm_models_changed": LLMModelsChangedEvent,
    "open_consultant_requested": OpenConsultantRequestedEvent,
    "open_feedback_requested": OpenFeedbackRequestedEvent,
}


def _event_name(event_type: type[AppEvent]) -> str:
    """Retourne le nom stable en snake_case utilisé par les API des addons historiques."""
    name = event_type.__name__.removesuffix("Event")
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


class AppEventBus:
    """Bus d'événements centralisé supportant à la fois les événements fortement typés et les noms sous forme de chaîne.

    Sûr vis-à-vis des threads et isolé des exceptions.
    """

    _instance: AppEventBus | None = None
    _lock = threading.RLock()

    def __init__(self) -> None:
        self._listeners: dict[type[AppEvent] | str, list[EventHandler]] = {}
        self._rw_lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> AppEventBus:
        """Accesseur singleton du bus d'événements."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = AppEventBus()
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Réinitialise l'instance singleton (utile pour l'isolation des tests)."""
        with cls._lock:
            cls._instance = None

    def subscribe(self, event_type: type[E] | str, handler: Callable[[E], Any] | EventHandler | None = None) -> Any:
        """Abonne un gestionnaire de callback à un type d'événement ou à une clé sous forme de chaîne.

        Peut être utilisé comme décorateur lorsque handler est omis.
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
        """Désabonne un gestionnaire de callback d'un type d'événement ou d'une clé sous forme de chaîne."""
        key: type[AppEvent] | str = event_type.lower().strip() if isinstance(event_type, str) else event_type

        with self._rw_lock:
            if key in self._listeners and handler in self._listeners[key]:
                self._listeners[key].remove(handler)
                return True
        return False

    def publish(self, event: AppEvent | str, *args: Any, **kwargs: Any) -> list[Any]:
        """Publie un événement auprès de tous les listeners abonnés.

        Intercepte et journalise les exceptions de chaque gestionnaire afin d'éviter les défaillances en cascade.
        """
        results: list[Any] = []
        matching_handlers: list[EventHandler] = []

        with self._rw_lock:
            if isinstance(event, str):
                str_key = event.lower().strip()
                matching_handlers.extend(self._listeners.get(str_key, []))
                typed_event = args[0] if args and isinstance(args[0], AppEvent) else None
                mapped_type = _EVENT_NAME_ALIASES.get(str_key)
                if typed_event is not None and mapped_type is type(typed_event):
                    matching_handlers.extend(self._listeners.get(mapped_type, []))
            elif isinstance(event, AppEvent):
                # Specific event class handlers
                event_cls = type(event)
                matching_handlers.extend(self._listeners.get(event_cls, []))
                # Also generic AppEvent handlers
                if event_cls is not AppEvent:
                    matching_handlers.extend(self._listeners.get(AppEvent, []))
                matching_handlers.extend(self._listeners.get(_event_name(event_cls), []))

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
        """Alias de compatibilité ascendante pour ``subscribe()``."""
        return self.subscribe(event_name, handler)

    def off(self, event_name: str, handler: EventHandler) -> bool:
        """Alias de compatibilité ascendante pour ``unsubscribe()``."""
        return self.unsubscribe(event_name, handler)

    def emit(self, event_name: str, *args: Any, **kwargs: Any) -> list[Any]:
        """Alias de compatibilité ascendante pour ``publish()``."""
        return self.publish(event_name, *args, **kwargs)

    def clear(self, event_type: type[E] | str | None = None) -> None:
        """Supprime les listeners d'un type d'événement précis ou de tous les événements."""
        with self._rw_lock:
            if event_type is None:
                self._listeners.clear()
            else:
                key = event_type.lower().strip() if isinstance(event_type, str) else event_type
                self._listeners.pop(key, None)

    def listener_count(self, event_type: type[E] | str) -> int:
        """Retourne le nombre de listeners enregistrés pour un événement."""
        key = event_type.lower().strip() if isinstance(event_type, str) else event_type
        with self._rw_lock:
            return len(self._listeners.get(key, []))


# Global default instance
event_bus = AppEventBus.get_instance()
