"""Tests unitaires pour CardCreateViewWidget.

Vérifie l'affichage de création de carte, la séparation en volets via QSplitter,
les modes d'affichage (split, fields, preview), la modification dynamique des champs et tags,
ainsi que la navigation dans un lot de cartes.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from ankidraft.database.models import DeckModel, NoteTypeModel
from ankidraft.ui.widgets.card_create_view_widget import CardCreateViewWidget


@pytest.fixture
def clean_widget(qtbot: QtBot) -> Any:
    widgets: list[QWidget] = []

    def _create() -> CardCreateViewWidget:
        w = CardCreateViewWidget()
        qtbot.addWidget(w)
        w.show()
        widgets.append(w)
        return w

    yield _create

    for w in widgets:
        w.cleanup()


@pytest.mark.ui
def test_card_create_view_initial_state(clean_widget: Any) -> None:
    """Vérifie la présence du splitter, des panneaux gauche/droite et du mode split par défaut."""
    widget: CardCreateViewWidget = clean_widget()
    assert widget.content_splitter.orientation() == Qt.Orientation.Horizontal
    assert widget.left_panel.isVisible()
    assert widget.right_panel.isVisible()
    assert widget.btn_mode_split.isChecked()
    assert not widget.btn_mode_fields.isChecked()
    assert not widget.btn_mode_preview.isChecked()


@pytest.mark.ui
def test_card_create_view_modes(clean_widget: Any) -> None:
    """Vérifie la bascule entre les modes champs, aperçu et partagé."""
    widget: CardCreateViewWidget = clean_widget()

    # Mode Champs seuls
    widget.set_view_mode("fields")
    assert widget.left_panel.isVisible()
    assert not widget.right_panel.isVisible()
    assert widget.btn_mode_fields.isChecked()

    # Mode Aperçu seul
    widget.set_view_mode("preview")
    assert not widget.left_panel.isVisible()
    assert widget.right_panel.isVisible()
    assert widget.btn_mode_preview.isChecked()

    # Mode Côte à côte
    widget.set_view_mode("split")
    assert widget.left_panel.isVisible()
    assert widget.right_panel.isVisible()
    assert widget.btn_mode_split.isChecked()


@pytest.mark.ui
def test_card_create_view_single_note_display_and_edit(clean_widget: Any, qtbot: QtBot) -> None:
    """Vérifie le chargement d'un patch note_create, l'édition d'un champ et le signal émis."""
    widget: CardCreateViewWidget = clean_widget()

    deck = DeckModel.create(name="DeckTest_CardCreate")
    nt = NoteTypeModel.create(
        name="ModelTest_CardCreate",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}"}]),
    )

    patch_data = {
        "patch_type": "note_create",
        "diff_payload": {
            "fields": {"Front": "Question test", "Back": "Réponse test"},
            "deck_name": deck.name,
            "note_type_name": nt.name,
            "tags": ["vocabulaire", "anglais"],
        },
    }

    widget.set_patch(patch_data)

    assert "Front" in widget._field_rows
    assert "Back" in widget._field_rows
    assert widget.badge_fields_count.text() == "2 champ(s)"
    assert len(widget.get_tags()) == 2

    # Édition d'un champ et écoute du signal
    edited_records: list[dict[str, Any]] = []
    widget.content_edited.connect(edited_records.append)

    front_row = widget._field_rows["Front"]
    front_row.value_edit.setPlainText("Nouvelle question modifiée")

    assert len(edited_records) >= 1
    assert edited_records[-1]["Front"] == "Nouvelle question modifiée"
    assert front_row.badge_words.text() == "3 mots"


@pytest.mark.ui
def test_card_create_view_tags_management(clean_widget: Any) -> None:
    """Vérifie l'ajout et le retrait de tags."""
    widget: CardCreateViewWidget = clean_widget()

    patch_data = {
        "patch_type": "note_create",
        "diff_payload": {
            "fields": {"Front": "Q", "Back": "A"},
            "tags": ["initial_tag"],
        },
    }
    widget.set_patch(patch_data)
    assert widget.get_tags() == ["initial_tag"]

    # Ajout d'un tag
    widget.new_tag_edit.setText("nouveau_tag")
    widget._on_new_tag_added()
    assert "nouveau_tag" in widget.get_tags()

    # Retrait d'un tag
    widget._on_tag_removed("initial_tag")
    assert "initial_tag" not in widget.get_tags()
    assert widget.get_tags() == ["nouveau_tag"]


@pytest.mark.ui
def test_card_create_view_batch_navigation(clean_widget: Any) -> None:
    """Vérifie la navigation dans un lot batch_note_create."""
    widget: CardCreateViewWidget = clean_widget()

    patch_data = {
        "patch_type": "batch_note_create",
        "diff_payload": {
            "notes": [
                {"fields": {"Front": "Carte 1 Q", "Back": "Carte 1 R"}, "tags": ["tag1"]},
                {"fields": {"Front": "Carte 2 Q", "Back": "Carte 2 R"}, "tags": ["tag2"]},
            ]
        },
    }
    widget.set_patch(patch_data)

    assert widget.nav_widget.isVisible()
    assert widget.lbl_nav_pos.text() == "1 / 2"
    assert not widget.btn_nav_prev.isEnabled()
    assert widget.btn_nav_next.isEnabled()
    assert widget.get_fields_dict()["Front"] == "Carte 1 Q"

    # Passer à la carte suivante
    widget._go_next()
    assert widget.lbl_nav_pos.text() == "2 / 2"
    assert widget.btn_nav_prev.isEnabled()
    assert not widget.btn_nav_next.isEnabled()
    assert widget.get_fields_dict()["Front"] == "Carte 2 Q"

    # Revenir en arrière
    widget._go_prev()
    assert widget.lbl_nav_pos.text() == "1 / 2"
    assert widget.get_fields_dict()["Front"] == "Carte 1 Q"
