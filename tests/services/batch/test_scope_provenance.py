"""
Tests de l'estampillage de provenance documentaire des cartes batch.

Une partie du Batch Slice Composer agrège N fragments de source : la provenance
exposée à la résolution fine doit alors être *explicitement* multi-blocs
(``_source_blocks``), et jamais un ``heading_path`` concaténé ni la page du
premier bloc.
"""

import pytest

from ankiforge.services.batch.models import BatchSourceBlock
from ankiforge.services.batch.provenance import scope_provenance, stamp_scope_provenance

pytestmark = pytest.mark.unit


def _block(ordinal: int, heading: str | None, page: int | None, chunk_id: int | None) -> BatchSourceBlock:
    return BatchSourceBlock(
        kind="section",
        label=heading or f"Bloc {ordinal}",
        content=f"Contenu du bloc {ordinal}",
        ordinal=ordinal,
        page_number=page,
        heading_path=heading,
        source_id=1,
        chunk_id=chunk_id,
    )


def test_single_block_stamps_exact_mono_block_provenance() -> None:
    """Une partie mono-bloc conserve une provenance exacte (chunk, fil d'Ariane, page)."""
    card: dict[str, object] = {"Front": "Q", "Back": "A"}

    stamp_scope_provenance([card], [_block(0, "Chapitre 1 > Intro", 4, 12)])

    assert card["_source_chunk_id"] == 12
    assert card["_source_heading_path"] == "Chapitre 1 > Intro"
    assert card["_source_page_number"] == 4
    assert card["_source_blocks"] == [{"chunk_id": 12, "heading_path": "Chapitre 1 > Intro", "page_number": 4}]
    assert card["_documentation_enabled"] is True


def test_multi_block_stamps_explicit_blocks_without_aggregated_scalars() -> None:
    """Une partie à N blocs n'expose ni fil d'Ariane concaténé ni page du premier bloc."""
    card: dict[str, object] = {"Front": "Q", "Back": "A"}
    blocks = [
        _block(0, "Chapitre 1 > Intro", 4, 12),
        _block(1, "Chapitre 1 > Définition", 5, 13),
        _block(2, "Chapitre 2 > Synthèse", None, 14),
    ]

    stamp_scope_provenance([card], blocks)

    assert card["_source_chunk_id"] is None
    assert card["_source_heading_path"] is None
    assert card["_source_page_number"] is None
    assert card["_source_blocks"] == [
        {"chunk_id": 12, "heading_path": "Chapitre 1 > Intro", "page_number": 4},
        {"chunk_id": 13, "heading_path": "Chapitre 1 > Définition", "page_number": 5},
        {"chunk_id": 14, "heading_path": "Chapitre 2 > Synthèse", "page_number": None},
    ]
    assert card["_documentation_enabled"] is True


def test_multi_block_stamps_every_card_of_the_task() -> None:
    """Toutes les cartes de la tâche portent la même provenance multi-blocs."""
    cards: list[dict[str, object]] = [{"Front": "Q1", "Back": "A1"}, {"Front": "Q2", "Back": "A2"}]

    stamp_scope_provenance(cards, [_block(0, "A", 1, 20), _block(1, "B", 2, 21)])

    assert all(card["_source_blocks"] == cards[0]["_source_blocks"] for card in cards)
    assert all(card["_source_chunk_id"] is None for card in cards)


def test_stamp_does_not_overwrite_an_existing_exact_provenance() -> None:
    """Une provenance déjà résolue par le pipeline (chunk source connu) prime sur la portée."""
    card: dict[str, object] = {"Front": "Q", "Back": "A", "_source_chunk_id": 77}

    stamp_scope_provenance([card], [_block(0, "A", 1, 20), _block(1, "B", 2, 21)])

    assert card["_source_chunk_id"] == 77


def test_blocks_without_chunk_id_still_declare_multi_block_shape() -> None:
    """Sans identifiant de fragment, la partie reste multi-blocs (fil d'Ariane distincts)."""
    card: dict[str, object] = {"Front": "Q", "Back": "A"}

    stamp_scope_provenance([card], [_block(0, "Titre A", None, None), _block(1, "Titre B", None, None)])

    assert card["_source_chunk_id"] is None
    assert card["_source_heading_path"] is None
    assert card["_source_page_number"] is None
    assert [b["heading_path"] for b in card["_source_blocks"]] == ["Titre A", "Titre B"]  # type: ignore[index]


def test_duplicate_blocks_are_collapsed() -> None:
    """Deux blocs identiques (même fil d'Ariane, même page) n'annoncent pas un faux multi-blocs."""
    card: dict[str, object] = {"Front": "Q", "Back": "A"}

    stamp_scope_provenance([card], [_block(0, "Titre A", 3, 20), _block(1, "Titre A", 3, 20)])

    assert card["_source_chunk_id"] == 20
    assert card["_source_heading_path"] == "Titre A"
    assert card["_source_page_number"] == 3


def test_scope_provenance_is_empty_without_blocks() -> None:
    """Une portée sans fragment ne fabrique aucune provenance mensongère."""
    assert scope_provenance(()) == []


def test_scope_provenance_drops_blocks_without_any_locator() -> None:
    """Un bloc sans fil d'Ariane, ni page, ni identifiant n'apporte aucune route de résolution."""
    assert scope_provenance([_block(0, None, None, None)]) == []
