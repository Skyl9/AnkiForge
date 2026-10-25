"""Unit tests for NoteRepository."""

from __future__ import annotations

import pytest

from ankiforge.database.models import DeckModel
from ankiforge.repositories.note_repository import NoteRepository

pytestmark = pytest.mark.integration


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
    assert note.sort_field == "What is mitochondria?"
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
    assert updated.sort_field == "What is mitochondria (updated)?"
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


def test_note_repository_sort_field_html_stripping_and_fallback() -> None:
    """Vérifie l'épuration HTML et le repli sur le premier champ non vide de sort_field."""
    repo = NoteRepository()
    deck = DeckModel.create(name="Science")
    note_type = repo.create_note_type(
        name="Science Model",
        fields_schema=["Front", "Back"],
        templates=[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}],
    )

    # 1. Épuration HTML
    note_html = repo.create_note(
        note_type=note_type,
        deck=deck,
        fields_data={"Front": "<b>Atome</b> &amp; <i>Molécule</i><br>", "Back": "Physique"},
    )
    assert note_html.sort_field == "Atome & Molécule"

    # 2. Repli si le premier champ est vide
    note_fallback = repo.create_note(
        note_type=note_type,
        deck=deck,
        fields_data={"Front": "   ", "Back": "Définition de secours"},
    )
    assert note_fallback.sort_field == "Définition de secours"

    # 3. Mise à jour via add_version
    note_fallback.add_version({"Front": "Nouveau Front Renseigné", "Back": "Suite"})
    reloaded = repo.get_note_by_id(note_fallback.id)
    assert reloaded is not None
    assert reloaded.sort_field == "Nouveau Front Renseigné"
