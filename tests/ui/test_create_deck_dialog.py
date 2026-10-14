"""
Tests unitaires et UI pour CreateDeckDialog (HierarchyCompleter, fil d'Ariane et idempotence).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from ankiforge.database.models import DeckModel
from ankiforge.repositories.deck_repository import DeckRepository
from ankiforge.ui.components.hierarchy_breadcrumb_bar import HierarchyBreadcrumbBar
from ankiforge.ui.components.hierarchy_completer import HierarchyCompleter
from ankiforge.ui.dialogs.create_deck_dialog import CreateDeckDialog

pytestmark = pytest.mark.ui


def test_create_deck_dialog_completer_and_breadcrumb_mounted(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le montage de HierarchyCompleter et HierarchyBreadcrumbBar alimentés par DeckRepository."""
    uid = uuid.uuid4().hex[:6]
    repo = DeckRepository()
    repo.get_or_create_deck_hierarchical(f"Sciences_{uid}::Physique")
    repo.get_or_create_deck_hierarchical(f"Histoire_{uid}")

    dlg = CreateDeckDialog(parent=None)
    qtbot.addWidget(dlg)

    # 1. Vérification du compléteur
    assert isinstance(dlg.completer, HierarchyCompleter)
    assert dlg.txt_name.completer() == dlg.completer
    paths = dlg.completer.paths
    assert f"Sciences_{uid}::Physique" in paths
    assert f"Histoire_{uid}" in paths

    # 2. Vérification de la présence de la barre fil d'Ariane
    assert isinstance(dlg.breadcrumb_bar, HierarchyBreadcrumbBar)
    assert dlg.breadcrumb_bar.parent() is not None


