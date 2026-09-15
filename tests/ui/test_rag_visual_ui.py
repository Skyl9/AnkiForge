"""Tests UI headless pour le RAG Visuel, RAGTestDialog et AlbumViewerWidget."""

from unittest.mock import patch

import pytest

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    DocumentPageModel,
    db,
)
from ankiforge.services.cards.media_manager import MediaManager
from ankiforge.services.workers.coverage_worker import CoverageWorker
from ankiforge.ui.views.documents_view.dialogs.rag_test_dialog import RAGTestDialog
from ankiforge.ui.views.documents_view.widgets.album_viewer import AlbumViewerWidget


@pytest.fixture
def sample_visual_doc(mock_db, tmp_path):
    """Crée un document album de test avec 1 page et média réel."""
    media_mgr = MediaManager()
    media_mgr.media_dir = tmp_path / "media"
    media_mgr.media_dir.mkdir(parents=True, exist_ok=True)
    img_file = tmp_path / "page_1.png"
    img_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

    with db.atomic():
        doc = DocumentModel.create(title="Planche Anatomique", file_type="album", total_pages=1)
        m = media_mgr.store_document_source(str(img_file))
        assert m is not None

        page = DocumentPageModel.create(document=doc, media=m, page_number=1, ocr_text="")
        chunk = DocumentChunkModel.create(
            document=doc,
            chunk_index=0,
            content="### Page 1\n\nSchéma de l'artère carotide et de la veine jugulaire.",
            page_number=1,
            heading_path="Page 1",
            media=m,
        )

    return {"doc": doc, "page": page, "chunk": chunk, "media": m, "media_mgr": media_mgr}


@pytest.mark.ui
def test_album_viewer_rag_buttons(qtbot, sample_visual_doc):
    """Vérifie que AlbumViewerWidget contient les boutons RAG et émet les signaux attendus."""
    widget = AlbumViewerWidget()
    qtbot.addWidget(widget)

    doc = sample_visual_doc["doc"]
    widget.load_album(doc)

    assert hasattr(widget, "btn_rag")
    assert hasattr(widget, "btn_search_rag")

    with qtbot.waitSignal(widget.visual_rag_requested, timeout=2000) as blocker_rag:
        widget.btn_rag.click()
    assert blocker_rag.args == [doc.id]

    with qtbot.waitSignal(widget.search_rag_requested, timeout=2000) as blocker_search:
        widget.btn_search_rag.click()
    assert blocker_search.args == [doc.id]


@pytest.mark.ui
def test_rag_test_dialog_visual_badge_and_search(qtbot, sample_visual_doc):
    """Vérifie que RAGTestDialog affiche le badge visuel [Visuel] et formate le résultat."""
    doc = sample_visual_doc["doc"]
    dlg = RAGTestDialog(doc)
    qtbot.addWidget(dlg)

    fake_results = [
        {
            "chunk_id": sample_visual_doc["chunk"].id,
            "chunk_index": 0,
            "content": "Schéma de l'artère carotide et de la veine jugulaire.",
            "heading_path": "Page 1",
            "page_number": 1,
            "score": 0.92,
            "dense_score": 0.92,
            "dense_rank": 1,
            "sparse_score": 5.4,
            "sparse_rank": 1,
            "rrf_score": 0.032,
            "relevance_pct": 95,
            "channel": "hybrid",
            "media_id": sample_visual_doc["media"].id,
            "media_filename": sample_visual_doc["media"].filename,
        }
    ]

    with patch("ankiforge.ui.views.documents_view.dialogs.rag_test_dialog.RAGService.search", return_value=fake_results):
        dlg.search_input.setText("carotide")
        dlg._on_search()

    assert dlg.results_list.count() == 1
    item = dlg.results_list.item(0)
    assert "[Visuel]" in item.text()
    assert "Page 1" in item.text()
    assert "carotide" in item.text()


@pytest.mark.ui
def test_coverage_worker_visual_album(qtbot, sample_visual_doc):
    """Vérifie que CoverageWorker exécute le flux Visual RAG pour un document de type album."""
    doc = sample_visual_doc["doc"]

    with patch("ankiforge.services.rag.visual_rag_service.VisualRAGService.index_visual_document", return_value=True) as mock_index:
        worker = CoverageWorker(document_id=doc.id)
        with qtbot.waitSignal(worker.finished_processing, timeout=3000):
            worker.start()

        mock_index.assert_called_once()
