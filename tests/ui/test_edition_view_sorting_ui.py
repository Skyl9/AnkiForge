"""Tests UI PySide6 / pytest-qt pour le triple accès au tri et sa persistance dans EditionView (ADR 0044).

Valide :
1. Le bouton de tri dans la barre de filtres avec son libellé dynamique et son menu.
2. L'interactivité des en-têtes de colonnes (QHeaderView.sectionClicked) avec cycle binaire et chevrons.
3. Le sous-menu de tri dans le menu contextuel clic droit.
4. La réinitialisation au tri par défaut.
5. La persistance indépendante par profil et par mode dans SettingsService.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu
from pytestqt.qtbot import QtBot

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.models.sorting import SortCriterion, SortDirection, SortOrder
from ankiforge.ui.views.edition_view import EditionView

pytestmark = pytest.mark.ui


@pytest.fixture
def sorting_ui_sample_data(mock_db: Any) -> dict[str, Any]:
    """Prépare un jeu de données pour valider le tri interactif dans EditionView."""
    uid = uuid.uuid4().hex[:6]
    deck_a = DeckModel.create(name=f"Deck Alpha {uid}")
    deck_b = DeckModel.create(name=f"Deck Beta {uid}")
    nt = NoteTypeModel.create(name=f"Type UI {uid}")

    n1 = NoteModel.create(guid=f"n1_{uid}", note_type=nt, sort_field="Zèbre", tags=json.dumps(["tag1"]))
    NoteVersionModel.create(note=n1, content=json.dumps({"Front": "Zèbre", "Back": "Animal rayé"}), is_active=True)
    c1 = CardModel.create(note=n1, deck=deck_b, lapses=8, flags=2, is_suspended=False)

    n2 = NoteModel.create(guid=f"n2_{uid}", note_type=nt, sort_field="Antilope", tags=json.dumps(["tag2"]))
    NoteVersionModel.create(note=n2, content=json.dumps({"Front": "Antilope", "Back": "Animal rapide"}), is_active=True)
    c2 = CardModel.create(note=n2, deck=deck_a, lapses=1, flags=1, is_suspended=True)

    return {
        "deck_a": deck_a,
        "deck_b": deck_b,
        "n1": n1,
        "n2": n2,
        "c1": c1,
        "c2": c2,
    }


def test_filter_bar_sort_button_and_dynamic_label(qtbot: QtBot, sorting_ui_sample_data: dict[str, Any]) -> None:
    """Vérifie la présence du bouton de tri dans la barre de filtres et son libellé dynamique."""
    # Réinitialise les réglages éventuels
    SettingsService.set("edition/sort_notes", None, category="ui")
    SettingsService.set("edition/sort_cards", None, category="ui")

    view = EditionView()
    qtbot.addWidget(view)

    # 1. Vérification du bouton
    assert hasattr(view, "btn_sort_order")
    btn = view.btn_sort_order
    assert btn.isVisibleTo(view) or not btn.isHidden()

    # Par défaut : Date de création
    assert "Date de création" in btn.text()
    assert "▲" in btn.text() or "▼" in btn.text()

    # 2. Changement de tri -> Mise à jour dynamique du libellé
    view.set_sort_order(SortOrder(SortCriterion.RECTO, SortDirection.DESC))
    assert "Recto" in btn.text() or "Question" in btn.text()
    assert "▼" in btn.text()

    # 3. Construction et ouverture du menu de tri
    menu = view._build_sort_menu()
    assert isinstance(menu, QMenu)
    action_texts = [a.text() for a in menu.actions() if a.text()]
    assert any("Date de création" in t for t in action_texts)
    assert any("Recto" in t or "Question" in t for t in action_texts)
    assert any("Paquet" in t for t in action_texts)
    assert any("Réinitialiser le tri par défaut" in t for t in action_texts)


def test_header_section_clicked_binary_cycle_and_indicators(qtbot: QtBot, sorting_ui_sample_data: dict[str, Any]) -> None:
    """Vérifie que le clic sur les en-têtes de colonnes alterne ASC ➔ DESC et met à jour le chevron."""
    view = EditionView()
    qtbot.addWidget(view)

    header = view.card_table.horizontalHeader()
    col_recto = 2  # Colonne Recto / Question

    # Clic sur colonne 0 : coche/décoche sans altérer le tri
    initial_order = view.get_current_sort_order()
    view._on_header_section_clicked(0)
    assert view.get_current_sort_order() == initial_order

    # Premier clic sur col_recto : active RECTO ASC
    view._on_header_section_clicked(col_recto)
    order1 = view.get_current_sort_order()
    assert order1.criterion == SortCriterion.RECTO
    assert order1.direction == SortDirection.ASC
    assert header.isSortIndicatorShown() is True
    assert header.sortIndicatorSection() == col_recto
    assert header.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder

    # Deuxième clic consécutif sur col_recto : bascule vers RECTO DESC (cycle binaire)
    view._on_header_section_clicked(col_recto)
    order2 = view.get_current_sort_order()
    assert order2.criterion == SortCriterion.RECTO
    assert order2.direction == SortDirection.DESC
    assert header.sortIndicatorSection() == col_recto
    assert header.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder

    # Troisième clic consécutif : re-bascule vers RECTO ASC
    view._on_header_section_clicked(col_recto)
    order3 = view.get_current_sort_order()
    assert order3.criterion == SortCriterion.RECTO
    assert order3.direction == SortDirection.ASC
    assert header.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder


def test_context_menu_contains_sort_submenu_and_reset(
    qtbot: QtBot,
    sorting_ui_sample_data: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vérifie que le menu contextuel clic droit contient 'Trier par...' et la réinitialisation."""
    view = EditionView()
    qtbot.addWidget(view)
    view.refresh_data()

    # 1. Vérification du sous-menu dans le menu contextuel
    from ankiforge.ui.theme import StyledMenu

    captured_menus: list[Any] = []
    monkeypatch.setattr(StyledMenu, "exec", lambda self_m, *args, **kwargs: captured_menus.append(self_m))

    rect = view.card_table.visualRect(view.note_table_model.index(0, 2))
    view._show_card_context_menu(rect.center())

    assert len(captured_menus) == 1
    ctx_menu = captured_menus[0]
    sort_submenus = [act.menu() for act in ctx_menu.actions() if act.menu() and "Trier par" in act.text()]
    assert len(sort_submenus) == 1
    sub_actions = [a.text() for a in sort_submenus[0].actions() if a.text()]
    assert any("Date de création" in t for t in sub_actions)
    assert any("Réinitialiser le tri par défaut" in t for t in sub_actions)

    # 2. Simulation d'un tri modifié
    view.set_sort_order(SortOrder(SortCriterion.RECTO, SortDirection.DESC))
    assert view.get_current_sort_order().criterion == SortCriterion.RECTO

    # 3. Réinitialisation via l'action dédiée
    view.reset_sort_order_to_default()
    assert view.get_current_sort_order().criterion == SortCriterion.CREATED_AT
    assert view.get_current_sort_order().direction == SortDirection.ASC