def test_create_deck_dialog_breadcrumb_bar_synchronization(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la synchronisation en temps réel du fil d'Ariane avec txt_name."""
    uid = uuid.uuid4().hex[:6]
    repo = DeckRepository()
    repo.get_or_create_deck_hierarchical(f"Fac_{uid}::Medecine")

    dlg = CreateDeckDialog(parent=None)
    qtbot.addWidget(dlg)

    dlg.txt_name.setText(f"Fac_{uid}::Medecine::Anatomie")

    assert dlg.breadcrumb_bar.segments() == [f"Fac_{uid}", "Medecine", "Anatomie"]
    assert dlg.breadcrumb_bar.subpaths() == [
        f"Fac_{uid}",
        f"Fac_{uid}::Medecine",
        f"Fac_{uid}::Medecine::Anatomie",
    ]
    # Les deux premiers segments existent, le troisième est nouveau
    assert dlg.breadcrumb_bar.is_segment_existing(0) is True
    assert dlg.breadcrumb_bar.is_segment_existing(1) is True
    assert dlg.breadcrumb_bar.is_segment_existing(2) is False


def test_create_deck_dialog_breadcrumb_click_updates_input(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que cliquer sur un segment parent tronque le texte de saisie."""
    uid = uuid.uuid4().hex[:6]
    dlg = CreateDeckDialog(parent=None)
    qtbot.addWidget(dlg)

    dlg.txt_name.setText(f"Langues_{uid}::Japonais::Vocabulaire::JLPT5")
    assert dlg.breadcrumb_bar.segment_count() == 4

    # Clic sur le 2e segment ("Japonais", subpath = "Langues_...::Japonais")
    buttons = dlg.breadcrumb_bar.segment_buttons()
    assert len(buttons) == 4
    buttons[1].click()

    assert dlg.txt_name.text() == f"Langues_{uid}::Japonais"
    assert dlg.breadcrumb_bar.segments() == [f"Langues_{uid}", "Japonais"]


def test_create_deck_dialog_idempotent_existing_deck_indication(qtbot: Any, mock_db: Any) -> None:
    """Vérifie l'indication bienveillante et l'état activé du bouton quand le paquet existe déjà."""
    uid = uuid.uuid4().hex[:6]
    repo = DeckRepository()
    deck_name = f"Existant_{uid}::SousPaquet"
    repo.get_or_create_deck_hierarchical(deck_name)

    dlg = CreateDeckDialog(parent=None)
    qtbot.addWidget(dlg)
    dlg.show()

    # Au départ champ vide -> bouton désactivé, info masquée
    assert not dlg.btn_submit.isEnabled()
    assert not dlg.lbl_info.isVisible()

    # Saisie d'un nouveau paquet -> bouton actif, info masquée
    dlg.txt_name.setText(f"Nouveau_{uid}")
    assert dlg.btn_submit.isEnabled()
    assert not dlg.lbl_info.isVisible()

    # Saisie du paquet existant -> bouton actif, message bienveillant visible
    dlg.txt_name.setText(deck_name)
    assert dlg.btn_submit.isEnabled()
    assert dlg.lbl_info.isVisible()
    assert not dlg.lbl_info.isHidden()
    assert "Ce paquet existe déjà (il sera sélectionné)" in dlg.lbl_info.text()

    # Modification vers un nom non existant -> message à nouveau masqué
    dlg.txt_name.setText(f"{deck_name}::Inedit")
    assert dlg.btn_submit.isEnabled()
    assert not dlg.lbl_info.isVisible()


def test_create_deck_dialog_submit_existing_deck_returns_instance(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la sélection idempotente retournant l'instance du paquet existant."""
    uid = uuid.uuid4().hex[:6]
    repo = DeckRepository()
    deck_name = f"Preexistant_{uid}"
    existing_deck = repo.get_or_create_deck_hierarchical(deck_name, description="Desc originale")

    dlg = CreateDeckDialog(initial_name=deck_name, parent=None)
    qtbot.addWidget(dlg)

    emitted: list[tuple[int, str]] = []
    dlg.deck_created.connect(lambda did, name: emitted.append((did, name)))

    dlg.btn_submit.click()

    assert len(emitted) == 1
    emitted_id, emitted_name = emitted[0]
    assert emitted_id == existing_deck.id
    assert emitted_name == deck_name
    assert dlg.created_deck is not None
    assert dlg.created_deck.id == existing_deck.id

    # Aucun doublon créé en base
    matching_decks = list(DeckModel.select().where(DeckModel.name == deck_name))
    assert len(matching_decks) == 1


def test_create_deck_dialog_submit_new_deck(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la création d'un nouveau paquet hiérarchique avec émission du signal."""
    uid = uuid.uuid4().hex[:6]
    deck_name = f"Arbre_{uid}::Branche::Feuille"

    dlg = CreateDeckDialog(parent=None)
    qtbot.addWidget(dlg)
    dlg.txt_name.setText(deck_name)
    dlg.txt_desc.setText("Test description")

    emitted: list[tuple[int, str]] = []
    dlg.deck_created.connect(lambda did, name: emitted.append((did, name)))

    dlg.btn_submit.click()

    assert len(emitted) == 1
    emitted_id, emitted_name = emitted[0]
    assert emitted_name == deck_name
    assert dlg.created_deck is not None
    assert dlg.created_deck.id == emitted_id

    created_in_db = DeckModel.get_or_none(DeckModel.name == deck_name)
    assert created_in_db is not None
    assert created_in_db.description == "Test description"
    assert created_in_db.parent_deck is not None
    assert created_in_db.parent_deck.name == f"Arbre_{uid}::Branche"


def test_create_deck_dialog_completer_contextual_filtering(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le filtrage hiérarchique contextuel par segment du compléteur monté."""
    uid = uuid.uuid4().hex[:6]
    repo = DeckRepository()
    repo.get_or_create_deck_hierarchical(f"Sciences_{uid}::Physique::Mecanique")
    repo.get_or_create_deck_hierarchical(f"Sciences_{uid}::Chimie")
    repo.get_or_create_deck_hierarchical(f"Lettres_{uid}::Litterature")

    dlg = CreateDeckDialog(parent=None)
    qtbot.addWidget(dlg)

    # Filtrage niveau racine
    completions_root = dlg.completer.completions_for(f"Sciences_{uid}")
    assert f"Sciences_{uid}" in completions_root

    # Filtrage contextuel après séparateur ::
    completions_nested = dlg.completer.completions_for(f"Sciences_{uid}::")
    assert f"Sciences_{uid}::Physique" in completions_nested
    assert f"Sciences_{uid}::Chimie" in completions_nested
    assert f"Lettres_{uid}::Litterature" not in completions_nested


def test_create_deck_dialog_empty_name_error(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le blocage et l'affichage d'erreur lors d'une soumission avec nom vide."""
    dlg = CreateDeckDialog(parent=None)
    qtbot.addWidget(dlg)
    dlg.show()

    dlg.txt_name.setText("   ")
    assert not dlg.btn_submit.isEnabled()

    # Forcer la soumission
    dlg._on_submit()
    assert dlg.lbl_error.isVisible()
    assert not dlg.lbl_error.isHidden()
    assert dlg.result() != 1


def test_create_deck_dialog_error_handling(qtbot: Any, mock_db: Any, monkeypatch: Any) -> None:
    """Vérifie la capture et l'affichage des erreurs de base de données dans lbl_error."""
    dlg = CreateDeckDialog(parent=None)
    qtbot.addWidget(dlg)
    dlg.show()

    def _failing_get_or_create(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Erreur BDD simulée")

    monkeypatch.setattr(dlg._deck_repo, "get_or_create_deck_hierarchical", _failing_get_or_create)

    dlg.txt_name.setText("PaquetValide")
    dlg._on_submit()

    assert dlg.lbl_error.isVisible()
    assert not dlg.lbl_error.isHidden()
    assert "Erreur BDD simulée" in dlg.lbl_error.text()
    assert dlg.result() != 1


def test_create_deck_dialog_refresh_decks(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que refresh_decks actualise dynamiquement la liste des paquets connus."""
    uid = uuid.uuid4().hex[:6]
    repo = DeckRepository()

    dlg = CreateDeckDialog(parent=None)
    qtbot.addWidget(dlg)

    initial_paths = set(dlg.completer.paths)
    assert f"Tardif_{uid}" not in initial_paths

    repo.get_or_create_deck_hierarchical(f"Tardif_{uid}")
    dlg.refresh_decks()

    assert f"Tardif_{uid}" in dlg.completer.paths
