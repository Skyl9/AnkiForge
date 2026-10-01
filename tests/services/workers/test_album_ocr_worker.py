"""
Tests unitaires pour AlbumOCRWorker avec options de transcription et suivi des échecs.
"""

from unittest.mock import MagicMock

import pytest

from ankiforge.database.models import DocumentModel, DocumentPageModel, MediaModel
from ankiforge.services.ai.album_transcription_types import AlbumTranscriptionOptions
from ankiforge.services.workers.album_worker import AlbumOCRWorker

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_pages(mock_db, tmp_path):
    doc = DocumentModel.create(title="Album Worker Test", original_path=str(tmp_path / "album"))
    media = MediaModel.create(
        filename="test.png",
        original_name="test.png",
        checksum="hash123",
        mime_type="image/png",
        file_size=100,
    )
    pages = [
        DocumentPageModel.create(document=doc, media=media, page_number=1, ocr_text="", status="ready"),
        DocumentPageModel.create(document=doc, media=media, page_number=2, ocr_text="", status="ready"),
        DocumentPageModel.create(document=doc, media=media, page_number=3, ocr_text="", status="ready"),
    ]
    return doc, pages


def test_album_ocr_worker_targets_selected_page_ids(qtbot, mock_db, mock_pages):
    doc, pages = mock_pages
    mock_ocr = MagicMock()
    mock_ocr.transcribe_page.side_effect = lambda pid, **kw: pages[pid - 1]

    opts = AlbumTranscriptionOptions(
        scope_mode="custom",
        custom_range="1, 3",
        target_page_ids=[pages[0].id, pages[2].id],
        category_id="structured",
    )

    worker = AlbumOCRWorker(document_id=doc.id, options=opts, ocr_service=mock_ocr)
    finished_records = []
    worker.finished_signal.connect(lambda s, e: finished_records.append((s, e)))

    with qtbot.waitSignal(worker.finished_signal, timeout=5000):
        worker.start()

    assert finished_records == [(2, 0)]
    assert mock_ocr.transcribe_page.call_count == 2
    called_ids = [call[0][0] for call in mock_ocr.transcribe_page.call_args_list]
    assert called_ids == [pages[0].id, pages[2].id]
    assert worker.failed_page_ids == []


def test_album_ocr_worker_collects_failed_page_ids(qtbot, mock_db, mock_pages):
    doc, pages = mock_pages
    mock_ocr = MagicMock()

    # La page 2 lève une exception
    def side_effect(pid: int, **kw):
        if pid == pages[1].id:
            raise RuntimeError("API timeout")
        return pages[pid - 1]

    mock_ocr.transcribe_page.side_effect = side_effect

    opts = AlbumTranscriptionOptions(
        scope_mode="all",
        custom_range="",
        target_page_ids=[pages[0].id, pages[1].id, pages[2].id],
        category_id="structured",
    )

    worker = AlbumOCRWorker(document_id=doc.id, options=opts, ocr_service=mock_ocr)
    finished_records = []
    worker.finished_signal.connect(lambda s, e: finished_records.append((s, e)))

    with qtbot.waitSignal(worker.finished_signal, timeout=5000):
        worker.start()

    assert finished_records == [(2, 1)]  # 2 succès, 1 échec
    assert worker.failed_page_ids == [pages[1].id]
