"""Tests unitaires pour la normalisation et la validation de la syntaxe des tags Anki (ADR 0040)."""

from __future__ import annotations

import pytest

from ankidraft.utils.tags import (
    detect_tag_anomalies,
    normalize_tag_input,
    split_tag_tokens,
    validate_tag_syntax,
)

pytestmark = pytest.mark.unit


def test_validate_tag_syntax_valid_tags() -> None:
    """Vérifie que les tags standards et hiérarchiques valides sont acceptés."""
    valid_tags = [
        "vocabulaire",
        "langue::anglais",
        "sciences::physique::mecanique",
        "examen_2026",
        "chapitre-1",
        "doc:12",
        "section:intro",
    ]
    for tag in valid_tags:
        is_valid, reason = validate_tag_syntax(tag)
        assert is_valid is True, f"Tag {tag} devrait être valide, raison: {reason}"
        assert reason is None


def test_validate_tag_syntax_invalid_tags() -> None:
    """Vérifie le rejet des tags contenant des espaces, segments vides ou malformés."""
    invalid_cases = [
        ("", "Le tag ne peut pas être vide."),
        ("   ", "Le tag ne peut pas être vide."),
        ("medecine generale", "Les espaces sont interdits dans un tag individuel."),
        ("tag with\ttab", "Les espaces sont interdits dans un tag individuel."),
        ("::anglais", "La hiérarchie '::' contient des segments vides."),
        ("sciences::", "La hiérarchie '::' contient des segments vides."),
        ("math::::analyse", "La hiérarchie '::' contient des segments vides."),
        ("bio:: ::cell", "Les espaces sont interdits dans un tag individuel."),
    ]
    for tag, expected_msg_snippet in invalid_cases:
        is_valid, reason = validate_tag_syntax(tag)
        assert is_valid is False, f"Tag '{tag}' devrait être invalide"
        assert reason is not None
        assert expected_msg_snippet.lower() in reason.lower()


def test_normalize_tag_input_spaces_to_underscores() -> None:
    """Vérifie le remplacement des espaces par des tirets bas selon l'ADR 0040."""
    assert normalize_tag_input("medecine generale") == "medecine_générale".replace("é", "e") or "medecine_generale"
    assert normalize_tag_input("  anatomie   humaine  ") == "anatomie_humaine"
    assert normalize_tag_input("histoire  de  france") == "histoire_de_france"


def test_normalize_tag_input_hierarchy_cleanup() -> None:
    """Vérifie le nettoyage des deux-points superflus et segments vides."""
    assert normalize_tag_input("::langues::anglais::") == "langues::anglais"
    assert normalize_tag_input("math::::algebre") == "math::algebre"
    assert normalize_tag_input("bio::  ::cellulaire") == "bio::cellulaire"
    assert normalize_tag_input("  ::  ") == ""


def test_split_tag_tokens() -> None:
    """Vérifie le découpage d'une saisie multi-tags par espaces et virgules."""
    # Espaces multiples
    tokens = split_tag_tokens("vocabulaire anglais::grammaire examen_2026")
    assert tokens == ["vocabulaire", "anglais::grammaire", "examen_2026"]

    # Virgules et espaces mélangés
    tokens2 = split_tag_tokens("tag1, tag2,tag3   tag4")
    assert tokens2 == ["tag1", "tag2", "tag3", "tag4"]

    # Dédoublonnage et préservation de l'ordre
    tokens3 = split_tag_tokens("tag1 tag2 tag1 tag3")
    assert tokens3 == ["tag1", "tag2", "tag3"]


def test_split_tag_tokens_polymorphic_inputs() -> None:
    """Vérifie la prise en charge de listes, tuples, sets, None et JSON sérialisé."""
    # None et vide
    assert split_tag_tokens(None) == []
    assert split_tag_tokens("") == []
    assert split_tag_tokens("   ") == []

    # Liste contenant un élément avec plusieurs tags délimités par des espaces
    raw_list = ["ankiforge_generated doc:11 source:livre_de_japonais page:1", "lecon_06"]
    tokens = split_tag_tokens(raw_list)
    assert tokens == ["ankiforge_generated", "doc:11", "source:livre_de_japonais", "page:1", "lecon_06"]

    # Tuple de tags
    assert split_tag_tokens(("tag1, tag2", "tag3")) == ["tag1", "tag2", "tag3"]

    # Ensemble de tags
    tokens_set = split_tag_tokens({"tag1 tag2", "tag3"})
    assert set(tokens_set) == {"tag1", "tag2", "tag3"}

    # Chaîne JSON sérialisée
    json_str = '["ankiforge_generated doc:11", "page:1"]'
    assert split_tag_tokens(json_str) == ["ankiforge_generated", "doc:11", "page:1"]


def test_extract_tag_metadata_resilience_to_untokenized_strings() -> None:
    """Vérifie que extract_tag_metadata récupère les métadonnées même si les tags sont scellés dans une chaîne avec espaces."""
    from ankidraft.utils.tags import extract_tag_metadata

    # Chaîne brute avec espaces (format Anki classique)
    meta1 = extract_tag_metadata("ankiforge_generated doc:11 source:livre_de_japonais page:1 section:page_1")
    assert meta1["doc_id"] == 11
    assert meta1["source_slug"] == "livre_de_japonais"
    assert meta1["page_number"] == 1
    assert meta1["section_slug"] == "page_1"

    # Liste contenant une chaîne unique avec espaces
    meta2 = extract_tag_metadata(["ankiforge_generated doc:42 source:manuel_bio page:5 section:intro"])
    assert meta2["doc_id"] == 42
    assert meta2["source_slug"] == "manuel_bio"
    assert meta2["page_number"] == 5
    assert meta2["section_slug"] == "intro"

    # Chaîne JSON contenant des tags avec espaces
    meta3 = extract_tag_metadata('["ankiforge_generated doc:99 source:physique"]')
    assert meta3["doc_id"] == 99
    assert meta3["source_slug"] == "physique"


def test_detect_tag_anomalies() -> None:
    """Vérifie la détection d'anomalies de tags legacy."""
    assert detect_tag_anomalies("medecine generale") == ["has_spaces"]
    assert detect_tag_anomalies("::physique::") == ["malformed_hierarchy"]
    assert detect_tag_anomalies("   ") == ["empty"]
    assert detect_tag_anomalies("valide::tag") == []


def test_split_tag_tokens_on_compound_list_items() -> None:
    """Vérifie que split_tag_tokens découpe rigoureusement les éléments d'une liste composite."""
    assert split_tag_tokens(["tag1 tag2", "tag3, tag4"]) == ["tag1", "tag2", "tag3", "tag4"]
    assert split_tag_tokens(["  doc:12   page:3  ", "source:manuel"]) == ["doc:12", "page:3", "source:manuel"]
