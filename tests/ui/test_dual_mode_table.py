"""
Tests unitaires et d'intégration pour le mode d'affichage Dual (Notes vs Cartes)
dans NoteVirtualTableModel et EditionView.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from PySide6.QtCore import Qt

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.ui.models.delegates import (
    CARD_ID_ROLE,
    FLAG_ROLE,
    NOTE_ID_ROLE,
    TEMPLATE_INDEX_ROLE,
)
from ankiforge.ui.models.note_table_model import NoteVirtualTableModel
from ankiforge.ui.views.edition_view import EditionView


@pytest.fixture
def dual_mode_sample_data(mock_db: Any) -> dict[str, Any]:
    """Crée des données de test avec 1 modèle multi-cartes, 1 deck, 2 notes et 4 cartes physiques."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck Test {uid}")

    templates = [
        {"name": "Recto -> Verso", "qfmt": "<b>Q1:</b> {{Front}}", "afmt": "{{FrontSide}}<hr><b>R1:</b> {{Back}}"},
        {"name": "Verso -> Recto", "qfmt": "<b>Q2:</b> {{Back}}", "afmt": "{{FrontSide}}<hr><b>R2:</b> {{Front}}"},
    ]
    nt = NoteTypeModel.create(
        name=f"Modèle Réversible {uid}",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps(templates),
        css_style=".card { font-size: 14px; }",
    )

    # Note 1 avec 2 cartes (gabarit 0 et gabarit 1)
    n1 = NoteModel.create(guid=f"guid_n1_{uid}", note_type=nt, deck=deck, tags=json.dumps(["vocabulaire", "anglais"]))
    NoteVersionModel.create(
        note=n1,
        content=json.dumps({"Front": "Apple", "Back": "Pomme"}),
        version_number=1,
        is_active=True,
    )
    c1_0 = CardModel.create(note=n1, deck=deck, template_index=0, flags=1)
    c1_1 = CardModel.create(note=n1, deck=deck, template_index=1, flags=2)

    # Note 2 avec 2 cartes (gabarit 0 et gabarit 1)
    n2 = NoteModel.create(guid=f"guid_n2_{uid}", note_type=nt, deck=deck, tags=json.dumps(["vocabulaire"]))
    NoteVersionModel.create(
        note=n2,
        content=json.dumps({"Front": "Sun", "Back": "Soleil"}),
        version_number=1,
        is_active=True,
    )
    c2_0 = CardModel.create(note=n2, deck=deck, template_index=0, flags=0)
    c2_1 = CardModel.create(note=n2, deck=deck, template_index=1, flags=0)

    return {
        "deck": deck,
        "note_type": nt,
        "notes": [n1, n2],
        "cards": [c1_0, c1_1, c2_0, c2_1],
    }


def test_table_model_headers_and_mode_switch(dual_mode_sample_data: dict[str, Any]) -> None:
    """Vérifie la mise à jour dynamique des en-têtes lors du basculement Notes <-> Cartes."""
    notes_query = NoteModel.select().order_by(NoteModel.id.asc())
    model = NoteVirtualTableModel(query=notes_query, display_mode="notes")

    assert model.display_mode == "notes"
    assert model.columnCount() == 7
    assert model.headerData(2, Qt.Orientation.Horizontal) == "Recto (Tri)"
    assert model.headerData(3, Qt.Orientation.Horizontal) == "Autres champs"

    # Basculement en mode cartes
    cards_query = CardModel.select().order_by(CardModel.id.asc())
    model.set_filter_query(cards_query, display_mode="cards")

    assert model.display_mode == "cards"
    assert model.columnCount() == 8
    expected_headers = ["", "", "Question", "Réponse", "Carte (Gabarit)", "Paquet", "Modèle", "Tags"]
    for idx, expected in enumerate(expected_headers):
        assert model.headerData(idx, Qt.Orientation.Horizontal) == expected


def test_table_model_data_and_roles_in_cards_mode(dual_mode_sample_data: dict[str, Any]) -> None:
    """Vérifie le chargement des CardRowData, le rendu des colonnes et les rôles Qt personnalisés."""
    cards = dual_mode_sample_data["cards"]
    cards_query = CardModel.select().where(CardModel.id.in_([c.id for c in cards])).order_by(CardModel.id.asc())
    model = NoteVirtualTableModel(query=cards_query, display_mode="cards")

    assert model.rowCount() == 4

    # Première ligne : c1_0 (Note 1, Template 0: "Recto -> Verso", Apple -> Pomme)
    idx_row0 = model.index(0, 0)
    assert model.data(idx_row0, NOTE_ID_ROLE) == dual_mode_sample_data["notes"][0].id
    assert model.data(idx_row0, CARD_ID_ROLE) == cards[0].id
    assert model.data(idx_row0, TEMPLATE_INDEX_ROLE) == 0

    # Colonne Flag (col 1)
    idx_flag = model.index(0, 1)
    assert model.data(idx_flag, FLAG_ROLE) == 1

    # Colonne Question (col 2) : "Q1: Apple" (HTML nettoyé par render_card_text)
    idx_q = model.index(0, 2)
    assert "Apple" in model.data(idx_q, Qt.ItemDataRole.DisplayRole)

    # Colonne Réponse (col 3) : "R1: Pomme"
    idx_a = model.index(0, 3)
    assert "Pomme" in model.data(idx_a, Qt.ItemDataRole.DisplayRole)

    # Colonne Gabarit (col 4) : "Recto -> Verso"
    idx_tmpl = model.index(0, 4)
    assert model.data(idx_tmpl, Qt.ItemDataRole.DisplayRole) == "Recto -> Verso"

    # Colonne Paquet (col 5) : Nom du deck
    idx_deck = model.index(0, 5)
    assert dual_mode_sample_data["deck"].name in model.data(idx_deck, Qt.ItemDataRole.DisplayRole)

    # Colonne Modèle (col 6) : Nom du modèle
    idx_model = model.index(0, 6)
    assert dual_mode_sample_data["note_type"].name in model.data(idx_model, Qt.ItemDataRole.DisplayRole)

    # Colonne Tags (col 7) : Tags affichés
    idx_tags = model.index(0, 7)
    assert "#vocabulaire" in model.data(idx_tags, Qt.ItemDataRole.DisplayRole)

    # Deuxième ligne : c1_1 (Note 1, Template 1: "Verso -> Recto", Pomme -> Apple)
    idx_row1_q = model.index(1, 2)
    assert "Pomme" in model.data(idx_row1_q, Qt.ItemDataRole.DisplayRole)
    idx_row1_a = model.index(1, 3)
    assert "Apple" in model.data(idx_row1_a, Qt.ItemDataRole.DisplayRole)
    assert model.data(model.index(1, 4), Qt.ItemDataRole.DisplayRole) == "Verso -> Recto"


