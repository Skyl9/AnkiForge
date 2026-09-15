"""
Tests unitaires pour ImageOcclusionService :
- Parsing JSON multimodal des coordonnées normalisées
- Génération SVG des masques (modes hide_all et hide_one, recto et verso)
- Persistance du modèle NoteType et création des NoteModel/CardModel
- Intégration avec ExportManager pour la vérification du paquet APKG
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from ankiforge.database.models import CardModel, DeckModel
from ankiforge.services.ai.base import LLMProvider, MockProvider
from ankiforge.services.cards.export_manager import ExportManager
from ankiforge.services.cards.image_occlusion_service import (
    IOE_FIELDS,
    IOE_MODEL_NAME,
    ImageOcclusionService,
    OcclusionBox,
)
from ankiforge.services.cards.media_manager import MediaManager


class DummyVisionProvider(LLMProvider):
    """Fournisseur de test renvoyant une réponse JSON de détection simulée."""

    def __init__(self, response_json: str) -> None:
        self.response_json = response_json

    def generate(self, system_prompt: str, user_prompt: str | list[dict], response_format: str = "json") -> str:
        return self.response_json


def test_ensure_ioe_model_exists() -> None:
    """Vérifie la création idempotente du NoteType Image Occlusion Enhanced."""
    model = ImageOcclusionService.ensure_ioe_model_exists()
    assert model is not None
    assert model.name == IOE_MODEL_NAME

    fields = json.loads(str(model.fields_schema))
    assert fields == IOE_FIELDS

    templates = json.loads(str(model.templates))
    assert len(templates) == 1
    assert "image-wrapper" in templates[0]["qfmt"]
    assert "Question Mask" in templates[0]["qfmt"]
    assert "Answer Mask" in templates[0]["afmt"]

    # Appel répété (idempotence)
    model2 = ImageOcclusionService.ensure_ioe_model_exists()
    assert model2.id == model.id


def test_occlusion_box_dataclass() -> None:
    """Vérifie la sérialisation et désérialisation d'OcclusionBox."""
    box = OcclusionBox(id=1, x=10.5, y=20.0, width=100.0, height=50.0, text="Noyau", hint="Organite")
    d = box.to_dict()
    assert d["id"] == 1
    assert d["text"] == "Noyau"

    box2 = OcclusionBox.from_dict(d)
    assert box2.id == box.id
    assert box2.x == box.x
    assert box2.text == box.text
    assert box2.hint == box.hint


def test_parse_vision_json() -> None:
    """Vérifie le recalcul en pixels réels et le clamping des boîtes de vision."""
    img_w, img_h = 1000, 500
    sample_json = json.dumps(
        {
            "labels": [
                {"id": 1, "text": "Zone Basse", "box_2d": [600, 100, 800, 400]},
                {"id": 2, "text": "Zone Haute", "box_2d": [100, 200, 200, 500]},
            ]
        }
    )

    boxes = ImageOcclusionService._parse_vision_json(sample_json, img_w, img_h)
    assert len(boxes) == 2

    # Doit être trié top-to-bottom (Zone Haute en premier)
    assert boxes[0].text == "Zone Haute"
    assert boxes[0].id == 1
    assert boxes[0].y == 50.0  # (100 / 1000) * 500
    assert boxes[0].x == 200.0  # (200 / 1000) * 1000
    assert boxes[0].width == 300.0  # (300 / 1000) * 1000
    assert boxes[0].height == 50.0  # (100 / 1000) * 500

    assert boxes[1].text == "Zone Basse"
    assert boxes[1].id == 2


