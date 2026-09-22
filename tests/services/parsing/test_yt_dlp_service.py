"""Tests unitaires pour YtDlpService (détection, exécution, téléchargement audio, annulation)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ankiforge.services.parsing.yt_dlp_service import YtDlpService, YtDlpUnavailableError

pytestmark = pytest.mark.unit


def test_ytdlp_unavailable_error_message() -> None:
    err = YtDlpUnavailableError()
    assert "yt-dlp est introuvable" in str(err)
    assert "uv add yt-dlp" in str(err)


def test_is_available_with_executable(tmp_path: Path) -> None:
    fake_exe = tmp_path / "yt-dlp"
    fake_exe.write_text("#!/bin/sh\necho yt-dlp")
    fake_exe.chmod(0o755)

    with patch.object(YtDlpService, "get_executable", return_value=fake_exe):
        assert YtDlpService.is_available() is True


def test_is_available_with_python_module() -> None:
    with patch.object(YtDlpService, "get_executable", return_value=None), patch("importlib.util.find_spec", return_value=MagicMock()):
        assert YtDlpService.is_available() is True


def test_is_available_none() -> None:
    with patch.object(YtDlpService, "get_executable", return_value=None), patch("importlib.util.find_spec", return_value=None):
        assert YtDlpService.is_available() is False


def test_download_audio_raises_when_unavailable(tmp_path: Path) -> None:
    with patch.object(YtDlpService, "get_executable", return_value=None), patch("importlib.util.find_spec", return_value=None):
        with pytest.raises(YtDlpUnavailableError) as exc:
            YtDlpService.download_audio("https://youtu.be/123", tmp_path)
        assert "yt-dlp est introuvable" in str(exc.value)


def test_download_audio_cancellation_before_start(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError) as exc:
        YtDlpService.download_audio(
            "https://youtu.be/123",
            tmp_path,
            check_cancel=lambda: True,
        )
    assert "annulé avant le démarrage" in str(exc.value)


def test_download_audio_via_subprocess_success(tmp_path: Path) -> None:
    fake_exe = tmp_path / "yt-dlp"
    fake_exe.touch()

    def side_effect_popen(cmd, **kwargs):
        # Crée un faux fichier audio dans le dossier de sortie
        out_file = tmp_path / "mock_vid.m4a"
        out_file.write_bytes(b"fake audio bytes")
        mock_proc = MagicMock()
        mock_proc.stdout = ["[download] 100% of 5.00MiB in 00:01\n"]
        mock_proc.wait.return_value = 0
        return mock_proc

    progress_messages: list[str] = []

    with patch.object(YtDlpService, "get_executable", return_value=fake_exe), patch("subprocess.Popen", side_effect=side_effect_popen) as mock_popen:
        res = YtDlpService.download_audio(
            "https://youtu.be/mock123",
            tmp_path,
            progress_callback=progress_messages.append,
        )

    assert res.exists()
    assert res.name == "mock_vid.m4a"
    assert mock_popen.called
    called_cmd = mock_popen.call_args[0][0]
    assert "-f" in called_cmd
    assert "ba[ext=m4a]/ba/b" in called_cmd
    assert any("[download]" in msg for msg in progress_messages)


def test_download_audio_subprocess_failure(tmp_path: Path) -> None:
    fake_exe = tmp_path / "yt-dlp"
    fake_exe.touch()

    mock_proc = MagicMock()
    mock_proc.stdout = ["ERROR: Video unavailable\n"]
    mock_proc.wait.return_value = 1
    mock_proc.poll.return_value = 1

    with patch.object(YtDlpService, "get_executable", return_value=fake_exe), patch("subprocess.Popen", return_value=mock_proc):
        with pytest.raises(RuntimeError) as exc:
            YtDlpService.download_audio("https://youtu.be/error", tmp_path)
        assert "yt-dlp a échoué avec le code d'erreur 1" in str(exc.value)


def test_download_audio_subprocess_cancellation_during_run(tmp_path: Path) -> None:
    fake_exe = tmp_path / "yt-dlp"
    fake_exe.touch()

    mock_proc = MagicMock()
    # Simule plusieurs lignes de sortie, l'annulation intervient au cours du stream
    mock_proc.stdout = ["[download] 10%\n", "[download] 20%\n"]
    mock_proc.poll.return_value = None

    cancel_counter = 0

    def should_cancel() -> bool:
        nonlocal cancel_counter
        cancel_counter += 1
        return cancel_counter >= 2

    with patch.object(YtDlpService, "get_executable", return_value=fake_exe), patch("subprocess.Popen", return_value=mock_proc):
        with pytest.raises(RuntimeError) as exc:
            YtDlpService.download_audio("https://youtu.be/cancel", tmp_path, check_cancel=should_cancel)
        assert "annulé par l'utilisateur" in str(exc.value)
        assert mock_proc.terminate.called
