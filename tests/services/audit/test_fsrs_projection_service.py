"""Tests de FsrsProjectionService : stabilité estimée, rétention projetée et charge d'équilibre."""

from __future__ import annotations

import math

import pytest

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel
from ankiforge.services.audit.fsrs_projection_service import FsrsProjectionService

pytestmark = pytest.mark.integration


def _make_note_type() -> NoteTypeModel:
    return NoteTypeModel.create(name="Basic", fields_schema=["Front", "Back"])


def _add_card(deck: DeckModel, note_type: NoteTypeModel, ivl: int, suspended: bool = False) -> CardModel:
    note = NoteModel.create(note_type=note_type)
    return CardModel.create(note=note, deck=deck, ivl=ivl, is_suspended=suspended)


def test_retention_formula_anchors_at_review_and_hits_target():
    # Ancrage : 100 % à la révision.
    assert FsrsProjectionService.projected_retention(0, 19) == pytest.approx(1.0)
    # À t = S, la loi de puissance atteint la rétention cible (90 %).
    assert FsrsProjectionService.projected_retention(19, 19) == pytest.approx(0.9, rel=1e-9)
    # Point intermédiaire analytique : (19/81)·t/S = 1/3 → R = (4/3)^-0.5 = √3/2.
    assert FsrsProjectionService.projected_retention(27, 19) == pytest.approx(math.sqrt(3) / 2, rel=1e-9)
    # Décroissance stricte.
    assert FsrsProjectionService.projected_retention(1, 10) > FsrsProjectionService.projected_retention(7, 10)


def test_estimate_stability_maps_interval_and_rejects_zero():
    assert FsrsProjectionService.estimate_stability_days(42) == 42.0
    assert FsrsProjectionService.estimate_stability_days(0) == 0.0
    assert FsrsProjectionService.estimate_stability_days(-3) == 0.0


def test_projection_empty_collection():
    result = FsrsProjectionService.project()
    assert result["available"] is False
    assert result["equilibrium_load_per_day"] == 0.0
    assert result["new_cards"] == 0
    assert [c["day"] for c in result["checkpoints"]] == [1, 3, 7, 14]


def test_projection_excludes_new_cards_and_counts_them():
    deck = DeckModel.create(name="Solo")
    nt = _make_note_type()
    _add_card(deck, nt, ivl=0)
    _add_card(deck, nt, ivl=0, suspended=True)
    _add_card(deck, nt, ivl=10)

    result = FsrsProjectionService.project()

    assert result["available"] is True
    assert result["total_cards"] == 3
    assert result["new_cards"] == 2
    assert result["studied_cards"] == 1


def test_projection_negative_interval_is_neither_new_nor_studied():
    """Un intervalle négatif (carte en apprentissage) n'est ni « nouvelle » ni étudié."""
    deck = DeckModel.create(name="Apprentissage")
    nt = _make_note_type()
    _add_card(deck, nt, ivl=-5)
    _add_card(deck, nt, ivl=10)

    result = FsrsProjectionService.project()

    assert result["total_cards"] == 2
    assert result["new_cards"] == 0
    assert result["studied_cards"] == 1


def test_projection_load_excludes_suspended_but_curve_includes_them():
    deck = DeckModel.create(name="Charge")
    nt = _make_note_type()
    _add_card(deck, nt, ivl=10)
    _add_card(deck, nt, ivl=20, suspended=True)

    result = FsrsProjectionService.project()

    # Étude : les deux cartes (suspendue incluse dans la stabilité).
    assert result["studied_cards"] == 2
    assert result["suspended_cards"] == 1
    # Charge : seule la carte non suspendue compte → 1/10.
    assert result["equilibrium_load_per_day"] == pytest.approx(0.1, abs=1e-6)
    assert result["load_cards"] == 1


def test_projection_aggregates_mean_retention_and_stability():
    deck = DeckModel.create(name="Agrégat")
    nt = _make_note_type()
    _add_card(deck, nt, ivl=10)
    _add_card(deck, nt, ivl=20)

    result = FsrsProjectionService.project()

    expected_load = 1.0 / 10 + 1.0 / 20
    assert result["equilibrium_load_per_day"] == pytest.approx(expected_load, abs=1e-6)
    assert result["mean_stability_days"] == pytest.approx(15.0)

    expected_j7 = (FsrsProjectionService.projected_retention(7, 10) + FsrsProjectionService.projected_retention(7, 20)) / 2
    checkpoint_j7 = next(c for c in result["checkpoints"] if c["day"] == 7)
    assert checkpoint_j7["retention"] == pytest.approx(expected_j7, abs=1e-3)
    # La courbe est ancrée à 100 % au jour 0 et bornée à l'horizon.
    assert result["curve"][0] == {"day": 0.0, "retention": 1.0}
    assert result["curve"][-1]["day"] == float(FsrsProjectionService.CURVE_MAX_DAY)


def test_projection_deck_filter_includes_subdecks():
    parent = DeckModel.create(name="Médecine")
    child = DeckModel.create(name="Médecine::Cardiologie", parent_deck=parent)
    other = DeckModel.create(name="Droit")
    nt = _make_note_type()
    _add_card(parent, nt, ivl=10)
    _add_card(child, nt, ivl=20)
    _add_card(other, nt, ivl=100)

    result = FsrsProjectionService.project(deck_id=parent.id)

    assert result["studied_cards"] == 2
    assert result["equilibrium_load_per_day"] == pytest.approx(1.0 / 10 + 1.0 / 20, abs=1e-6)


def test_projection_unknown_deck_yields_empty():
    result = FsrsProjectionService.project(deck_id=999_999)
    assert result["available"] is False
    assert result["total_cards"] == 0
