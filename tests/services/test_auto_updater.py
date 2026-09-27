"""Tests unitaires pour le service d'auto-mise à jour durci et sécurisé."""

import hashlib
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ankiforge.services.auto_updater import (
    MAX_DOWNLOAD_SIZE_BYTES,
    UpdateDownloaderWorker,
    _validate_download_url,
    apply_update_and_restart,
    find_asset_for_current_platform,
    find_manifest_assets,
    is_standalone_app,
    validate_update_file_confinement,
)

pytestmark = pytest.mark.unit


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

    with (
        patch("ankiforge.services.auto_updater.get_updates_storage_dir", return_value=tmp_path),
        pytest.raises(ValueError, match="est un lien symbolique non autorisé"),
    ):
        validate_update_file_confinement(symlink_file)


# ── Tests ISSUE 6 : Validation URL (HTTPS + domaine de confiance) ──────────────


def test_validate_download_url_accepts_trusted_github_domains() -> None:
    """ISSUE 6 : Vérifie que les domaines GitHub de confiance sont acceptés."""
    _validate_download_url("https://objects.githubusercontent.com/github-production-release-asset/AnkiForge.dmg")
    _validate_download_url("https://github.com/Skyl9/AnkiForge/releases/download/v1.1.0/AnkiForge.dmg")
    _validate_download_url("https://codeload.github.com/Skyl9/AnkiForge/archive/refs/tags/v1.1.0.zip")


def test_validate_download_url_rejects_non_https() -> None:
    """ISSUE 6 : Vérifie que les URLs non-HTTPS sont rejetées."""
    with pytest.raises(ValueError, match="schéma"):
        _validate_download_url("http://objects.githubusercontent.com/AnkiForge.dmg")
    with pytest.raises(ValueError, match="schéma"):
        _validate_download_url("file:///etc/passwd")
    with pytest.raises(ValueError, match="schéma"):
        _validate_download_url("ftp://ftp.example.com/AnkiForge.dmg")


def test_validate_download_url_rejects_untrusted_domain() -> None:
    """ISSUE 6 : Vérifie que les domaines hors liste de confiance sont rejetés."""
    with pytest.raises(ValueError, match="domaine"):
        _validate_download_url("https://evil.example.com/AnkiForge.dmg")
    with pytest.raises(ValueError, match="domaine"):
        _validate_download_url("https://github.com.evil.com/AnkiForge.dmg")


# ── Tests ISSUE 7 : Limite de taille du téléchargement ────────────────────────


def test_downloader_rejects_oversized_content_length(tmp_path: Path) -> None:
    """ISSUE 7 : Vérifie que le downloader refuse les téléchargements dépassant le plafond (Content-Length)."""
    worker = UpdateDownloaderWorker(
        "https://objects.githubusercontent.com/AnkiForge.dmg",
        "test.dmg",
        require_signature=False,
    )

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-length": str(MAX_DOWNLOAD_SIZE_BYTES + 1)}
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = None

    error_msgs: list[str] = []
    worker.signals.download_error.connect(lambda msg: error_msgs.append(msg))

    with (
        patch("requests.get", return_value=fake_response),
        patch("ankiforge.services.auto_updater.get_updates_storage_dir", return_value=tmp_path),
    ):
        worker.run()

    assert len(error_msgs) == 1
    assert "plafond" in error_msgs[0]


def test_downloader_worker_streams_and_computes_sha256(tmp_path: Path) -> None:
    """Vérifie que le worker de téléchargement diffuse les blocs et calcule le bon hash SHA-256."""
    fake_content = b"AnkiForge Binary Update Content 1234567890"
    expected_sha256 = hashlib.sha256(fake_content).hexdigest()

    # ISSUE 6 : URL avec domaine GitHub de confiance
    worker = UpdateDownloaderWorker(
        "https://objects.githubusercontent.com/AnkiForge.bin",
        "test_update.bin",
        require_signature=False,
    )

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


