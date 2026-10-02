from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent

from ankiforge.database.models import (
    DocumentModel,
    DocumentPageModel,
)
from ankiforge.services.ai.vision_category_service import VisionCategoryService
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

pytestmark = pytest.mark.ui


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

    assert card.btn_inspect.icon_name == "ph.arrow-square-out"
    assert card.btn_inspect.toolTip() == "Inspecter la page"

    with qtbot.waitSignal(card.inspect_requested, timeout=1000):
        card.btn_inspect.click()


def test_page_inspector_widget_zoom_and_save(qtbot, created_album):
    inspector = PageInspectorWidget()
    qtbot.addWidget(inspector)

    page = created_album.pages.first()
    inspector.load_page(page, total_pages=3)

    assert inspector.lbl_title.text() == "Page 1 sur 3"
    # À l'ouverture, l'inspecteur ajuste à la fenêtre (ticket S1) : 100 % natif faisait
    # déborder la planche hors du viewport, et paraissait cassé.
    assert inspector._zoom_is_fit is True

    fit_factor = inspector._fit_zoom_factor()
    assert inspector._zoom_factor == pytest.approx(fit_factor)

    # Zoom in : quitte l'ajustement, c'est désormais un choix explicite de l'utilisateur.
    inspector._on_zoom_in()
    assert inspector._zoom_factor > fit_factor
    assert inspector._zoom_is_fit is False

    # « Ajuster » retrouve l'échelle qui tient dans la fenêtre, pas 1.0.
    inspector._on_zoom_reset()
    assert inspector._zoom_is_fit is True
    assert inspector._zoom_factor == pytest.approx(fit_factor)

    # Zoom out
    inspector._on_zoom_out()
    assert inspector._zoom_factor < fit_factor

    # Le contraste factice a disparu : il ne changeait rien au rendu et laissait croire
    # à un réglage qui aurait un effet.
    assert not hasattr(inspector, "slider_contrast")


def test_page_inspector_fits_in_logical_pixels_on_a_hidpi_screen(qtbot, created_album, monkeypatch):
    """
    Sur un écran à haute densité, l'ajustement doit toujours remplir le viewport.

    Le calcul d'échelle se faisait sur des pixels **physiques** alors que Qt met en page
    un `QPixmap` sans `devicePixelRatio` en pixels **logiques** : l'image rendue
    débordait donc d'autant qu'il y avait de densité — un ajustement qui échouait
    précisément sur les écrans Retina, où le débordement se voit. La densité sert à
    décoder plus de pixels, jamais à dimensionner.
    """
    inspector = PageInspectorWidget()
    qtbot.addWidget(inspector)
    monkeypatch.setattr(inspector, "devicePixelRatioF", lambda: 2.0, raising=False)

    page = created_album.pages.first()
    inspector.load_page(page, total_pages=3)

    view_size = inspector.image_display.size()
    view_w, view_h = view_size.width(), view_size.height()
    pix = inspector._display_pixmap()
    assert pix is not None and not pix.isNull()

    displayed_w = pix.width() * inspector._zoom_factor
    displayed_h = pix.height() * inspector._zoom_factor

    # L'image ajustée tient dans le viewport, et son grand axe le remplit.
    assert displayed_w <= view_w + 1
    assert displayed_h <= view_h + 1
    assert max(displayed_w / view_w, displayed_h / view_h) == pytest.approx(1.0, rel=0.02)

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


class _StubSignal:
    """
    Signal factice : la vue branche ses slots, et le double peut les déclencher.

    Mémoriser les slots n'est pas un détail : la vue ne libère un worker que sur le vrai
    `QThread.finished`. Un double qui jetait les branchements rendait ce chemin
    invérifiable — et le bouton de compilation restait bloqué après une annulation.
    """

    def __init__(self) -> None:
        self._slots: list[Any] = []

    def connect(self, slot, *_args, **_kwargs) -> None:
        self._slots.append(slot)

    def emit(self, *args: Any, **kwargs: Any) -> None:
        for slot in list(self._slots):
            slot(*args, **kwargs)


