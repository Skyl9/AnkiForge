"""Tests unitaires pour le suivi financier du linter (TokenSrsFinancialService)."""

from __future__ import annotations

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    TokenUsageModel,
)
from ankiforge.services.ai.linter import TokenSrsFinancialService

pytestmark = pytest.mark.unit


def _creer_carte(deck, note_type: NoteTypeModel) -> CardModel:
    note = NoteModel.create(deck=deck, note_type=note_type, fields={"Front": "Q", "Back": "A"})
    return CardModel.create(note=note, deck=deck, template_index=0)


def test_avg_cost_per_card_meme_perimetre_numerateur_denominateur() -> None:
    """avg_cost_per_card_usd doit rapporter le coût global au nombre global de cartes (même périmètre).

    Le bug consistait à diviser un total de dépense global par un nombre de cartes filtré par paquet.
    """
    deck_a = DeckModel.create(name="Deck A")
    deck_b = DeckModel.create(name="Deck B")
    note_type = NoteTypeModel.create(name="NT_Linter_Financial", fields_schema=["Front", "Back"])
    _creer_carte(deck_a, note_type)
    _creer_carte(deck_a, note_type)
    _creer_carte(deck_b, note_type)
    _creer_carte(deck_b, note_type)
    _creer_carte(deck_b, note_type)  # 5 cartes au total, 2 dans le deck A

    TokenUsageModel.create(
        provider="openai",
        model_id="gpt-4o",
        prompt_tokens=100,
        completion_tokens=100,
        total_tokens=200,
        estimated_cost_usd=0.10,
    )

    summary = TokenSrsFinancialService.get_financial_summary(deck_id=deck_a.id)

    assert summary["total_cards"] == 2  # dénominateur affiché reste filtré par paquet
    # Numérateur (dépense globale) et dénominateur (cartes globales) sur le même périmètre :
    # 0.10 $ / 5 cartes = 0.02 $, et non 0.10 $ / 2 cartes = 0.05 $ (ancien bug).
    assert abs(summary["avg_cost_per_card_usd"] - (0.10 / 5)) < 0.001


def test_avg_cost_sans_deck_coherence_globale() -> None:
    """Sans filtre de paquet, coût global divisé par nombre global de cartes."""
    deck = DeckModel.create(name="Deck Unique")
    note_type = NoteTypeModel.create(name="NT_Linter_Financial", fields_schema=["Front", "Back"])
    _creer_carte(deck, note_type)
    _creer_carte(deck, note_type)

    TokenUsageModel.create(
        provider="openai",
        model_id="gpt-4o",
        prompt_tokens=100,
        completion_tokens=100,
        total_tokens=200,
        estimated_cost_usd=0.10,
    )

    summary = TokenSrsFinancialService.get_financial_summary()

    assert summary["total_cards"] == 2
    assert abs(summary["avg_cost_per_card_usd"] - (0.10 / 2)) < 0.001
