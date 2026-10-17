"""Tests unitaires et UI headless pour CardSemanticDiffWidget.

Couvre la comparaison champ par champ, le diff mot-à-mot, l'édition directe,
l'aperçu live et la gestion polymorphique (card, split, note_create).
"""

from __future__ import annotations

from typing import Any

import pytest

from ankiforge.database.models import NoteTypeModel
from ankiforge.ui.widgets.card_semantic_diff_widget import (
    CardSemanticDiffWidget,
    compute_field_word_diff_html,
)

pytestmark = [pytest.mark.ui]


def test_compute_field_word_diff_html_basic():
    """Vérifie le calcul du diff mot-à-mot intra-ligne."""
    orig = "Bonjour le monde"
    mod = "Bonjour tout le monde"
    html_diff = compute_field_word_diff_html(orig, mod)
    assert "Bonjour" in html_diff
    assert "tout" in html_diff
    assert "monde" in html_diff


def test_compute_field_word_diff_html_escape():
    """Vérifie l'échappement sécurisé des caractères HTML."""
    orig = "<script>alert('xss')</script>"
    mod = "<b>alert('xss')</b>"
    html_diff = compute_field_word_diff_html(orig, mod)
    assert "<script>" not in html_diff
    assert "&lt;script&gt;" in html_diff


def test_card_semantic_diff_widget_instantiation(qtbot):
    """Vérifie l'instanciation propre du widget."""
    widget = CardSemanticDiffWidget()
    qtbot.addWidget(widget)
    assert widget.tab_widget is not None
    assert widget.tab_widget.count() == 2
    assert "Comparaison" in widget.tab_widget.tabText(0)
    assert "Aperçu" in widget.tab_widget.tabText(1)


def test_card_semantic_diff_widget_set_diff_card(qtbot):
    """Vérifie le découpage sémantique champ par champ pour une carte standard."""
    widget = CardSemanticDiffWidget()
    qtbot.addWidget(widget)

    orig = {"Front": "Capitale de la France ?", "Back": "Paris"}
    mod = {"Front": "Quelle est la capitale de la France ?", "Back": "Paris (75)"}

    widget.set_diff(orig, mod)

    rows = widget.get_field_rows()
    assert len(rows) == 2
    assert "Front" in rows
    assert "Back" in rows

    # Front : modifié
    front_row = rows["Front"]
    assert front_row.is_modified is True
    assert "Capitale" in front_row.orig_browser.toPlainText()
    assert "Quelle est la capitale" in front_row.mod_editor.toPlainText()

    # Back : modifié
    back_row = rows["Back"]
    assert back_row.is_modified is True
    assert "Paris (75)" in back_row.mod_editor.toPlainText()


def test_card_semantic_diff_widget_direct_edit_emits_signal(qtbot):
    """Vérifie que la saisie dans l'éditeur émet le signal content_edited."""
    widget = CardSemanticDiffWidget()
    qtbot.addWidget(widget)

    orig = {"Front": "Question 1", "Back": "Réponse 1"}
    mod = {"Front": "Question 2", "Back": "Réponse 2"}
    widget.set_diff(orig, mod)

    emitted: list[dict[str, Any]] = []
    widget.content_edited.connect(emitted.append)

    front_row = widget.get_field_rows()["Front"]
    front_row.mod_editor.setPlainText("Question modifiée par utilisateur")

    assert len(emitted) >= 1
    latest = emitted[-1]
    assert latest["Front"] == "Question modifiée par utilisateur"
    assert latest["Back"] == "Réponse 2"

    content = widget.get_modified_content()
    assert content["Front"] == "Question modifiée par utilisateur"


def test_card_semantic_diff_widget_applied_read_only(qtbot):
    """Vérifie que le mode appliqué verrouille les éditeurs en lecture seule."""
    widget = CardSemanticDiffWidget()
    qtbot.addWidget(widget)

    orig = {"Front": "A"}
    mod = {"Front": "B"}
    widget.set_diff(orig, mod, is_applied=True)

    front_row = widget.get_field_rows()["Front"]
    assert front_row.mod_editor.isReadOnly() is True


def test_card_semantic_diff_widget_polymorphic_split(qtbot):
    """Vérifie la prise en charge d'un patch de type split (N cartes atomiques)."""
    widget = CardSemanticDiffWidget()
    qtbot.addWidget(widget)

    orig = {"Front": "Question dense avec 2 points clés"}
    mod_cards = [
        {"Front": "Point clé 1 ?", "Back": "Explication 1"},
        {"Front": "Point clé 2 ?", "Back": "Explication 2"},
    ]

    widget.set_diff(orig, mod_cards, patch_type="split")

    assert widget.is_split is True
    assert widget.split_selector is not None
    assert widget.split_selector.count() == 2

    # Carte 1 active
    content = widget.get_modified_content()
    assert isinstance(content, list)
    assert len(content) == 2
    assert content[0]["Front"] == "Point clé 1 ?"


def test_card_semantic_diff_widget_preview_update(qtbot):
    """Vérifie la mise à jour de l'onglet Aperçu Live."""
    widget = CardSemanticDiffWidget()
    qtbot.addWidget(widget)

    nt = NoteTypeModel(name="TestNT", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    orig = {"Front": "Q1", "Back": "R1"}
    mod = {"Front": "Q2", "Back": "R2"}

    widget.set_diff(orig, mod, note_type=nt)
    widget.tab_widget.setCurrentIndex(1)  # Bascule sur l'onglet Aperçu

    assert widget.preview_widget.current_fields.get("Front") == "Q2"
