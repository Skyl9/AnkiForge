import pytest

from ankiforge.database.models import DeckModel
from ankiforge.ui.components import DBComboBox

pytestmark = pytest.mark.ui


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


def test_combobox_wheel_filter_prevents_accidental_selection_change_when_closed(qtbot: pytest.FixtureRequest) -> None:
    """Vérifie que la molette sur une QComboBox fermée ne modifie pas sa valeur et fait défiler la zone parente."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication, QComboBox, QScrollArea, QVBoxLayout, QWidget

    from ankiforge.ui.components import ComboBoxWheelFilter, StyledComboBox

    app = QApplication.instance()
    assert isinstance(app, QApplication)
    app.setStyle("Fusion")
    ComboBoxWheelFilter.install(app)

    scroll = QScrollArea()
    content = QWidget()
    content.setFixedHeight(1200)
    layout = QVBoxLayout(content)

    std_combo = QComboBox(content)
    std_combo.addItems(["Alpha", "Beta", "Gamma"])
    layout.addWidget(std_combo)

    styled_combo = StyledComboBox(content)
    styled_combo.addItems(["Un", "Deux", "Trois"])
    layout.addWidget(styled_combo)

    scroll.setWidget(content)
    scroll.resize(400, 300)
    qtbot.addWidget(scroll)
    scroll.show()

    assert std_combo.currentIndex() == 0
    assert styled_combo.currentIndex() == 0
    initial_scroll_val = scroll.verticalScrollBar().value()

    # 1. Événement de molette sur la QComboBox standard fermée
    wheel_down = QWheelEvent(
        QPointF(10, 10),
        QPointF(10, 10),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    app.sendEvent(std_combo, wheel_down)

    # La sélection ne doit PAS avoir changé
    assert std_combo.currentIndex() == 0
    # La zone de défilement parente doit avoir avancé
    assert scroll.verticalScrollBar().value() > initial_scroll_val

    # 2. Événement de molette sur la StyledComboBox fermée
    scroll_val_after_first = scroll.verticalScrollBar().value()
    wheel_down_styled = QWheelEvent(
        QPointF(10, 10),
        QPointF(10, 10),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    app.sendEvent(styled_combo, wheel_down_styled)

    assert styled_combo.currentIndex() == 0
    assert scroll.verticalScrollBar().value() > scroll_val_after_first


def test_styled_combobox_wheel_event_ignores_when_closed(qtbot: pytest.FixtureRequest) -> None:
    """Vérifie que StyledComboBox.wheelEvent ignore expressément l'événement si le menu est fermé."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent

    from ankiforge.ui.components import StyledComboBox

    combo = StyledComboBox()
    combo.addItems(["Option 1", "Option 2", "Option 3"])
    qtbot.addWidget(combo)
    combo.show()

    assert combo.currentIndex() == 0

    event = QWheelEvent(
        QPointF(10, 10),
        QPointF(10, 10),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    combo.wheelEvent(event)

    assert event.isAccepted() is False
    assert combo.currentIndex() == 0


def test_combobox_wheel_filter_is_popup_open_predicate(qtbot: pytest.FixtureRequest) -> None:
    """Vérifie la détection d'ouverture et de fermeture du menu déroulant."""
    from PySide6.QtWidgets import QComboBox

    from ankiforge.ui.components import ComboBoxWheelFilter

    combo = QComboBox()
    combo.addItems(["A", "B", "C"])
    qtbot.addWidget(combo)
    combo.show()

    # Au départ, popup fermé
    assert ComboBoxWheelFilter._is_popup_open(combo) is False

    # Popup déployé
    combo.showPopup()
    assert ComboBoxWheelFilter._is_popup_open(combo) is True

    # Popup refermé
    combo.hidePopup()
    assert ComboBoxWheelFilter._is_popup_open(combo) is False
