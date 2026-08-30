"""
Bus d'événements découplé et typé pour AnkiForge.
Permet aux addons et au cœur de l'application de communiquer sans dépendance circulaire.
"""

from __future__ import annotations

from ankiforge.utils.event_bus import (
    AppEvent,
    AppEventBus,
    AuditCompletedEvent,
    AuditStartedEvent,
    CardCreatedEvent,
    CardDeletedEvent,
    CardUpdatedEvent,
    DeckCreatedEvent,
    DeckDeletedEvent,
    DeckRenamedEvent,
    DocumentAddedEvent,
    DocumentDeletedEvent,
    DocumentIndexedEvent,
    DocumentUpdatedEvent,
    EventHandler,
    LinterRuleToggledEvent,
    NoteCreatedEvent,
    NoteDeletedEvent,
    NoteUpdatedEvent,
    PersonaCreatedEvent,
    PersonaDeletedEvent,
    PersonaUpdatedEvent,
    PipelineCreatedEvent,
    PipelineDeletedEvent,
    PipelineRunFinishedEvent,
    PipelineRunStartedEvent,
    PipelineUpdatedEvent,
    ProfileSwitchedEvent,
    SettingChangedEvent,
    ThemeChangedEvent,
    event_bus,
)

# Alias for backward compatibility with existing plugins
EventBus = AppEventBus

__all__ = [
    "AppEvent",
    "AppEventBus",
    "EventBus",
    "EventHandler",
    "event_bus",
    "DeckCreatedEvent",
    "DeckRenamedEvent",
    "DeckDeletedEvent",
    "NoteCreatedEvent",
    "NoteUpdatedEvent",
    "NoteDeletedEvent",
    "CardCreatedEvent",
    "CardUpdatedEvent",
    "CardDeletedEvent",
    "ProfileSwitchedEvent",
    "ThemeChangedEvent",
    "PipelineCreatedEvent",
    "PipelineUpdatedEvent",
    "PipelineDeletedEvent",
    "PipelineRunStartedEvent",
    "PipelineRunFinishedEvent",
    "DocumentAddedEvent",
    "DocumentUpdatedEvent",
    "DocumentDeletedEvent",
    "DocumentIndexedEvent",
    "AuditStartedEvent",
    "AuditCompletedEvent",
    "LinterRuleToggledEvent",
    "PersonaCreatedEvent",
    "PersonaUpdatedEvent",
    "PersonaDeletedEvent",
    "SettingChangedEvent",
]
