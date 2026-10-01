"""
Tests UI d'intégration pour le flux de transcription et le retry dans AlbumViewerWidget.
"""

import pytest

from ankiforge.database.models import DocumentModel, DocumentPageModel, MediaModel
from ankiforge.services.ai.album_transcription_types import AlbumTranscriptionOptions
from ankiforge.ui.views.documents_view.widgets.album_viewer import AlbumViewerWidget

pytestmark = pytest.mark.ui


class _StubSignal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, slot) -> None:
        self._callbacks.append(slot)

    def emit(self, *args) -> None:
        for cb in self._callbacks:
            cb(*args)


@pytest.fixture
def album_with_pages(mock_db, tmp_path):
    doc = DocumentModel.create(title="Album Viewer Integration", original_path=str(tmp_path / "album"))
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
    ]
    return doc, pages


def test_album_viewer_retry_failures_triggers_worker_on_failed_ids(qtbot, mock_db, album_with_pages, monkeypatch):
    doc, pages = album_with_pages
    viewer = AlbumViewerWidget()
    qtbot.addWidget(viewer)
    viewer.show()
    viewer.load_album(doc)

    captured_runs = []

    class MockWorker:
        def __init__(self, document_id, options=None, category_id=None, page_ids=None, **_kw):
            self.document_id = document_id
            self.options = options
            self.failed_page_ids = [pages[1].id]
            for sig in ("progress", "page_processed", "finished", "finished_signal", "cancelled_signal", "error_signal"):
                setattr(self, sig, _StubSignal())

        def deleteLater(self):
            pass

        def isRunning(self):
            return False

        def start(self):
            captured_runs.append(self)

    monkeypatch.setattr("ankiforge.ui.views.documents_view.widgets.album_viewer.AlbumOCRWorker", MockWorker)

    # Démarrage avec options
    opts = AlbumTranscriptionOptions(
        scope_mode="all",
        custom_range="",
        target_page_ids=[pages[0].id, pages[1].id],
        category_id="structured",
    )
    viewer._on_transcription_options_confirmed(opts)
    assert len(captured_runs) == 1

    worker1 = viewer._ocr_worker
    assert worker1 is not None

    # Simuler fin avec 1 succès et 1 échec
    viewer._on_worker_finished(success_count=1, error_count=1)

    # Le bouton de relance doit être visible
    assert viewer.btn_retry_failures.isVisible() is True
    assert "1" in viewer.btn_retry_failures.text()

    # Clic sur "Relancer les échecs"
    viewer._on_retry_failures()

    # Un deuxième worker a été lancé ciblant uniquement page 2
    assert len(captured_runs) == 2
    worker2 = captured_runs[1]
    assert worker2.options is not None
    assert worker2.options.target_page_ids == [pages[1].id]
