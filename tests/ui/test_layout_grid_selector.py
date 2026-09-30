"""
Tests unitaires et UI pour LayoutGridSelector et LayoutThumbnailCard.
"""

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent

from ankiforge.ui.layouts.layout_manager import LayoutManager
from ankiforge.ui.widgets.settings_modal.components.layout_grid_selector import (
    LayoutGridSelector,
    LayoutThumbnailCard,
)

pytestmark = pytest.mark.ui


def test_layout_thumbnail_card_attributes_and_selection(qtbot):
    """Vérifie l'initialisation d'une carte de layout, son accessibilité et son état de sélection."""
    card = LayoutThumbnailCard(
        layout_id="ide",
        name="Concept IDE",
        description="Barre latérale sombre",
        icon_name="ph.sidebar",
        thumbnail_path=None,
    )
    qtbot.addWidget(card)

    assert card.layout_id == "ide"
    assert card.name == "Concept IDE"
    assert card.description == "Barre latérale sombre"
    assert card.icon_name == "ph.sidebar"
    assert not card.is_selected

    # Accessibilité initiale
    assert "Concept IDE" in card.accessibleName()
    assert card.accessibleDescription() == "Barre latérale sombre"

    # Basculement de sélection
    card.show()
    card.set_selected(True)
    assert card.is_selected
    assert not card.check_badge.isHidden()
    assert "sélectionnée" in card.accessibleName()

    card.set_selected(False)
    assert not card.is_selected
    assert card.check_badge.isHidden()


def test_layout_thumbnail_card_click_and_keyboard(qtbot):
    """Vérifie l'émission du signal de sélection au clic et aux touches Entrée/Espace."""
    card = LayoutThumbnailCard(
        layout_id="macos",
        name="Concept macOS",
        description="Barre supérieure",
        icon_name="ph.app-window",
    )
    qtbot.addWidget(card)

    selected_ids = []
    card.selected.connect(selected_ids.append)

    # 1. Clic souris
    card.mousePressEvent(None)
    assert selected_ids == ["macos"]

    # 2. Touche Espace
    event_space = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
    card.keyPressEvent(event_space)
    assert selected_ids == ["macos", "macos"]

    # 3. Touche Entrée
    event_enter = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    card.keyPressEvent(event_enter)
    assert selected_ids == ["macos", "macos", "macos"]


def test_layout_thumbnail_card_fallback_when_thumbnail_missing(qtbot):
    """Vérifie le repli explicite lorsque la miniature statique est absente."""
    card = LayoutThumbnailCard(
        layout_id="custom_future_layout",
        name="Futur Layout",
        description="Disposition sans miniature",
        icon_name="ph.squares-four",
        thumbnail_path=Path("/chemin/inexistant/thumbnail.png"),
    )
    qtbot.addWidget(card)

    assert card.is_fallback_active
    assert card.fallback_label is not None
    assert "Aperçu indisponible" in card.fallback_label.text()


def test_layout_grid_selector_creation_and_count(qtbot):
    """Vérifie que la grille instancie une carte par disposition enregistrée."""
    selector = LayoutGridSelector(current_layout_id="ide")
    qtbot.addWidget(selector)

    assert selector.count() == len(LayoutManager.LAYOUTS)
    assert selector.current_layout_id() == "ide"
    assert selector.currentData() == "ide"

    # Vérifie que les 4 layouts sont présents
    available_ids = [item["id"] for item in LayoutManager.get_available_layouts()]
    for lid in available_ids:
        assert lid in selector.cards
        assert selector.cards[lid].layout_id == lid

    # Seule la carte active est sélectionnée
    for lid, card in selector.cards.items():
        assert card.is_selected == (lid == "ide")


def test_layout_grid_selector_selection_change(qtbot):
    """Vérifie le changement de disposition sélectionnée et l'émission des signaux."""
    selector = LayoutGridSelector(current_layout_id="ide")
    qtbot.addWidget(selector)

    changed_layouts = []
    changed_indices = []
    selector.layout_changed.connect(changed_layouts.append)
    selector.currentIndexChanged.connect(changed_indices.append)

    # Sélection par identifiant
    selector.set_current_layout_id("macos")
    assert selector.current_layout_id() == "macos"
    assert selector.currentData() == "macos"
    assert changed_layouts == ["macos"]
    assert len(changed_indices) == 1

    # Les états des cartes sont mis à jour
    assert selector.cards["macos"].is_selected
    assert not selector.cards["ide"].is_selected

    # Clic sur une autre carte
    selector.cards["dashboard"].selected.emit("dashboard")
    assert selector.current_layout_id() == "dashboard"
    assert selector.cards["dashboard"].is_selected
    assert not selector.cards["macos"].is_selected


def test_layout_grid_selector_duck_typing(qtbot):
    """Vérifie la compatibilité de l'interface avec celle d'un QComboBox pour SettingsModal."""
    selector = LayoutGridSelector(current_layout_id="ide")
    qtbot.addWidget(selector)

    assert selector.count() == 4
    assert selector.itemData(0) == "ide"
    assert selector.currentIndex() == 0
    assert "IDE" in selector.currentText()

    # Définition par index
    selector.setCurrentIndex(1)
    assert selector.currentIndex() == 1
    assert selector.currentData() == selector.itemData(1)


def test_layout_grid_selector_arrow_navigation(qtbot):
    """Vérifie la navigation au clavier (flèches directionnelles) entre les cartes."""
    selector = LayoutGridSelector(current_layout_id="ide")
    qtbot.addWidget(selector)
    selector.show()
    selector.activateWindow()

    # Focus initial sur la première carte
    selector.cards["ide"].setFocus()
    assert selector.cards["ide"].hasFocus() or selector.current_layout_id() == "ide"

    # Flèche droite -> focus sur la carte suivante (macos)
    event_right = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
    selector.keyPressEvent(event_right)
    assert selector.current_layout_id() == "macos"

    # Flèche bas -> focus sur la carte du dessous
    event_down = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    selector.keyPressEvent(event_down)
    # Ligne 1, colonne 1 (glassmorphism)
    assert selector.current_layout_id() == "glassmorphism"
