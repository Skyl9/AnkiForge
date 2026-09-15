import pytest
from PIL import Image
from PySide6.QtCore import Qt

from ankiforge.database.models import (
    DocumentModel,
    DocumentPageModel,
)
from ankiforge.services.cards.album_service import AlbumService
from ankiforge.ui.views.creation_view.view import CreationView
from ankiforge.ui.views.documents_view.dialogs.album_import_dialog import (
    AlbumImportDialog,
)
from ankiforge.ui.views.documents_view.view import DocumentsView
from ankiforge.ui.views.documents_view.widgets.album_viewer import (
    AlbumPageCard,
    AlbumViewerWidget,
    PageInspectorWidget,
)


@pytest.fixture
def sample_album_files(tmp_path):
    """Crée 3 images de test temporaires."""
    img_paths = []
    for i in (1, 2, 3):
        p = tmp_path / f"scan_page_{i}.png"
        img = Image.new("RGB", (100, 150), color=(i * 60, 100, 200))
        img.save(p)
        img_paths.append(str(p))
    return img_paths


@pytest.fixture
def created_album(sample_album_files, mock_db):
    """Crée un album de test en BDD."""
    service = AlbumService()
    return service.create_album_from_images(
        title="Manuel Anatomie Test",
        image_paths=sample_album_files,
        sort_mode="natural",
    )


def test_album_import_dialog_initialization(qtbot, mock_db):
    dialog = AlbumImportDialog()
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "Créer un Album d'Images"
    assert dialog.combo_sort.count() == 3
    assert dialog.combo_folder.count() >= 1
    assert dialog.btn_create.isEnabled() is False


def test_album_import_dialog_set_files_and_create(qtbot, sample_album_files, mock_db):
    dialog = AlbumImportDialog()
    qtbot.addWidget(dialog)

    dialog.set_initial_files(sample_album_files)
    assert len(dialog._image_paths) == 3
    assert dialog.files_list.count() == 3
    assert dialog.btn_create.isEnabled() is True
    assert "scan_page" in dialog.input_title.text() or "Album" in dialog.input_title.text()

    dialog.input_title.setText("Mon Bel Album")

    created_signal_doc_id = []
    dialog.album_created.connect(lambda doc_id: created_signal_doc_id.append(doc_id))

    dialog._on_create_album()

    assert len(created_signal_doc_id) == 1
    doc = DocumentModel.get_by_id(created_signal_doc_id[0])
    assert doc.title == "Mon Bel Album"
    assert doc.file_type == "album"
    assert doc.total_pages == 3


def test_album_page_card_signals(qtbot, created_album):
    page = created_album.pages.first()
    card = AlbumPageCard(page)
    qtbot.addWidget(card)

    assert card.page_badge.text() == "P. 1"
    assert card.ocr_badge.text() == "Non transcrit"

    # Test update_status
    card.update_status("Le tissu musculaire est composé de fibres.")
    assert card.ocr_badge.text() == "✓ OCR"

    # Test signals
    with qtbot.waitSignal(card.rotate_requested, timeout=1000):
        card.btn_rotate.click()

    with qtbot.waitSignal(card.move_requested, timeout=1000):
        card.btn_left.click()

    with qtbot.waitSignal(card.inspect_requested, timeout=1000):
        card.btn_inspect.click()


def test_page_inspector_widget_zoom_and_save(qtbot, created_album):
    inspector = PageInspectorWidget()
    qtbot.addWidget(inspector)

    page = created_album.pages.first()
    inspector.load_page(page, total_pages=3)

    assert inspector.lbl_title.text() == "Page 1 sur 3"
    assert inspector._zoom_factor == 1.0

    # Zoom in
    inspector._on_zoom_in()
    assert inspector._zoom_factor > 1.0

    # Zoom reset
    inspector._on_zoom_reset()
    assert inspector._zoom_factor == 1.0

    # Zoom out
    inspector._on_zoom_out()
    assert inspector._zoom_factor < 1.0

    # Contrast slider
    inspector.slider_contrast.setValue(10)
    assert inspector.slider_contrast.value() == 10

    # Save OCR
    inspector.ocr_text_edit.setPlainText("Transcription corrigée manuellement")
    saved_events = []
    inspector.page_saved.connect(lambda pid, txt: saved_events.append((pid, txt)))

    inspector._on_save_ocr()
    assert len(saved_events) == 1
    assert saved_events[0] == (page.id, "Transcription corrigée manuellement")

    # Reload from DB
    updated_page = DocumentPageModel.get_by_id(page.id)
    assert updated_page.ocr_text == "Transcription corrigée manuellement"


def test_album_viewer_widget_operations(qtbot, created_album):
    viewer = AlbumViewerWidget()
    qtbot.addWidget(viewer)

    viewer.load_album(created_album)

    assert viewer.lbl_album_title.text() == "Manuel Anatomie Test"
    assert viewer.pages_badge.text() == "3 pages"
    assert viewer.grid_layout.count() == 3

    # Rotation de page
    page1 = viewer._pages[0]
    viewer._on_rotate_page(page1.id)
    p1_reloaded = DocumentPageModel.get_by_id(page1.id)
    assert p1_reloaded.rotation == 90

    # Inspecteur
    viewer._on_open_inspector(page1.id)
    assert viewer.stack.currentIndex() == 1
    assert viewer.inspector.current_page.id == page1.id

    # Retour à la planche
    viewer.inspector.close_requested.emit()
    assert viewer.stack.currentIndex() == 0

    # Déplacement
    viewer._on_move_page(page1.id, 1)
    pages_after_move = list(DocumentPageModel.select().where(DocumentPageModel.document == created_album).order_by(DocumentPageModel.page_number))
    assert pages_after_move[1].id == page1.id

    # Forger signal
    forge_signals = []
    viewer.forge_requested.connect(lambda did: forge_signals.append(did))
    viewer.btn_forge.click()
    assert forge_signals == [created_album.id]


def test_documents_view_album_integration(qtbot, created_album, mock_db):
    view = DocumentsView()
    qtbot.addWidget(view)

    view.refresh_data()

    # Trouver l'item album dans l'arborescence
    found_item = None
    for i in range(view.tree_explorer.topLevelItemCount()):
        it = view.tree_explorer.topLevelItem(i)
        data = it.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("id") == created_album.id:
            found_item = it
            break

    assert found_item is not None
    assert "Manuel Anatomie Test" in found_item.text(0)
    assert "3p" in found_item.text(0)

    # Sélection de l'item -> doit afficher l'album_viewer (index 2 de l'editor_stack)
    view.tree_explorer.setCurrentItem(found_item)
    assert view.editor_stack.currentIndex() == 2
    assert view.album_viewer._doc.id == created_album.id


def test_creation_view_album_integration(qtbot, created_album, mock_db):
    view = CreationView()
    qtbot.addWidget(view)

    view.refresh_data()

    # Trouver l'item album dans file_tree
    found_item = None
    for i in range(view.file_tree.topLevelItemCount()):
        it = view.file_tree.topLevelItem(i)
        doc = it.data(0, Qt.ItemDataRole.UserRole)
        if doc and hasattr(doc, "id") and doc.id == created_album.id:
            found_item = it
            break

    assert found_item is not None
    assert "Manuel Anatomie Test" in found_item.text(0)

    # Double-clic sur l'album
    view._on_explorer_item_double_clicked(found_item, 0)

    # Doit avoir ouvert un onglet pour l'album
    assert "Manuel Anatomie Test" in view.open_editors
    assert not view.scope_card.isHidden()
    assert not view.vision_card.isHidden()
    assert view.btn_preset_all.text() == "Tout (3p)"
