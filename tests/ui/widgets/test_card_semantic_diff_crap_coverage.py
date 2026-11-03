"""Tests de couverture ciblés pour CardSemanticDiffWidget et BatchNoteCreateView afin de résorber le risque CRAP."""

from __future__ import annotations

from typing import Any

import pytest

from ankiforge.ui.widgets.card_semantic_diff_widget import (
    BatchNoteCreateView,
    CardSemanticDiffWidget,
)

pytestmark = pytest.mark.ui


def test_batch_note_create_view_lifecycle(qtbot: Any) -> None:
    """Couvre set_payload, _render_current, navigation et modifications dans BatchNoteCreateView (CC=19, CRAP=380)."""
    view = BatchNoteCreateView()
    qtbot.addWidget(view)

    payload = {
        "notes": [
            {
                "fields": {"Front": "Q1", "Back": "R1"},
                "note_type": "Basic",
                "deck": "Default",
            },
            {
                "fields": {"Front": "Q2", "Back": "R2"},
                "note_type": "Basic",
                "deck": "Default",
            },
        ],
        "tags": ["science", "physique"],
    }

    # 1. Chargement du payload
    view.set_payload(payload)
    assert view._notes == payload["notes"]
    assert "2 note(s)" in view.lbl_title.text()
    assert "1 / 2" in view.lbl_count.text()
    assert view.btn_next.isEnabled()
    assert not view.btn_prev.isEnabled()

    # 2. Navigation
    view._go_next()
    assert view._current_index == 1
    assert "2 / 2" in view.lbl_count.text()
    assert not view.btn_next.isEnabled()
    assert view.btn_prev.isEnabled()

    view._go_prev()
    assert view._current_index == 0

    # 3. Modification de cellule (_on_cell_changed)
    item_val = view.table.item(0, 1)
    assert item_val is not None
    item_val.setText("Q1 modifie")
    view._on_cell_changed(0, 1)

    mod_content = view.get_modified_content()
    assert mod_content["notes"][0]["fields"]["Front"] == "Q1 modifie"

    # Modification de colonne non éditable (column=0)
    view._on_cell_changed(0, 0)

    # 4. Modification des tags (_on_tags_changed)
    view._on_tags_changed("chimie biologie")
    mod_tags = view.get_modified_content().get("tags", [])
    assert "chimie" in mod_tags
    assert "biologie" in mod_tags


def test_card_semantic_diff_widget_batch_create_and_split(qtbot: Any) -> None:
    """Couvre set_patch avec batch_note_create, split et les extracteurs de contenu modifié."""
    widget = CardSemanticDiffWidget()
    qtbot.addWidget(widget)

    # 1. Batch note create patch
    batch_patch = {
        "patch_type": "batch_note_create",
        "notes": [
            {"fields": {"Front": "Q batch", "Back": "R batch"}, "note_type": "Basic", "deck": "D"},
        ],
        "tags": ["lot1", "lot2"],
    }
    widget.set_patch(batch_patch)
    assert widget._batch_view is not None
    assert widget._batch_view.get_modified_content().get("tags") == ["lot1", "lot2"]

    # Test avec set_diff direct pour get_modified_tags
    widget.set_diff(
        original={"Front": "Q", "Back": "R"},
        modified={"Front": "Q2", "Back": "R2"},
        modified_tags=["lot1", "lot2"],
    )
    assert widget.get_modified_tags() == ["lot1", "lot2"]
    res_content = widget.get_modified_content()
    assert isinstance(res_content, dict)

    # 2. Split patch
    split_patch = {
        "patch_type": "split",
        "original": {"Front": "Long texte complexe", "Back": "Explication detaillee"},
        "new_cards": [
            {"Front": "Partie 1", "Back": "Reponse 1"},
            {"Front": "Partie 2", "Back": "Reponse 2"},
        ],
    }
    widget.set_patch(split_patch)
    assert widget.is_split
    assert widget.split_selector.count() == 2

    # Sélection de la deuxième carte scindée
    widget.split_selector.setCurrentIndex(1)
    assert widget._active_split_index == 1
