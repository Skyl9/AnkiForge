"""Tests unitaires pour les types d'options et l'assemblage de prompt de transcription d'album."""

import pytest

from ankiforge.services.ai.album_transcription_types import (
    AlbumTranscriptionOptions,
    build_album_transcription_prompt,
    parse_page_ranges,
)

pytestmark = pytest.mark.unit


def test_parse_page_ranges_valid() -> None:
    assert parse_page_ranges("1-3, 5, 8-10", max_page=12) == {1, 2, 3, 5, 8, 9, 10}
    assert parse_page_ranges(" 4 , 2-2 ", max_page=10) == {2, 4}
    assert parse_page_ranges("10-15", max_page=12) == {10, 11, 12}


def test_parse_page_ranges_invalid_or_empty() -> None:
    assert parse_page_ranges("", max_page=10) == set()
    assert parse_page_ranges("abc, foo", max_page=10) == set()
    assert parse_page_ranges("0, -5", max_page=10) == set()
    assert parse_page_ranges("15-20", max_page=10) == set()


def test_parse_page_ranges_borne_avant_allocation_range() -> None:
    """Un intervalle très grand est borné par max_page AVANT la construction du range (pas de DoS)."""
    assert parse_page_ranges("1-999999", max_page=5) == {1, 2, 3, 4, 5}
    assert parse_page_ranges("1-999999, 50-60", max_page=10) == {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
    # Pas d'allocation mémoire démesurée : l'intervalle est tronqué, pas matérialisé en entier.
    assert parse_page_ranges("1-1000000", max_page=1) == {1}


def test_build_album_transcription_prompt_defaults() -> None:
    opts = AlbumTranscriptionOptions(
        scope_mode="all",
        custom_range="",
        target_page_ids=[1, 2],
        category_id="structured",
        include_latex=True,
        include_tables=True,
        include_figures=False,
        include_headings=True,
        custom_instructions="",
    )
    prompt = build_album_transcription_prompt(opts)
    assert "LaTeX" in prompt
    assert "tableaux" in prompt.lower()
    assert "titres" in prompt.lower()
    assert "Ne produis aucun préambule" in prompt
    assert "Figure:" not in prompt


def test_build_album_transcription_prompt_with_figures_and_custom() -> None:
    opts = AlbumTranscriptionOptions(
        scope_mode="custom",
        custom_range="1-2",
        target_page_ids=[1],
        category_id="reasoning",
        include_latex=False,
        include_tables=False,
        include_figures=True,
        include_headings=False,
        custom_instructions="Vocabulaire médical en latin uniquement.",
    )
    prompt = build_album_transcription_prompt(opts)
    assert "[Figure:" in prompt
    assert "Vocabulaire médical en latin uniquement." in prompt
    assert "LaTeX" not in prompt
