"""
Unit tests for CreationViewModel.
"""

from __future__ import annotations

from ankiforge.repositories.deck_repository import DeckRepository
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.repositories.note_repository import NoteRepository
from ankiforge.repositories.pipeline_repository import PipelineRepository
from ankiforge.ui.viewmodels.creation_viewmodel import CreationViewModel
from ankiforge.utils.event_bus import AppEventBus, CardCreatedEvent, NoteCreatedEvent


def test_creation_viewmodel_workflow() -> None:
    bus = AppEventBus()
    note_repo = NoteRepository()
    deck_repo = DeckRepository()
    pipeline_repo = PipelineRepository()
    doc_repo = DocumentRepository()

    vm = CreationViewModel(
        note_repo=note_repo,
        deck_repo=deck_repo,
        pipeline_repo=pipeline_repo,
        doc_repo=doc_repo,
        bus=bus,
    )

    # Initial data
    deck = deck_repo.create_deck("Biology")
    model = note_repo.create_note_type(name="Basic", fields_schema=["Front", "Back"], templates=[])

    vm.load_data()
    assert vm.selected_deck is not None
    assert vm.selected_deck.id == deck.id
    assert vm.selected_model is not None
    assert vm.selected_model.id == model.id

    # Source config
    vm.set_source("Cells Chapter", "Mitochondria is the powerhouse...", "text")
    assert vm.source_title == "Cells Chapter"
    assert "Mitochondria" in vm.source_content

    # Generated cards
    generated_cards = [
        {"Front": "What is Mitochondria?", "Back": "Powerhouse of the cell", "tags": ["cell", "organelle"]},
        {"Front": "What is Ribosome?", "Back": "Protein synthesis machine", "tags": ["cell", "ribosome"]},
    ]
    vm.set_generated_cards(generated_cards)
    assert len(vm.generated_cards) == 2
    assert vm.current_preview_index == 0

    # Card update
    vm.update_generated_card(0, {"Front": "What is Mitochondria (v2)?", "Back": "Cell powerhouse", "tags": ["cell"]})
    assert vm.generated_cards[0]["Front"] == "What is Mitochondria (v2)?"

    # Card removal
    vm.remove_generated_card(1)
    assert len(vm.generated_cards) == 1

    # Save cards & Event tracking
    published_events: list = []
    bus.subscribe(NoteCreatedEvent, lambda e: published_events.append(e))
    bus.subscribe(CardCreatedEvent, lambda e: published_events.append(e))

    saved_count = vm.save_all_cards()
    assert saved_count == 1
    assert len(vm.generated_cards) == 0
    assert len(published_events) == 2  # 1 NoteCreatedEvent + 1 CardCreatedEvent

    vm.dispose()