def test_table_model_live_updates_in_cards_mode(dual_mode_sample_data: dict[str, Any]) -> None:
    """Vérifie la mise à jour en direct du flag et du contenu d'une note sur toutes ses cartes."""
    cards = dual_mode_sample_data["cards"]
    cards_query = CardModel.select().where(CardModel.id.in_([c.id for c in cards])).order_by(CardModel.id.asc())
    model = NoteVirtualTableModel(query=cards_query, display_mode="cards")

    c1_0 = cards[0]
    # Test update_card_flag
    model.update_card_flag(c1_0.id, 4)  # Bleu
    assert model.data(model.index(0, 1), FLAG_ROLE) == 4

    # Test update_note_content : les cartes 0 et 1 partagent la note 1
    n1 = dual_mode_sample_data["notes"][0]
    model.update_note_content(n1.id, {"Front": "Banana", "Back": "Banane"})

    # Carte 0 (Recto -> Verso) : Question "Banana", Réponse "Banane"
    assert "Banana" in model.data(model.index(0, 2), Qt.ItemDataRole.DisplayRole)
    assert "Banane" in model.data(model.index(0, 3), Qt.ItemDataRole.DisplayRole)

    # Carte 1 (Verso -> Recto) : Question "Banane", Réponse "Banana"
    assert "Banane" in model.data(model.index(1, 2), Qt.ItemDataRole.DisplayRole)
    assert "Banana" in model.data(model.index(1, 3), Qt.ItemDataRole.DisplayRole)


def test_table_model_checkboxes_in_cards_mode(dual_mode_sample_data: dict[str, Any]) -> None:
    """Vérifie la gestion des cases à cocher par carte en mode cartes."""
    cards = dual_mode_sample_data["cards"]
    cards_query = CardModel.select().where(CardModel.id.in_([c.id for c in cards])).order_by(CardModel.id.asc())
    model = NoteVirtualTableModel(query=cards_query, display_mode="cards")

    # Cocher la carte 0
    idx_chk0 = model.index(0, 0)
    model.setData(idx_chk0, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    assert model.get_checked_card_ids() == [cards[0].id]

    # Tout sélectionner
    model.set_all_checked(True)
    assert len(model.get_checked_card_ids()) == 4

    # Décocher une carte
    model.setData(idx_chk0, Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
    checked = model.get_checked_card_ids()
    assert cards[0].id not in checked
    assert len(checked) == 3


@pytest.mark.ui
def test_edition_view_dual_mode_toggle_and_interaction(qtbot: Any, dual_mode_sample_data: dict[str, Any]) -> None:
    """Vérifie le basculement interactif du bouton [ Notes | Cartes ] et la synchronisation avec le volet d'aperçu."""
    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # 1. Par défaut : Mode Notes
    assert view.btn_mode_notes.isChecked()
    assert not view.btn_mode_cards.isChecked()
    assert view.note_table_model.display_mode == "notes"
    assert view.note_table_model.rowCount() == 2  # 2 notes

    # 2. Basculement en Mode Cartes via le bouton pill
    view.btn_mode_cards.click()
    assert view.btn_mode_cards.isChecked()
    assert view.note_table_model.display_mode == "cards"
    assert view.note_table_model.rowCount() == 4  # 4 cartes

    # 3. Sélection de la deuxième carte (c1_1 : Template 1 "Verso -> Recto")
    row1_index = view.card_table.model().index(1, 2)
    view.card_table.setCurrentIndex(row1_index)

    # Vérification que la note parente est chargée dans l'éditeur
    assert view._current_note is not None
    assert view._current_note.id == dual_mode_sample_data["notes"][0].id
    assert "Front" in view.dynamic_field_widgets
    assert "Back" in view.dynamic_field_widgets

    # Vérification que le template_index 1 est sélectionné dans CardPreviewWidget
    assert view.card_preview.current_template_index == 1

    # 4. Vérification du ruban de navigation en mode Cartes
    view._toggle_table_collapsed()
    assert view._table_collapsed is True
    ribbon_text = view.lbl_card_ribbon_info.text()
    assert "Carte #" in ribbon_text
    assert "Verso -> Recto" in ribbon_text

    # 5. Retour en Mode Notes
    view._toggle_table_collapsed()
    view.btn_mode_notes.click()
    assert view.btn_mode_notes.isChecked()
    assert view.note_table_model.display_mode == "notes"
    assert view.note_table_model.rowCount() == 2
