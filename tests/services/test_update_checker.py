"""Tests unitaires pour le service UpdateCheckerWorker."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QSettings

from ankiforge.services.update_checker import (
    SETTINGS_KEY_CACHED_VERSION,
    SETTINGS_KEY_CHANNEL,
    SETTINGS_KEY_LAST_CHECK,
    UpdateCheckerWorker,
    UpdateInfo,
)


@pytest.fixture(autouse=True)
def clean_settings() -> Any:
    """Nettoie les paramètres QSettings de test."""
    settings = QSettings("AnkiForgeOrg", "AnkiForge")
    settings.remove(SETTINGS_KEY_LAST_CHECK)
    settings.remove(SETTINGS_KEY_CACHED_VERSION)
    settings.remove(SETTINGS_KEY_CHANNEL)
    yield
    settings.remove(SETTINGS_KEY_LAST_CHECK)
    settings.remove(SETTINGS_KEY_CACHED_VERSION)
    settings.remove(SETTINGS_KEY_CHANNEL)


def test_update_checker_detects_newer_version() -> None:
    """Vérifie qu'une version distante supérieure émet le signal update_available."""
    worker = UpdateCheckerWorker(current_version="1.0.5", channel="stable", force=True)

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "tag_name": "v1.1.0",
        "name": "AnkiForge 1.1.0",
        "body": "## Nouveautés\n- Système d'auto-update\n- Nouvelles icônes",
        "html_url": "https://github.com/Skyl9/AnkiForge/releases/tag/v1.1.0",
        "published_at": "2026-09-02T08:00:00Z",
        "prerelease": False,
    }

    received_updates: list[UpdateInfo] = []
    worker.signals.update_available.connect(lambda info: received_updates.append(info))

    with patch("requests.get", return_value=fake_response):
        worker.run()

    assert len(received_updates) == 1
    info = received_updates[0]
    assert info.version == "1.1.0"
    assert info.title == "AnkiForge 1.1.0"
    assert "Système d'auto-update" in info.release_notes
    assert info.html_url == "https://github.com/Skyl9/AnkiForge/releases/tag/v1.1.0"


def test_update_checker_no_update_when_same_or_older_version() -> None:
    """Vérifie qu'aucune mise à jour n'est signalée si la version distante est égale ou inférieure."""
    worker = UpdateCheckerWorker(current_version="1.0.5", channel="stable", force=True)

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "tag_name": "v1.0.5",
        "name": "AnkiForge 1.0.5",
        "body": "Release actuelle",
        "html_url": "https://github.com/Skyl9/AnkiForge/releases/tag/v1.0.5",
    }

    no_update_called = False

    def on_no_update(cur: str) -> None:
        nonlocal no_update_called
        no_update_called = True
        assert cur == "1.0.5"

    worker.signals.no_update.connect(on_no_update)

    with patch("requests.get", return_value=fake_response):
        worker.run()

    assert no_update_called is True


def test_update_checker_nightly_channel() -> None:
    """Vérifie que le canal Nightly interroge l'endpoint nightly et émet la mise à jour."""
    worker = UpdateCheckerWorker(current_version="1.0.5", channel="nightly", force=True)

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "tag_name": "nightly",
        "name": "AnkiForge Nightly Build",
        "body": "Nouveautés nightly",
        "html_url": "https://github.com/Skyl9/AnkiForge/releases/tag/nightly",
        "published_at": "2029-01-01T00:00:00Z",
        "prerelease": True,
    }

    received_updates: list[UpdateInfo] = []
    worker.signals.update_available.connect(lambda info: received_updates.append(info))

    with patch("requests.get", return_value=fake_response) as mock_get:
        worker.run()
        assert "tags/nightly" in mock_get.call_args[0][0]

    assert len(received_updates) == 1
    assert received_updates[0].channel == "nightly"


def test_update_checker_handles_network_error_gracefully() -> None:
    """Vérifie que les erreurs de connexion n'entraînent aucun crash et émettent check_failed."""
    worker = UpdateCheckerWorker(current_version="1.0.5", force=True)

    failed_messages: list[str] = []
    worker.signals.check_failed.connect(lambda msg: failed_messages.append(msg))

    with patch("requests.get", side_effect=Exception("Connection refused")):
        worker.run()

    assert len(failed_messages) == 1
    assert "Connection refused" in failed_messages[0]