def test_inspector_surfaces_a_stale_transcription(qtbot, created_album):
    """
    Un état périmé se dit à l'endroit où l'on corrige la transcription.

    L'inspecteur est précisément l'écran de relecture : y montrer un texte décrivant une
    orientation abandonnée invite à le recopier, donc à figer l'erreur dans les cartes.
    """
    inspector = PageInspectorWidget()
    qtbot.addWidget(inspector)

    page = created_album.pages.first()
    page.ocr_text = "Texte décrivant la planche couchée"
    page.status = "stale"
    page.save()

    inspector.load_page(page, total_pages=3)
    # `isHidden` et non `isVisible` : le parent n'étant pas montré, un enfant visible
    # rapporterait déjà `isVisible() == False`, ce qui ne prouverait rien.
    assert inspector.stale_notice.isHidden() is False

    page.status = "ready"
    page.save()
    inspector.load_page(page, total_pages=3)
    assert inspector.stale_notice.isHidden() is True


def test_rotation_marks_the_transcription_stale(qtbot, created_album):
    """Tourner la planche invalide sa transcription, et l'interface le dit."""
    viewer = AlbumViewerWidget()
    qtbot.addWidget(viewer)
    viewer.load_album(created_album)

    page = created_album.pages.first()
    AlbumService().rotate_page(page.id, degrees=90)

    viewer.refresh_pages()
    card = viewer.grid_layout.itemAt(0).widget()
    assert card.ocr_badge.text() == "Périmé"


def test_album_viewer_offers_the_configured_categories(qtbot, created_album):
    """
    Le sélecteur de catégorie est réellement peuplé.

    L'album utilisait `categories[0]` sans jamais proposer le choix : le paramètre
    existait dans le worker, mais l'utilisateur ne pouvait pas orienter la transcription.
    """
    VisionCategoryService.save_all_categories(VisionCategoryService.get_default_categories())

    viewer = AlbumViewerWidget()
    qtbot.addWidget(viewer)
    viewer.load_album(created_album)

    expected = {cat.id for cat in VisionCategoryService.get_categories()}
    offered = {viewer.combo_category.itemData(i) for i in range(viewer.combo_category.count())}

    assert expected <= offered
    assert viewer._current_category_id() in expected


def test_ocr_uses_the_selected_category_not_the_first(qtbot, created_album, monkeypatch):
    """La catégorie choisie est celle transmise au worker, pas la première de la liste."""
    VisionCategoryService.save_all_categories(VisionCategoryService.get_default_categories())

    viewer = AlbumViewerWidget()
    qtbot.addWidget(viewer)
    viewer.load_album(created_album)

    target = "hardware"
    index = viewer.combo_category.findData(target)
    assert index >= 0
    viewer.combo_category.setCurrentIndex(index)
    assert viewer._current_category_id() == target

    captured: dict[str, object] = {}

    class SpyWorker:
        def __init__(self, document_id, category_id, **_kwargs):
            captured["document_id"] = document_id
            captured["category_id"] = category_id
            # La vue branche ses slots sur ces signaux : le double doit donc les porter.
            # `finished` / `deleteLater` appartiennent au contrat `QThread`, sur lequel la
            # vue s'appuie pour ne pas détruire un thread encore en cours d'exécution.
            for name in ("progress", "page_processed", "finished", "finished_signal", "cancelled_signal", "error_signal"):
                setattr(self, name, _StubSignal())

        def deleteLater(self) -> None:
            captured["deleted"] = True

        def isRunning(self) -> bool:
            return False

        def start(self) -> None:
            captured["started"] = True

    monkeypatch.setattr("ankiforge.ui.views.documents_view.widgets.album_viewer.AlbumOCRWorker", SpyWorker)
    viewer._on_start_ocr_flow()

    assert captured["category_id"] == target
    assert captured["document_id"] == created_album.id
    assert captured["started"] is True


