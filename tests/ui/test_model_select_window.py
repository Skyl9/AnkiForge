"""
Tests unitaires et UI pour ModelSelectWindow.
"""

import uuid
from typing import Any

import pytest

from ankiforge.database.models import NoteModel, NoteTypeModel
from ankiforge.ui.components.model_select_window import ModelSelectWindow


@pytest.mark.ui
def test_model_select_window_init_allow_all(qtbot: Any, mock_db: Any) -> None:
    """Vérifie l'initialisation de ModelSelectWindow avec allow_all=True."""
    uid = uuid.uuid4().hex[:6]
    nt1 = NoteTypeModel.create(name=f"Basique {uid}", fields_schema='["Front", "Back"]', description="Description 1")
    NoteTypeModel.create(name=f"Cloze {uid}", fields_schema='["Text", "Extra"]', description="Description 2")

    # Créer une note liée à nt1
    NoteModel.create(note_type=nt1, tags="test")

    win = ModelSelectWindow(allow_all=True, current_model_id=-1)
    qtbot.addWidget(win)

    assert win.windowTitle() == "Sélectionner un Modèle de Carte"
    assert win.tree.topLevelItemCount() >= 3  # "Tous les modèles" + nt1 + nt2

    # Vérifier l'item racine "Tous les modèles"
    root_item = win.tree.topLevelItem(0)
    assert root_item is not None
    assert "Tous les modèles" in root_item.text(0)

    # Tester la sélection et l'émission du signal
    emitted: list[tuple[int, str]] = []
    win.model_selected.connect(lambda mid, name: emitted.append((mid, name)))

    # Sélectionner le modèle nt1
    item_nt1 = win._items_by_id.get(nt1.id)
    assert item_nt1 is not None
    win.tree.setCurrentItem(item_nt1)
    win.btn_confirm.click()

    assert len(emitted) == 1
    assert emitted[0][0] == nt1.id
    assert f"Basique {uid}" in emitted[0][1]


@pytest.mark.ui
def test_model_select_window_search_filter(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le filtrage dynamique en direct par la barre de recherche."""
    uid = uuid.uuid4().hex[:6]
    nt1 = NoteTypeModel.create(name=f"Physique {uid}", fields_schema='["Formule", "Unite"]')
    nt2 = NoteTypeModel.create(name=f"Histoire {uid}", fields_schema='["Date", "Evenement"]')

    win = ModelSelectWindow(allow_all=False)
    qtbot.addWidget(win)

    # Avant recherche, nt1 et nt2 sont visibles
    item1 = win._items_by_id[nt1.id]
    item2 = win._items_by_id[nt2.id]
    assert not item1.isHidden()
    assert not item2.isHidden()

    # Rechercher "Physique"
    win.search_input.setText("Physique")
    assert not item1.isHidden()
    assert item2.isHidden()

    # Rechercher un champ "Evenement"
    win.search_input.setText("Evenement")
    assert item1.isHidden()
    assert not item2.isHidden()

    # Effacer la recherche
    win.search_input.setText("")
    assert not item1.isHidden()
    assert not item2.isHidden()


@pytest.mark.ui
def test_model_select_window_allow_all_false_and_get_selected(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le mode allow_all=False (assignation de modèle) et get_selected_model."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"Medical {uid}", fields_schema='["Symptome", "Traitement"]')

    win = ModelSelectWindow(allow_all=False, current_model_id=nt.id)
    qtbot.addWidget(win)

    # -1 ne doit pas être présent
    assert -1 not in win._items_by_id

    # nt doit être pré-sélectionné
    selected_model = win.get_selected_model()
    assert selected_model is not None
    assert selected_model.id == nt.id
    assert selected_model.name == f"Medical {uid}"
