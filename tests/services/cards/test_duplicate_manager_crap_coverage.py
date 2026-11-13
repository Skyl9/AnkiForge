"""Tests de couverture ciblés pour DuplicateManager afin de résorber le risque CRAP."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from ankidraft.database.models import (
    CardModel,
    DeckModel,
    IgnoredDuplicateModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankidraft.services.cards.duplicate_manager import DuplicateManager, strip_html

pytestmark = pytest.mark.unit


def test_strip_html_helpers() -> None:
    """Couvre la fonction utilitaire strip_html de duplicate_manager."""
    assert strip_html(None) == ""
    assert strip_html("") == ""
    assert strip_html("<p>Texte avec <b>balises</b>&nbsp;et saut\nde ligne</p>") == "Texte avec balises et saut de ligne"


def test_find_duplicates_detection_and_ignore(mock_db: Any) -> None:
    """Couvre find_duplicates sur DuplicateManager (CC=23, anciennement CRAP=525.6)."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck_{uid}")
    nt = NoteTypeModel.create(
        name=f"Type_{uid}",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "C1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
        css_style="",
    )

    # Note 1 : Question originale
    n1 = NoteModel.create(guid=f"g1_{uid}", note_type=nt)
    NoteVersionModel.create(
        note=n1,
        content=json.dumps({"Front": "Quelle est la capitale de la France ?", "Back": "Paris"}),
        is_active=True,
    )
    CardModel.create(note=n1, deck=deck, template_index=0)

    # Note 2 : Doublon quasi identique
    n2 = NoteModel.create(guid=f"g2_{uid}", note_type=nt)
    NoteVersionModel.create(
        note=n2,
        content=json.dumps({"Front": "Quelle est la capitale de la France ?", "Back": "Paris."}),
        is_active=True,
    )
    CardModel.create(note=n2, deck=deck, template_index=0)

    # Note 3 : Note complètement différente
    n3 = NoteModel.create(guid=f"g3_{uid}", note_type=nt)
    NoteVersionModel.create(
        note=n3,
        content=json.dumps({"Front": "Formule chimique de l'eau ?", "Back": "H2O"}),
        is_active=True,
    )
    CardModel.create(note=n3, deck=deck, template_index=0)

    # 1. Recherche ciblée sur le paquet : 1 doublon détecté entre n1 et n2
    conflicts = DuplicateManager.find_duplicates(deck.id)
    assert len(conflicts) == 1
    detected_a, _, detected_b, _, score = conflicts[0]
    assert {detected_a.id, detected_b.id} == {n1.id, n2.id}
    assert score > 0.90

    # 2. Recherche globale avec deck_id = -1
    all_conflicts = DuplicateManager.find_duplicates(-1)
    assert len(all_conflicts) >= 1

    # 3. Ignorer le doublon via IgnoredDuplicateModel
    id_1, id_2 = min(n1.id, n2.id), max(n1.id, n2.id)
    IgnoredDuplicateModel.create(note_a=id_1, note_b=id_2)

    # Nouvelle recherche : le conflit est désormais ignoré
    conflicts_after_ignore = DuplicateManager.find_duplicates(deck.id)
    assert len(conflicts_after_ignore) == 0