def test_text_only_category_disables_transcription(qtbot, created_album, monkeypatch):
    """
    Une catégorie visant un moteur texte seul refuse la transcription, avec son motif.

    Le dépôt applique déjà cette règle au Studio et à la Batch ; l'album sans elle
    exposait l'utilisateur à une erreur d'API sans raison affichée.
    """
    VisionCategoryService.save_all_categories(VisionCategoryService.get_default_categories())
    monkeypatch.setattr(VisionCategoryService, "category_declares_vision", staticmethod(lambda _category: False))

    viewer = AlbumViewerWidget()
    qtbot.addWidget(viewer)
    viewer.load_album(created_album)

    assert viewer.btn_ocr.isEnabled() is False
    assert "Vision" in viewer.btn_ocr.toolTip()

    # Une capacité non vérifiée ne condamne pas : un moteur multimodal encore absent du
    # catalogue local doit rester utilisable.
    monkeypatch.setattr(VisionCategoryService, "category_declares_vision", staticmethod(lambda _category: None))
    viewer._refresh_category_vision_state()
    assert viewer.btn_ocr.isEnabled() is True


def test_compiling_to_pdf_does_not_block_and_reports_cancellation(qtbot, created_album, monkeypatch, tmp_path):
    """La compilation part en worker et rend compte d'une annulation comme telle."""
    viewer = AlbumViewerWidget()
    qtbot.addWidget(viewer)
    viewer.load_album(created_album)

    monkeypatch.setattr(
        "ankiforge.ui.views.documents_view.widgets.album_viewer.QFileDialog.getSaveFileName",
        staticmethod(lambda *_a, **_k: (str(tmp_path / "album.pdf"), "")),
    )

    started: dict[str, object] = {}

    class SpyPDFWorker:
        def __init__(self, document_id, output_path, album_service=None, parent=None):
            started["document_id"] = document_id
            started["output_path"] = output_path
            self.cancelled = False
            # `finished` et `deleteLater` font partie du contrat `QThread` : la vue s'y
            # branche pour lâcher la référence sur la fin *réelle* du thread. Un double
            # qui les omettait cassait le test pour une raison étrangère au comportement
            # vérifié ici.
            for name in ("progress", "finished", "finished_signal", "cancelled_signal", "error_signal"):
                setattr(self, name, _StubSignal())

        def deleteLater(self) -> None:
            started["deleted"] = True

        def isRunning(self) -> bool:
            return False

        def start(self) -> None:
            started["started"] = True

        def cancel(self) -> None:
            self.cancelled = True
            started["cancelled"] = True

    monkeypatch.setattr("ankiforge.ui.views.documents_view.widgets.album_viewer.AlbumPDFWorker", SpyPDFWorker)

    viewer._on_compile_pdf()

    assert started["started"] is True
    assert started["document_id"] == created_album.id
    # Le nom de paramètre attendu par le service, et non celui qui levait un TypeError.
    assert str(started["output_path"]).endswith("album.pdf")

    # Bouton désactivé pendant l'opération, puis rétabli à l'annulation.
    assert viewer.btn_compile_pdf.isEnabled() is False
    assert viewer.pdf_progress_container.isHidden() is False

    viewer._on_pdf_cancelled(1, 3)
    # Le signal métier ne suffit pas : c'est `QThread.finished`, émis après le retour de
    # `run()`, qui autorise enfin le bouton. Un worker fantôme qui n'émettrait que le
    # premier laisserait la vue verrouillée — c'est le comportement voulu.
    assert viewer.btn_compile_pdf.isEnabled() is False

    viewer._pdf_worker.finished.emit()
    assert viewer._pdf_worker is None
    assert viewer.btn_compile_pdf.isEnabled() is True
    assert viewer.pdf_progress_container.isHidden() is True


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


