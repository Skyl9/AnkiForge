"""
Tests unitaires pour les outils de contrôle qualité et de diagnostic 360° du Consultant IA.
"""

import json
import uuid

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.ai.consultant_engine import ConsultantToolRegistry


@pytest.fixture
def sample_data():
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck 360 {uid}")
    nt = NoteTypeModel.create(
        name=f"NoteType 360 {uid}",
        fields_schema='["Front", "Back"]',
        templates="[]",
        css_style=".card { font-size: 14px; }",
    )
    doc = DocumentModel.create(title=f"Doc 360 {uid}", file_path=f"/path/{uid}.pdf", format="pdf")

    # Carte 1 normale
    note1 = NoteModel.create(guid=f"g1_{uid}", note_type=nt, tags="tag1 tag2")
    NoteVersionModel.create(note=note1, version_number=1, content='{"Front": "Question courte", "Back": "Reponse claire"}', is_active=True)
    card1 = CardModel.create(note=note1, deck=deck, reps=4, lapses=0, ivl=10)

    # Carte 2 sangsue et verbeuse (pour audit Wozniak)
    note2 = NoteModel.create(guid=f"g2_{uid}", note_type=nt, tags="tag2 sangsue")
    long_front = "Voici une question extrêmement longue avec beaucoup trop de détails inutiles pour tester l'atomicité de la carte mémoire."
    long_back = "Voici une réponse détaillée comportant une liste :\n- Point 1\n- Point 2\n- Point 3"
    NoteVersionModel.create(note=note2, version_number=1, content=json.dumps({"Front": long_front, "Back": long_back}), is_active=True)
    card2 = CardModel.create(note=note2, deck=deck, reps=10, lapses=5, ivl=1)

    return {
        "uid": uid,
        "deck": deck,
        "nt": nt,
        "doc": doc,
        "note1": note1,
        "note2": note2,
        "card1": card1,
        "card2": card2,
    }


def test_get_collection_panorama_360(sample_data):
    panorama = ConsultantToolRegistry.get_collection_panorama_360()
    assert "Panorama 360° de la Collection AnkiForge" in panorama
    assert "Total Paquets :" in panorama
    assert "Total Cartes :" in panorama
    assert "Cartes Sangsues globales" in panorama


def test_inspect_deck_deep_scan(sample_data):
    deck = sample_data["deck"]
    scan = ConsultantToolRegistry.inspect_deck_deep_scan(deck.name)
    assert f"Deep Scan du Paquet '{deck.name}'" in scan
    assert "Apprentissage" in scan
    assert "Top cartes sangsues" in scan


def test_inspect_deck_deep_scan_non_existent():
    res = ConsultantToolRegistry.inspect_deck_deep_scan("Paquet_Totalement_Inconnu_XYZ")
    assert "Erreur" in res or "n'existe pas" in res


def test_audit_deck_wozniak(sample_data):
    deck = sample_data["deck"]
    res = ConsultantToolRegistry.audit_deck_wozniak(deck.name)
    assert "Rapport d'Audit Qualité Wozniak" in res
    assert "Score de conformité global" in res


def test_audit_card_wozniak(sample_data):
    note = sample_data["note2"]
    res = ConsultantToolRegistry.audit_card_wozniak(note.id)
    assert "Audit Wozniak de la Note" in res
    assert "Règle #4 (Atomicité)" in res or "Score Qualité" in res


def test_find_duplicate_cards(sample_data):
    deck = sample_data["deck"]
    res = ConsultantToolRegistry.find_duplicate_cards(deck.name, threshold=0.8)
    assert "doublon" in res.lower() or "similarité" in res.lower()


def test_propose_card_refactor_garde_fou(sample_data):
    note = sample_data["note1"]
    new_data = {"Front": "Question Reformulée", "Back": "Réponse Optimisée"}
    res = ConsultantToolRegistry.propose_card_refactor(note.id, json.dumps(new_data), explanation="Simplification")

    parsed = json.loads(res)
    assert parsed.get("status") == "staged_diff"
    assert parsed.get("type") == "card"
    assert parsed.get("note_id") == note.id
    assert parsed.get("modified") == new_data

    # Vérifier que la BDD n'a PAS été modifiée (Garde-fou)
    v_active = NoteVersionModel.get(note=note, is_active=True)
    assert "Question courte" in v_active.content


def test_propose_card_split_garde_fou(sample_data):
    note = sample_data["note2"]
    atomic_cards = [
        {"Front": "Partie 1", "Back": "Réponse 1"},
        {"Front": "Partie 2", "Back": "Réponse 2"},
    ]
    res = ConsultantToolRegistry.propose_card_split(note.id, json.dumps(atomic_cards), explanation="Scission atomique")

    parsed = json.loads(res)
    assert parsed.get("status") == "staged_diff"
    assert parsed.get("type") == "split"
    assert len(parsed.get("modified")) == 2

    # Vérifier que la note originale n'est PAS encore archivée
    reloaded_note = NoteModel.get_by_id(note.id)
    assert reloaded_note.status != "archived"


def test_propose_css_tune_garde_fou(sample_data):
    nt = sample_data["nt"]
    res = ConsultantToolRegistry.propose_css_tune(nt.name, ".card.highlight { color: #8b5cf6; }")

    parsed = json.loads(res)
    assert parsed.get("status") == "staged_diff"
    assert parsed.get("type") == "css"
