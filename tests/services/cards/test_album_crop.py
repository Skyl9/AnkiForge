import json
from pathlib import Path

import pytest
from PIL import Image

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    DocumentPageModel,
    MediaModel,
)
from ankiforge.services.cards.album_service import (
    AlbumService,
    crop_box_rotated_to_source,
    crop_box_source_to_rotated,
)
from ankiforge.services.cards.media_manager import MediaManager

pytestmark = pytest.mark.integration


def _create_test_image(path: Path, width: int = 100, height: int = 80, color: str = "red") -> Path:
    img = Image.new("RGB", (width, height), color=color)
    img.save(path)
    return path


def test_set_and_remove_page_crop(tmp_path: Path):
    """Vérifie l'enregistrement, la restitution et l'invalidation d'état dérivé lors du recadrage."""
    service = AlbumService()
    img_path = _create_test_image(tmp_path / "crop_test.png", width=120, height=90)
    doc = service.create_album_from_images("Album Crop Test", [img_path], sort_mode="none")
    page = service.get_album_pages(doc.id)[0]

    # Données dérivées initiales
    page.ocr_text = "Texte avant recadrage"
    page.status = "ready"
    page.save()
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        content="Chunk avant recadrage",
        content_hash="h1",
        page_number=1,
        heading_path="Page 1",
        media=page.media,
    )

    # 1. Application du recadrage
    cropped_page = service.set_page_crop(page.id, (10, 15, 60, 40))
    assert cropped_page.crop_box == (10, 15, 60, 40)
    assert cropped_page.ocr_text == ""
    assert cropped_page.status == "stale"
    assert DocumentChunkModel.select().where(DocumentChunkModel.document == doc).count() == 0

    # 2. Retrait du recadrage
    uncropped_page = service.remove_page_crop(page.id)
    assert uncropped_page.crop_box is None
    assert uncropped_page.status == "stale"


def test_render_page_image_with_crop_and_reversibility(tmp_path: Path):
    """
    Vérifie que la couture de lecture rend fidèlement la zone recadrée et
    restitue l'image pleine lors du retrait du recadrage.
    """
    service = AlbumService()
    img_path = _create_test_image(tmp_path / "render_crop.png", width=100, height=80)
    doc = service.create_album_from_images("Render Crop Test", [img_path], sort_mode="none")
    page = service.get_album_pages(doc.id)[0]

    # Recadrage à 40x30
    service.set_page_crop(page.id, (20, 10, 40, 30))
    page = DocumentPageModel.get_by_id(page.id)

    rendered = service.render_page_image(page)
    assert (rendered.width, rendered.height) == (40, 30)
    rendered.close()

    # Retrait du recadrage -> pleine résolution (100x80)
    service.remove_page_crop(page.id)
    page = DocumentPageModel.get_by_id(page.id)

    rendered_full = service.render_page_image(page)
    assert (rendered_full.width, rendered_full.height) == (100, 80)
    rendered_full.close()


def test_crop_never_alters_source_file(tmp_path: Path):
    """Le recadrage est restrictif et non destructif : l'empreinte du fichier sur disque ne change jamais."""
    service = AlbumService()
    img_path = _create_test_image(tmp_path / "immutable_crop.png", width=100, height=80)
    doc = service.create_album_from_images("Immutable Crop", [img_path], sort_mode="none")
    page = service.get_album_pages(doc.id)[0]

    media_file = service.media_manager.media_dir / page.media.filename
    checksum_before = MediaManager._calculate_md5(str(media_file))

    # Recadre, rend plusieurs fois, retire
    service.set_page_crop(page.id, (5, 5, 50, 50))
    page = DocumentPageModel.get_by_id(page.id)
    for _ in range(3):
        im = service.render_page_image(page)
        im.close()

    service.remove_page_crop(page.id)
    page = DocumentPageModel.get_by_id(page.id)
    im = service.render_page_image(page)
    im.close()

    assert MediaManager._calculate_md5(str(media_file)) == checksum_before


def test_rotation_does_not_displace_crop_rect(tmp_path: Path):
    """
    CRITÈRE MAJEUR : Le rectangle est stocké sur l'image source, jamais sur la planche.
    La rotation de la planche ne déplace pas le rect source.
    """
    service = AlbumService()
    img_path = _create_test_image(tmp_path / "rot_crop.png", width=100, height=80)
    doc = service.create_album_from_images("Rot Crop Test", [img_path], sort_mode="none")
    page = service.get_album_pages(doc.id)[0]

    # Crop de 40x30 sur l'image source
    service.set_page_crop(page.id, (10, 20, 40, 30))
    page = DocumentPageModel.get_by_id(page.id)
    assert page.crop_box == (10, 20, 40, 30)

    # 1. Rotation à 90°
    service.rotate_page(page.id, 90)
    page = DocumentPageModel.get_by_id(page.id)
    # Le rect source n'a PAS bougé
    assert page.crop_box == (10, 20, 40, 30)
    rendered = service.render_page_image(page)
    # L'image rendue à 90° a maintenant w=30, h=40
    assert (rendered.width, rendered.height) == (30, 40)
    rendered.close()

    # 2. Rotation à 180°
    service.rotate_page(page.id, 90)
    page = DocumentPageModel.get_by_id(page.id)
    assert page.crop_box == (10, 20, 40, 30)
    rendered = service.render_page_image(page)
    assert (rendered.width, rendered.height) == (40, 30)
    rendered.close()

    # 3. Rotation à 270°
    service.rotate_page(page.id, 90)
    page = DocumentPageModel.get_by_id(page.id)
    assert page.crop_box == (10, 20, 40, 30)
    rendered = service.render_page_image(page)
    assert (rendered.width, rendered.height) == (30, 40)
    rendered.close()


def test_crop_box_coordinate_transforms():
    """Vérifie la bijection des coordonnées de recadrage entre image source et vue pivotée."""
    W, H = 100, 80
    source_box = (10, 20, 40, 30)  # x, y, w, h

    for rot in (0, 90, 180, 270):
        rotated_box = crop_box_source_to_rotated(source_box, W, H, rot)
        reverted = crop_box_rotated_to_source(rotated_box, W, H, rot)
        assert reverted == source_box, f"Échec de réversibilité pour rotation={rot}"


def test_thumbnail_cache_key_includes_crop():
    """Vérifie que la clé de cache de vignette change quand la page est recadrée."""
    from ankiforge.ui.views.documents_view.widgets.album_thumbnails import ThumbnailCache

    doc = DocumentModel.create(title="Doc Thumb Key Test")
    media = MediaModel.create(filename="f.png", original_name="f.png", checksum="chk", mime_type="image/png")
    page = DocumentPageModel.create(document=doc, media=media, page_number=1, rotation=0, crop_data=None)

    key_uncropped = ThumbnailCache.key_for(page, 180)
    page.crop_data = json.dumps([10, 10, 50, 50])
    key_cropped = ThumbnailCache.key_for(page, 180)

    assert key_uncropped != key_cropped