def test_occlusion_receives_the_rotated_planche(qtbot, tmp_path, mock_db, monkeypatch):
    """
    Le masque d'occlusion est cuit sur l'image **dans son orientation**.

    Les masques SVG sont cuits aux coordonnées relevées sur l'image fournie : passer le
    fichier brut produisait un masque en rapport avec une image que l'utilisateur ne voit
    pas — une réponse à la mauvaise question, réutilisable en l'état dans les cartes.

    Le témoin : un unique pixel bleu dans le coin haut-gauche d'une planche paysage. À 90°,
    la couture le déplace en haut à droite. Un dialogue nourri du fichier brut verrait
    encore le témoin en haut à gauche, et le masque tomberait à côté.
    """
    witness = tmp_path / "witness.png"
    img = Image.new("RGB", (120, 60), color="white")
    img.putpixel((2, 2), (0, 0, 255))
    img.save(witness)

    service = AlbumService()
    doc = service.create_album_from_images("Album témoin", [witness])
    page = service.get_album_pages(doc.id)[0]
    # La page retournée par la rotation, et non celle d'avant : l'objet en mémoire
    # portait encore `rotation=0`, et l'inspecteur travaille sur l'objet qu'on lui donne.
    # En production c'est `refresh_pages()` qui relit la base après le pivot.
    page = service.rotate_page(page.id, 90)
    assert page.rotation == 90

    inspector = PageInspectorWidget()
    qtbot.addWidget(inspector)
    inspector.load_page(page, total_pages=1)

    captured: dict[str, object] = {}

    class SpyOcclusionDialog:
        def __init__(self, image_path, parent=None):
            captured["path"] = Path(image_path)
            captured["image"] = Image.open(image_path).copy()

        def exec(self) -> None:
            captured["exec"] = True

    monkeypatch.setattr("ankiforge.ui.dialogs.image_occlusion_dialog.ImageOcclusionDialog", SpyOcclusionDialog)

    inspector._on_open_image_occlusion()

    assert captured.get("exec") is True, "le dialogue d'occlusion n'a pas été ouvert"
    staged = captured["image"]
    try:
        width, height = staged.size
        assert height > width, "le dialogue a reçu une planche couchée : la rotation n'a pas été appliquée"
        # Le témoin est passé du coin haut-gauche au coin haut-droit.
        blue = [(x, y) for x in range(width) for y in range(height) if staged.getpixel((x, y))[2] > 128 and staged.getpixel((x, y))[0] < 128]
        assert blue, "le pixel témoin a disparu de l'image fournie"
        assert max(x for x, _ in blue) > width // 2, "le témoin est resté à gauche : l'orientation d'origine a été servie"
    finally:
        staged.close()


def _blue_columns(pixmap) -> list[int]:
    """Colonnes contenant du bleu, sur une grille sous-échantillonnée (aperçu réduit)."""
    columns: list[int] = []
    for x in range(0, pixmap.width(), 4):
        for y in range(0, pixmap.height(), 4):
            color = pixmap.pixelColor(x, y)
            if color.blue() > 180 and color.red() < 90 and color.green() < 90:
                columns.append(x)
                break
    return columns


