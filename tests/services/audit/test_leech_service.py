"""
Tests unitaires pour LeechService (détection des cartes sangsues et métriques de rechutes).
"""

from __future__ import annotations

import json

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.audit.leech_service import LeechService

pytestmark = pytest.mark.integration


def test_leech_service_empty_db() -> None:
    assert LeechService.get_leech_cards() == []
    assert LeechService.count_leeches() == 0


def test_leech_service_strict_mode_anki_tag() -> None:
    deck = DeckModel.create(name="Informatique")
    nt = NoteTypeModel.create(name="Basic", fields_schema=json.dumps(["Recto", "Verso"]))

    # Note 1 : tagguée 'leech' par Anki
    n1 = NoteModel.create(note_type=nt, tags=json.dumps(["leech", "algo"]))
    NoteVersionModel.create(
        note=n1,
        version_number=1,
        content=json.dumps({"Recto": "Complexité Quicksort ?", "Verso": "O(n log n)"}),
        is_active=True,
    )
    c1 = CardModel.create(
        note=n1,
        deck=deck,
        template_index=0,
        lapses=8,
        stability=1.2,
        difficulty=7.5,
        ivl=3,
    )

    # Note 2 : fort taux d'échecs (lapses=5) MAIS PAS encore de tag 'leech'
    n2 = NoteModel.create(note_type=nt, tags=json.dumps(["algo"]))
    NoteVersionModel.create(
        note=n2,
        version_number=1,
        content=json.dumps({"Recto": "Tri fusion ?", "Verso": "O(n log n)"}),
        is_active=True,
    )
    c2 = CardModel.create(
        note=n2,
        deck=deck,
        template_index=0,
        lapses=5,
        stability=1.8,
        difficulty=6.0,
        ivl=4,
    )

    # Note 3 : carte saine (lapses=0)
    n3 = NoteModel.create(note_type=nt, tags=json.dumps(["math"]))
    NoteVersionModel.create(
        note=n3,
        version_number=1,
        content=json.dumps({"Recto": "1+1 ?", "Verso": "2"}),
        is_active=True,
    )
    CardModel.create(
        note=n3,
        deck=deck,
        template_index=0,
        lapses=0,
        stability=15.0,
        difficulty=2.0,
        ivl=30,
    )

    # En mode strict (include_high_lapses=False) -> Seule la carte tagguée 'leech' remonte
    results_strict = LeechService.get_leech_cards(include_high_lapses=False)
    assert len(results_strict) == 1
    assert results_strict[0]["card_id"] == c1.id
    assert results_strict[0]["note_id"] == n1.id
    assert results_strict[0]["is_leech_tagged"] is True
    assert results_strict[0]["lapses"] == 8
    assert "Quicksort" in results_strict[0]["front_snippet"]
    assert LeechService.count_leeches(include_high_lapses=False) == 1

    # En mode dual (include_high_lapses=True, seuil=4) -> n1 et n2 remontent
    results_dual = LeechService.get_leech_cards(include_high_lapses=True, lapse_threshold=4)
    assert len(results_dual) == 2
    ids = [r["card_id"] for r in results_dual]
    assert c1.id in ids
    assert c2.id in ids
    assert LeechService.count_leeches(include_high_lapses=True, lapse_threshold=4) == 2


