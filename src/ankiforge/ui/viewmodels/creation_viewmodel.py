"""
ViewModel for Creation Studio, AI Flashcard Ingestion, and Review.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, Signal

from ankiforge.database.models import (
    DeckModel,
    NoteTypeModel,
    PipelineModel,
)
from ankiforge.repositories.deck_repository import DeckRepository
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.repositories.note_repository import NoteRepository
from ankiforge.repositories.pipeline_repository import PipelineRepository
from ankiforge.ui.viewmodels.base import BaseViewModel
from ankiforge.utils.event_bus import (
    AppEventBus,
    CardCreatedEvent,
    NoteCreatedEvent,
)

logger = logging.getLogger(__name__)


class CreationViewModel(BaseViewModel):
    """Encapsulates state and reactive logic for document source selection and flashcard generation."""

    data_loaded = Signal()
    deck_selected = Signal(object)
    model_selected = Signal(object)
    pipeline_selected = Signal(object)
    source_content_changed = Signal(str, str)
    cards_generated = Signal(list)
    card_updated = Signal(int, dict)
    card_removed = Signal(int)
    preview_index_changed = Signal(int, dict)
    cards_saved = Signal(int)
    generation_progress = Signal(int, str)

    def __init__(
        self,
        note_repo: NoteRepository | None = None,
        deck_repo: DeckRepository | None = None,
        pipeline_repo: PipelineRepository | None = None,
        doc_repo: DocumentRepository | None = None,
        bus: AppEventBus | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(bus=bus, parent=parent)
        self._note_repo = note_repo or NoteRepository()
        self._deck_repo = deck_repo or DeckRepository()
        self._pipeline_repo = pipeline_repo or PipelineRepository()
        self._doc_repo = doc_repo or DocumentRepository()

        self._decks: list[DeckModel] = []
        self._selected_deck: DeckModel | None = None
        self._models: list[NoteTypeModel] = []
        self._selected_model: NoteTypeModel | None = None
        self._selected_models: list[NoteTypeModel] = []
        self._pipelines: list[PipelineModel] = []
        self._selected_pipeline: PipelineModel | None = None

        self._source_title: str = "Saisie Libre"
        self._source_content: str = ""
        self._source_type: str = "text"
        self._page_ranges: str = ""
        self._card_count_target: int = 10
        self._chunk_size: int = 2500

        self._generated_cards: list[dict[str, Any]] = []
        self._current_preview_index: int = 0

    @property
    def decks(self) -> list[DeckModel]:
        return self._decks

    @property
    def selected_deck(self) -> DeckModel | None:
        return self._selected_deck

    @property
    def models(self) -> list[NoteTypeModel]:
        return self._models

    @property
    def selected_model(self) -> NoteTypeModel | None:
        return self._selected_model

    @property
    def selected_models(self) -> list[NoteTypeModel]:
        return self._selected_models

    @property
    def pipelines(self) -> list[PipelineModel]:
        return self._pipelines

    @property
    def selected_pipeline(self) -> PipelineModel | None:
        return self._selected_pipeline

    @property
    def source_title(self) -> str:
        return self._source_title

    @property
    def source_content(self) -> str:
        return self._source_content

    @property
    def source_type(self) -> str:
        return self._source_type

    @property
    def generated_cards(self) -> list[dict[str, Any]]:
        return self._generated_cards

    @property
    def current_preview_index(self) -> int:
        return self._current_preview_index

    def load_data(self) -> None:
        """Load decks, note types, and pipelines."""
        try:
            self._decks = self._deck_repo.get_all_decks()
            self._models = self._note_repo.get_all_note_types()
            self._pipelines = self._pipeline_repo.get_all_pipelines()

            if self._decks and (self._selected_deck is None or self._selected_deck not in self._decks):
                self.select_deck_by_id(self._decks[0].id)

            if self._models and (self._selected_model is None or self._selected_model not in self._models):
                self.select_model_by_id(self._models[0].id)

            if self._pipelines and (self._selected_pipeline is None or self._selected_pipeline not in self._pipelines):
                self.select_pipeline_by_id(self._pipelines[0].id)

            self.data_loaded.emit()
        except Exception as e:
            self.set_error(f"Failed to load creation data: {e}")

    def select_deck_by_id(self, deck_id: int) -> None:
        """Select deck by ID."""
        deck = self._deck_repo.get_deck_by_id(deck_id)
        if deck:
            self._selected_deck = deck
            self.deck_selected.emit(deck)

    def select_model_by_id(self, model_id: int) -> None:
        """Select note type by ID."""
        model = self._note_repo.get_note_type_by_id(model_id)
        if model:
            self._selected_model = model
            self.model_selected.emit(model)

    def set_selected_models(self, models: list[NoteTypeModel]) -> None:
        """Set multi-selected target models."""
        self._selected_models = list(models)
        if models and (self._selected_model not in models):
            self.select_model_by_id(models[0].id)

    def select_pipeline_by_id(self, pipeline_id: int) -> None:
        """Select pipeline by ID."""
        pipeline = self._pipeline_repo.get_pipeline_by_id(pipeline_id)
        if pipeline:
            self._selected_pipeline = pipeline
            self.pipeline_selected.emit(pipeline)

    def set_source(self, title: str, content: str, source_type: str = "text") -> None:
        """Set source document or text."""
        self._source_title = title
        self._source_content = content
        self._source_type = source_type
        self.source_content_changed.emit(title, content)

    def set_card_count_target(self, count: int) -> None:
        """Set target number of flashcards to generate."""
        self._card_count_target = max(1, count)

    def set_generated_cards(self, cards: list[dict[str, Any]]) -> None:
        """Set full list of generated flashcards."""
        self._generated_cards = list(cards)
        self._current_preview_index = 0
        self.cards_generated.emit(self._generated_cards)
        if self._generated_cards:
            self.preview_index_changed.emit(0, self._generated_cards[0])
        else:
            self.preview_index_changed.emit(-1, {})

    def update_generated_card(self, index: int, card_data: dict[str, Any]) -> None:
        """Update fields of a generated card."""
        if 0 <= index < len(self._generated_cards):
            self._generated_cards[index] = card_data
            self.card_updated.emit(index, card_data)
            if index == self._current_preview_index:
                self.preview_index_changed.emit(index, card_data)

    def remove_generated_card(self, index: int) -> None:
        """Remove a card from the generated list."""
        if 0 <= index < len(self._generated_cards):
            self._generated_cards.pop(index)
            self.card_removed.emit(index)
            if self._generated_cards:
                new_idx = max(0, min(self._current_preview_index, len(self._generated_cards) - 1))
                self.select_preview_card(new_idx)
            else:
                self._current_preview_index = -1
                self.preview_index_changed.emit(-1, {})

    def select_preview_card(self, index: int) -> None:
        """Select a card for visual preview."""
        if 0 <= index < len(self._generated_cards):
            self._current_preview_index = index
            self.preview_index_changed.emit(index, self._generated_cards[index])

    def save_all_cards(
        self,
        deck: DeckModel | None = None,
        model: NoteTypeModel | None = None,
    ) -> int:
        """Save all generated cards into SQLite database."""
        target_deck = deck or self._selected_deck
        target_model = model or self._selected_model

        if not target_deck or not target_model:
            self.set_error("No target deck or model selected.")
            return 0

        saved_count = 0
        for card_data in self._generated_cards:
            try:
                # Extract fields and tags
                fields = {k: str(v) for k, v in card_data.items() if k not in ["tags", "note_type", "deck", "chunk_id", "source_doc_id"]}
                raw_tags = card_data.get("tags", [])
                tags = raw_tags if isinstance(raw_tags, list) else str(raw_tags).split()

                note = self._note_repo.create_note(
                    note_type=target_model,
                    deck=target_deck,
                    fields_data=fields,
                    tags=tags,
                    status="new",
                    source="ai",
                )
                self.publish_event(
                    NoteCreatedEvent(
                        note_id=note.id,
                        deck_name=target_deck.name,
                        tags=tags,
                    )
                )
                cards = self._note_repo.get_cards_by_note(note.id)
                for c in cards:
                    self.publish_event(
                        CardCreatedEvent(
                            card_id=c.id,
                            note_id=note.id,
                            deck_name=target_deck.name,
                        )
                    )
                saved_count += 1
            except Exception as e:
                logger.error("Failed to save generated card: %s", e)

        self.cards_saved.emit(saved_count)
        self.clear_generated_cards()
        return saved_count

    def clear_generated_cards(self) -> None:
        """Clear generated cards."""
        self._generated_cards = []
        self._current_preview_index = -1
        self.cards_generated.emit([])
        self.preview_index_changed.emit(-1, {})
