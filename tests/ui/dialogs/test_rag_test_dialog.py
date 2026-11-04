"""Tests UI headless pour RAGTestDialog et la prévention du chevauchement dans QListWidget."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage

from ankiforge.database.models import DocumentModel
from ankiforge.ui.views.documents_view.dialogs.rag_test_dialog import (
    RAGTestDialog,
    _RAGResultWidget,
)

pytestmark = pytest.mark.ui


@pytest.fixture
def fake_doc(mock_db: Any) -> DocumentModel:
    """Document factice pour RAGTestDialog."""
    return DocumentModel.create(title="Neuro-Anatomie", file_type="pdf", total_pages=10)


def test_rag_result_widget_size_hint_basic(qtbot: Any) -> None:
    """Vérifie que _RAGResultWidget calcule une hauteur minimale suffisante pour prévenir l'overlap."""
    res = {
        "chunk_index": 0,
        "content": "Le cortex cérébral est divisé en quatre lobes principaux.",
        "heading_path": "Système Nerveux Central > Télencéphale",
        "page_number": 3,
        "score": 0.95,
        "dense_score": 0.95,
        "dense_rank": 1,
        "sparse_score": 7.8,
        "sparse_rank": 1,
        "rrf_score": 0.033,
        "relevance_pct": 98,
        "channel": "hybrid",
    }
    widget = _RAGResultWidget(res, "cortex")
    qtbot.addWidget(widget)
    hint = widget.sizeHint()
    assert isinstance(hint, QSize)
    assert hint.height() >= 120


def test_rag_result_widget_size_hint_with_media(qtbot: Any, tmp_path: Path) -> None:
    """Vérifie que _RAGResultWidget avec un média réel alloue une hauteur accrue pour l'image."""
    img_file = tmp_path / "cortex_schema.png"
    img = QImage(120, 80, QImage.Format.Format_RGB32)
    img.fill(QColor("blue"))
    img.save(str(img_file))

    res = {
        "chunk_index": 1,
        "content": "Schéma fonctionnel des aires de Brodmann.",
        "heading_path": "Système Nerveux Central > Aires Corticales",
        "page_number": 5,
        "score": 0.88,
        "relevance_pct": 90,
        "channel": "hybrid",
        "media_filename": "cortex_schema.png",
    }
    with patch(
        "ankiforge.ui.views.documents_view.dialogs.rag_test_dialog.resolve_media_path",
        return_value=img_file,
    ):
        widget = _RAGResultWidget(res, "aires")
        qtbot.addWidget(widget)
        hint = widget.sizeHint()
        # Doit inclure l'en-tête, la jauge, le texte, les détails, plus l'image (64px) et le bouton
        assert hint.height() >= 180


def test_rag_test_dialog_sets_size_hint_on_items(qtbot: Any, fake_doc: DocumentModel) -> None:
    """Vérifie que chaque item de results_list reçoit un sizeHint non nul évitant l'écrasement visuel."""
    dlg = RAGTestDialog(fake_doc)
    qtbot.addWidget(dlg)

    fake_results = [
        {
            "chunk_id": 101,
            "chunk_index": 0,
            "content": "Premier extrait sur l'hippocampe et la consolidation mnésique.",
            "heading_path": "Lobe Temporal > Hippocampe",
            "page_number": 8,
            "score": 0.94,
            "relevance_pct": 95,
            "channel": "hybrid",
        },
        {
            "chunk_id": 102,
            "chunk_index": 1,
            "content": "Deuxième extrait sur l'amygdale et les réponses émotionnelles.",
            "heading_path": "Système Limbique > Amygdale",
            "page_number": 9,
            "score": 0.89,
            "relevance_pct": 89,
            "channel": "hybrid",
        },
        {
            "chunk_id": 103,
            "chunk_index": 2,
            "content": "Troisième extrait sur le thalamus et le relais sensoriel.",
            "heading_path": "Diencéphale > Thalamus",
            "page_number": 11,
            "score": 0.82,
            "relevance_pct": 82,
            "channel": "hybrid",
        },
    ]

    with patch(
        "ankiforge.ui.views.documents_view.dialogs.rag_test_dialog.RAGService.search",
        return_value=fake_results,
    ):
        dlg.search_input.setText("hippocampe amygdale")
        dlg._on_search()

    assert dlg.results_list.count() == 3

    for i in range(dlg.results_list.count()):
        item = dlg.results_list.item(i)
        assert item is not None
        widget = dlg.results_list.itemWidget(item)
        assert widget is not None
        # Le sizeHint de l'item doit être configuré et égal au sizeHint du widget
        assert item.sizeHint().isValid()
        assert item.sizeHint().height() >= 120
        assert item.sizeHint() == widget.sizeHint()
        # Le texte de l'item doit rester accessible
        assert "hippocampe" in item.text().lower() or "amygdale" in item.text().lower() or "thalamus" in item.text().lower()

    # Vérification géométrique de non-chevauchement vertical
    dlg.show()
    for i in range(dlg.results_list.count() - 1):
        rect_current = dlg.results_list.visualItemRect(dlg.results_list.item(i))
        rect_next = dlg.results_list.visualItemRect(dlg.results_list.item(i + 1))
        # Chaque item suivant doit débuter strictement à la fin du précédent (aucun chevauchement)
        assert rect_next.top() >= rect_current.bottom()
