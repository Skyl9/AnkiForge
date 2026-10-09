"""
Tests unitaires et UI pour DeckSelectWindow et CreateDeckDialog.
"""

import types
import uuid
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from ankiforge.database.models import DeckModel
from ankiforge.ui.components import deck_select_window as dsw
from ankiforge.ui.components.deck_select_window import DeckSelectWindow
from ankiforge.ui.dialogs.create_deck_dialog import CreateDeckDialog

pytestmark = pytest.mark.ui


def _patch_deck_prompts(monkeypatch: Any, *, rename: str | None = None, confirm: bool = True) -> None:
    """Branche les boîtes de dialogue Qt sur des réponses scriptées, sans bloquer l'UI."""
    if rename is not None:
        monkeypatch.setattr(dsw, "QInputDialog", types.SimpleNamespace(getText=lambda *a, **k: (rename, True)))
    monkeypatch.setattr(
        dsw,
        "QMessageBox",
        types.SimpleNamespace(
            question=lambda *a, **k: QMessageBox.StandardButton.Yes if confirm else QMessageBox.StandardButton.No,
            warning=lambda *a, **k: QMessageBox.StandardButton.Ok,
            StandardButton=QMessageBox.StandardButton,
        ),
    )


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


def test_create_deck_dialog_enter_submits(qtbot: Any, mock_db: Any) -> None:
    """Dans le modal de création de paquet, Enter doit créer le paquet (et non fermer via Annuler)."""
    uid = uuid.uuid4().hex[:6]
    dlg = CreateDeckDialog(initial_name=f"Entree_{uid}::Sous", parent=None)
    qtbot.addWidget(dlg)

    assert dlg.btn_submit.isDefault()
    assert not dlg.btn_cancel.isDefault()

    emitted: list[tuple[int, str]] = []
    dlg.deck_created.connect(lambda did, name: emitted.append((did, name)))

    qtbot.keyClick(dlg.txt_name, Qt.Key.Key_Return)

    assert len(emitted) == 1
    assert emitted[0][1] == f"Entree_{uid}::Sous"
    assert dlg.result() == 1  # QDialog.DialogCode.Accepted
    created = DeckModel.get_by_id(emitted[0][0])
    parent = DeckModel.get_or_none(DeckModel.name == f"Entree_{uid}")
    assert parent is not None
    assert created.parent_deck.id == parent.id


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


def test_deck_select_window_context_menu_lists_modify_actions(qtbot: Any, mock_db: Any) -> None:
    """Le clic droit sur un paquet propose Nouveau sous-paquet / Renommer / Supprimer."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck_{uid}")

    win = DeckSelectWindow(allow_all=False)
    qtbot.addWidget(win)

    # Le nœud racine « Tous les paquets » n'est pas un paquet modifiable.
    assert win._build_context_menu(-1) is None

    menu = win._build_context_menu(deck.id)
    assert menu is not None
    assert [action.text() for action in menu.actions()] == [
        win.tr("Nouveau sous-paquet"),
        win.tr("Renommer le paquet"),
        win.tr("Supprimer le paquet"),
    ]


def test_deck_select_window_rename_updates_leaf_and_children(qtbot: Any, mock_db: Any, monkeypatch: Any) -> None:
    """Renommer un paquet depuis le menu met à jour son nom, ses enfants et la sélection."""
    uid = uuid.uuid4().hex[:6]
    parent = DeckModel.create(name=f"Parent_{uid}")
    child = DeckModel.create(name=f"Parent_{uid}::Enfant", parent_deck=parent)

    win = DeckSelectWindow(allow_all=False, selected_deck_id=parent.id)
    qtbot.addWidget(win)

    new_leaf = f"Renomme_{uid}"
    _patch_deck_prompts(monkeypatch, rename=new_leaf)

    win._build_context_menu(parent.id).actions()[1].trigger()

    renamed = DeckModel.get_by_id(parent.id)
    assert renamed.name == new_leaf
    # Le préfixe des sous-paquets suit le renommage.
    assert DeckModel.get_by_id(child.id).name == f"{new_leaf}::Enfant"
    # L'arbre est rechargé et le paquet renommé reste sélectionné.
    assert win.selected_deck_id == parent.id
    assert win.tree.selectedItems()[0].text(0) == new_leaf


def test_deck_select_window_rename_refuses_existing_sibling(qtbot: Any, mock_db: Any, monkeypatch: Any) -> None:
    """Renommer vers un nom déjà pris laisse le paquet intact."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Cible_{uid}")
    DeckModel.create(name=f"Occupe_{uid}")

    win = DeckSelectWindow(allow_all=False, selected_deck_id=deck.id)
    qtbot.addWidget(win)

    _patch_deck_prompts(monkeypatch, rename=f"Occupe_{uid}")
    win._build_context_menu(deck.id).actions()[1].trigger()

    assert DeckModel.get_by_id(deck.id).name == f"Cible_{uid}"


