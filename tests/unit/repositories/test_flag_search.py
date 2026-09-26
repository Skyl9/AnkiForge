"""
Tests de recherche de cartes et notes par drapeaux (libellés standards et personnalisés).
Vérifie la syntaxe flag:X, -flag:X avec quotes et libellés multi-mots.
"""

from __future__ import annotations

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.repositories.note_repository import NoteRepository
from ankiforge.services.cards.flag_service import FlagService

pytestmark = pytest.mark.integration


@pytest.fixture
def sample_flagged_notes():
    """Crée 3 notes avec des drapeaux distincts (0, 1, 3)."""
    FlagService.reset_to_defaults()

    nt = NoteTypeModel.create(name="FlagSearchModel", fields_schema='["Front", "Back"]')
    deck = DeckModel.create(name="FlagSearchDeck")

    # Note 0 : Sans drapeau
    n0 = NoteModel.create(note_type=nt)
    NoteVersionModel.create(note=n0, content='{"Front": "Question Sans Drapeau", "Back": "R"}', is_active=True, version_number=1)
    CardModel.create(note=n0, deck=deck, template_index=0, flags=0)

    # Note 1 : Drapeau 1 (Rouge)
    n1 = NoteModel.create(note_type=nt)
    NoteVersionModel.create(note=n1, content='{"Front": "Question Rouge", "Back": "R"}', is_active=True, version_number=1)
    CardModel.create(note=n1, deck=deck, template_index=0, flags=1)

    # Note 3 : Drapeau 3 (Vert)
    n3 = NoteModel.create(note_type=nt)
    NoteVersionModel.create(note=n3, content='{"Front": "Question Verte", "Back": "R"}', is_active=True, version_number=1)
    CardModel.create(note=n3, deck=deck, template_index=0, flags=3)

    yield n0, n1, n3
    FlagService.reset_to_defaults()


def test_search_notes_standard_flags(sample_flagged_notes) -> None:
    """La recherche par nom de couleur standard ou index fonctionne."""
    n0, n1, n3 = sample_flagged_notes
    repo = NoteRepository()

    # Recherche flag:rouge ou flag:red ou flag:1
    res_red = repo.search_notes("flag:rouge")
    assert [n.id for n in res_red] == [n1.id]

    res_1 = repo.search_notes("flag:1")
    assert [n.id for n in res_1] == [n1.id]

    res_vert = repo.search_notes("flag:vert")
    assert [n.id for n in res_vert] == [n3.id]


def test_search_notes_custom_flag_labels(sample_flagged_notes) -> None:
    """La recherche par libellé personnalisé (simple ou multi-mots entre guillemets) fonctionne."""
    n0, n1, n3 = sample_flagged_notes
    repo = NoteRepository()

    # Personnalisation des drapeaux
    FlagService.set_flag_labels({1: "À revoir", 3: "Formule Complexe"})

    # Recherche avec slugifié / minuscules
    res_revoir = repo.search_notes("flag:à_revoir")
    assert [n.id for n in res_revoir] == [n1.id]

    # Recherche avec guillemets multi-mots
    res_multi = repo.search_notes('flag:"formule complexe"')
    assert [n.id for n in res_multi] == [n3.id]

    # Négation de libellé personnalisé
    res_neg = repo.search_notes("-flag:à_revoir")
    neg_ids = [n.id for n in res_neg]
    assert n1.id not in neg_ids
    assert n0.id in neg_ids
    assert n3.id in neg_ids