def test_leech_service_deck_filter_and_sorting() -> None:
    deck1 = DeckModel.create(name="Deck A")
    deck2 = DeckModel.create(name="Deck B")
    nt = NoteTypeModel.create(name="Basic", fields_schema=json.dumps(["Recto", "Verso"]))

    # Card 1 dans Deck A (lapses=4, stability=2.0)
    n1 = NoteModel.create(note_type=nt, tags=json.dumps(["leech"]))
    NoteVersionModel.create(
        note=n1,
        version_number=1,
        content=json.dumps({"Recto": "Question A1", "Verso": "Reponse A1"}),
        is_active=True,
    )
    c1 = CardModel.create(note=n1, deck=deck1, lapses=4, stability=2.0)

    # Card 2 dans Deck A (lapses=10, stability=0.8) -> Plus critique
    n2 = NoteModel.create(note_type=nt, tags=json.dumps(["leech"]))
    NoteVersionModel.create(
        note=n2,
        version_number=1,
        content=json.dumps({"Recto": "Question A2", "Verso": "Reponse A2"}),
        is_active=True,
    )
    c2 = CardModel.create(note=n2, deck=deck1, lapses=10, stability=0.8)

    # Card 3 dans Deck B (lapses=9, stability=1.0)
    n3 = NoteModel.create(note_type=nt, tags=json.dumps(["leech"]))
    NoteVersionModel.create(
        note=n3,
        version_number=1,
        content=json.dumps({"Recto": "Question B1", "Verso": "Reponse B1"}),
        is_active=True,
    )
    c3 = CardModel.create(note=n3, deck=deck2, lapses=9, stability=1.0)

    # Tri global : c2 (lapses=10) puis c3 (lapses=9) puis c1 (lapses=4)
    all_leeches = LeechService.get_leech_cards()
    assert len(all_leeches) == 3
    assert [r["card_id"] for r in all_leeches] == [c2.id, c3.id, c1.id]

    # Filtrage par deck : Deck A uniquement
    deck_a_leeches = LeechService.get_leech_cards(deck_id=deck1.id)
    assert len(deck_a_leeches) == 2
    assert [r["card_id"] for r in deck_a_leeches] == [c2.id, c1.id]

    # Filtrage Deck B
    deck_b_leeches = LeechService.get_leech_cards(deck_id=deck2.id)
    assert len(deck_b_leeches) == 1
    assert deck_b_leeches[0]["card_id"] == c3.id


def test_leech_service_split_proposal_and_two_phase_commit() -> None:
    from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

    deck = DeckModel.create(name="Philosophie")
    nt = NoteTypeModel.create(name="Basic", fields_schema=json.dumps(["Recto", "Verso"]))
    note = NoteModel.create(note_type=nt, tags=json.dumps(["leech"]))
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps(
            {
                "Recto": "Expliquer l'allégorie de la caverne de Platon et le monde des idées.",
                "Verso": "Platon décrit des prisonniers enchaînés voyant des ombres. Le monde intelligible est supérieur.",
            }
        ),
        is_active=True,
    )
    CardModel.create(note=note, deck=deck, lapses=9, stability=0.9)

    assert LeechService.count_leeches() == 1

    # 1. Génération de proposition de scission atomique
    subcards = [
        {"Recto": "Que voient les prisonniers dans l'allégorie de la caverne ?", "Verso": "Des ombres projetées sur le mur."},
        {"Recto": "Que représente la sortie de la caverne selon Platon ?", "Verso": "L'accession au monde intelligible des Idées."},
    ]
    proposal = LeechService.generate_split_proposal(
        note_id=note.id,
        subcards=subcards,
        explanation="Scission en 2 cartes atomiques selon la règle 4 de Wozniak",
    )
    assert proposal["status"] == "staged_diff"
    patch_id = proposal["patch_id"]
    assert patch_id.startswith("patch_")

    # 2. Application du patch (Two-Phase Commit)
    apply_result = StagedPatchRegistry.apply_staged_patch(patch_id)
    assert apply_result["status"] == "applied"

    # Vérification : note parente archivée et nouvelles notes créées dans le même deck
    reloaded_parent = NoteModel.get_by_id(note.id)
    assert reloaded_parent.status == "archived"

    new_notes = list(NoteModel.select().where(NoteModel.id.in_(apply_result["created_note_ids"])))
    assert len(new_notes) == 2
    for nn in new_notes:
        assert nn.cards.first().deck_id == deck.id
        assert nn.cards.first().lapses == 0  # Nouvelles cartes remises à zéro

    # La note parente étant archivée, elle ne doit plus ressortir dans les sangsues actives
    assert LeechService.count_leeches() == 0
