"""
Tests unitaires et UI pour DeckSelectWindow et CreateDeckDialog.
"""

import uuid
from typing import Any

import pytest

from ankiforge.database.models import DeckModel
from ankiforge.ui.components.deck_select_window import DeckSelectWindow
from ankiforge.ui.dialogs.create_deck_dialog import CreateDeckDialog


@pytest.mark.ui
def test_deck_select_window_allow_all(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le comportement de allow_all (True vs False)."""
    uid = uuid.uuid4().hex[:6]
    d1 = DeckModel.create(name=f"Deck_{uid}")

    # allow_all=True
    win_all = DeckSelectWindow(allow_all=True)
    qtbot.addWidget(win_all)
    assert win_all.tree.topLevelItem(0).text(0) == "Tous les paquets"

    # allow_all=False
    win_strict = DeckSelectWindow(allow_all=False, selected_deck_id=d1.id)
    qtbot.addWidget(win_strict)
    # L'élément racine "Tous les paquets" ne doit pas exister
    top_items = [win_strict.tree.topLevelItem(i).text(0) for i in range(win_strict.tree.topLevelItemCount())]
    assert "Tous les paquets" not in top_items
    assert win_strict.btn_confirm.isEnabled()


@pytest.mark.ui
def test_create_deck_dialog(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la création d'un paquet et de ses sous-paquets via CreateDeckDialog."""
    uid = uuid.uuid4().hex[:6]
    dlg = CreateDeckDialog(initial_name=f"Maths_{uid}::Algebre", parent=None)
    qtbot.addWidget(dlg)

    assert dlg.btn_submit.isEnabled()

    emitted: list[tuple[int, str]] = []
    dlg.deck_created.connect(lambda did, name: emitted.append((did, name)))

    dlg.btn_submit.click()

    assert len(emitted) == 1
    deck_id, deck_name = emitted[0]
    assert deck_name == f"Maths_{uid}::Algebre"

    # Vérifier que le paquet parent a bien été créé automatiquement
    parent_deck = DeckModel.get_or_none(DeckModel.name == f"Maths_{uid}")
    assert parent_deck is not None
    child_deck = DeckModel.get_by_id(deck_id)
    assert child_deck.parent_deck.id == parent_deck.id


@pytest.mark.ui
def test_deck_select_window_creates_and_selects_deck(qtbot: Any, mock_db: Any, monkeypatch: Any) -> None:
    """Vérifie que la création d'un paquet recharge l'arbre et sélectionne le nouveau paquet."""
    uid = uuid.uuid4().hex[:6]
    new_deck_name = f"Nouveau_{uid}"

    win = DeckSelectWindow(allow_all=False)
    qtbot.addWidget(win)

    # Simuler le dialogue de création sans bloquer l'UI
    def mock_open_create_dialog(self_win: DeckSelectWindow) -> None:
        created = DeckModel.create(name=new_deck_name)
        self_win._on_deck_created(created.id, created.name)

    monkeypatch.setattr(win, "_open_create_deck_dialog", lambda: mock_open_create_dialog(win))

    win._open_create_deck_dialog()

    assert win.selected_deck_id is not None
    assert win.btn_confirm.isEnabled()

    # Confirmer et vérifier le signal émis
    emitted: list[tuple[int, str]] = []
    win.deck_selected.connect(lambda did, name: emitted.append((did, name)))
    win.btn_confirm.click()

    assert len(emitted) == 1
    assert emitted[0][1] == new_deck_name
