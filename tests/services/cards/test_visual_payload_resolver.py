import base64
import io

import pytest
from PIL import Image

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    DocumentPageModel,
    MediaModel,
)
from ankiforge.services.cards.visual_resolver import (
    VisualPayloadResolver,
    get_max_vision_images_for_provider,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def sample_album(tmp_path, monkeypatch):
    """Crée un album avec deux planches physiques dans le répertoire média."""
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("ankiforge.utils.paths.get_media_dir", lambda: media_dir)

    # Image 1 : 200x100 (largeur > hauteur)
    img1_path = media_dir / "p1.png"
    img1 = Image.new("RGB", (200, 100), color="red")
    img1.save(img1_path)

    # Image 2 : 150x150
    img2_path = media_dir / "p2.png"
    img2 = Image.new("RGB", (150, 150), color="blue")
    img2.save(img2_path)

    doc = DocumentModel.create(
        title="Album Test Visual",
        file_type="album",
        total_pages=2,
        content="",
    )
    m1 = MediaModel.create(
        filename="p1.png",
        media_type="image",
        original_name="p1.png",
        checksum="chk1",
        mime_type="image/png",
    )
    m2 = MediaModel.create(
        filename="p2.png",
        media_type="image",
        original_name="p2.png",
        checksum="chk2",
        mime_type="image/png",
    )
    # Planche 1 pivotée à 90° (ADR 0011)
    p1 = DocumentPageModel.create(
        document=doc,
        media=m1,
        page_number=1,
        rotation=90,
        ocr_text="Texte de la planche 1",
        status="ready",
    )
    # Planche 2 sans rotation
    p2 = DocumentPageModel.create(
        document=doc,
        media=m2,
        page_number=2,
        rotation=0,
        ocr_text="Texte de la planche 2",
        status="ready",
    )

    # Chunks RAG correspondants
    c1 = DocumentChunkModel.create(
        document=doc,
        page_number=1,
        chunk_index=0,
        content="<!-- PAGE: 1 -->\nTexte de la planche 1",
        media=m1,
    )
    c2 = DocumentChunkModel.create(
        document=doc,
        page_number=2,
        chunk_index=1,
        content="<!-- PAGE: 2 -->\nTexte de la planche 2",
        media=m2,
    )
    return doc, [p1, p2], [c1, c2], media_dir


def test_get_max_vision_images_for_provider():
    assert get_max_vision_images_for_provider("anthropic") == 20
    assert get_max_vision_images_for_provider("Anthropic") == 20
    assert get_max_vision_images_for_provider("openai") == 50
    assert get_max_vision_images_for_provider("gemini") == 50


def test_resolve_album_page_honors_rotation(sample_album):
    doc, pages, chunks, media_dir = sample_album
    resolver = VisualPayloadResolver(media_dir=media_dir)

    # Résolution de la planche 1 (pivotée à 90°, image source 200x100)
    images = resolver.resolve_visual_images(document_id=doc.id, page_numbers=[1])
    assert len(images) == 1
    assert images[0]["type"] == "image_url"
    url = images[0]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")

    # Décoder l'image rendue et vérifier que la rotation a été appliquée (100x200 après rotation 90°)
    b64_data = url.split(",", 1)[1]
    raw_bytes = base64.b64decode(b64_data)
    rendered = Image.open(io.BytesIO(raw_bytes))
    assert rendered.size == (100, 200), f"Attendu (100, 200) après rotation 90°, obtenu {rendered.size}"


def test_resolve_chunk_visual_payload_for_album(sample_album):
    doc, pages, chunks, media_dir = sample_album
    resolver = VisualPayloadResolver(media_dir=media_dir)

    # Résolution depuis le chunk 2 (page 2)
    images = resolver.resolve_visual_images(
        document_id=doc.id,
        chunk={"page_number": 2, "id": chunks[1].id},
    )
    assert len(images) == 1
    assert "data:image/png;base64," in images[0]["image_url"]["url"]


def test_resolve_chunk_with_linked_media_non_album(tmp_path, monkeypatch):
    """Document PDF ou cours non-album avec clé étrangère chunk.media."""
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("ankiforge.utils.paths.get_media_dir", lambda *args, **kwargs: media_dir)

    img_path = media_dir / "diagram.jpg"
    img = Image.new("RGB", (50, 50), color="green")
    img.save(img_path)

    doc = DocumentModel.create(title="Cours PDF", file_type="pdf", total_pages=5, content="")
    m = MediaModel.create(filename="diagram.jpg", media_type="image", original_name="diagram.jpg", checksum="chk_d", mime_type="image/jpeg")
    chunk = DocumentChunkModel.create(document=doc, page_number=3, content="Paragraphe avec schéma", media=m)

    resolver = VisualPayloadResolver(media_dir=media_dir)
    images = resolver.resolve_visual_images(
        document_id=doc.id,
        chunk=chunk,
    )
    assert len(images) == 1
    assert "data:image/jpeg;base64," in images[0]["image_url"]["url"]
