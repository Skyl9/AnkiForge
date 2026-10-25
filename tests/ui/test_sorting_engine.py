"""Tests unitaires pour le moteur de tri Peewee multi-critères (ADR 0044).

Valide exhaustivement SortDirection, SortCriterion, SortOrder et apply_query_sorting
pour les modes Notes et Cartes avec clé de départage déterministe (sort_field, id).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import peewee
import pytest

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.ui.models.sorting import (
    SortCriterion,
    SortDirection,
    SortOrder,
    apply_query_sorting,
)

pytestmark = pytest.mark.ui


def test_sort_direction_properties_and_toggle() -> None:
    """Vérifie le comportement de SortDirection (is_asc, is_desc, toggle)."""
    asc = SortDirection.ASC
    assert asc.is_asc is True
    assert asc.is_desc is False
    assert asc.toggle() == SortDirection.DESC

    desc = SortDirection.DESC
    assert desc.is_asc is False
    assert desc.is_desc is True
    assert desc.toggle() == SortDirection.ASC


def test_sort_order_defaults_and_serialization() -> None:
    """Vérifie la création, bascule et sérialisation/désérialisation de SortOrder."""
    default_notes = SortOrder.default_for_mode("notes")
    assert default_notes.criterion == SortCriterion.CREATED_AT
    assert default_notes.direction == SortDirection.ASC

    toggled = default_notes.toggled()
    assert toggled.direction == SortDirection.DESC
    assert toggled.criterion == SortCriterion.CREATED_AT

    # with_criterion
    recto_order = default_notes.with_criterion(SortCriterion.RECTO)
    assert recto_order.criterion == SortCriterion.RECTO
    assert recto_order.direction == SortDirection.ASC

    lapses_order = default_notes.with_criterion(SortCriterion.LAPSES)
    assert lapses_order.criterion == SortCriterion.LAPSES
    assert lapses_order.direction == SortDirection.DESC  # Direction sémantique par défaut

    # to_dict et from_dict
    custom = SortOrder(criterion=SortCriterion.SPECIFIC_FIELD, direction=SortDirection.DESC, field_name="Front")
    data = custom.to_dict()
    assert data == {
        "criterion": "field",
        "direction": "desc",
        "field_name": "Front",
    }
    restored = SortOrder.from_dict(data)
    assert restored == custom

    # from_dict avec valeurs corrompues ou None
    assert SortOrder.from_dict(None) == SortOrder()
    assert SortOrder.from_dict({"criterion": "invalide", "direction": "invalide"}).criterion == SortCriterion.CREATED_AT


@pytest.fixture
def sample_sorting_data(mock_db: Any) -> dict[str, Any]:
    """Crée un ensemble représentatif de notes et cartes pour valider tous les critères de tri."""
    uid = uuid.uuid4().hex[:6]
    deck_a = DeckModel.create(name=f"Deck A {uid}")
    deck_b = DeckModel.create(name=f"Deck B {uid}")

    nt_basic = NoteTypeModel.create(name=f"Type Basic {uid}")
    nt_cloze = NoteTypeModel.create(name=f"Type Cloze {uid}")

    # Note 1 : Pomme, Basic, Deck B, lapses=10, flags=3, suspended=False
    n1 = NoteModel.create(
        guid=f"n1_{uid}",
        note_type=nt_basic,
        sort_field="Pomme",
        tags=json.dumps(["fruits", "rouge"]),
    )
    v1 = NoteVersionModel.create(
        note=n1,
        content=json.dumps({"Front": "Pomme", "Verso": "Fruit rouge croquant", "Extra": "Origine Europe"}),
        version_number=1,
        is_active=True,
    )
    c1 = CardModel.create(
        note=n1,
        deck=deck_b,
        template_index=0,
        flags=3,
        is_suspended=False,
        lapses=10,
        ivl=30,
        reps=8,
        stability=4.5,
        difficulty=0.8,
    )

    # Note 2 : Abricot, Cloze, Deck A, lapses=2, flags=1, suspended=True
    n2 = NoteModel.create(
        guid=f"n2_{uid}",
        note_type=nt_cloze,
        sort_field="Abricot",
        tags=json.dumps(["fruits", "orange"]),
    )
    v2 = NoteVersionModel.create(
        note=n2,
        content=json.dumps({"Front": "Abricot", "Verso": "Fruit orange à noyau", "Extra": "Origine Asie"}),
        version_number=1,
        is_active=True,
    )
    c2 = CardModel.create(
        note=n2,
        deck=deck_a,
        template_index=0,
        flags=1,
        is_suspended=True,
        lapses=2,
        ivl=5,
        reps=2,
        stability=1.5,
        difficulty=0.3,
    )

    # Note 3 : Banane, Basic, Deck A (même deck que Note 2), lapses=2 (même lapse que Note 2 pour tester le départage)
    n3 = NoteModel.create(
        guid=f"n3_{uid}",
        note_type=nt_basic,
        sort_field="Banane",
        tags=json.dumps(["exotique"]),
    )
    v3 = NoteVersionModel.create(
        note=n3,
        content=json.dumps({"Front": "Banane", "Verso": "Fruit jaune allongé", "Extra": "Origine Tropiques"}),
        version_number=1,
        is_active=True,
    )
    c3 = CardModel.create(
        note=n3,
        deck=deck_a,
        template_index=0,
        flags=1,
        is_suspended=False,
        lapses=2,
        ivl=15,
        reps=4,
        stability=2.0,
        difficulty=0.5,
    )

    return {
        "deck_a": deck_a,
        "deck_b": deck_b,
        "nt_basic": nt_basic,
        "nt_cloze": nt_cloze,
        "n1": n1,
        "n2": n2,
        "n3": n3,
        "v1": v1,
        "v2": v2,
        "v3": v3,
        "c1": c1,
        "c2": c2,
        "c3": c3,
    }


def test_notes_sorting_by_recto(sample_sorting_data: dict[str, Any]) -> None:
    """Vérifie le tri des notes par Recto (sort_field) ASC et DESC."""
    base_query = NoteModel.select().where(
        NoteModel.id.in_(
            [
                sample_sorting_data["n1"].id,
                sample_sorting_data["n2"].id,
                sample_sorting_data["n3"].id,
            ]
        )
    )

    # ASC : Abricot, Banane, Pomme
    q_asc = apply_query_sorting(base_query, SortOrder(SortCriterion.RECTO, SortDirection.ASC), display_mode="notes")
    results_asc = [n.sort_field for n in q_asc]
    assert results_asc == ["Abricot", "Banane", "Pomme"]

    # DESC : Pomme, Banane, Abricot
    q_desc = apply_query_sorting(base_query, SortOrder(SortCriterion.RECTO, SortDirection.DESC), display_mode="notes")
    results_desc = [n.sort_field for n in q_desc]
    assert results_desc == ["Pomme", "Banane", "Abricot"]


def test_notes_sorting_by_verso(sample_sorting_data: dict[str, Any]) -> None:
    """Vérifie le tri des notes par Verso via json_extract."""
    base_query = NoteModel.select().where(
        NoteModel.id.in_(
            [
                sample_sorting_data["n1"].id,
                sample_sorting_data["n2"].id,
                sample_sorting_data["n3"].id,
            ]
        )
    )

    # Versos : "Fruit rouge croquant", "Fruit orange à noyau", "Fruit jaune allongé"
    # ASC alphabétique : "Fruit jaune...", "Fruit orange...", "Fruit rouge..." -> Banane, Abricot, Pomme
    q_asc = apply_query_sorting(base_query, SortOrder(SortCriterion.VERSO, SortDirection.ASC), display_mode="notes")
    results_asc = [n.sort_field for n in q_asc]
    assert results_asc == ["Banane", "Abricot", "Pomme"]


def test_notes_sorting_by_specific_field(sample_sorting_data: dict[str, Any]) -> None:
    """Vérifie le tri des notes sur un champ personnalisé ('Extra')."""
    base_query = NoteModel.select().where(
        NoteModel.id.in_(
            [
                sample_sorting_data["n1"].id,
                sample_sorting_data["n2"].id,
                sample_sorting_data["n3"].id,
            ]
        )
    )

    # Extra : "Origine Europe" (Pomme), "Origine Asie" (Abricot), "Origine Tropiques" (Banane)
    # ASC : "Origine Asie" (Abricot), "Origine Europe" (Pomme), "Origine Tropiques" (Banane)
    order = SortOrder(SortCriterion.SPECIFIC_FIELD, SortDirection.ASC, field_name="Extra")
    q_asc = apply_query_sorting(base_query, order, display_mode="notes")
    results_asc = [n.sort_field for n in q_asc]
    assert results_asc == ["Abricot", "Pomme", "Banane"]


def test_notes_sorting_by_deck_and_tie_breaker(sample_sorting_data: dict[str, Any]) -> None:
    """Vérifie le tri par Paquet et la clé de départage déterministe (sort_field)."""
    base_query = NoteModel.select().where(
        NoteModel.id.in_(
            [
                sample_sorting_data["n1"].id,
                sample_sorting_data["n2"].id,
                sample_sorting_data["n3"].id,
            ]
        )
    )

    # Deck A : Abricot, Banane (Départage alphabétique sur sort_field -> Abricot puis Banane)
    # Deck B : Pomme
    q_asc = apply_query_sorting(base_query, SortOrder(SortCriterion.DECK, SortDirection.ASC), display_mode="notes")
    results_asc = [n.sort_field for n in q_asc]
    assert results_asc == ["Abricot", "Banane", "Pomme"]


def test_notes_sorting_by_note_type(sample_sorting_data: dict[str, Any]) -> None:
    """Vérifie le tri par Type de note."""
    base_query = NoteModel.select().where(
        NoteModel.id.in_(
            [
                sample_sorting_data["n1"].id,
                sample_sorting_data["n2"].id,
                sample_sorting_data["n3"].id,
            ]
        )
    )

    # Type Basic : Pomme, Banane (Départage -> Banane puis Pomme)
    # Type Cloze : Abricot
    q_asc = apply_query_sorting(base_query, SortOrder(SortCriterion.NOTE_TYPE, SortDirection.ASC), display_mode="notes")
    results_asc = [n.sort_field for n in q_asc]
    assert results_asc == ["Banane", "Pomme", "Abricot"]


def test_cards_sorting_by_lapses_and_tie_breaker(sample_sorting_data: dict[str, Any]) -> None:
    """Vérifie le tri des cartes par nombre de chutes (lapses) et départage par sort_field."""
    base_query = (
        CardModel.select(CardModel, NoteModel, DeckModel, NoteTypeModel)
        .join(NoteModel, peewee.JOIN.LEFT_OUTER)
        .join(NoteTypeModel, peewee.JOIN.LEFT_OUTER)
        .switch(CardModel)
        .join(DeckModel, peewee.JOIN.LEFT_OUTER)
        .where(
            CardModel.id.in_(
                [
                    sample_sorting_data["c1"].id,
                    sample_sorting_data["c2"].id,
                    sample_sorting_data["c3"].id,
                ]
            )
        )
    )

    # lapses : c1=10 (Pomme), c2=2 (Abricot), c3=2 (Banane)
    # DESC : c1 (10), puis pour lapses=2 départage sur sort_field.asc() -> Abricot (c2) puis Banane (c3)
    q_desc = apply_query_sorting(base_query, SortOrder(SortCriterion.LAPSES, SortDirection.DESC), display_mode="cards")
    results_desc = [c.note.sort_field for c in q_desc]
    assert results_desc == ["Pomme", "Abricot", "Banane"]


def test_cards_sorting_by_srs_metrics(sample_sorting_data: dict[str, Any]) -> None:
    """Vérifie le tri des cartes selon les métriques FSRS/SRS (ivl, reps, stability, difficulty)."""
    base_query = (
        CardModel.select(CardModel, NoteModel, DeckModel, NoteTypeModel)
        .join(NoteModel, peewee.JOIN.LEFT_OUTER)
        .join(NoteTypeModel, peewee.JOIN.LEFT_OUTER)
        .switch(CardModel)
        .join(DeckModel, peewee.JOIN.LEFT_OUTER)
        .where(
            CardModel.id.in_(
                [
                    sample_sorting_data["c1"].id,
                    sample_sorting_data["c2"].id,
                    sample_sorting_data["c3"].id,
                ]
            )
        )
    )

    # Intervalle (ivl) ASC : c2=5 (Abricot), c3=15 (Banane), c1=30 (Pomme)
    q_ivl = apply_query_sorting(base_query, SortOrder(SortCriterion.IVL, SortDirection.ASC), display_mode="cards")
    assert [c.note.sort_field for c in q_ivl] == ["Abricot", "Banane", "Pomme"]

    # Répétitions (reps) DESC : c1=8 (Pomme), c3=4 (Banane), c2=2 (Abricot)
    q_reps = apply_query_sorting(base_query, SortOrder(SortCriterion.REPS, SortDirection.DESC), display_mode="cards")
    assert [c.note.sort_field for c in q_reps] == ["Pomme", "Banane", "Abricot"]

    # Stabilité (stability) ASC : c2=1.5 (Abricot), c3=2.0 (Banane), c1=4.5 (Pomme)
    q_stab = apply_query_sorting(base_query, SortOrder(SortCriterion.STABILITY, SortDirection.ASC), display_mode="cards")
    assert [c.note.sort_field for c in q_stab] == ["Abricot", "Banane", "Pomme"]

    # Difficulté (difficulty) DESC : c1=0.8 (Pomme), c3=0.5 (Banane), c2=0.3 (Abricot)
    q_diff = apply_query_sorting(base_query, SortOrder(SortCriterion.DIFFICULTY, SortDirection.DESC), display_mode="cards")
    assert [c.note.sort_field for c in q_diff] == ["Pomme", "Banane", "Abricot"]


def test_cards_sorting_by_flags_and_suspended(sample_sorting_data: dict[str, Any]) -> None:
    """Vérifie le tri des cartes par Drapeaux et Suspension."""
    base_query = (
        CardModel.select(CardModel, NoteModel, DeckModel, NoteTypeModel)
        .join(NoteModel, peewee.JOIN.LEFT_OUTER)
        .join(NoteTypeModel, peewee.JOIN.LEFT_OUTER)
        .switch(CardModel)
        .join(DeckModel, peewee.JOIN.LEFT_OUTER)
        .where(
            CardModel.id.in_(
                [
                    sample_sorting_data["c1"].id,
                    sample_sorting_data["c2"].id,
                    sample_sorting_data["c3"].id,
                ]
            )
        )
    )

    # Flags DESC : c1=3 (Pomme), puis c2=1 (Abricot) et c3=1 (Banane) -> départage sort_field : Abricot puis Banane
    q_flags = apply_query_sorting(base_query, SortOrder(SortCriterion.FLAGS, SortDirection.DESC), display_mode="cards")
    assert [c.note.sort_field for c in q_flags] == ["Pomme", "Abricot", "Banane"]

    # Suspended DESC : c2=True (Abricot), puis False (c1=Pomme, c3=Banane -> départage Banane puis Pomme)
    q_susp = apply_query_sorting(base_query, SortOrder(SortCriterion.SUSPENDED, SortDirection.DESC), display_mode="cards")
    assert [c.note.sort_field for c in q_susp] == ["Abricot", "Banane", "Pomme"]


def test_notes_sorting_by_modified_at_and_tags(sample_sorting_data: dict[str, Any]) -> None:
    """Vérifie le tri des notes par date de modification et par tags."""
    base_query = NoteModel.select().where(
        NoteModel.id.in_(
            [
                sample_sorting_data["n1"].id,
                sample_sorting_data["n2"].id,
                sample_sorting_data["n3"].id,
            ]
        )
    )

    # Tri par tags ASC : '["exotique"]' (Banane), puis '["fruits", "orange"]' (Abricot), puis '["fruits", "rouge"]' (Pomme)
    q_tags = apply_query_sorting(base_query, SortOrder(SortCriterion.TAGS, SortDirection.ASC), display_mode="notes")
    assert [n.sort_field for n in q_tags] == ["Banane", "Abricot", "Pomme"]

    # Tri par date de modification ASC : v1, v2, v3
    q_mod = apply_query_sorting(base_query, SortOrder(SortCriterion.MODIFIED_AT, SortDirection.ASC), display_mode="notes")
    assert len(list(q_mod)) == 3
