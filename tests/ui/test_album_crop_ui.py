import pytest
from PIL import Image
from PySide6.QtCore import QRect

from ankiforge.database.models import DocumentPageModel
from ankiforge.services.cards.album_service import AlbumService
from ankiforge.ui.views.documents_view.widgets.album_viewer import (
    AlbumPageCard,
    AlbumViewerWidget,
    CropImageLabel,
    PageInspectorWidget,
)

pytestmark = pytest.mark.ui


@pytest.fixture
def album_with_pages(tmp_path, mock_db):
    """Crée un album de test avec 2 pages."""
    service = AlbumService()
    img_paths = []
    for i in (1, 2):
        p = tmp_path / f"scan_{i}.png"
        img = Image.new("RGB", (100, 80), color="blue")
        img.save(p)
        img_paths.append(str(p))

    doc = service.create_album_from_images("Album Crop UI", img_paths, sort_mode="none")
    return doc


def test_album_page_card_crop_badge(qtbot, album_with_pages):
    """Vérifie l'affichage du badge 'Recadrée' sur AlbumPageCard."""
    service = AlbumService()
    pages = service.get_album_pages(album_with_pages.id)
    page = pages[0]

    card = AlbumPageCard(page)
    qtbot.addWidget(card)
    card.show()

    assert hasattr(card, "crop_badge")
    assert not card.crop_badge.isVisible()

    # Recadrer la page
    service.set_page_crop(page.id, (10, 10, 50, 40))
    page_reloaded = DocumentPageModel.get_by_id(page.id)
    card.page = page_reloaded
    card.update_crop_status(page_reloaded.crop_data)
    assert card.crop_badge.isVisible()


def test_page_inspector_crop_controls(qtbot, album_with_pages):
    """Vérifie les contrôles de recadrage dans PageInspectorWidget."""
    service = AlbumService()
    pages = service.get_album_pages(album_with_pages.id)
    page = pages[0]

    inspector = PageInspectorWidget()
    qtbot.addWidget(inspector)
    inspector.show()

    inspector.load_page(page, total_pages=2)

    # État initial non recadré
    assert inspector.btn_crop.isVisible()
    assert not inspector.btn_remove_crop.isVisible()
    assert not inspector.crop_badge.isVisible()
    assert not inspector.crop_banner.isVisible()

    # Entrée en mode recadrage
    inspector.btn_crop.click()
    assert inspector.crop_banner.isVisible()
    assert inspector.image_display.is_crop_mode is True

    # Annulation
    inspector.btn_cancel_crop.click()
    assert not inspector.crop_banner.isVisible()
    assert inspector.image_display.is_crop_mode is False

    # Application d'un recadrage direct via service
    service.set_page_crop(page.id, (5, 5, 40, 30))
    page_cropped = DocumentPageModel.get_by_id(page.id)
    inspector.load_page(page_cropped, total_pages=2)

    assert inspector.crop_badge.isVisible()
    assert inspector.btn_remove_crop.isVisible()

    # Retrait du recadrage via bouton
    with qtbot.waitSignal(inspector.page_crop_changed, timeout=1000):
        inspector.btn_remove_crop.click()

    page_after_remove = DocumentPageModel.get_by_id(page.id)
    assert page_after_remove.crop_box is None
    assert not inspector.crop_badge.isVisible()
    assert not inspector.btn_remove_crop.isVisible()


def test_crop_image_label_interaction(qtbot):
    """Vérifie le fonctionnement de CropImageLabel (sélection et dessin)."""
    lbl = CropImageLabel()
    qtbot.addWidget(lbl)
    lbl.resize(200, 200)
    lbl.show()

    assert not lbl.is_crop_mode
    lbl.set_crop_mode(True)
    assert lbl.is_crop_mode

    # Définition de la sélection
    lbl.set_selection_rect(QRect(20, 30, 80, 50))
    rect = lbl.get_selection_rect()
    assert rect == QRect(20, 30, 80, 50)

    # Réinitialisation
    lbl.reset_selection()
    assert lbl.get_selection_rect().isNull()


def test_page_inspector_apply_crop_flow(qtbot, album_with_pages):
    """Vérifie le flux complet d'application d'un recadrage depuis l'inspecteur."""
    service = AlbumService()
    pages = service.get_album_pages(album_with_pages.id)
    page = pages[0]

    inspector = PageInspectorWidget()
    qtbot.addWidget(inspector)
    inspector.resize(400, 400)
    inspector.show()

    inspector.load_page(page, total_pages=2)

    # Démarrage du recadrage
    inspector.btn_crop.click()
    assert inspector.crop_banner.isVisible()

    # Définition manuelle d'une sélection valide sur l'affichage
    pix = inspector.image_display.pixmap()
    assert pix is not None and not pix.isNull()

    # Sélection au centre de l'image
    offset_x = max(0, (inspector.image_display.width() - pix.width()) // 2)
    offset_y = max(0, (inspector.image_display.height() - pix.height()) // 2)
    inspector.image_display._selection_rect = QRect(offset_x + 10, offset_y + 10, 40, 30)

    with qtbot.waitSignal(inspector.page_crop_changed, timeout=1000):
        inspector.btn_apply_crop.click()

    assert not inspector.crop_banner.isVisible()
    assert not inspector.image_display.is_crop_mode

    page_updated = DocumentPageModel.get_by_id(page.id)
    assert page_updated.crop_box is not None
    assert len(page_updated.crop_box) == 4
    assert inspector.crop_badge.isVisible()
    assert inspector.btn_remove_crop.isVisible()


def test_album_viewer_crop_integration(qtbot, album_with_pages):
    """Vérifie que le changement de recadrage dans l'inspecteur rafraîchit l'AlbumViewerWidget."""
    viewer = AlbumViewerWidget()
    qtbot.addWidget(viewer)
    viewer.resize(800, 600)
    viewer.show()

    viewer.load_album(album_with_pages)
    assert viewer.grid_layout.count() == 2

    first_card = viewer.grid_layout.itemAt(0).widget()
    assert isinstance(first_card, AlbumPageCard)
    assert not first_card.crop_badge.isVisible()

    # Simuler le signal de modification de recadrage
    with qtbot.waitSignal(viewer.album_modified, timeout=1000):
        # On définit un recadrage et on déclenche le signal
        service = AlbumService()
        pages = service.get_album_pages(album_with_pages.id)
        service.set_page_crop(pages[0].id, (10, 10, 30, 30))
        viewer.inspector.page_crop_changed.emit(pages[0].id)

    # Vérifier que les cartes ont été rafraîchies
    new_first_card = viewer.grid_layout.itemAt(0).widget()
    assert isinstance(new_first_card, AlbumPageCard)
    assert new_first_card.crop_badge.isVisible()
