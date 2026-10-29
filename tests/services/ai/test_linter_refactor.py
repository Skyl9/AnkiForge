"""Tests unitaires pour la refonte du linter Wozniak : détecteurs réels, zéro carte factice, contrat cohérent."""

from __future__ import annotations

import pytest

from ankiforge.services.ai.linter import WozniakLinterEngine

pytestmark = pytest.mark.integration


def _note(nid: int, recto: str, verso: str = "", extra: str = "", tags: str = "") -> dict:
    return {
        "id": nid,
        "note_type": "AnkiForge-Basic",
        "tags": tags or "#general",
        "recto": recto,
        "verso": verso,
        "extra": extra,
    }


def test_audit_deck_without_notes_returns_no_dummy_cards():
    """Aucune carte factice (card_id 1042, 1105, ...) ne doit être générée quand la base est vide."""
    report = WozniakLinterEngine.audit_deck(deck_id=None)
    assert report["score_global"] == 100
    for cat in report["categories"].values():
        assert cat["count"] == 0
        assert cat["items"] == []
    dummy_ids = {1042, 1105, 1218, 1340, 1088, 1092, 1095, 1120, 1135, 1012}
    for cat in report["categories"].values():
        for item in cat["items"]:
            assert item["card_id"] not in dummy_ids


def test_detect_atomicite_no_et_false_positive():
    """Le mot 'et' isolé dans le recto ne doit pas déclencher un faux positif d'atomicité."""
    real = [_note(1, "La question contient le mot et mais reste atomique et univoque.", "Réponse courte.")]
    items = WozniakLinterEngine._detect_atomicite_issues(real)
    assert items == []


def test_detect_atomicite_flags_overlong_note():
    real = [_note(2, " ".join(["mot"] * 50), "Réponse.")]
    items = WozniakLinterEngine._detect_atomicite_issues(real)
    assert len(items) == 1
    assert items[0]["card_id"] == 2


def test_detect_katex_flags_undelimited_latex():
    real = [_note(3, r"L'integrale \int_{-\infty}^{\infty} |f|^2 dx vaut 1.", "Réponse.")]
    items = WozniakLinterEngine._detect_katex_issues(real)
    assert len(items) == 1
    assert items[0]["card_id"] == 3


def test_detect_katex_accepts_delimited_latex():
    real = [_note(4, r"Voici la formule : $\int_{-\infty}^{\infty} |f|^2 dx = 1$.", "Réponse.")]
    items = WozniakLinterEngine._detect_katex_issues(real)
    assert items == []


def test_detect_katex_flags_unbalanced_dollars():
    real = [_note(5, r"Formule $\int x dx non fermee.", "Réponse.")]
    items = WozniakLinterEngine._detect_katex_issues(real)
    assert len(items) == 1


def test_detect_cloze_flags_cloze_on_basic_note():
    real = [_note(6, r"Les principes sont {{c1::Single Responsibility}} et {{c2::Open-Closed}}.", "Réponse.")]
    items = WozniakLinterEngine._detect_cloze_issues(real)
    assert len(items) == 1
    assert items[0]["card_id"] == 6


def test_detect_cloze_accepts_plain_note():
    real = [_note(7, "Question simple ?", "Réponse simple.")]
    items = WozniakLinterEngine._detect_cloze_issues(real)
    assert items == []


def test_detect_interference_flags_similar_recto():
    real = [
        _note(8, "Quelle est la formule de l'energie cinétique ?", "Ec = 1/2 m v^2."),
        _note(9, "Quelle est la formule de l'énergie cinétique ?", "Ec = 0.5 * m * v**2."),
    ]
    items = WozniakLinterEngine._detect_interference_issues(real)
    assert len(items) == 1


def test_detect_interference_no_false_positive_on_different_notes():
    real = [
        _note(10, "Quelle est la capitale de la France ?", "Paris."),
        _note(11, "Qui a écrit Les Misérables ?", "Victor Hugo."),
    ]
    items = WozniakLinterEngine._detect_interference_issues(real)
    assert items == []


def test_sources_diagnostic_service_removed():
    """La classe morte SourcesDiagnosticService n'existe plus dans le module linter."""
    import ankiforge.services.ai.linter as linter_mod

    assert not hasattr(linter_mod, "SourcesDiagnosticService")


def test_audit_deck_contract_exposes_score_global_and_titles():
    """Le contrat retourne score_global et categories[*].{title, count}, jamais total_notes/notes_flagged/name."""
    report = WozniakLinterEngine.audit_deck(deck_id=None)
    assert "score_global" in report
    assert "enable_cloze_audit" in report
    assert "categories" in report
    for _cat_id, cat in report["categories"].items():
        assert "title" in cat
        assert "count" in cat
        assert "items" in cat
        assert "score" in cat
        assert isinstance(cat["score"], int)
    # Pas de clés obsolètes du contrat
    assert "total_notes" not in report
    assert "notes_flagged" not in report
    for cat in report["categories"].values():
        assert "name" not in cat
