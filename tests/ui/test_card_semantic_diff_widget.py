"""Tests unitaires et UI headless pour CardSemanticDiffWidget.

Couvre la comparaison champ par champ, le diff mot-à-mot, l'édition directe,
l'aperçu live et la gestion polymorphique (card, split, note_create).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from ankiforge.database.models import NoteTypeModel, StagedPatchModel
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
    widget.show()
    assert widget.tab_widget is not None
    assert widget.tab_widget.count() == 2
    assert "Comparaison" in widget.tab_widget.tabText(0)
    assert "Aperçu" in widget.tab_widget.tabText(1)


def test_card_semantic_diff_widget_set_diff_card(qtbot):
    """Vérifie le découpage sémantique champ par champ pour une carte standard."""
    widget = CardSemanticDiffWidget()
    qtbot.addWidget(widget)
    widget.show()

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
    widget.show()

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
    widget.show()

    orig = {"Front": "A"}
    mod = {"Front": "B"}
    widget.set_diff(orig, mod, is_applied=True)

    front_row = widget.get_field_rows()["Front"]
    assert front_row.mod_editor.isReadOnly() is True


def test_card_semantic_diff_widget_polymorphic_split(qtbot):
    """Vérifie la prise en charge d'un patch de type split (N cartes atomiques)."""
    widget = CardSemanticDiffWidget()
    qtbot.addWidget(widget)
    widget.show()

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
    """Vérifie la mise à jour dédoublée de l'onglet Aperçu (Originale vs Modifiée)."""
    widget = CardSemanticDiffWidget()
    qtbot.addWidget(widget)
    widget.show()

    nt = NoteTypeModel(name="TestNT", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    orig = {"Front": "Q1", "Back": "R1"}
    mod = {"Front": "Q2", "Back": "R2"}

    widget.set_diff(orig, mod, note_type=nt)
    widget.tab_widget.setCurrentIndex(1)  # Bascule sur l'onglet Aperçu

    # Vérification des deux cartes côte-à-côte
    assert widget.preview_orig.current_fields.get("Front") == "Q1"
    assert widget.preview_mod.current_fields.get("Front") == "Q2"
    assert widget.preview_widget.current_fields.get("Front") == "Q2"


def test_card_semantic_diff_widget_dual_preview_sync(qtbot):
    """Vérifie la synchronisation des commandes partagées (Recto/Verso, appareil, cleanup)."""
    widget = CardSemanticDiffWidget()
    qtbot.addWidget(widget)
    widget.show()

    nt = NoteTypeModel(name="TestNT", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    orig = {"Front": "Orig Front", "Back": "Orig Back"}
    mod = {"Front": "Mod Front", "Back": "Mod Back"}

    widget.set_diff(orig, mod, note_type=nt)

    # Initialement recto
    assert widget.preview_orig.is_recto is True
    assert widget.preview_mod.is_recto is True

    # Bascule Recto/Verso partagée
    widget._on_shared_toggle_side()
    assert widget.preview_orig.is_recto is False
    assert widget.preview_mod.is_recto is False

    # Deuxième bascule -> retour au recto
    widget._on_shared_toggle_side()
    assert widget.preview_orig.is_recto is True
    assert widget.preview_mod.is_recto is True

    # Bascule appareil partagée
    widget._on_shared_device_mode("mobile")
    assert widget._shared_device_mode == "mobile"
    assert widget.preview_orig._device_mode == "mobile"
    assert widget.preview_mod._device_mode == "mobile"

    # Libération propre sans exception
    widget.cleanup()


def test_card_semantic_diff_widget_set_patch_split_with_wozniak(qtbot) -> None:
    """Vérifie set_patch avec un patch de type 'split', l'inspection, la retouche et l'indicateur Wozniak."""
    widget = CardSemanticDiffWidget()
    qtbot.addWidget(widget)
    widget.show()

    payload = {
        "type": "split",
        "note_id": 42,
        "title": "Proposition de Scission Atomique — Note #42",
        "original": {"Front": "Question originale dense avec plus de vingt-cinq mots pour violer l'atomicité de Wozniak", "Back": "Réponse 1 et Réponse 2"},
        "modified": [
            {"Front": "Question atomique 1 ?", "Back": "Réponse concise 1"},
            {"Front": "Question atomique 2 ?", "Back": "Réponse concise 2"},
        ],
    }
    patch = StagedPatchModel(
        patch_id="patch_split_test",
        patch_type="split",
        target_id=42,
        diff_payload=json.dumps(payload),
        status="pending",
    )

    widget.set_patch(patch)

    assert widget.is_split is True
    assert widget.split_bar.isVisible() is True
    assert widget.split_selector.count() == 2

    # Indicateur Wozniak présent
    assert hasattr(widget, "wozniak_badge")
    assert widget.wozniak_badge.isVisible() is True
    assert "Wozniak" in widget.wozniak_badge.text()

    # Retouche de la carte atomique 1
    rows = widget.get_field_rows()
    assert "Front" in rows
    rows["Front"].mod_editor.setPlainText("Question atomique 1 retouchée")

    # Bascule sur la carte atomique 2
    widget.split_selector.setCurrentIndex(1)
    rows_c2 = widget.get_field_rows()
    assert rows_c2["Front"].mod_editor.toPlainText() == "Question atomique 2 ?"

    # Vérification du modified_content complet
    content = widget.get_modified_content()
    assert isinstance(content, list)
    assert len(content) == 2
    assert content[0]["Front"] == "Question atomique 1 retouchée"
    assert content[1]["Front"] == "Question atomique 2 ?"


def test_card_semantic_diff_widget_set_patch_note_type_create(qtbot) -> None:
    """Vérifie set_patch avec un patch de type 'note_type_create'."""
    widget = CardSemanticDiffWidget()
    qtbot.addWidget(widget)
    widget.show()

    payload = {
        "type": "note_type_create",
        "name": "Nouveau Type Géographie",
        "fields_schema": ["Capitale", "Pays", "Drapeau"],
        "templates": [{"name": "Carte 1", "qfmt": "{{Capitale}}", "afmt": "{{Pays}}"}],
        "css_style": ".card { font-size: 16px; color: blue; }",
        "description": "Modèle pour apprendre les capitales du monde",
        "title": "Proposition de Création de Type de Note — 'Nouveau Type Géographie'",
    }
    patch = StagedPatchModel(
        patch_id="patch_nt_create_test",
        patch_type="note_type_create",
        target_id=0,
        diff_payload=json.dumps(payload),
        status="pending",
    )

    # Ne doit pas lever d'exception
    widget.set_patch(patch)

    # Récupération du contenu modifié (doit préserver le nom et les champs)
    mod_content = widget.get_modified_content()
    assert isinstance(mod_content, dict)
    assert mod_content.get("name") == "Nouveau Type Géographie"
    assert "Capitale" in str(mod_content.get("fields_schema"))


def test_card_semantic_diff_widget_set_patch_note_type_change(qtbot) -> None:
    """Vérifie set_patch avec un patch de type 'note_type_change'."""
    widget = CardSemanticDiffWidget()
    qtbot.addWidget(widget)
    widget.show()

    payload = {
        "type": "note_type_change",
        "note_ids": [10, 11, 12],
        "target_model": "Modèle Standard",
        "target_model_id": 5,
        "mapping_champs": {"Front": "Recto", "Back": "Verso"},
        "warnings": ["Le modèle source possède 2 gabarits vs 1 pour le modèle cible"],
        "title": "Proposition de Migration de 3 note(s) vers 'Modèle Standard'",
    }
    patch = StagedPatchModel(
        patch_id="patch_nt_change_test",
        patch_type="note_type_change",
        target_id=5,
        diff_payload=json.dumps(payload),
        status="pending",
    )

    # Ne doit pas lever d'exception
    widget.set_patch(patch)

    mod_content = widget.get_modified_content()
    assert isinstance(mod_content, dict)
    assert mod_content.get("target_model") == "Modèle Standard"
    assert mod_content.get("note_ids") == [10, 11, 12]


def test_card_semantic_diff_widget_set_patch_model_refactor(qtbot) -> None:
    """Vérifie set_patch avec un patch de type 'model' (refactor de modèle existant)."""
    widget = CardSemanticDiffWidget()
    qtbot.addWidget(widget)
    widget.show()

    payload = {
        "type": "model",
        "name": "Basic",
        "original": {"fields": ["Front", "Back"], "css": ".card { font-size: 14px; }", "description": "Modèle standard"},
        "modified": {"fields": ["Front", "Back", "Extra"], "css": ".card { font-size: 16px; }", "description": "Modèle enrichi"},
        "title": "Refactor du modèle Basic",
    }
    patch = StagedPatchModel(
        patch_id="patch_model_test",
        patch_type="model",
        target_id=1,
        diff_payload=json.dumps(payload),
        status="pending",
    )

    widget.set_patch(patch)

    mod_content = widget.get_modified_content()
    assert isinstance(mod_content, dict)
    assert "Extra" in str(mod_content.get("fields_schema"))


def test_card_semantic_diff_widget_set_patch_css_tune(qtbot) -> None:
    """Vérifie set_patch avec un patch de type 'css_tune'."""
    widget = CardSemanticDiffWidget()
    qtbot.addWidget(widget)
    widget.show()

    payload = {
        "type": "css_tune",
        "name": "Basic",
        "original": ".card { color: black; }",
        "modified": ".card { color: #123456; }",
        "title": "Ajustement CSS pour Basic",
    }
    patch = StagedPatchModel(
        patch_id="patch_css_test",
        patch_type="css_tune",
        target_id=1,
        diff_payload=json.dumps(payload),
        status="pending",
    )

    widget.set_patch(patch)

    mod_content = widget.get_modified_content()
    assert ".card { color: #123456; }" in str(mod_content)