def test_generate_svg_mask_modes() -> None:
    """Vérifie la syntaxe SVG selon les modes hide_all et hide_one, recto et verso."""
    service = ImageOcclusionService()
    boxes = [
        OcclusionBox(id=1, x=10, y=10, width=50, height=20, text="A"),
        OcclusionBox(id=2, x=70, y=10, width=50, height=20, text="B"),
    ]

    # 1. Mode Hide All - Question pour Box 1
    q_all = service.generate_svg_mask(boxes, 200, 100, active_box_id=1, mode="hide_all", is_answer=False)
    assert 'class="mask-active-q"' in q_all
    assert 'class="mask-inactive"' in q_all
    assert "[1]" in q_all
    assert "[2]" in q_all

    # 2. Mode Hide All - Réponse pour Box 1 avec persistance des autres masques
    a_all_keep = service.generate_svg_mask(boxes, 200, 100, active_box_id=1, mode="hide_all", is_answer=True, keep_other_masks_on_answer=True)
    assert 'class="mask-active-a"' in a_all_keep  # Révélé avec délimitation verte
    assert 'class="mask-inactive"' in a_all_keep  # Box 2 reste occultée
    assert "[2]" in a_all_keep

    # 3. Mode Hide All - Réponse pour Box 1 SANS persistance
    a_all_nokeep = service.generate_svg_mask(boxes, 200, 100, active_box_id=1, mode="hide_all", is_answer=True, keep_other_masks_on_answer=False)
    assert 'class="mask-active-a"' in a_all_nokeep
    assert 'class="mask-inactive"' not in a_all_nokeep  # Box 2 non dessinée

    # 4. Mode Hide One - Question pour Box 1
    q_one = service.generate_svg_mask(boxes, 200, 100, active_box_id=1, mode="hide_one", is_answer=False)
    assert 'class="mask-active-q"' in q_one
    assert 'class="mask-inactive"' not in q_one  # Box 2 non masquée au recto

    # 5. Original Mask (active_box_id is None)
    o_mask = service.generate_svg_mask(boxes, 200, 100, active_box_id=None)
    assert 'class="mask-inactive"' in o_mask
    assert 'class="mask-active-q"' not in o_mask


def test_create_occlusion_notes(tmp_path: Path) -> None:
    """Vérifie la création complète des notes, cartes, médias et l'exportation APKG."""
    # Création d'une image factice de test
    img_file = tmp_path / "schema_test.png"
    img = Image.new("RGB", (400, 300), color=(240, 240, 240))
    img.save(img_file)

    deck = DeckModel.create(name="Biologie::Anatomie")

    boxes = [
        OcclusionBox(id=1, x=20, y=30, width=80, height=30, text="Mitochondrie", hint="Énergie"),
        OcclusionBox(id=2, x=150, y=100, width=90, height=35, text="Ribosome", hint="Protéines"),
    ]

    media_mgr = MediaManager(media_dir=tmp_path / "media")
    service = ImageOcclusionService(media_manager=media_mgr)

    notes = service.create_occlusion_notes(
        image_path=img_file,
        boxes=boxes,
        deck_id=deck.id,
        header="Organites Cellulaires",
        mode="hide_all",
        keep_other_masks_on_answer=True,
        tags=["bio", "cellule"],
    )

    assert len(notes) == 2

    # Vérification des notes créées en BDD
    for idx, note in enumerate(notes, start=1):
        assert note.note_type.name == IOE_MODEL_NAME
        cards = list(CardModel.select().where(CardModel.note == note))
        assert len(cards) == 1
        assert cards[0].deck == deck

        active_version = note.versions.where(note.versions.model.is_active == True).first()  # noqa: E712
        content = json.loads(str(active_version.content))

        assert content["Header"] == "Organites Cellulaires"
        assert "<img src=" in content["Image"]
        assert f"_q_{idx}.svg" in content["Question Mask"]
        assert f"_a_{idx}.svg" in content["Answer Mask"]
        assert "_o.svg" in content["Original Mask"]

    # Vérification de l'exportation APKG
    export_mgr = ExportManager()
    export_mgr.media_dir = tmp_path / "media"
    apkg_file = tmp_path / "test_export.apkg"

    count = export_mgr.export_package(output_path=apkg_file, deck_id=deck.id)
    assert count == 2
    assert apkg_file.exists()
    assert apkg_file.stat().st_size > 0


def test_detect_labels_with_vision(tmp_path: Path) -> None:
    """Vérifie l'intégration du LLM de vision via DummyVisionProvider et MockProvider."""
    img_file = tmp_path / "dummy.png"
    img = Image.new("RGB", (600, 400), color=(255, 255, 255))
    img.save(img_file)

    service = ImageOcclusionService()

    # 1. Avec MockProvider
    mock_boxes = service.detect_labels_with_vision(img_file, provider=MockProvider())
    assert len(mock_boxes) == 3

    # 2. Avec DummyVisionProvider
    dummy_json = json.dumps(
        {
            "labels": [
                {"id": 1, "text": "Atrium droit", "box_2d": [200, 100, 300, 250]},
            ]
        }
    )
    boxes = service.detect_labels_with_vision(img_file, provider=DummyVisionProvider(dummy_json))
    assert len(boxes) == 1
    assert boxes[0].text == "Atrium droit"
