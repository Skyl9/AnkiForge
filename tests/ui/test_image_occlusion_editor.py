"""
Tests UI pour ImageOcclusionEditor et ImageOcclusionDialog avec pytest-qt.
Vérifie la manipulation graphique, l'ajout/suppression de masques et les signaux.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from ankiforge.database.models import DeckModel
from ankiforge.services.cards.image_occlusion_service import OcclusionBox
from ankiforge.ui.dialogs.image_occlusion_dialog import ImageOcclusionDialog
from ankiforge.ui.widgets.image_occlusion_editor import (
    ImageOcclusionEditor,
    OcclusionGraphicsItem,
)


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    """Génère une image PNG de test."""
    p = tmp_path / "diagram_test.png"
    img = Image.new("RGB", (600, 400), color=(230, 240, 250))
    img.save(p)
    return p


def test_image_occlusion_editor_init_and_load(qtbot: Any, sample_image: Path) -> None:
    """Vérifie le chargement de l'image et l'initialisation de l'éditeur."""
    editor = ImageOcclusionEditor(image_path=sample_image)
    qtbot.addWidget(editor)
    editor.show()

    assert editor.image_path == sample_image
    assert editor._pixmap_item is not None
    assert editor.scene.width() == 600
    assert editor.scene.height() == 400
    assert editor.table_boxes.rowCount() == 0


def test_image_occlusion_editor_draw_and_delete_box(qtbot: Any, sample_image: Path) -> None:
    """Vérifie l'ajout manuel d'un rectangle et sa suppression."""
    editor = ImageOcclusionEditor(image_path=sample_image)
    qtbot.addWidget(editor)

    # 1. Tracé manuel d'un masque
    editor._on_box_drawn(50.0, 60.0, 120.0, 40.0)
    assert len(editor.boxes) == 1
    assert editor.boxes[0].id == 1
    assert editor.boxes[0].x == 50.0
    assert editor.boxes[0].width == 120.0
    assert editor.table_boxes.rowCount() == 1

    # 2. Vérification de l'élément graphique dans la scène
    item = editor._graphics_items.get(1)
    assert item is not None
    assert isinstance(item, OcclusionGraphicsItem)
    assert item.rect().width() == 120.0

    # 3. Modification du texte dans le tableau
    editor.table_boxes.item(0, 1).setText("Aorte")
    assert editor.boxes[0].text == "Aorte"

    # 4. Suppression du masque sélectionné
    item.setSelected(True)
    editor._delete_selected_box()
    assert len(editor.boxes) == 0
    assert editor.table_boxes.rowCount() == 0
    assert 1 not in editor._graphics_items


def test_image_occlusion_editor_ai_detection(qtbot: Any, sample_image: Path) -> None:
    """Vérifie la réception des boîtes détectées par l'IA."""
    editor = ImageOcclusionEditor(image_path=sample_image)
    qtbot.addWidget(editor)

    detected_boxes = [
        OcclusionBox(id=1, x=10.0, y=10.0, width=50.0, height=20.0, text="Légende 1"),
        OcclusionBox(id=2, x=80.0, y=10.0, width=50.0, height=20.0, text="Légende 2"),
    ]

    editor._on_ai_detection_finished(detected_boxes)

    assert len(editor.boxes) == 2
    assert editor.table_boxes.rowCount() == 2
    assert editor.table_boxes.item(0, 1).text() == "Légende 1"
    assert editor.table_boxes.item(1, 1).text() == "Légende 2"


def test_image_occlusion_editor_generate_cards(qtbot: Any, sample_image: Path) -> None:
    """Vérifie la génération complète des cartes depuis l'interface."""
    deck = DeckModel.create(name="Sciences")
    editor = ImageOcclusionEditor(image_path=sample_image)
    qtbot.addWidget(editor)

    # Ajout d'une boîte
    editor._on_box_drawn(20.0, 30.0, 100.0, 40.0)
    editor.table_boxes.item(0, 1).setText("Ventricule")

    # Sélection du paquet créé
    for i in range(editor.combo_deck.count()):
        if editor.combo_deck.itemData(i) == deck.id:
            editor.combo_deck.setCurrentIndex(i)
            break

    with qtbot.waitSignal(editor.notes_created, timeout=5000) as blocker:
        editor._generate_cards()

    created_notes = blocker.args[0]
    assert len(created_notes) == 1
    assert created_notes[0].note_type.name == "Image Occlusion Enhanced"


def test_image_occlusion_dialog(qtbot: Any, sample_image: Path) -> None:
    """Vérifie l'instanciation de la modale ImageOcclusionDialog."""
    dialog = ImageOcclusionDialog(image_path=sample_image)
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.editor is not None
    assert dialog.editor.image_path == sample_image
    assert len(dialog.get_created_notes()) == 0
