"""
Unit tests for EditionViewModel.
"""

from __future__ import annotations

from ankiforge.repositories.deck_repository import DeckRepository
from ankiforge.repositories.note_repository import NoteRepository
from ankiforge.ui.viewmodels.edition_viewmodel import EditionViewModel
from ankiforge.utils.event_bus import AppEventBus, NoteDeletedEvent, NoteUpdatedEvent


def test_edition_viewmodel_browser() -> None:
    bus = AppEventBus()
    note_repo = NoteRepository()
    deck_repo = DeckRepository()

    vm = EditionViewModel(note_repo=note_repo, deck_repo=deck_repo, bus=bus)

    deck = deck_repo.create_deck("History")
    nt = note_repo.create_note_type("Basic", ["Front", "Back"], [])
    note = note_repo.create_note(nt, deck, {"Front": "1789?"}, tags=["revolution", "france"])

    vm.load_data()
    assert len(vm.decks) == 1
    assert len(vm.notes) == 1

    # Select note
    vm.select_note_by_id(note.id)
    assert vm.selected_note is not None
    assert vm.active_version is not None
    assert "1789" in vm.active_version.content

    # Save note content
    updated_events: list = []
    bus.subscribe(NoteUpdatedEvent, lambda e: updated_events.append(e))

    saved = vm.save_note_content(note.id, {"Front": "French Revolution Date?", "Back": "1789"}, tags=["france"])
    assert saved is True
    assert len(updated_events) == 1

    # Search notes
    vm.set_search_query("Revolution")
    assert len(vm.notes) == 1

    # Delete note
    deleted_events: list = []
    bus.subscribe(NoteDeletedEvent, lambda e: deleted_events.append(e))

    vm.delete_selected_note()
    assert len(deleted_events) == 1
    assert vm.selected_note is None

    vm.dispose()