def test_find_manifest_assets() -> None:
    """Vérifie l'identification correcte du manifeste checksums.txt et de sa signature .sig."""
    assets: list[dict[str, Any]] = [
        {"name": "AnkiForge-macos-arm64.dmg", "browser_download_url": "https://example.com/app.dmg"},
        {"name": "checksums.txt", "browser_download_url": "https://example.com/checksums.txt"},
        {"name": "checksums.txt.sig", "browser_download_url": "https://example.com/checksums.txt.sig"},
    ]
    chk, sig = find_manifest_assets(assets)
    assert chk is not None and chk["name"] == "checksums.txt"
    assert sig is not None and sig["name"] == "checksums.txt.sig"


def test_downloader_worker_verifies_valid_signature_and_sha256(tmp_path: Path) -> None:
    """Vérifie la chaîne complète de téléchargement avec signature Ed25519 valide et hash conforme."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv_key = Ed25519PrivateKey.generate()
    pub_hex = priv_key.public_key().public_bytes_raw().hex()

    binary_content = b"Official Valid Release Binary"
    binary_sha256 = hashlib.sha256(binary_content).hexdigest()
    binary_name = "AnkiForge-macos-arm64.dmg"

    manifest_text = f"{binary_sha256}  {binary_name}\n"
    manifest_bytes = manifest_text.encode("utf-8")
    signature_bytes = priv_key.sign(manifest_bytes)

    worker = UpdateDownloaderWorker(
        download_url="https://objects.githubusercontent.com/AnkiForge-macos-arm64.dmg",
        filename=binary_name,
        checksums_url="https://objects.githubusercontent.com/checksums.txt",
        signature_url="https://objects.githubusercontent.com/checksums.txt.sig",
        require_signature=True,
        trusted_public_keys=(pub_hex,),
    )

    def fake_requests_get(url: str, **kwargs: Any) -> Any:
        resp = MagicMock()
        resp.status_code = 200
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = None

        if "checksums.txt.sig" in url:
            resp.content = signature_bytes
        elif "checksums.txt" in url:
            resp.content = manifest_bytes
        else:
            resp.headers = {"content-length": str(len(binary_content))}
            resp.iter_content.return_value = [binary_content]
        return resp

    completed: list[tuple[Any, str]] = []
    errors: list[str] = []
    worker.signals.download_complete.connect(lambda path, sha: completed.append((path, sha)))
    worker.signals.download_error.connect(lambda err: errors.append(err))

    with (
        patch("requests.get", side_effect=fake_requests_get),
        patch("ankiforge.services.auto_updater.get_updates_storage_dir", return_value=tmp_path),
    ):
        worker.run()

    assert len(errors) == 0
    assert len(completed) == 1
    dest, sha = completed[0]
    assert sha == binary_sha256
    assert dest.exists()
    assert dest.read_bytes() == binary_content


def test_downloader_worker_fail_closed_on_invalid_signature(tmp_path: Path) -> None:
    """Vérifie le rejet immédiat (Fail-Closed) si la signature Ed25519 est invalide."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv_key = Ed25519PrivateKey.generate()
    other_key = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()

    manifest_bytes = b"bad manifest content\n"
    signature_bytes = priv_key.sign(manifest_bytes)

    worker = UpdateDownloaderWorker(
        download_url="https://objects.githubusercontent.com/AnkiForge.dmg",
        filename="AnkiForge.dmg",
        checksums_url="https://objects.githubusercontent.com/checksums.txt",
        signature_url="https://objects.githubusercontent.com/checksums.txt.sig",
        require_signature=True,
        trusted_public_keys=(other_key,),  # Clé différente -> invalide
    )

    def fake_requests_get(url: str, **kwargs: Any) -> Any:
        resp = MagicMock()
        resp.status_code = 200
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = None
        if "checksums.txt.sig" in url:
            resp.content = signature_bytes
        else:
            resp.content = manifest_bytes
        return resp

    errors: list[str] = []
    worker.signals.download_error.connect(lambda err: errors.append(err))

    with (
        patch("requests.get", side_effect=fake_requests_get),
        patch("ankiforge.services.auto_updater.get_updates_storage_dir", return_value=tmp_path),
    ):
        worker.run()

    assert len(errors) == 1
    assert "Échec de validation cryptographique" in errors[0]


