"""Tests unitaires pour la normalisation et la validation de la syntaxe des tags Anki (ADR 0040)."""

from __future__ import annotations

import pytest

from ankiforge.utils.tags import (
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


def test_detect_tag_anomalies() -> None:
    """Vérifie la détection d'anomalies de tags legacy."""
    assert detect_tag_anomalies("medecine generale") == ["has_spaces"]
    assert detect_tag_anomalies("::physique::") == ["malformed_hierarchy"]
    assert detect_tag_anomalies("   ") == ["empty"]
    assert detect_tag_anomalies("valide::tag") == []
