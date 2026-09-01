"""Tests unitaires pour le service d'auto-mise à jour durci et sécurisé."""

import hashlib
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ankiforge.services.auto_updater import (
    UpdateDownloaderWorker,
    apply_update_and_restart,
    find_asset_for_current_platform,
    is_standalone_app,
    validate_update_file_confinement,
)


def test_is_standalone_app_returns_false_in_dev_env() -> None:
    """Vérifie que l'environnement de développement/tests est détecté comme non-standalone."""
    assert is_standalone_app() is False


def test_find_asset_for_current_platform() -> None:
    """Vérifie la sélection de l'asset pertinent selon les mots-clés de plateforme."""
    fake_assets: list[dict[str, Any]] = [
        {"name": "checksums.txt", "browser_download_url": "https://example.com/checksums.txt"},
        {"name": "AnkiForge-x86_64.AppImage", "browser_download_url": "https://example.com/appimage"},
        {"name": "AnkiForge-macos-arm64.dmg", "browser_download_url": "https://example.com/dmg"},
        {"name": "AnkiForge-Setup-x64.exe", "browser_download_url": "https://example.com/exe"},
    ]

    asset = find_asset_for_current_platform(fake_assets)
    assert asset is not None
    assert "name" in asset


def test_validate_update_file_confinement_success(tmp_path: Path) -> None:
    """Vérifie qu'un fichier légitime situé dans le dossier de mises à jour est accepté."""
    with patch("ankiforge.services.auto_updater.get_updates_storage_dir", return_value=tmp_path):
        valid_file = tmp_path / "AnkiForge-Update.dmg"
        valid_file.write_bytes(b"test binary content")

        result = validate_update_file_confinement(valid_file)
        assert result == valid_file.resolve()


def test_validate_update_file_confinement_rejects_path_traversal(tmp_path: Path) -> None:
    """Vérifie qu'un fichier en dehors du dossier de mises à jour est rejeté."""
    trusted_dir = tmp_path / "trusted_updates"
    trusted_dir.mkdir()
    outside_dir = tmp_path / "outside_directory"
    outside_dir.mkdir()

    outside_file = outside_dir / "malicious.bin"
    outside_file.write_bytes(b"malicious")

    with (
        patch("ankiforge.services.auto_updater.get_updates_storage_dir", return_value=trusted_dir),
        pytest.raises(ValueError, match="Alerte de sécurité : Le fichier .* est situé hors du répertoire sécurisé"),
    ):
        validate_update_file_confinement(outside_file)


def test_validate_update_file_confinement_rejects_symlink(tmp_path: Path) -> None:
    """Vérifie que les liens symboliques sont catégoriquement rejetés."""
    target_file = tmp_path / "real_file.bin"
    target_file.write_bytes(b"target")

    symlink_file = tmp_path / "symlink_file.bin"
    try:
        os.symlink(target_file, symlink_file)
    except OSError:
        pytest.skip("Les liens symboliques ne sont pas supportés sur ce système.")

    with patch("ankiforge.services.auto_updater.get_updates_storage_dir", return_value=tmp_path), pytest.raises(ValueError, match="est un lien symbolique non autorisé"):
        validate_update_file_confinement(symlink_file)


def test_downloader_worker_streams_and_computes_sha256(tmp_path: Path) -> None:
    """Vérifie que le worker de téléchargement diffuse les blocs et calcule le bon hash SHA-256."""
    fake_content = b"AnkiForge Binary Update Content 1234567890"
    expected_sha256 = hashlib.sha256(fake_content).hexdigest()

    worker = UpdateDownloaderWorker("https://fake.url/binary", "test_update.bin")

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-length": str(len(fake_content))}
    fake_response.iter_content.return_value = [fake_content[:15], fake_content[15:]]
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = None

    progress_events: list[int] = []
    completed_result: list[tuple[Any, str]] = []

    worker.signals.progress.connect(lambda pct, _down, _tot: progress_events.append(pct))
    worker.signals.download_complete.connect(lambda path, sha: completed_result.append((path, sha)))

    with (
        patch("requests.get", return_value=fake_response),
        patch("ankiforge.services.auto_updater.get_updates_storage_dir", return_value=tmp_path),
    ):
        worker.run()

    assert len(completed_result) == 1
    dest_path, computed_sha = completed_result[0]
    assert computed_sha == expected_sha256
    assert dest_path.exists()
    assert dest_path.read_bytes() == fake_content
    assert len(progress_events) >= 1


def test_apply_update_and_restart_dev_mode_safety(tmp_path: Path) -> None:
    """Vérifie que le mode développement est strictement préservé sans altération système."""
    with patch("ankiforge.services.auto_updater.get_updates_storage_dir", return_value=tmp_path):
        dummy_file = tmp_path / "dummy_update.bin"
        dummy_file.write_bytes(b"content")

        # En mode dev (non standalone), apply_update_and_restart doit retourner True avec un message explicite
        success, msg = apply_update_and_restart(dummy_file)
        assert success is True
        assert "Mode Développement" in msg