def test_satellite_surfaces_render_a_rotated_planche(qtbot, tmp_path, mock_db):
    """
    Les consommateurs satellites rendent la planche **dans son orientation**.

    Studio et délimitation partageaient le défaut que la couture est venue supprimer :
    chacun ouvrait le fichier brut, donc montrait une planche couchée, et — pour la
    délimitation — bases des bornes sur une image que l'utilisateur ne voit pas. Le
    témoin bleu, en haut à gauche avant rotation, doit se retrouver en haut à droite.
    """
    # Un **bloc** témoin, et non un pixel unique : l'aperçu de délimitation réduit
    # l'image à 700 px de large, et un pixel isolé disparaissait sous l'échantillonnage.
    witness = tmp_path / "satellite.png"
    img = Image.new("RGB", (200, 100), color="white")
    for x in range(24):
        for y in range(24):
            img.putpixel((x, y), (0, 0, 255))
    img.save(witness)

    service = AlbumService()
    doc = service.create_album_from_images("Album satellites", [witness])
    page = service.rotate_page(service.get_album_pages(doc.id)[0].id, 90)
    assert page.rotation == 90

    # ── Studio de création ───────────────────────────────────────────────
    from ankiforge.ui.views.creation_view.widgets.document_editor import DocumentEditorWidget

    editor = DocumentEditorWidget()
    qtbot.addWidget(editor)
    studio_image = editor._album_page_image(page)
    assert studio_image is not None, "la galerie du Studio n'a pas rendu la planche"
    assert studio_image.height() > studio_image.width(), "galerie : planche couchée, orientation non appliquée"
    assert studio_image.width() <= DocumentEditorWidget.ALBUM_THUMBNAIL_PX, "la vignette du Studio n'est pas plafonnée"

    # ── Délimitation ─────────────────────────────────────────────────────
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentPreviewWidget

    preview = DocumentPreviewWidget(DocumentModel.get_by_id(doc.id))
    qtbot.addWidget(preview)
    preview._load_album_page(1)

    shown = preview.image_label.pixmap()
    assert not shown.isNull(), "l'aperçu de délimitation n'a rien affiché"
    pixmap = shown.toImage()
    assert pixmap.height() > pixmap.width(), "délimitation : planche couchée, orientation non appliquée"
    blue_x = _blue_columns(pixmap)
    assert blue_x, "le bloc témoin a disparu de l'aperçu"
    assert max(blue_x) > pixmap.width() // 2, "témoin resté à gauche : l'orientation d'origine a été servie"


def test_inspector_keeps_the_capped_render_until_zoom_exceeds_it(qtbot, tmp_path, mock_db):
    """
    La pleine résolution se charge *à la demande*, et jamais parce qu'une planche est petite.

    Décoder une planche entière pour l'afficher dans un cadre de quelques centaines de
    pixels est le gel que S1 supprime. Mais refuser cette lecture au-delà de 100 %
    condamnerait le zoom à rester flou — le plafond doit céder quand l'utilisateur
    demande plus de détails, et seulement là.
    """
    big = tmp_path / "big.png"
    Image.new("RGB", (4000, 3000), color=(20, 90, 160)).save(big)
    service = AlbumService()
    doc = service.create_album_from_images("Album zoom", [big])

    inspector = PageInspectorWidget()
    qtbot.addWidget(inspector)
    page = service.get_album_pages(doc.id)[0]
    inspector.load_page(page, total_pages=1)

    # À l'ajustement, le rendu plafonné suffit : aucune lecture native.
    assert inspector._full_pixmap is None, "la pleine résolution a été chargée sans zoom"
    capped = inspector._display_pixmap()
    assert capped is not None
    assert max(capped.width(), capped.height()) <= inspector._inspection_px()

    # Le zoom part de l'ajustement (~0.17 ici) et progresse par paliers de 1.2 : il
    # faut donc plusieurs clics pour dépasser 100 %.
    for _ in range(12):
        inspector._on_zoom_in()
    assert inspector._zoom_factor > 1.0
    detailed = inspector._display_pixmap()
    assert detailed is not None and not detailed.isNull()
    assert inspector._full_pixmap is not None, "un zoom au-delà de 100 % n'a pas chargé la pleine résolution"
    assert max(detailed.width(), detailed.height()) > max(capped.width(), capped.height())
    assert detailed.width() == 4000, "la lecture à la demande n'a pas rendu la planche native"


