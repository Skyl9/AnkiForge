"""
Unit tests for DeckRepository.
"""

from __future__ import annotations

from ankiforge.repositories.deck_repository import DeckRepository


def test_deck_repository_crud() -> None:
    repo = DeckRepository()

    # Create parent and child decks
    parent = repo.create_deck("Science", description="All science topics")
    child1 = repo.create_deck("Science::Physics", description="Physics", parent_deck=parent)
    repo.create_deck("Science::Chemistry", description="Chemistry", parent_deck=parent)

    assert repo.get_deck_by_id(parent.id) is not None
    assert repo.get_deck_by_name("Science::Physics") is not None
    assert len(repo.get_all_decks()) == 3

    # get_or_create
    existing = repo.get_or_create_deck("Science")
    assert existing.id == parent.id

    new_deck = repo.get_or_create_deck("Literature")
    assert new_deck.id != parent.id

    # get_descendant_decks
    descendants = repo.get_descendant_decks("Science")
    assert len(descendants) == 3

    # rename deck and verify child prefix propagation
    renamed = repo.rename_deck(parent.id, "NaturalScience")
    assert renamed is not None
    assert renamed.name == "NaturalScience"

    child1_refreshed = repo.get_deck_by_id(child1.id)
    assert child1_refreshed is not None
    assert child1_refreshed.name == "NaturalScience::Physics"

    # delete deck
    deleted = repo.delete_deck(parent.id)
    assert deleted is True
    assert repo.get_deck_by_id(parent.id) is None


def test_deck_repository_get_or_create_hierarchical() -> None:
    repo = DeckRepository()

    # Création d'une hiérarchie à 3 niveaux
    leaf = repo.get_or_create_deck_hierarchical("Langues::Japonais::Grammaire", description="Grammaire JLPT")
    assert leaf is not None
    assert leaf.name == "Langues::Japonais::Grammaire"
    assert leaf.description == "Grammaire JLPT"

    # Vérification des paquets parents automatiques
    japonais = repo.get_deck_by_name("Langues::Japonais")
    assert japonais is not None
    assert leaf.parent_deck.id == japonais.id

    langues = repo.get_deck_by_name("Langues")
    assert langues is not None
    assert japonais.parent_deck.id == langues.id
    assert langues.parent_deck is None

    # Idempotence : appel récurrent ne recrée rien
    same_leaf = repo.get_or_create_deck_hierarchical("Langues::Japonais::Grammaire")
    assert same_leaf.id == leaf.id
