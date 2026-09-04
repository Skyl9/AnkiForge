import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from pypdf import PdfReader

from ankiforge.database.models import DocumentModel, DocumentPageModel, FolderModel, MediaModel
from ankiforge.services.cards.album_service import AlbumService, extract_exif_timestamp, natural_sort_key
from ankiforge.services.cards.media_manager import MediaManager


def _create_test_image(path: Path, width: int = 100, height: int = 80, color: str = "red", exif_date: str | None = None) -> Path:
    """Utilitaire de création d'une image physique de test avec ou sans EXIF."""
    img = Image.new("RGB", (width, height), color=color)
    if exif_date:
        exif = img.getexif()
        # 306 = DateTime
        exif[306] = exif_date
        img.save(path, exif=exif)
    else:
        img.save(path)
    return path


def test_natural_sort_key(tmp_path: Path):
    """Vérifie que le tri naturel ordonne logiquement les chaînes numériques."""
    files = ["page_10.png", "page_1.png", "page_2.png", "page_20.png", "page_3.png"]
    sorted_files = sorted(files, key=natural_sort_key)
    assert sorted_files == ["page_1.png", "page_2.png", "page_3.png", "page_10.png", "page_20.png"]


def test_extract_exif_timestamp(tmp_path: Path):
    """Vérifie l'extraction du timestamp EXIF et le repli sur None si absent."""
    img_with_exif = tmp_path / "exif.jpg"
    _create_test_image(img_with_exif, exif_date="2026:09:04 12:30:45")

    img_no_exif = tmp_path / "no_exif.png"
    _create_test_image(img_no_exif)

    dt = extract_exif_timestamp(img_with_exif)
    assert dt == datetime.datetime(2026, 9, 4, 12, 30, 45)

    assert extract_exif_timestamp(img_no_exif) is None
    assert extract_exif_timestamp(tmp_path / "inexistant.jpg") is None


def test_sort_images_modes(tmp_path: Path):
    """Vérifie le fonctionnement des modes de tri 'natural', 'exif', et 'none'."""
    service = AlbumService()

    img1 = tmp_path / "img_2.jpg"
    img2 = tmp_path / "img_10.jpg"
    img3 = tmp_path / "img_1.jpg"

    _create_test_image(img1, exif_date="2026:01:01 10:00:00")
    _create_test_image(img2, exif_date="2026:01:01 09:00:00")
    _create_test_image(img3, exif_date="2026:01:01 11:00:00")

    # Mode natural
    res_nat = service.sort_images([img1, img2, img3], mode="natural")
    assert [p.name for p in res_nat] == ["img_1.jpg", "img_2.jpg", "img_10.jpg"]

    # Mode exif (img2 à 9h = img_10.jpg, img1 à 10h = img_2.jpg, img3 à 11h = img_1.jpg)
    res_exif = service.sort_images([img1, img2, img3], mode="exif")
    assert [p.name for p in res_exif] == ["img_10.jpg", "img_2.jpg", "img_1.jpg"]

    # Mode none
    res_none = service.sort_images([img1, img2, img3], mode="none")
    assert [p.name for p in res_none] == ["img_2.jpg", "img_10.jpg", "img_1.jpg"]


def test_create_album_from_images(tmp_path: Path):
    """Vérifie la création d'un album complet et de ses DocumentPageModel ordonnés."""
    service = AlbumService()
    folder = FolderModel.create(name="Dossier Album")

    img_paths = [
        _create_test_image(tmp_path / "p1.png", color="blue"),
        _create_test_image(tmp_path / "p2.png", color="green"),
        _create_test_image(tmp_path / "p3.png", color="yellow"),
    ]

    doc = service.create_album_from_images("Manuel Anatomie", img_paths, folder=folder)

    assert doc.title == "Manuel Anatomie"
    assert doc.file_type == "album"
    assert doc.total_pages == 3
    assert doc.folder == folder

    pages = service.get_album_pages(doc.id)
    assert len(pages) == 3
    for idx, page in enumerate(pages):
        assert page.page_number == idx + 1
        assert page.rotation == 0
        assert page.status == "ready"
        assert page.media is not None
        assert Path(service.media_manager.media_dir / page.media.filename).exists()


def test_create_album_validation(tmp_path: Path):
    """Vérifie que la validation des arguments rejette les albums invalides."""
    service = AlbumService()

    with pytest.raises(ValueError, match="sans image"):
        service.create_album_from_images("Titre", [])

    img = _create_test_image(tmp_path / "test.png")
    with pytest.raises(ValueError, match="vide"):
        service.create_album_from_images("   ", [img])


def test_rotate_page(tmp_path: Path):
    """Vérifie la rotation d'une page par paliers de 90°."""
    service = AlbumService()
    img = _create_test_image(tmp_path / "rot.png")
    doc = service.create_album_from_images("Rotation Test", [img])
    page = service.get_album_pages(doc.id)[0]

    p1 = service.rotate_page(page.id, 90)
    assert p1.rotation == 90

    p2 = service.rotate_page(page.id, 90)
    assert p2.rotation == 180

    p3 = service.rotate_page(page.id, 180)
    assert p3.rotation == 0