def test_album_view_keeps_the_worker_reference_until_the_thread_really_ends(qtbot, created_album, mock_db):
    """
    La référence Python du worker n'est lâchée qu'à la **vraie** fin du QThread.

    `finished_signal` est émis depuis `run()`, donc juste avant que le thread ne rende la
    main. Y remettre `self._ocr_worker = None` suffisait à laisser le wrapper être ramassé
    pendant que le C++ tournait encore — le crash natif que `deleteLater` cherche à éviter.
    """
    viewer = AlbumViewerWidget()
    qtbot.addWidget(viewer)

    worker = MagicMock()
    viewer._ocr_worker = worker

    # Le signal métier termine, `run()` est sur le point de rendre la main.
    viewer._on_worker_finished(2, 0)
    assert viewer._ocr_worker is worker, "la référence a été lâchée sur le signal métier, pas sur la fin du thread"

    # Le vrai `QThread.finished` la libère enfin.
    viewer._release_worker("ocr")
    assert viewer._ocr_worker is None


def test_album_view_refuses_to_close_while_a_worker_still_runs(qtbot, created_album, mock_db):
    """
    Fermer la vue pendant qu'un worker tourne doit **refuser** l'événement, pas l'annoncer.

    Le `closeEvent` journalisait « destruction reportée » puis laissait l'événement passer :
    la vue se détruisait quand même et le `QThread` avec elle. Un avertissement dans le
    journal n'a jamais empêché un crash natif.
    """
    viewer = AlbumViewerWidget()
    qtbot.addWidget(viewer)

    class StuckWorker:
        def isRunning(self):
            return True

        def cancel(self):
            pass

        def wait(self, timeout=None):
            return False  # l'annulation n'a pas abouti dans le délai imparti

    viewer._pdf_worker = StuckWorker()  # type: ignore[assignment]

    event = QCloseEvent()
    viewer.closeEvent(event)

    assert not event.isAccepted(), "la fermeture a été acceptée alors qu'un worker tournait encore"
    assert viewer._pdf_worker is not None, "la référence worker a été perdue pendant une fermeture refusée"

    # Une fois le worker parti, la fermeture doit passer.
    viewer._pdf_worker = None
    event_ok = QCloseEvent()
    viewer.closeEvent(event_ok)
    assert event_ok.isAccepted(), "la fermeture a été refusée alors qu'aucun worker ne tournait"


def test_album_viewer_toolbar_responsive_wrapping(qtbot):
    """La barre d'outils de l'album viewer s'agence de manière fluide sans tronquer les boutons."""
    viewer = AlbumViewerWidget()
    qtbot.addWidget(viewer)
    viewer.show()

    assert hasattr(viewer, "toolbar_flow_layout")
    fl = viewer.toolbar_flow_layout

    # À grande largeur (>= 700px), les actions tiennent sur 1 ligne
    h_large = fl.heightForWidth(750)
    assert h_large <= 32

    # À largeur intermédiaire (450px), les actions passent sur au moins 2 lignes
    h_medium = fl.heightForWidth(450)
    assert h_medium > h_large
    assert h_medium >= 58

    # À largeur étroite (380px), les actions passent sur 2 ou 3 lignes
    h_narrow = fl.heightForWidth(380)
    assert h_narrow >= h_medium

    # Vérifier la présence et lisibilité de tous les boutons
    buttons = [viewer.btn_ocr, viewer.btn_rag, viewer.btn_search_rag, viewer.btn_compile_pdf, viewer.btn_add_pages, viewer.btn_forge]
    for btn in buttons:
        assert btn.toolTip() != ""
        if btn != viewer.btn_search_rag:
            assert len(btn.text()) > 0

    # Titre long : ne bloque pas le conteneur grâce à Policy.Ignored
    viewer.lbl_album_title.setText("Un titre d'album extrêmement long qui ne doit pas écraser les boutons")
    viewer.resize(380, 500)
    viewer.layout().activate()
    assert viewer.toolbar_container.width() <= 380
