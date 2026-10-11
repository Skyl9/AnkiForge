"""Tests UI headless pour TagHygieneDialog et TagClusterCard."""

from __future__ import annotations

import json
import uuid

import pytest

from ankiforge.database.models import DeckModel, NoteModel, NoteTypeModel
from ankiforge.services.cards.bulk_hygiene_service import TagCluster, TagFrequency
from ankiforge.ui.dialogs.tag_hygiene_dialog import TagClusterCard, TagHygieneDialog

pytestmark = pytest.mark.ui


@pytest.fixture
def tag_dialog_setup(mock_db):
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck_{uid}")
    nt = NoteTypeModel.create(
        name=f"Model_{uid}",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "C1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
    )
    n1 = NoteModel.create(note_type=nt, tags='["Anatomie"]')
    n2 = NoteModel.create(note_type=nt, tags='["anatomie"]')
    n3 = NoteModel.create(note_type=nt, tags='["pharmacologie"]')
    n4 = NoteModel.create(note_type=nt, tags='["pharmacologies"]')
    return {"deck": deck, "nt": nt, "notes": [n1, n2, n3, n4]}


def test_tag_cluster_card_unit(qtbot):
    """Vérifie le fonctionnement unitaire de TagClusterCard (sélection, plan de fusion, exclusion partielle)."""
    cluster = TagCluster(
        cluster_id="case_1",
        cluster_type="case",
        canonical_tag="anatomie",
        tags=[
            TagFrequency(tag="anatomie", count=10),
            TagFrequency(tag="Anatomie", count=2),
            TagFrequency(tag="ANATOMIE", count=1),
        ],
        total_notes_count=12,
    )
    card = TagClusterCard(cluster)
    qtbot.addWidget(card)

    assert card.cluster_cb.isChecked() is True
    assert card.target_combo.currentText() == "anatomie"

    # Vérification du plan de fusion initial : Anatomie et ANATOMIE fusionnent vers anatomie
    plan = card.get_merge_plan()
    assert plan is not None
    assert plan.target_tag == "anatomie"
    assert set(plan.tags_to_merge) == {"Anatomie", "ANATOMIE"}

    # Exclusion partielle : décocher ANATOMIE
    cb_caps = card._variant_checkboxes["ANATOMIE"]
    cb_caps.setChecked(False)

    plan_partial = card.get_merge_plan()
    assert plan_partial is not None
    assert plan_partial.tags_to_merge == ["Anatomie"]

    # Décocher la grappe globale
    card.cluster_cb.setChecked(False)
    assert card.is_included() is False
    assert card.get_merge_plan() is None


def test_tag_hygiene_dialog_lifecycle(qtbot, tag_dialog_setup):
    """Vérifie le cycle de vie du dialogue TagHygieneDialog (analyse, filtrage et application)."""
    dialog = TagHygieneDialog()
    qtbot.addWidget(dialog)
    dialog.show()

    # Attendre que le worker termine
    qtbot.waitUntil(lambda: len(dialog.cards) >= 2, timeout=5000)

    assert len(dialog.cards) == 2
    assert dialog.btn_apply.isEnabled() is True

    # Test du filtre par pilule : Casse uniquement
    dialog._set_filter_type("case")
    visible_cards = [c for c in dialog.cards if not c.isHidden()]
    assert len(visible_cards) == 1
    assert visible_cards[0].cluster.cluster_type == "case"

    # Test du filtre : Toutes
    dialog._set_filter_type("all")
    assert sum(1 for c in dialog.cards if not c.isHidden()) == 2

    # Test de la recherche textuelle
    dialog.search_input.setText("pharma")
    matching_cards = [c for c in dialog.cards if not c.isHidden()]
    assert len(matching_cards) == 1
    assert "pharmacologie" in matching_cards[0].cluster.canonical_tag

    # Réinitialisation de la recherche
    dialog.search_input.clear()
    assert sum(1 for c in dialog.cards if not c.isHidden()) == 2

    # Tout décocher
    dialog._toggle_all_selection()
    assert dialog.btn_apply.isEnabled() is False

    # Tout recocher
    dialog._toggle_all_selection()
    assert dialog.btn_apply.isEnabled() is True

    # Sélection partielle : décocher 1 carte sur 2
    dialog.cards[0].cluster_cb.setChecked(False)
    assert dialog.btn_apply.isEnabled() is True
    assert "restent intactes" in dialog.status_lbl.text()

    # Recocher la première carte
    dialog.cards[0].cluster_cb.setChecked(True)
    assert "restent intactes" not in dialog.status_lbl.text()

    # Clic sur Appliquer la fusion
    dialog._on_apply_clicked()
    assert dialog.applied_result is not None
    assert dialog.applied_result.success is True
    assert dialog.applied_result.merged_clusters_count == 2
