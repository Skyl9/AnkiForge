"""
Unit tests for central typed AppEventBus.
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
)


def test_event_bus_singleton() -> None:
    AppEventBus.reset_instance()
    bus1 = AppEventBus.get_instance()
    bus2 = AppEventBus.get_instance()
    assert bus1 is bus2
    AppEventBus.reset_instance()


def test_typed_event_publish_subscribe() -> None:
    bus = AppEventBus()
    received: list[CardCreatedEvent] = []

    def on_card_created(event: CardCreatedEvent) -> None:
        received.append(event)

    bus.subscribe(CardCreatedEvent, on_card_created)
    assert bus.listener_count(CardCreatedEvent) == 1

    event = CardCreatedEvent(card_id=42, note_id=10, deck_name="Biology")
    bus.publish(event)

    assert len(received) == 1
    assert received[0].card_id == 42
    assert received[0].note_id == 10
    assert received[0].deck_name == "Biology"

    bus.unsubscribe(CardCreatedEvent, on_card_created)
    assert bus.listener_count(CardCreatedEvent) == 0

    bus.publish(CardCreatedEvent(card_id=43, note_id=11, deck_name="Math"))
    assert len(received) == 1


def test_base_app_event_subscriber() -> None:
    bus = AppEventBus()
    all_events: list[AppEvent] = []

    def on_any_event(event: AppEvent) -> None:
        all_events.append(event)

    bus.subscribe(AppEvent, on_any_event)

    bus.publish(DeckCreatedEvent(deck_id=1, deck_name="Deck 1"))
    bus.publish(NoteCreatedEvent(note_id=2, deck_name="Deck 1", tags=["tag1"]))
    bus.publish(ProfileSwitchedEvent(profile_name="custom"))

    assert len(all_events) == 3
    assert isinstance(all_events[0], DeckCreatedEvent)
    assert isinstance(all_events[1], NoteCreatedEvent)
    assert isinstance(all_events[2], ProfileSwitchedEvent)


def test_legacy_string_event_compatibility() -> None:
    bus = AppEventBus()
    calls: list[str] = []

    @bus.on("custom_hook")
    def my_listener(arg1: str, extra: int = 0) -> str:
        calls.append(f"{arg1}:{extra}")
        return "ok"

    assert bus.listener_count("custom_hook") == 1
    res = bus.emit("custom_hook", "hello", extra=42)
    assert res == ["ok"]
    assert calls == ["hello:42"]

    bus.off("custom_hook", my_listener)
    assert bus.listener_count("custom_hook") == 0


def test_handler_exception_isolation() -> None:
    bus = AppEventBus()
    executed: list[str] = []

    def faulty_handler(event: ThemeChangedEvent) -> None:
        raise RuntimeError("Crash in subscriber!")

    def valid_handler(event: ThemeChangedEvent) -> None:
        executed.append(event.theme_name)

    bus.subscribe(ThemeChangedEvent, faulty_handler)
    bus.subscribe(ThemeChangedEvent, valid_handler)

    # Should not raise exception
    bus.publish(ThemeChangedEvent(theme_name="dark", layout_name="ide"))

    assert executed == ["dark"]


def test_clear_listeners() -> None:
    bus = AppEventBus()
    bus.subscribe(DeckRenamedEvent, lambda e: None)
    bus.subscribe(NoteDeletedEvent, lambda e: None)
    assert bus.listener_count(DeckRenamedEvent) == 1
    assert bus.listener_count(NoteDeletedEvent) == 1

    bus.clear(DeckRenamedEvent)
    assert bus.listener_count(DeckRenamedEvent) == 0
    assert bus.listener_count(NoteDeletedEvent) == 1

    bus.clear()
    assert bus.listener_count(NoteDeletedEvent) == 0


def test_all_typed_events_instantiation() -> None:
    events = [
        DeckCreatedEvent(deck_id=1, deck_name="d"),
        DeckRenamedEvent(deck_id=1, old_name="a", new_name="b"),
        DeckDeletedEvent(deck_id=1, deck_name="d"),
        NoteCreatedEvent(note_id=1, deck_name="d", tags=["a"]),
        NoteUpdatedEvent(note_id=1, version_number=2),
        NoteDeletedEvent(note_id=1),
        CardCreatedEvent(card_id=1, note_id=1, deck_name="d"),
        CardUpdatedEvent(card_id=1, note_id=1),
        CardDeletedEvent(card_id=1),
        ProfileSwitchedEvent(profile_name="p"),
        ThemeChangedEvent(theme_name="t", layout_name="l"),
        PipelineCreatedEvent(pipeline_id=1, pipeline_name="p"),
        PipelineUpdatedEvent(pipeline_id=1, pipeline_name="p"),
        PipelineDeletedEvent(pipeline_id=1),
        PipelineRunStartedEvent(pipeline_id=1, pipeline_name="p", run_id="r1"),
        PipelineRunFinishedEvent(pipeline_id=1, pipeline_name="p", success=True, generated_cards_count=5),
        DocumentAddedEvent(doc_id=1, title="doc"),
        DocumentUpdatedEvent(doc_id=1, title="doc"),
        DocumentDeletedEvent(doc_id=1),
        DocumentIndexedEvent(doc_id=1, chunks_count=10),
        AuditStartedEvent(deck_id=1),
        AuditCompletedEvent(total_notes=10, anomalies_count=2, deck_id=1),
        LinterRuleToggledEvent(rule_id=1, is_active=True),
        PersonaCreatedEvent(persona_id=1, name="p"),
        PersonaUpdatedEvent(persona_id=1, name="p"),
        PersonaDeletedEvent(persona_id=1),
        SettingChangedEvent(key="k", value="v"),
    ]

    for ev in events:
        assert isinstance(ev, AppEvent)
        assert ev.timestamp is not None
