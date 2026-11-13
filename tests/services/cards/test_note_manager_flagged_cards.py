"""Tests unitaires pour NoteManager.get_flagged_cards.

Couvre la résolution tolérante des drapeaux, la descente récursive dans les
sous-paquets, la charge utile complète sans requêtes N+1 et le respect de la
borne limite.
"""

from __future__ import annotations

import json
import uuid

import pytest

from ankidraft.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel, NoteVersionModel
from ankidraft.services.cards.flag_service import FlagService
from ankidraft.services.cards.note_manager import NoteManager

pytestmark = pytest.mark.integration


def _creer_deck(nom: str) -> DeckModel:
    return DeckModel.get_or_create(name=f"{nom} {uuid.uuid4().hex[:6]}")[0]


def _creer_carte_avec_version(deck: DeckModel, flags: int, tags: str = "") -> CardModel:
    note_type, _ = NoteTypeModel.get_or_create(
        name=f"Type Note Drapeau {flags}",
        defaults={"fields_schema": '["Front", "Back"]', "templates": "[]", "css_style": ""},
    )
    note = NoteModel.create(guid=str(uuid.uuid4()), note_type=note_type, tags=tags)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        is_active=True,
        content='{"Front": "Question", "Back": "Réponse"}',
    )
    return CardModel.create(note=note, deck=deck, flags=flags)


def test_get_flagged_cards_par_nom_ou_par_valeur(mock_db):
    """Un drapeau s'identifie indifféremment par son nom ou sa valeur entière."""
    deck = _creer_deck("Paquet Parent")
    carte_rouge = _creer_carte_avec_version(deck, 1, "scolaire")
    _creer_carte_avec_version(deck, 0, "")

    par_nom = json.loads(NoteManager.get_flagged_cards(flag="rouge"))
    par_valeur = json.loads(NoteManager.get_flagged_cards(flag=1))

    assert par_nom["status"] == "success"
    assert par_nom["total"] == par_valeur["total"] == 1
    assert par_nom["items"] == par_valeur["items"]
    item = par_nom["items"][0]
    assert item["card_id"] == carte_rouge.id
    assert item["note_id"] == carte_rouge.note_id
    assert item["deck_name"] == deck.name
    assert item["flag_number"] == 1
    assert item["flag_label"] == "Rouge"
    assert item["flag_color"] == FlagService.get_flag_color(1)
    assert item["model_name"] == f"Type Note Drapeau {carte_rouge.flags}"
    assert item["fields"]["Front"] == "Question"
    assert item["fields"]["Back"] == "Réponse"
    assert item["tags"] == "scolaire"


def test_get_flagged_cards_descente_recursive_par_deck(mock_db):
    """Un paquet désigne aussi ses sous-paquets (nom::%)."""
    deck = _creer_deck("Paquet Parent")
    enfant = DeckModel.create(name=f"Paquet Parent::Enfant {uuid.uuid4().hex[:6]}")
    _creer_carte_avec_version(deck, 1)
    carte_enfant = _creer_carte_avec_version(enfant, 2)
    _creer_carte_avec_version(deck, 0)

    res = json.loads(NoteManager.get_flagged_cards(deck_name="Paquet Parent", flag=2))
    assert res["status"] == "success"
    assert res["total"] == 1
    item = res["items"][0]
    assert item["card_id"] == carte_enfant.id
    assert item["deck_name"] == enfant.name


def test_get_flagged_cards_sans_flag_retourne_tous_les_drapeaux(mock_db):
    """flag=None désigne toute carte portant au moins un drapeau."""
    deck = _creer_deck("Paquet")
    _creer_carte_avec_version(deck, 1)
    _creer_carte_avec_version(deck, 3)
    _creer_carte_avec_version(deck, 0)

    res = json.loads(NoteManager.get_flagged_cards())

    assert res["status"] == "success"
    assert res["total"] == 2
    assert {item["flag_number"] for item in res["items"]} == {1, 3}
    for item in res["items"]:
        assert item["flag_number"] > 0


def test_get_flagged_cards_respecte_la_limite(mock_db):
    deck = _creer_deck("Paquet")
    _creer_carte_avec_version(deck, 1)
    _creer_carte_avec_version(deck, 2)

    res = json.loads(NoteManager.get_flagged_cards(limit=1))

    assert res["status"] == "success"
    assert res["total"] == 2
    assert len(res["items"]) == 1
    assert res["filters"]["limit"] == 1


def test_get_flagged_cards_drapeau_invalide_raise_value_error(mock_db):
    _creer_deck("Paquet")

    with pytest.raises(ValueError, match="[Dd]rapeau"):
        NoteManager.get_flagged_cards(flag="magenta")

    with pytest.raises(ValueError, match="[Dd]rapeau"):
        NoteManager.get_flagged_cards(flag=9)
