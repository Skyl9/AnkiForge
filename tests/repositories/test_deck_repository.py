"""
Unit tests for DeckRepository.
"""

from __future__ import annotations

import pytest

from ankiforge.repositories.deck_repository import DeckRepository

pytestmark = pytest.mark.integration


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
    assert repo.get_deck_by_id(child1.id) is None


def test_deck_repository_delete_cascades_to_subdecks_and_cards() -> None:
    """Supprimer un paquet emporte sa sous-arborescence (préfixe hiérarchique) et leurs cartes."""
    repo = DeckRepository()
    from ankiforge.database.models import CardModel, NoteModel, NoteTypeModel

    parent = repo.create_deck("DeleteRoot", description="À supprimer")
    child = repo.create_deck("DeleteRoot::Child", description="Sous-paquet", parent_deck=parent)
    grandchild = repo.create_deck("DeleteRoot::Child::Leaf", description="Feuille", parent_deck=child)

    note_type = NoteTypeModel.create(name="DeckDeleteBasic", fields_schema='["Front", "Back"]', templates="[]")
    note = NoteModel.create(note_type=note_type, tags="")
    CardModel.create(note=note, deck=parent, template_index=0)
    CardModel.create(note=note, deck=grandchild, template_index=0)

    # Un paquet sans lien de préfixe n'est pas emporté.
    unrelated = repo.create_deck("DeleteOtherRoot")

    assert repo.delete_deck(parent.id) is True

    assert repo.get_deck_by_id(parent.id) is None
    assert repo.get_deck_by_id(child.id) is None
    assert repo.get_deck_by_id(grandchild.id) is None
    assert repo.get_deck_by_id(unrelated.id) is not None
    # Les cartes des paquets supprimés sont parties ; il n'en reste aucune.
    assert CardModel.select().count() == 0


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


def test_get_or_create_hierarchical_repairs_parent_link() -> None:
    """Un paquet créé à plat (ex: 'A::B' sans parent) doit être rattaché à son parent
    lors d'un appel hiérarchique ultérieur, sans dupliquer."""
    repo = DeckRepository()

    flat = repo.create_deck("Sciences::Physique")
    assert flat.parent_deck is None

    leaf = repo.get_or_create_deck_hierarchical("Sciences::Physique::Thermo")

    sciences = repo.get_deck_by_name("Sciences")
    physique = repo.get_deck_by_name("Sciences::Physique")
    assert sciences is not None and sciences.parent_deck is None
    assert physique is not None
    assert physique.parent_deck_id == sciences.id
    assert leaf.parent_deck_id == physique.id

    # Idempotence : un second appel ne duplique rien et conserve les liens
    again = repo.get_or_create_deck_hierarchical("Sciences::Physique::Thermo")
    assert again.id == leaf.id
    assert repo.get_deck_by_name("Sciences::Physique").parent_deck_id == sciences.id
