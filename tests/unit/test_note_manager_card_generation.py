"""Tests unitaires pour la création conditionnelle de cartes par NoteManager (ADR 0037).

Vérifie :
1. Qu'un modèle avec carte inversée optionnelle n'engendre que la Carte 1 si le déclencheur est vide.
2. Qu'il engendre 2 cartes si le déclencheur et le verso sont non vides.
"""

import json

import pytest

from ankiforge.database.models import CardModel, DeckModel, NoteTypeModel
from ankiforge.services.cards.note_manager import NoteManager

pytestmark = pytest.mark.unit


def test_note_manager_optional_reversed_only_creates_active_card(mock_db):
    """Vérifie que NoteManager ne crée pas de CardModel pour les gabarits au recto vide."""
    deck = DeckModel.create(name="Défaut", anki_id=1)

    # Modèle 'Basique (carte inversée optionnelle)'
    templates = [
        {"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"},
        {"name": "Carte 2", "qfmt": "{{#Add Reverse}}{{Back}}{{/Add Reverse}}", "afmt": "{{Front}}"},
    ]
    nt = NoteTypeModel.create(
        name="Basique Inversé Optionnel",
        fields_schema=json.dumps(["Front", "Back", "Add Reverse"]),
        templates=json.dumps(templates),
        css_style="",
    )

    # 1. Note avec Add Reverse vide -> Une seule carte physique (template_index=0)
    note_single = NoteManager.create_note(
        note_type=nt,
        deck=deck,
        content_dict={"Front": "Question 1", "Back": "Réponse 1", "Add Reverse": ""},
    )
    cards_single = list(note_single.cards)
    assert len(cards_single) == 1
    assert cards_single[0].template_index == 0

    # 2. Note avec Add Reverse rempli -> Deux cartes physiques (template_index=0 et 1)
    note_double = NoteManager.create_note(
        note_type=nt,
        deck=deck,
        content_dict={"Front": "Question 2", "Back": "Réponse 2", "Add Reverse": "y"},
    )
    cards_double = list(note_double.cards.order_by(CardModel.template_index))
    assert len(cards_double) == 2
    assert cards_double[0].template_index == 0
    assert cards_double[1].template_index == 1