def test_downloader_worker_fail_closed_on_missing_signature_files(tmp_path: Path) -> None:
    """Vérifie le rejet Fail-Closed si le manifeste ou la signature est absent."""
    worker = UpdateDownloaderWorker(
        download_url="https://objects.githubusercontent.com/AnkiForge.dmg",
        filename="AnkiForge.dmg",
        checksums_url=None,  # Pas de manifeste
        signature_url=None,
        require_signature=True,
    )

    errors: list[str] = []
    worker.signals.download_error.connect(lambda err: errors.append(err))

    with patch("ankiforge.services.auto_updater.get_updates_storage_dir", return_value=tmp_path):
        worker.run()

    assert len(errors) == 1
    assert "manquant pour cette release" in errors[0]


def test_downloader_worker_fail_closed_on_sha256_mismatch_and_purges_file(tmp_path: Path) -> None:
    """Vérifie que si l'empreinte SHA-256 du binaire ne correspond pas au manifeste, le fichier téléchargé est purgé."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv_key = Ed25519PrivateKey.generate()
    pub_hex = priv_key.public_key().public_bytes_raw().hex()

    binary_name = "AnkiForge.dmg"
    manifest_text = f"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  {binary_name}\n"
    manifest_bytes = manifest_text.encode("utf-8")
    signature_bytes = priv_key.sign(manifest_bytes)

    # Contenu binaire réel dont le hash est DIFFÉRENT de e3b0c442...
    real_binary_content = b"Malicious or Corrupted Binary Content"

    worker = UpdateDownloaderWorker(
        download_url="https://objects.githubusercontent.com/AnkiForge.dmg",
        filename=binary_name,
        checksums_url="https://objects.githubusercontent.com/checksums.txt",
        signature_url="https://objects.githubusercontent.com/checksums.txt.sig",
        require_signature=True,
        trusted_public_keys=(pub_hex,),
    )

    def fake_requests_get(url: str, **kwargs: Any) -> Any:
        resp = MagicMock()
        resp.status_code = 200
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = None
        if "checksums.txt.sig" in url:
            resp.content = signature_bytes
        elif "checksums.txt" in url:
            resp.content = manifest_bytes
        else:
            resp.headers = {"content-length": str(len(real_binary_content))}
            resp.iter_content.return_value = [real_binary_content]
        return resp

    errors: list[str] = []
    worker.signals.download_error.connect(lambda err: errors.append(err))

    with (
        patch("requests.get", side_effect=fake_requests_get),
        patch("ankiforge.services.auto_updater.get_updates_storage_dir", return_value=tmp_path),
    ):
        worker.run()

    assert len(errors) == 1
    assert "Intégrité compromise" in errors[0]
    # Vérification primordiale : le fichier a été purgé du disque !
    downloaded_target = tmp_path / binary_name
    assert not downloaded_target.exists()


def test_apply_update_and_restart_dev_mode_safety(tmp_path: Path) -> None:
    """Vérifie que le mode développement est strictement préservé sans altération système."""
    with patch("ankiforge.services.auto_updater.get_updates_storage_dir", return_value=tmp_path):
        dummy_file = tmp_path / "dummy_update.bin"
        dummy_file.write_bytes(b"content")

        # En mode dev (non standalone), apply_update_and_restart doit retourner True avec un message explicite
        success, msg = apply_update_and_restart(dummy_file)
        assert success is True
        assert "Mode Développement" in msg
