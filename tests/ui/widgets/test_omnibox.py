import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem
from unittest.mock import patch, MagicMock

from ankiforge.database.models import DocumentModel
# Ajuste le chemin d'import selon la structure exacte de ton projet
from ankiforge.ui.widgets.omnibox import Omnibox


@pytest.fixture
def omnibox(qtbot):
    """Fixture qui crée l'Omnibox et la confie à qtbot pour le nettoyage."""
    widget = Omnibox()
    qtbot.addWidget(widget)
    return widget


def test_omnibox_initialization(omnibox):
    """Vérifie que l'omnibox s'initialise correctement et que la liste est vide."""
    assert omnibox.search_bar.placeholderText() != ""
    assert omnibox.results_list.count() == 0


def test_omnibox_typing_triggers_timer_not_search(omnibox, qtbot):
    """Vérifie la logique de 'debounce' : taper lance le timer, pas la recherche directe."""
    with patch.object(omnibox, 'perform_search') as mock_search:
        # On simule la frappe du mot "test" au clavier
        qtbot.keyClicks(omnibox.search_bar, "test")

        # Le timer de 300ms doit avoir été armé
        assert omnibox.search_timer.isActive() == True

        # Mais la fonction de recherche ne doit pas encore avoir été appelée !
        mock_search.assert_not_called()


def test_omnibox_keyboard_navigation_and_signal(omnibox, qtbot):
    """Vérifie la navigation clavier (Flèche Bas, Entrée) et l'émission du signal."""

    # 0. AFFICHER LE WIDGET (Crucial pour le focus clavier dans Qt)
    with qtbot.waitExposed(omnibox):
        omnibox.show()

    # 1. PRÉPARATION : On court-circuite la BDD en ajoutant manuellement un faux résultat
    item = QListWidgetItem("Faux Résultat de test")
    item.setData(Qt.ItemDataRole.UserRole, {"type": "doc", "id": 42, "deck_id": None})
    omnibox.results_list.addItem(item)

    # 2. ACTION : Depuis la barre de recherche, on simule "Flèche du Bas"
    omnibox.search_bar.setFocus()

    # Pour les QShortcut, il est parfois plus fiable d'envoyer la touche à la fenêtre entière
    qtbot.keyPress(omnibox, Qt.Key.Key_Down)

    # Vérification : La liste a pris le focus et le 1er élément est sélectionné
    assert omnibox.results_list.hasFocus()
    assert omnibox.results_list.currentRow() == 0

    # 3. ACTION : On simule "Entrée" en espionnant le signal
    with qtbot.waitSignal(omnibox.result_selected, timeout=1000) as blocker:
        qtbot.keyPress(omnibox.results_list, Qt.Key.Key_Return)

    # 4. VÉRIFICATIONS : On vérifie les arguments du signal et la fermeture
    assert blocker.args == ["doc", 42, None]
    assert omnibox.isVisible() == False



def test_omnibox_perform_search_with_mocked_db(omnibox,qtbot):
    """Vérifie que perform_search formate bien les résultats venus de la base de données."""

    # --- 1. PRÉPARATION EN BASE EN MÉMOIRE ---
    # On crée un vrai document dans la base éphémère de pytest
    doc = DocumentModel.create(title="Cours de Python Avancé", content="Contenu factice")

    # --- 2. ACTION ---
    omnibox.search_bar.setText("python")
    omnibox.perform_search()

    # --- 3. VÉRIFICATION DE L'UI ---
    assert omnibox.results_list.count() == 1
    item = omnibox.results_list.item(0)
    assert "Cours de Python Avancé" in item.text()

    data = item.data(Qt.ItemDataRole.UserRole)
    assert data["type"] == "doc"
    assert data["id"] == doc.id