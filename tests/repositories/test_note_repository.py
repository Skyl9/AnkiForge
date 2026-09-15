"""
Unit tests for NoteRepository.
"""

from __future__ import annotations

from ankiforge.database.models import DeckModel
from ankiforge.repositories.note_repository import NoteRepository


def test_note_repository_crud() -> None:
    repo = NoteRepository()

    # Create Deck and NoteType
    deck = DeckModel.create(name="Biology::Cells")
    note_type = repo.create_note_type(
        name="Basic Model",
        fields_schema=["Front", "Back"],
        templates=[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Front}}<hr>{{Back}}"}],
    )

    assert repo.get_note_type_by_id(note_type.id) is not None
    assert repo.get_note_type_by_name("Basic Model") is not None
    assert len(repo.get_all_note_types()) == 1

    # Create Note
    note = repo.create_note(
        note_type=note_type,
        deck=deck,
        fields_data={"Front": "What is mitochondria?", "Back": "Powerhouse of the cell."},
        tags=["biology", "organelles"],
    )

    assert note is not None
    assert repo.get_note_by_id(note.id) is not None
    assert repo.get_note_by_guid(note.guid) is not None
    assert repo.count_notes() == 1
    assert repo.count_cards() == 1

    # Active version
    active_ver = repo.get_active_version(note)
    assert active_ver is not None
    assert active_ver.version_number == 1
    assert "mitochondria" in active_ver.content

    # Update note content
    updated = repo.update_note_content(
        note_id=note.id,
        fields_data={"Front": "What is mitochondria (updated)?", "Back": "Powerhouse."},
        tags=["biology", "cellular"],
    )
    assert updated is not None
    versions = repo.get_versions(note)
    assert len(versions) == 2
    active_ver2 = repo.get_active_version(note)
    assert active_ver2 is not None
    assert active_ver2.version_number == 2

    # Query by deck and model
    notes_by_deck = repo.get_notes_by_deck(deck.id)
    assert len(notes_by_deck) == 1
    notes_by_model = repo.get_notes_by_model(note_type.id)
    assert len(notes_by_model) == 1

    # Tags & Search
    tags = repo.get_all_tags()
    assert "biology" in tags
    assert "cellular" in tags

    search_res = repo.search_notes("mitochondria")
    assert len(search_res) == 1

    # Delete Note
    success = repo.delete_note(note.id)
    assert success is True
    assert repo.get_note_by_id(note.id) is None
    assert repo.count_notes() == 0
    assert repo.count_cards() == 0
