"""Tests du worker d'extraction documentaire unitaire DocumentWorker."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ankiforge.services.parsing.marker_service import MarkerOptions
from ankiforge.services.workers.document_worker import DocumentWorker

pytestmark = pytest.mark.integration


def test_document_worker_relays_marker_options(qtbot) -> None:
    """Vérifie que DocumentWorker transmet fidèlement marker_options à DocumentParser."""
    options = MarkerOptions(page_range="0-2", force_ocr=True, device="cpu")
    worker = DocumentWorker("/tmp/cours_physique.pdf", marker_options=options)

    assert worker.marker_options == options

    with patch("ankiforge.services.workers.document_worker.DocumentParser") as mock_parser_cls:
        mock_parser = MagicMock()
        mock_parser.parse_document.return_value = "# Contenu extrait"
        mock_parser_cls.return_value = mock_parser

        with qtbot.waitSignal(worker.finished_signal, timeout=2000) as blocker:
            worker.start()

        assert blocker.args[0] == "cours_physique"
        assert blocker.args[1] == "# Contenu extrait"
        mock_parser.parse_document.assert_called_once_with(
            "/tmp/cours_physique.pdf",
            progress_callback=worker.log_signal.emit,
            check_cancel=worker.is_cancelled,
            marker_options=options,
        )


def test_document_worker_default_marker_options_none(qtbot) -> None:
    """Vérifie que marker_options est None par défaut et transmis tel quel."""
    worker = DocumentWorker("/tmp/cours_chimie.pdf")

    assert worker.marker_options is None

    with patch("ankiforge.services.workers.document_worker.DocumentParser") as mock_parser_cls:
        mock_parser = MagicMock()
        mock_parser.parse_document.return_value = "# Chimie"
        mock_parser_cls.return_value = mock_parser

        with qtbot.waitSignal(worker.finished_signal, timeout=2000):
            worker.start()

        mock_parser.parse_document.assert_called_once_with(
            "/tmp/cours_chimie.pdf",
            progress_callback=worker.log_signal.emit,
            check_cancel=worker.is_cancelled,
            marker_options=None,
        )
