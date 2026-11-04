"""Tests unitaires et UI pour DeletionImpactWidget avec CardPreviewWidget et navigation par lot."""

from __future__ import annotations

import json
import uuid

import pytest
from pytestqt.qtbot import QtBot

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry
from ankiforge.ui.views.consultant_view.widgets.garde_fou_views import DeletionImpactWidget
from ankiforge.ui.views.consultant_view.widgets.mcp_garde_fou_widget import MCPGardeFouWidget

pytestmark = [pytest.mark.ui]


@pytest.fixture
def sample_note() -> NoteModel:
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(
        name=f"NT_DEL_{uid}",
        fields_schema='["Front", "Back"]',
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}]),
        css_style="",
    )
    note = NoteModel.create(guid=f"g_del_{uid}", note_type=nt)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Front": "Mot en japonais", "Back": "Définition française"}),
        is_active=True,
    )
    return note


def test_deletion_impact_widget_single_note_preview(qtbot: QtBot, sample_note: NoteModel) -> None:
    """Vérifie que la suppression unitaire affiche l'aperçu de la note ciblée et son affordance."""
    patch = StagedPatchRegistry.create_patch(
        patch_type="card_delete",
        target_id=sample_note.id,
        diff_payload={
            "type": "card_delete",
            "note_id": sample_note.id,
            "reason": "Carte redondante",
        },
    )

    widget = DeletionImpactWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_patch(patch)

    # 1. Vérification de la présence de CardPreviewWidget
    assert hasattr(widget, "preview_widget"), "DeletionImpactWidget doit posséder une instance preview_widget"
    assert widget.preview_widget.current_fields.get("Front") == "Mot en japonais"
    assert widget.preview_widget.current_fields.get("Back") == "Définition française"

    # 2. Affordance de suppression présente
    assert hasattr(widget, "lbl_preview_badge") or hasattr(widget, "lbl_preview_title")

    # 3. Navigation par lot masquée pour 1 seule note
    assert hasattr(widget, "nav_widget")
    assert not widget.nav_widget.isVisible()

    # 4. Nettoyage
    widget.cleanup()


def test_deletion_impact_widget_payload_fallback(qtbot: QtBot) -> None:
    """Vérifie le repli sur les champs du payload lorsque la note n'est plus présente en BDD."""
    patch = StagedPatchRegistry.create_patch(
        patch_type="card_delete",
        target_id=999999,
        diff_payload={
            "type": "card_delete",
            "note_id": 999999,
            "original": {
                "fields": {
                    "Front": "Concept orphelin",
                    "Back": "Explication de secours",
                }
            },
            "reason": "Nettoyage orphelin",
        },
    )

    widget = DeletionImpactWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_patch(patch)

    assert widget.preview_widget.current_fields.get("Front") == "Concept orphelin"
    assert widget.preview_widget.current_fields.get("Back") == "Explication de secours"
    widget.cleanup()


def test_deletion_impact_widget_batch_notes_navigation(qtbot: QtBot) -> None:
    """Vérifie la navigation séquentielle entre les cartes d'un lot supprimé."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(
        name=f"NT_BATCH_{uid}",
        fields_schema='["Front", "Back"]',
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}]),
        css_style="",
    )

    notes = []
    for idx in range(3):
        n = NoteModel.create(guid=f"g_b_{uid}_{idx}", note_type=nt)
        NoteVersionModel.create(
            note=n,
            version_number=1,
            content=json.dumps({"Front": f"Question {idx + 1}", "Back": f"Réponse {idx + 1}"}),
            is_active=True,
        )
        notes.append(n)

    patch = StagedPatchRegistry.create_patch(
        patch_type="batch_card_deletion",
        target_id=notes[0].id,
        diff_payload={
            "type": "batch_card_deletion",
            "note_ids": [n.id for n in notes],
            "reason": "Suppression en masse de doublons",
        },
    )

    widget = DeletionImpactWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_patch(patch)

    # La barre de navigation doit être visible
    assert widget.nav_widget.isVisible()
    assert widget.combo_nav.count() == 3
    assert widget.preview_widget.current_fields.get("Front") == "Question 1"

    # Navigation vers l'élément suivant
    widget.btn_nav_next.click()
    assert widget.preview_widget.current_fields.get("Front") == "Question 2"
    assert widget.combo_nav.currentIndex() == 1

    # Navigation vers l'élément suivant
    widget.btn_nav_next.click()
    assert widget.preview_widget.current_fields.get("Front") == "Question 3"
    assert widget.combo_nav.currentIndex() == 2

    # Bouton suivant désactivé au dernier élément
    assert not widget.btn_nav_next.isEnabled()

    # Navigation retour
    widget.btn_nav_prev.click()
    assert widget.preview_widget.current_fields.get("Front") == "Question 2"

    widget.cleanup()


def test_deletion_impact_widget_deck_sample_preview(qtbot: QtBot) -> None:
    """Vérifie qu'une suppression de deck échantillonne les cartes pour l'aperçu."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck_Del_{uid}")
    nt = NoteTypeModel.create(
        name=f"NT_DECK_{uid}",
        fields_schema='["Front", "Back"]',
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}]),
        css_style="",
    )

    notes = []
    for idx in range(4):
        n = NoteModel.create(guid=f"g_d_{uid}_{idx}", note_type=nt)
        NoteVersionModel.create(
            note=n,
            version_number=1,
            content=json.dumps({"Front": f"DeckCard {idx + 1}", "Back": f"DeckAnswer {idx + 1}"}),
            is_active=True,
        )
        CardModel.create(note=n, deck=deck, ord=0)
        notes.append(n)

    patch = StagedPatchRegistry.create_patch(
        patch_type="deck_delete",
        target_id=deck.id,
        diff_payload={
            "type": "deck_delete",
            "deck_name": deck.name,
            "reason": "Suppression de paquet obsolète",
        },
    )

    widget = DeletionImpactWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_patch(patch)

    assert widget.nav_widget.isVisible()
    assert widget.combo_nav.count() == 4
    assert widget.preview_widget.current_fields.get("Front") == "DeckCard 1"

    widget.cleanup()


def test_deletion_impact_widget_empty_deck(qtbot: QtBot) -> None:
    """Vérifie le message d'état vide si le paquet supprimé ne contient aucune carte."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck_Empty_{uid}")

    patch = StagedPatchRegistry.create_patch(
        patch_type="deck_delete",
        target_id=deck.id,
        diff_payload={
            "type": "deck_delete",
            "deck_name": deck.name,
            "reason": "Paquet vide",
        },
    )

    widget = DeletionImpactWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_patch(patch)

    assert not widget.nav_widget.isVisible()
    widget.cleanup()


def test_mcp_garde_fou_widget_cleans_up_deletion_view(qtbot: QtBot, sample_note: NoteModel) -> None:
    """Vérifie que MCPGardeFouWidget appelle bien la libération des ressources de DeletionImpactWidget."""
    patch = StagedPatchRegistry.create_patch(
        patch_type="card_delete",
        target_id=sample_note.id,
        diff_payload={
            "type": "card_delete",
            "note_id": sample_note.id,
            "reason": "Purge",
        },
    )

    gf = MCPGardeFouWidget()
    qtbot.addWidget(gf)
    gf.show()
    gf.reload_pending_patches()
    assert gf.count() == 1

    # Sélection du patch de suppression
    assert gf.polymorphic_stack.currentWidget() is gf.deletion_view
    assert gf.deletion_view._patch is not None
    assert gf.deletion_view._patch.patch_id == patch.patch_id

    # Cleanup global sans crash
    gf.cleanup()
