"""Tests unitaires et UI pour DeckSelectWindow et CreateDeckDialog."""

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


def test_deck_select_window_displays_leaf_only_and_emits_full_name(qtbot: Any, mock_db: Any) -> None:
    """L'arborescence n'affiche que le nom de la feuille (sans préfixe), et le signal émet le chemin complet."""
    DeckSelectWindow.reset_session_expanded_state()
    uid = uuid.uuid4().hex[:6]
    gp = DeckModel.create(name=f"Sciences_{uid}")
    parent = DeckModel.create(name=f"Sciences_{uid}::Physique", parent_deck=gp)
    child = DeckModel.create(name=f"Sciences_{uid}::Physique::Mecanique", parent_deck=parent)

    win = DeckSelectWindow(allow_all=False, selected_deck_id=child.id)
    qtbot.addWidget(win)

    item_gp = win._items_by_id[gp.id]
    item_parent = win._items_by_id[parent.id]
    item_child = win._items_by_id[child.id]

    assert item_gp.text(0) == f"Sciences_{uid}"
    assert item_parent.text(0) == "Physique"
    assert item_child.text(0) == "Mecanique"

    emitted: list[tuple[int, str]] = []
    win.deck_selected.connect(lambda did, name: emitted.append((did, name)))
    win.btn_confirm.click()

    assert len(emitted) == 1
    assert emitted[0] == (child.id, f"Sciences_{uid}::Physique::Mecanique")


def test_deck_select_window_sticky_header_shows_container_context(qtbot: Any, mock_db: Any) -> None:
    """Le bandeau sticky au-dessus de l'arbre affiche le paquet conteneur de la sélection active."""
    DeckSelectWindow.reset_session_expanded_state()
    uid = uuid.uuid4().hex[:6]
    gp = DeckModel.create(name=f"Sciences_{uid}")
    parent = DeckModel.create(name=f"Sciences_{uid}::Physique", parent_deck=gp)
    child = DeckModel.create(name=f"Sciences_{uid}::Physique::Mecanique", parent_deck=parent)

    win = DeckSelectWindow(allow_all=True, selected_deck_id=child.id)
    qtbot.addWidget(win)

    # 1. Sélection du sous-paquet : le sticky header affiche son conteneur parent
    sticky_text = win.lbl_sticky_container.text()
    assert f"Sciences_{uid}" in sticky_text
    assert "Physique" in sticky_text
    assert "Mecanique" not in sticky_text or "Dans :" in sticky_text

    # 2. Sélection d'un paquet racine : indique le niveau racine
    win.tree.setCurrentItem(win._items_by_id[gp.id])
    assert "racine" in win.lbl_sticky_container.text().lower()

    # 3. Sélection de « Tous les paquets »
    all_item = win._items_by_id[dsw.ALL_DECKS_NODE_ID]
    win.tree.setCurrentItem(all_item)
    assert "tous les paquets" in win.lbl_sticky_container.text().lower() or "collection" in win.lbl_sticky_container.text().lower()


def test_deck_select_window_search_matches_full_path_and_restores_expansion(qtbot: Any, mock_db: Any) -> None:
    """La recherche trouve par préfixe ou feuille, et l'effacement restaure l'expansion précédente."""
    DeckSelectWindow.reset_session_expanded_state()
    uid = uuid.uuid4().hex[:6]
    root1 = DeckModel.create(name=f"Root1_{uid}")
    child1 = DeckModel.create(name=f"Root1_{uid}::SubAlpha", parent_deck=root1)
    root2 = DeckModel.create(name=f"Root2_{uid}")
    child2 = DeckModel.create(name=f"Root2_{uid}::SubBeta", parent_deck=root2)

    win = DeckSelectWindow(allow_all=False)
    qtbot.addWidget(win)

    # État initial : root1 et root2 sont repliés
    item_root1 = win._items_by_id[root1.id]
    item_root2 = win._items_by_id[root2.id]
    item_child1 = win._items_by_id[child1.id]
    item_child2 = win._items_by_id[child2.id]

    item_root1.setExpanded(False)
    item_root2.setExpanded(False)

    # Recherche sur "Alpha"
    win.search_input.setText("SubAlpha")
    assert not item_child1.isHidden()
    assert not item_root1.isHidden()
    assert item_root1.isExpanded()
    assert item_root2.isHidden()

    # Recherche par préfixe "Root2" trouve child2
    win.search_input.setText(f"Root2_{uid}")
    assert not item_child2.isHidden()
    assert not item_root2.isHidden()
    assert item_root2.isExpanded()
    assert item_root1.isHidden()

    # Effacement de la recherche -> Restauration de l'état d'expansion antérieur
    win.search_input.setText("")
    assert not item_root1.isHidden()
    assert not item_root2.isHidden()
    assert not item_root1.isExpanded()
    assert not item_root2.isExpanded()


def test_deck_select_window_persists_expansion_state_across_reopenings(qtbot: Any, mock_db: Any) -> None:
    """L'état d'expansion est préservé entre les réouvertures successives sans tout redéplier."""
    DeckSelectWindow.reset_session_expanded_state()
    uid = uuid.uuid4().hex[:6]
    root1 = DeckModel.create(name=f"R1_{uid}")
    DeckModel.create(name=f"R1_{uid}::C1", parent_deck=root1)
    root2 = DeckModel.create(name=f"R2_{uid}")
    DeckModel.create(name=f"R2_{uid}::C2", parent_deck=root2)

    # Première ouverture
    win1 = DeckSelectWindow(allow_all=False)
    qtbot.addWidget(win1)

    item_r1 = win1._items_by_id[root1.id]
    item_r2 = win1._items_by_id[root2.id]

    # Déplier root1 mais replier root2
    item_r1.setExpanded(True)
    item_r2.setExpanded(False)

    win1.close()

    # Deuxième ouverture : l'état doit être exactement restauré !
    win2 = DeckSelectWindow(allow_all=False)
    qtbot.addWidget(win2)

    item2_r1 = win2._items_by_id[root1.id]
    item2_r2 = win2._items_by_id[root2.id]

    assert item2_r1.isExpanded()
    assert not item2_r2.isExpanded()


def test_deck_select_window_expand_and_collapse_all_buttons(qtbot: Any, mock_db: Any) -> None:
    """Les boutons Tout déplier et Tout replier modifient l'ensemble de l'arborescence."""
    DeckSelectWindow.reset_session_expanded_state()
    uid = uuid.uuid4().hex[:6]
    root = DeckModel.create(name=f"Arbre_{uid}")
    DeckModel.create(name=f"Arbre_{uid}::Branche", parent_deck=root)

    win = DeckSelectWindow(allow_all=False)
    qtbot.addWidget(win)

    item_root = win._items_by_id[root.id]

    # Clic Tout replier
    win.btn_collapse_all.click()
    assert not item_root.isExpanded()

    # Clic Tout déplier
    win.btn_expand_all.click()
    assert item_root.isExpanded()


def test_deck_select_window_resizable(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que la fenêtre n'est pas bloquée à une taille fixe et peut être redimensionnée."""
    win = DeckSelectWindow()
    qtbot.addWidget(win)

    assert win.minimumWidth() <= 450
    assert win.minimumHeight() <= 400
    assert win.maximumWidth() > win.minimumWidth()
    assert win.maximumHeight() > win.minimumHeight()