def test_deck_select_window_rename_refuses_prefix_collision(qtbot: Any, mock_db: Any, monkeypatch: Any) -> None:
    """Renommer vers un nom qui existe déjà comme préfixe d'un descendant est refusé."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Cible_{uid}")
    # « Occupe_x::Sous_x » occupe déjà le préfixe « Occupe_x:: » : renommer Cible → Occupe le dupliquerait.
    DeckModel.create(name=f"Occupe_{uid}::Sous", parent_deck=None)

    win = DeckSelectWindow(allow_all=False, selected_deck_id=deck.id)
    qtbot.addWidget(win)

    _patch_deck_prompts(monkeypatch, rename=f"Occupe_{uid}")
    win._build_context_menu(deck.id).actions()[1].trigger()

    assert DeckModel.get_by_id(deck.id).name == f"Cible_{uid}"
    # Le descendant qui occupait le préfixe reste intact.
    assert DeckModel.get_or_none(DeckModel.name == f"Occupe_{uid}::Sous") is not None


def test_deck_select_window_delete_cascades(qtbot: Any, mock_db: Any, monkeypatch: Any) -> None:
    """Supprimer un paquet depuis le menu emporte ses sous-paquets et recharge l'arbre."""
    uid = uuid.uuid4().hex[:6]
    parent = DeckModel.create(name=f"ASupprimer_{uid}")
    child = DeckModel.create(name=f"ASupprimer_{uid}::Enfant", parent_deck=parent)

    win = DeckSelectWindow(allow_all=False, selected_deck_id=parent.id)
    qtbot.addWidget(win)

    _patch_deck_prompts(monkeypatch, confirm=True)
    win._build_context_menu(parent.id).actions()[2].trigger()

    assert DeckModel.get_or_none(DeckModel.id == parent.id) is None
    assert DeckModel.get_or_none(DeckModel.id == child.id) is None
    assert win.selected_deck_id is None
    assert parent.id not in win._items_by_id


def test_deck_select_window_delete_ancestor_revokes_descendant_selection(qtbot: Any, mock_db: Any, monkeypatch: Any) -> None:
    """Supprimer un ancêtre révoque une sélection qui pointait vers un paquet disparu."""
    uid = uuid.uuid4().hex[:6]
    parent = DeckModel.create(name=f"ASupprimer_{uid}")
    child = DeckModel.create(name=f"ASupprimer_{uid}::Enfant", parent_deck=parent)

    # La sélection courante pointe vers le SOUS-paquet ; on supprime le paquet parent.
    win = DeckSelectWindow(allow_all=False, selected_deck_id=child.id)
    qtbot.addWidget(win)

    _patch_deck_prompts(monkeypatch, confirm=True)
    win._build_context_menu(parent.id).actions()[2].trigger()

    # Le paquet sélectionné ayant disparu avec son ancêtre, plus rien n'est sélectionné
    # et la confirmation est désactivée (pas de paquet de destination orphelin).
    assert win.selected_deck_id is None
    assert not win.btn_confirm.isEnabled()


def test_deck_select_window_delete_declined_keeps_deck(qtbot: Any, mock_db: Any, monkeypatch: Any) -> None:
    """Refuser la confirmation ne supprime rien."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Intact_{uid}")

    win = DeckSelectWindow(allow_all=False, selected_deck_id=deck.id)
    qtbot.addWidget(win)

    _patch_deck_prompts(monkeypatch, confirm=False)
    win._build_context_menu(deck.id).actions()[2].trigger()

    assert DeckModel.get_by_id(deck.id) is not None


def test_deck_select_window_subdeck_prefills_parent(qtbot: Any, mock_db: Any, monkeypatch: Any) -> None:
    """« Nouveau sous-paquet » pré-remplit le nom avec le paquet sélectionné comme parent."""
    uid = uuid.uuid4().hex[:6]
    parent = DeckModel.create(name=f"Parent_{uid}")

    win = DeckSelectWindow(allow_all=False, selected_deck_id=parent.id)
    qtbot.addWidget(win)

    captured: dict[str, str] = {}
    monkeypatch.setattr(win, "_open_create_deck_dialog", lambda initial_name="": captured.update(initial_name=initial_name))

    win._build_context_menu(parent.id).actions()[0].trigger()

    assert captured["initial_name"] == f"Parent_{uid}::"
