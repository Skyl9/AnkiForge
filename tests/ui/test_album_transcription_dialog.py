"""
Tests UI pour le dialogue dédié AlbumTranscriptionDialog.
"""

import pytest
from PySide6.QtCore import Qt

from ankiforge.database.models import DocumentModel, DocumentPageModel, MediaModel
from ankiforge.services.ai.album_transcription_types import AlbumTranscriptionOptions
from ankiforge.ui.dialogs.album_transcription_dialog import AlbumTranscriptionDialog

pytestmark = pytest.mark.ui


@pytest.fixture
def album_with_mixed_pages(mock_db, tmp_path):
    """Crée un album avec 4 planches : 1 prête avec OCR, 1 sans OCR, 2 avec status 'stale'."""
    doc = DocumentModel.create(title="Album Test Dialog", original_path=str(tmp_path / "album"))
    media = MediaModel.create(
        filename="test.png",
        original_name="test.png",
        checksum="hash123",
        mime_type="image/png",
        file_size=100,
    )
    pages = []
    # Planche 1 : prête avec OCR
    pages.append(DocumentPageModel.create(document=doc, media=media, page_number=1, ocr_text="Texte existant", status="ready"))
    # Planche 2 : sans OCR
    pages.append(DocumentPageModel.create(document=doc, media=media, page_number=2, ocr_text="", status="ready"))
    # Planche 3 : périmée (stale)
    pages.append(DocumentPageModel.create(document=doc, media=media, page_number=3, ocr_text="Ancien texte", status="stale"))
    # Planche 4 : périmée (stale)
    pages.append(DocumentPageModel.create(document=doc, media=media, page_number=4, ocr_text="", status="stale"))
    return doc, pages


def test_dialog_scope_defaults_to_stale_when_present(qtbot, mock_db, album_with_mixed_pages):
    doc, pages = album_with_mixed_pages
    dialog = AlbumTranscriptionDialog(doc)
    qtbot.addWidget(dialog)

    # 4 planches au total : 1 prête, 1 sans OCR, 2 stale
    assert dialog.lbl_count_all.text() == "(4)"
    assert dialog.lbl_count_untranscribed.text() == "(2)"
    assert dialog.lbl_count_stale.text() == "(2)"

    # Des planches stale existent, le mode stale doit être pré-sélectionné
    assert dialog.rb_stale.isChecked()
    assert dialog.btn_start.isEnabled()

    opts = dialog.get_options()
    assert opts.scope_mode == "stale"
    assert set(opts.target_page_ids) == {pages[2].id, pages[3].id}


def test_dialog_custom_range_updates_and_validates(qtbot, mock_db, album_with_mixed_pages):
    doc, pages = album_with_mixed_pages
    dialog = AlbumTranscriptionDialog(doc)
    qtbot.addWidget(dialog)

    dialog.rb_custom.setChecked(True)
    assert dialog.le_custom_range.isEnabled()

    # Saisie intervalle "1, 3"
    dialog.le_custom_range.setText("1, 3")
    assert dialog.lbl_count_custom.text() == "(2)"
    opts = dialog.get_options()
    assert set(opts.target_page_ids) == {pages[0].id, pages[2].id}

    # Saisie intervalle hors borne (ex: "99") -> 0 planche -> bouton désactivé
    dialog.le_custom_range.setText("99")
    assert dialog.lbl_count_custom.text() == "(0)"
    assert dialog.btn_start.isEnabled() is False


def test_dialog_hardware_category_greys_out_directives(qtbot, mock_db, album_with_mixed_pages):
    doc, pages = album_with_mixed_pages
    dialog = AlbumTranscriptionDialog(doc)
    qtbot.addWidget(dialog)

    # Sélection de la catégorie Apple Vision (id="hardware")
    idx = dialog.combo_category.findData("hardware")
    assert idx >= 0
    dialog.combo_category.setCurrentIndex(idx)

    # Le groupe des directives doit être désactivé et le bandeau explicatif visible
    assert dialog.directives_group.isEnabled() is False
    assert dialog.hardware_notice.isVisible() is True

    # Revenir sur "structured" réactive les directives
    idx_struct = dialog.combo_category.findData("structured")
    assert idx_struct >= 0
    dialog.combo_category.setCurrentIndex(idx_struct)
    assert dialog.directives_group.isEnabled() is True
    assert dialog.hardware_notice.isVisible() is False


def test_dialog_accept_emits_transcription_requested(qtbot, mock_db, album_with_mixed_pages):
    doc, pages = album_with_mixed_pages
    dialog = AlbumTranscriptionDialog(doc)
    qtbot.addWidget(dialog)

    received_options = []
    dialog.transcription_requested.connect(received_options.append)

    dialog.rb_all.setChecked(True)
    dialog.cb_figures.setChecked(True)
    dialog.txt_custom_instructions.setText("Langue allemande")

    qtbot.mouseClick(dialog.btn_start, Qt.MouseButton.LeftButton)

    assert len(received_options) == 1
    opts: AlbumTranscriptionOptions = received_options[0]
    assert opts.scope_mode == "all"
    assert len(opts.target_page_ids) == 4
    assert opts.include_figures is True
    assert opts.custom_instructions == "Langue allemande"
