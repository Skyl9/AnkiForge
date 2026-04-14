from ankiforge.database.models import DeckModel
from ankiforge.ui.components.components import DBComboBox


def test_db_combobox_initialization(qtbot, mock_db):
    """Vérifie que la combobox se peuple et se trie correctement à l'initialisation."""
    # 1. Préparation de la base de données
    DeckModel.create(name="Zebra Deck")
    DeckModel.create(name="Alpha Deck")

    # 2. Instanciation du composant
    combo = DBComboBox(model_class=DeckModel, display_field="name", sort_field="name")
    qtbot.addWidget(combo)

    # 3. Vérifications
    assert combo.count() == 2
    # Le tri alphabétique doit placer "Alpha" en premier
    assert combo.itemText(0) == "Alpha Deck"
    assert combo.itemText(1) == "Zebra Deck"


def test_db_combobox_refresh_keeps_selection(qtbot, mock_db):
    """Vérifie que rafraîchir les données ne fait pas perdre la sélection de l'utilisateur."""
    # 1. Préparation
    d1 = DeckModel.create(name="Deck 1")
    combo = DBComboBox(model_class=DeckModel)
    qtbot.addWidget(combo)

    # On simule l'utilisateur qui sélectionne "Deck 1"
    combo.setCurrentIndex(0)
    assert combo.currentData() == d1.id

    # 2. Action : un nouveau paquet est ajouté en base (il va se glisser en haut alphabétiquement)
    DeckModel.create(name="Deck 0")

    # On rafraîchit la combobox
    combo.refresh_data()

    # 3. Vérifications
    assert combo.count() == 2
    assert combo.itemText(0) == "Deck 0"
    assert combo.itemText(1) == "Deck 1"

    # MAGIE : La sélection doit être restée sur "Deck 1" malgré le décalage des index !
    assert combo.currentData() == d1.id