def test_sort_persistence_across_modes_and_sessions(qtbot: QtBot, sorting_ui_sample_data: dict[str, Any]) -> None:
    """Vérifie que les réglages de tri sont persistés indépendamment pour les notes et les cartes."""
    # Nettoyage préalable
    SettingsService.set("edition/sort_notes", None, category="ui")
    SettingsService.set("edition/sort_cards", None, category="ui")

    view1 = EditionView()
    qtbot.addWidget(view1)

    # Configuration d'un tri spécifique en mode Notes
    order_notes = SortOrder(criterion=SortCriterion.RECTO, direction=SortDirection.DESC)
    view1.set_sort_order(order_notes)

    # Vérification persistance SettingsService
    saved_notes = SettingsService.get("edition/sort_notes", None)
    assert saved_notes is not None
    assert saved_notes.get("criterion") == "recto"
    assert saved_notes.get("direction") == "desc"

    # Bascule vers mode Cartes et configuration d'un tri Cartes (ex: LAPSES DESC)
    view1._on_display_mode_changed(1)  # 1 = Cartes
    order_cards = SortOrder(criterion=SortCriterion.LAPSES, direction=SortDirection.DESC)
    view1.set_sort_order(order_cards)

    saved_cards = SettingsService.get("edition/sort_cards", None)
    assert saved_cards is not None
    assert saved_cards.get("criterion") == "lapses"
    assert saved_cards.get("direction") == "desc"

    # Simulation d'une nouvelle session (nouvelle instance EditionView)
    view2 = EditionView()
    qtbot.addWidget(view2)

    # En mode Notes initial, view2 restaure order_notes
    assert view2.get_current_sort_order() == order_notes

    # Bascule en mode Cartes restaure order_cards
    view2._on_display_mode_changed(1)
    assert view2.get_current_sort_order() == order_cards
