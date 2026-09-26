"""
Tests UI PySide6 / pytest-qt pour l'intégration des libellés personnalisés de drapeaux dans EditionView et NoteVirtualTableModel :
- Infobulle de la colonne drapeau reflétant le libellé personnalisé
- Titre du menu de filtrage des drapeaux
- Rafraîchissement live lors de l'émission de FlagLabelsUpdatedEvent
"""

from __future__ import annotations

import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.cards.flag_service import FlagService
from ankiforge.ui.models.note_table_model import NoteVirtualTableModel
from ankiforge.ui.views.edition_view import EditionView

pytestmark = pytest.mark.ui


@pytest.fixture(autouse=True)
def clean_flags():
    """Réinitialise les drapeaux avant et après chaque test."""
    FlagService.reset_to_defaults()
    yield
    FlagService.reset_to_defaults()


def test_note_virtual_table_model_flag_tooltip(mock_db) -> None:
    """La colonne Drapeau de NoteVirtualTableModel affiche le libellé personnalisé dans son ToolTipRole."""
    FlagService.set_flag_labels({1: "Vocabulaire Prioritaire", 4: "Formule"})

    nt = NoteTypeModel.create(name="NTFlags", fields_schema='["Front", "Back"]')
    deck = DeckModel.create(name="DeckFlags")
    n1 = NoteModel.create(note_type=nt)
    NoteVersionModel.create(note=n1, content=json.dumps({"Front": "Q1", "Back": "A1"}), is_active=True)
    CardModel.create(note=n1, deck=deck, template_index=0, flags=1)

    model = NoteVirtualTableModel(query=NoteModel.select())

    row_idx = model.find_row_by_note_id(n1.id)
    assert row_idx >= 0

    # Index ligne row_idx, colonne 1 (Drapeau)
    idx_flag = model.index(row_idx, 1)
    tooltip = model.data(idx_flag, Qt.ItemDataRole.ToolTipRole)
    assert tooltip == "Drapeau : Vocabulaire Prioritaire"


def test_edition_view_flag_filter_and_live_update(qtbot, mock_db) -> None:
    """EditionView prend en compte les libellés personnalisés et se rafraîchit lors d'un FlagLabelsUpdatedEvent."""
    FlagService.reset_to_defaults()
    FlagService.set_flag_labels({1: "À revoir", 3: "Validé"})

    nt = NoteTypeModel.create(name="NTFlags2", fields_schema='["Front", "Back"]')
    deck = DeckModel.create(name="DeckFlags2")
    n1 = NoteModel.create(note_type=nt)
    NoteVersionModel.create(note=n1, content=json.dumps({"Front": "Q1", "Back": "A1"}), is_active=True)
    CardModel.create(note=n1, deck=deck, template_index=0, flags=1)

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()
    QApplication.processEvents()

    # Sélectionner le filtre drapeau 1
    view._on_flag_filter_selected(1, f"Drapeau : {FlagService.get_flag_name(1)} ▾")
    assert "À revoir" in view.btn_filter_flag.text()

    # Mise à jour en direct via FlagService
    FlagService.set_flag_labels({1: "Urgence Absolue"})
    QApplication.processEvents()

    # Le libellé du bouton de filtre actif doit s'être mis à jour dynamiquement
    assert "Urgence Absolue" in view.btn_filter_flag.text()