def test_reorder_pages(tmp_path: Path):
    """Vérifie le réordonnancement de pages sans violation de contrainte d'unicité."""
    service = AlbumService()
    imgs = [
        _create_test_image(tmp_path / "a.png", color="red"),
        _create_test_image(tmp_path / "b.png", color="blue"),
        _create_test_image(tmp_path / "c.png", color="green"),
    ]
    doc = service.create_album_from_images("Reorder Test", imgs, sort_mode="none")
    pages = service.get_album_pages(doc.id)
    p0, p1, p2 = pages[0], pages[1], pages[2]

    # Inversion : [p2, p0, p1]
    new_order = [p2.id, p0.id, p1.id]
    reordered = service.reorder_pages(doc.id, new_order)

    assert [p.id for p in reordered] == [p2.id, p0.id, p1.id]
    assert [p.page_number for p in reordered] == [1, 2, 3]

    # Tentative avec des IDs invalides
    with pytest.raises(ValueError, match="ne correspond pas"):
        service.reorder_pages(doc.id, [p0.id, 99999])


def test_delete_page_and_renumbering(tmp_path: Path):
    """Vérifie la suppression d'une page et la renumérotation contiguë des pages restantes."""
    service = AlbumService()
    imgs = [
        _create_test_image(tmp_path / "d1.png"),
        _create_test_image(tmp_path / "d2.png"),
        _create_test_image(tmp_path / "d3.png"),
    ]
    doc = service.create_album_from_images("Delete Test", imgs, sort_mode="none")
    pages = service.get_album_pages(doc.id)
    p2_id = pages[1].id
    p3_id = pages[2].id

    # Supprime la page 2
    service.delete_page(p2_id)

    remaining = service.get_album_pages(doc.id)
    assert len(remaining) == 2
    assert [p.page_number for p in remaining] == [1, 2]
    # L'ancienne page 3 est devenue page 2
    assert remaining[1].id == p3_id

    doc_reloaded = DocumentModel.get_by_id(doc.id)
    assert doc_reloaded.total_pages == 2


def test_add_pages_to_album(tmp_path: Path):
    """Vérifie l'insertion de nouvelles pages à la fin et en position intercalaire."""
    service = AlbumService()
    imgs_initial = [
        _create_test_image(tmp_path / "init1.png"),
        _create_test_image(tmp_path / "init2.png"),
    ]
    doc = service.create_album_from_images("Add Test", imgs_initial, sort_mode="none")

    # Ajout à la fin (insert_at=None)
    img_end = _create_test_image(tmp_path / "end.png")
    added_end = service.add_pages_to_album(doc.id, [img_end])
    assert len(added_end) == 1
    assert added_end[0].page_number == 3

    # Insertion intercalaire en position 2
    img_inter = _create_test_image(tmp_path / "inter.png")
    added_inter = service.add_pages_to_album(doc.id, [img_inter], insert_at=2)
    assert len(added_inter) == 1
    assert added_inter[0].page_number == 2

    pages = service.get_album_pages(doc.id)
    assert len(pages) == 4
    assert [p.page_number for p in pages] == [1, 2, 3, 4]

    doc_reloaded = DocumentModel.get_by_id(doc.id)
    assert doc_reloaded.total_pages == 4


def test_compile_album_to_pdf(tmp_path: Path):
    """Vérifie la compilation d'un album en document PDF avec rotations."""
    service = AlbumService()
    imgs = [
        _create_test_image(tmp_path / "pdf1.png", width=200, height=100, color="red"),
        _create_test_image(tmp_path / "pdf2.png", width=100, height=200, color="blue"),
    ]
    doc = service.create_album_from_images("PDF Test", imgs, sort_mode="none")

    # On pivote la page 1 de 90°
    pages = service.get_album_pages(doc.id)
    service.rotate_page(pages[0].id, 90)

    pdf_out = tmp_path / "result.pdf"
    res_path = service.compile_album_to_pdf(doc.id, output_path=pdf_out)

    assert res_path.exists()
    assert res_path.stat().st_size > 0

    # Vérification du format PDF valide
    with open(res_path, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"

    # Vérification avec pypdf
    reader = PdfReader(str(res_path))
    assert len(reader.pages) == 2


def test_cascade_delete_document(tmp_path: Path):
    """Vérifie que la suppression d'un DocumentModel supprime en cascade ses DocumentPageModel."""
    service = AlbumService()
    imgs = [_create_test_image(tmp_path / "casc.png")]
    doc = service.create_album_from_images("Cascade Test", imgs)

    assert DocumentPageModel.select().where(DocumentPageModel.document == doc).count() == 1

    doc.delete_instance()
    assert DocumentPageModel.select().where(DocumentPageModel.document == doc).count() == 0


def test_clean_orphaned_media_preserves_album_media(tmp_path: Path):
    """Vérifie que clean_orphaned_media() ne détruit pas les images d'albums."""
    with patch("ankiforge.services.cards.media_manager.get_app_data_dir", return_value=tmp_path):
        manager = MediaManager()
        service = AlbumService(media_manager=manager)

        img = _create_test_image(tmp_path / "keep_me.png")
        doc = service.create_album_from_images("Album Keep", [img])
        page = service.get_album_pages(doc.id)[0]
        filename = page.media.filename

        # Exécution du nettoyage
        manager.clean_orphaned_media()
        assert (manager.media_dir / filename).exists()
        assert MediaModel.select().where(MediaModel.filename == filename).exists()
