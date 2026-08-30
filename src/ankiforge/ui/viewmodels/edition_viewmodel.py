"""
ViewModel for Edition View, Card Browser, and Note Version Management.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from ankiforge.database.models import (
    DeckModel,
    NoteModel,
    NoteVersionModel,
)
from ankiforge.repositories.deck_repository import DeckRepository
from ankiforge.repositories.note_repository import NoteRepository
from ankiforge.ui.viewmodels.base import BaseViewModel
from ankiforge.utils.event_bus import (
    AppEventBus,
    NoteDeletedEvent,
    NoteUpdatedEvent,
)

logger = logging.getLogger(__name__)


class EditionViewModel(BaseViewModel):
    """Encapsulates state and reactive logic for browsing, searching, and editing notes."""

    data_loaded = Signal()
    note_selected = Signal(object, object)  # NoteModel | None, NoteVersionModel | None
    notes_list_updated = Signal(list)
    tags_updated = Signal(list)
    decks_updated = Signal(list)

    def __init__(
        self,
        note_repo: NoteRepository | None = None,
        deck_repo: DeckRepository | None = None,
        bus: AppEventBus | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(bus=bus, parent=parent)
        self._note_repo = note_repo or NoteRepository()
        self._deck_repo = deck_repo or DeckRepository()

        self._decks: list[DeckModel] = []
        self._selected_deck_id: int | None = None
        self._notes: list[NoteModel] = []
        self._selected_note: NoteModel | None = None
        self._active_version: NoteVersionModel | None = None
        self._all_tags: list[str] = []
        self._selected_tag: str | None = None
        self._search_query: str = ""

    @property
    def decks(self) -> list[DeckModel]:
        return self._decks

    @property
    def notes(self) -> list[NoteModel]:
        return self._notes

    @property
    def selected_note(self) -> NoteModel | None:
        return self._selected_note

    @property
    def active_version(self) -> NoteVersionModel | None:
        return self._active_version

    @property
    def all_tags(self) -> list[str]:
        return self._all_tags

    def load_data(self) -> None:
        """Load decks, tags, and initial notes."""
        try:
            self._decks = self._deck_repo.get_all_decks()
            self._all_tags = self._note_repo.get_all_tags()
            self.refresh_notes()
            self.decks_updated.emit(self._decks)
            self.tags_updated.emit(self._all_tags)
            self.data_loaded.emit()
        except Exception as e:
            self.set_error(f"Failed to load edition data: {e}")

    def refresh_notes(self) -> None:
        """Refresh notes list based on search and deck filters."""
        if self._search_query:
            self._notes = self._note_repo.search_notes(self._search_query)
        elif self._selected_deck_id:
            self._notes = self._note_repo.get_notes_by_deck(self._selected_deck_id)
        else:
            self._notes = self._note_repo.get_all_notes(limit=300)

        self.notes_list_updated.emit(self._notes)

    def select_deck(self, deck_id: int | None) -> None:
        """Filter notes by deck ID."""
        self._selected_deck_id = deck_id
        self.refresh_notes()

    def set_search_query(self, query: str) -> None:
        """Filter notes by text query."""
        self._search_query = query.strip()
        self.refresh_notes()

    def select_note_by_id(self, note_id: int) -> None:
        """Select a note and load its active version."""
        note = self._note_repo.get_note_by_id(note_id)
        self._selected_note = note
        if note:
            self._active_version = self._note_repo.get_active_version(note)
        else:
            self._active_version = None

        self.note_selected.emit(self._selected_note, self._active_version)

    def save_note_content(self, note_id: int, fields_data: dict[str, str], tags: list[str] | None = None) -> bool:
        """Save a new version for the edited note."""
        updated = self._note_repo.update_note_content(
            note_id=note_id,
            fields_data=fields_data,
            tags=tags,
            source="manual",
        )
        if updated:
            self._selected_note = updated
            self._active_version = self._note_repo.get_active_version(updated)
            self.publish_event(
                NoteUpdatedEvent(
                    note_id=note_id,
                    version_number=self._active_version.version_number if self._active_version else 1,
                )
            )
            self.note_selected.emit(self._selected_note, self._active_version)
            self.refresh_notes()
            return True
        return False

    def delete_selected_note(self) -> bool:
        """Delete currently selected note."""
        if not self._selected_note:
            return False

        note_id = self._selected_note.id
        success = self._note_repo.delete_note(note_id)
        if success:
            self.publish_event(NoteDeletedEvent(note_id=note_id))
            self._selected_note = None
            self._active_version = None
            self.note_selected.emit(None, None)
            self.refresh_notes()
        return success
