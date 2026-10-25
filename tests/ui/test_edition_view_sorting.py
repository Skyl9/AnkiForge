"""Tests d'intégration pour le tri dans NoteVirtualTableModel et EditionView (ADR 0044).

Valide la réinitialisation de pagination lors du changement de tri,
la persistance par mode (Notes vs Cartes) et l'ordonnancement dynamique dans EditionView.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from pytestqt.qtbot import QtBot

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.ui.models.note_table_model import NoteVirtualTableModel
from ankiforge.ui.models.sorting import SortCriterion, SortDirection, SortOrder
from ankiforge.ui.views.edition_view import EditionView

pytestmark = pytest.mark.ui


@pytest.fixture
def edition_sorting_data(mock_db: Any) -> dict[str, Any]:
    """Crée 25 notes et cartes ordonnées pour valider la pagination et le tri."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck Pagination {uid}")
    nt = NoteTypeModel.create(name=f"Type Simple {uid}")

    notes: list[NoteModel] = []
    cards: list[CardModel] = []

    words = [
        "Antilope",
        "Baleine",
        "Castor",
        "Dauphin",
        "Elephant",
        "Faucon",
        "Girafe",
        "Herisson",
        "Iguane",
        "Jaguar",
        "Koala",
        "Lion",
        "Manchot",
        "Nandou",
        "Otarie",
        "Panda",
        "Quetzal",
        "Renard",
        "Singe",
        "Tigre",
        "Urubu",
        "Vipere",
        "Wallaby",
        "Xerus",
        "Zebre",
    ]
    for i, word in enumerate(words):
        note = NoteModel.create(
            guid=f"guid_{i}_{uid}",
            note_type=nt,
            sort_field=word,
            tags=json.dumps(["animaux"]),
        )
        NoteVersionModel.create(
            note=note,
            content=json.dumps({"Front": word, "Back": f"Définition de {word}"}),
            version_number=1,
            is_active=True,
        )
        card = CardModel.create(
            note=note,
            deck=deck,
            template_index=0,
            flags=(i % 4),
            lapses=i * 2,
            is_suspended=(i % 2 == 0),
        )
        notes.append(note)
        cards.append(card)

    return {
        "deck": deck,
        "nt": nt,
        "notes": notes,
        "cards": cards,
    }


def test_note_virtual_table_model_apply_sort_resets_pagination(edition_sorting_data: dict[str, Any]) -> None:
    """Vérifie que NoteVirtualTableModel réinitialise sa pagination et émet sort_changed."""
    note_ids = [n.id for n in edition_sorting_data["notes"]]
    base_query = NoteModel.select().where(NoteModel.id.in_(note_ids))

    # Initialisation avec tri alphabétique ASC sur sort_field (chunk_size=10 pour tester la pagination)
    order_asc = SortOrder(criterion=SortCriterion.RECTO, direction=SortDirection.ASC)
    model = NoteVirtualTableModel(query=base_query, chunk_size=10, sort_order=order_asc, display_mode="notes")

    # Ordre alphabétique attendu : Antilope ... Zèbre
    assert model.total_count == 25
    assert model.loaded_count == 10
    row0 = model.get_row(0)
    assert row0 is not None
    assert row0.recto.startswith("Antilope")

    # Écoute du signal sort_changed
    emitted_orders: list[SortOrder] = []
    model.sort_changed.connect(emitted_orders.append)

    # Bascule vers RECTO DESC
    order_desc = SortOrder(criterion=SortCriterion.RECTO, direction=SortDirection.DESC)
    model.apply_sort(order_desc)

    assert len(emitted_orders) == 1
    assert emitted_orders[0] == order_desc
    assert model.sort_order == order_desc

    # Après apply_sort, le premier bloc est rechargé avec Zebre en tête
    assert model.loaded_count == 10
    row0_desc = model.get_row(0)
    assert row0_desc is not None
    assert row0_desc.recto.startswith("Zebre")

    # canFetchMore et fetchMore fonctionnent sur le nouvel ordre
    assert model.canFetchMore() is True
    model.fetchMore()
    assert model.loaded_count == 20
    row10 = model.get_row(10)
    assert row10 is not None
    assert row10.recto.startswith("Otarie")


def test_edition_view_sort_orders_and_mode_switching(qtbot: QtBot, edition_sorting_data: dict[str, Any]) -> None:
    """Vérifie que EditionView gère séparément les tris notes/cartes et répercute le tri."""
    view = EditionView()
    qtbot.addWidget(view)

    # Par défaut, mode notes
    assert view.get_current_sort_order().criterion == SortCriterion.CREATED_AT

    # Définition d'un tri notes spécifique (ex: RECTO ASC)
    sort_notes = SortOrder(criterion=SortCriterion.RECTO, direction=SortDirection.ASC)
    view.set_sort_order(sort_notes)
    assert view.get_current_sort_order() == sort_notes

    # Bascule vers le mode Cartes
    view._on_display_mode_changed(1)  # 1 = mode Cartes
    assert view._display_mode == "cards"
    # Le mode Cartes conserve son tri par défaut (indépendant de notes)
    assert view.get_current_sort_order().criterion == SortCriterion.CREATED_AT

    # Définition d'un tri cartes spécifique (ex: LAPSES DESC)
    sort_cards = SortOrder(criterion=SortCriterion.LAPSES, direction=SortDirection.DESC)
    view.set_sort_order(sort_cards)
    assert view.get_current_sort_order() == sort_cards

    # Retour vers le mode Notes : restaure sort_notes sans collision
    view._on_display_mode_changed(0)  # 0 = mode Notes
    assert view._display_mode == "notes"
    assert view.get_current_sort_order() == sort_notes
