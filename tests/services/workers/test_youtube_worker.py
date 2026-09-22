"""Tests unitaires pour YouTubeWorker (exécution, progression, annulation, gestion d'erreurs)."""

from unittest.mock import patch

import pytest

from ankiforge.services.parsing.yt_dlp_service import YtDlpUnavailableError
from ankiforge.services.workers.youtube_worker import YouTubeWorker

pytestmark = pytest.mark.integration


def test_youtube_worker_success(qtbot) -> None:
    worker = YouTubeWorker(url="https://youtu.be/ok123")

    progress_messages: list[str] = []
    worker.signals.progress.connect(progress_messages.append)

    expected_content = "# Titre\n\nContenu extrait"

    def mock_parse(url, ai_manager, progress_callback=None, check_cancel=None):
        if progress_callback:
            progress_callback("Étape 1...")
            progress_callback("Étape 2...")
        return expected_content

    with patch.object(worker.parser, "parse", side_effect=mock_parse), qtbot.waitSignal(worker.signals.finished, timeout=2000) as blocker:
        worker.run()

    assert blocker.args == [expected_content]
    assert len(progress_messages) >= 2


def test_youtube_worker_empty_result(qtbot) -> None:
    worker = YouTubeWorker(url="https://youtu.be/empty")

    with patch.object(worker.parser, "parse", return_value=""), qtbot.waitSignal(worker.signals.error, timeout=2000) as blocker:
        worker.run()

    assert "Impossible d'extraire" in blocker.args[0]


def test_youtube_worker_exception(qtbot) -> None:
    worker = YouTubeWorker(url="https://youtu.be/err")

    with patch.object(worker.parser, "parse", side_effect=YtDlpUnavailableError("yt-dlp absent")), qtbot.waitSignal(worker.signals.error, timeout=2000) as blocker:
        worker.run()

    assert "yt-dlp absent" in blocker.args[0]


def test_youtube_worker_cancel_before_run(qtbot) -> None:
    worker = YouTubeWorker(url="https://youtu.be/cancel_early")
    worker.cancel()

    with qtbot.waitSignal(worker.signals.cancelled, timeout=2000):
        worker.run()


def test_youtube_worker_cancel_during_run(qtbot) -> None:
    worker = YouTubeWorker(url="https://youtu.be/cancel_mid")

    def mock_parse(url, ai_manager, progress_callback=None, check_cancel=None):
        worker.cancel()
        return ""

    with patch.object(worker.parser, "parse", side_effect=mock_parse), qtbot.waitSignal(worker.signals.cancelled, timeout=2000):
        worker.run()
