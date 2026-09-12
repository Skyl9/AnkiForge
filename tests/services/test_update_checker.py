"""Tests unitaires pour le service UpdateCheckerWorker."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ankiforge.services.update_checker import (
    SETTINGS_KEY_CACHED_METADATA,
    SETTINGS_KEY_CACHED_VERSION,
    SETTINGS_KEY_CHANNEL,
    SETTINGS_KEY_ETAG_NIGHTLY,
    SETTINGS_KEY_ETAG_STABLE,
    SETTINGS_KEY_LAST_CHECK,
    UpdateCheckerWorker,
    UpdateInfo,
)
from ankiforge.utils.environment import get_app_qsettings


@pytest.fixture(autouse=True)
def clean_settings() -> Any:
    """Nettoie les paramètres QSettings de test."""
    settings = get_app_qsettings()
    settings.remove(SETTINGS_KEY_LAST_CHECK)
    settings.remove(SETTINGS_KEY_CACHED_VERSION)
    settings.remove(SETTINGS_KEY_CHANNEL)
    settings.remove(SETTINGS_KEY_CACHED_METADATA)
    settings.remove(SETTINGS_KEY_ETAG_STABLE)
    settings.remove(SETTINGS_KEY_ETAG_NIGHTLY)
    yield
    settings.remove(SETTINGS_KEY_LAST_CHECK)
    settings.remove(SETTINGS_KEY_CACHED_VERSION)
    settings.remove(SETTINGS_KEY_CHANNEL)
    settings.remove(SETTINGS_KEY_CACHED_METADATA)
    settings.remove(SETTINGS_KEY_ETAG_STABLE)
    settings.remove(SETTINGS_KEY_ETAG_NIGHTLY)


def test_update_checker_detects_newer_version() -> None:
    """Vérifie qu'une version distante supérieure émet le signal update_available."""
    worker = UpdateCheckerWorker(current_version="1.0.5", channel="stable", force=True)

    fake_response = MagicMock()
    fake_response.status_code = 200
    # BUG 2 : L'endpoint /releases retourne TOUJOURS une liste JSON — le mock doit être une list.
    fake_response.json.return_value = [
        {
            "tag_name": "v1.1.0",
            "name": "AnkiForge 1.1.0",
            "body": "## Nouveautés\n- Système d'auto-update\n- Nouvelles icônes",
            "html_url": "https://github.com/Skyl9/AnkiForge/releases/tag/v1.1.0",
            "published_at": "2026-09-02T08:00:00Z",
            "prerelease": False,
            "draft": False,
        }
    ]

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
    fake_response.json.return_value = [
        {
            "tag_name": "v1.0.5",
            "name": "AnkiForge 1.0.5",
            "body": "Release actuelle",
            "html_url": "https://github.com/Skyl9/AnkiForge/releases/tag/v1.0.5",
            "prerelease": False,
            "draft": False,
        }
    ]

    no_update_called = False

    def on_no_update(cur: str) -> None:
        nonlocal no_update_called
        no_update_called = True
        assert cur == "1.0.5"

    worker.signals.no_update.connect(on_no_update)

    with patch("requests.get", return_value=fake_response):
        worker.run()

    assert no_update_called is True


def test_update_checker_ignores_release_older_than_current_1_1_5() -> None:
    """Une release v1.1.0 ne doit pas être proposée depuis une application v1.1.5."""
    worker = UpdateCheckerWorker(current_version="1.1.5", channel="stable", force=True)

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = [
        {
            "tag_name": "v1.1.0",
            "name": "AnkiForge 1.1.0",
            "prerelease": False,
            "draft": False,
        }
    ]

    received_updates: list[UpdateInfo] = []
    no_update_called: list[bool] = []
    worker.signals.update_available.connect(lambda info: received_updates.append(info))
    worker.signals.no_update.connect(lambda _: no_update_called.append(True))

    with patch("requests.get", return_value=fake_response):
        worker.run()

    assert received_updates == []
    assert no_update_called == [True]


def test_update_checker_uses_latest_stable_release() -> None:
    """La release stable proposée doit provenir de la version GitHub la plus récente."""
    worker = UpdateCheckerWorker(current_version="1.0.5", channel="stable", force=True)

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "tag_name": "v1.1.5",
        "name": "AnkiForge 1.1.5",
        "body": "Correctifs de production",
        "prerelease": False,
        "draft": False,
    }

    received_updates: list[UpdateInfo] = []
    worker.signals.update_available.connect(lambda info: received_updates.append(info))

    with patch("requests.get", return_value=fake_response) as mock_get:
        worker.run()

    assert mock_get.call_args.args[0].endswith("/releases/latest")
    assert [info.version for info in received_updates] == ["1.1.5"]


def test_update_checker_api_returns_non_list_uses_tags_fallback() -> None:
    """Vérifie qu'une réponse Releases invalide déclenche le fallback public des tags."""
    worker = UpdateCheckerWorker(current_version="1.0.5", channel="stable", force=True)

    fake_response = MagicMock()
    fake_response.status_code = 200
    # L'API GitHub peut retourner un objet JSON d'erreur avec un HTTP 200 dans certains cas limites
    fake_response.json.return_value = {"message": "API rate limit exceeded for ..."}

    no_update_called: list[bool] = []
    worker.signals.no_update.connect(lambda _: no_update_called.append(True))

    with patch("requests.get", return_value=fake_response):
        worker.run()

    assert len(no_update_called) == 1


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


def test_update_checker_nightly_no_false_alarm_when_build_date_missing() -> None:
    """BUG 3 : Vérifie que l'absence de build_date dans _version.py ne génère pas
    de fausse alerte de mise à jour nightly à chaque démarrage."""
    worker = UpdateCheckerWorker(current_version="1.0.5", channel="nightly", force=True)

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "tag_name": "nightly",
        "name": "AnkiForge Nightly",
        "body": "Nightly build",
        "html_url": "https://github.com/Skyl9/AnkiForge/releases/tag/nightly",
        "published_at": "2026-09-01T00:00:00Z",
        "prerelease": True,
    }

    received_updates: list[UpdateInfo] = []
    no_update_called: list[bool] = []
    worker.signals.update_available.connect(lambda info: received_updates.append(info))
    worker.signals.no_update.connect(lambda _: no_update_called.append(True))

    # Simulation d'un build avec build_date vide (build incomplet / _version.py manquant)
    from ankiforge.version import AppVersionInfo

    dummy_info = AppVersionInfo(
        version="1.0.5",
        commit_hash="abc123",
        build_date="",  # build_date absent
        build_channel="nightly",
        platform_str="macOS arm64",
        is_standalone=True,
    )

    with (
        patch("requests.get", return_value=fake_response),
        patch("ankiforge.services.update_checker.VERSION_INFO", dummy_info),
    ):
        worker.run()

    assert len(received_updates) == 0, "Aucune alerte ne doit être émise si build_date est vide"
    assert len(no_update_called) == 1, "no_update doit être émis de façon conservatrice"


def test_update_checker_handles_network_error_gracefully() -> None:
    """Vérifie que les erreurs de connexion n'entraînent aucun crash et émettent check_failed."""
    worker = UpdateCheckerWorker(current_version="1.0.5", force=True)

    failed_messages: list[str] = []
    worker.signals.check_failed.connect(lambda msg: failed_messages.append(msg))

    with patch("requests.get", side_effect=Exception("Connection refused")):
        worker.run()

    assert len(failed_messages) == 1
    assert "Connection refused" in failed_messages[0]


def test_semver_tuple_and_comparison_logic() -> None:
    """Vérifie l'exactitude mathématique de parse_semver_tuple et is_version_strictly_greater."""
    from ankiforge.services.update_checker import is_version_strictly_greater, parse_semver_tuple

    assert parse_semver_tuple("v1.1.0") == (1, 1, 0)
    assert parse_semver_tuple("1.1.0") == (1, 1, 0)
    assert parse_semver_tuple("V2.4.12") == (2, 4, 12)
    assert parse_semver_tuple("invalid") is None

    # Patch supérieur
    assert is_version_strictly_greater("v1.0.6", "v1.0.5") is True
    assert is_version_strictly_greater("1.0.6", "1.0.5") is True
    # Mineure supérieure
    assert is_version_strictly_greater("v1.1.0", "v1.0.6") is True
    # Majeure supérieure
    assert is_version_strictly_greater("v2.0.0", "v1.99.99") is True
    # Égalité
    assert is_version_strictly_greater("v1.1.0", "v1.1.0") is False
    assert is_version_strictly_greater("1.1.0", "v1.1.0") is False
    # Inférieure
    assert is_version_strictly_greater("v1.0.5", "v1.1.0") is False


def test_update_checker_selects_highest_semver_from_releases_list() -> None:
    """Vérifie que même si un patch a été publié plus récemment qu'une mineure, la version max absolue est choisie."""
    worker = UpdateCheckerWorker(current_version="v1.0.5", channel="stable", force=True)

    # v1.0.6 a été publié chronologiquement après v1.1.0 (ex: premier de la liste)
    fake_releases = [
        {
            "tag_name": "v1.0.6",
            "name": "AnkiForge 1.0.6 (Patch récent)",
            "published_at": "2026-09-04T12:00:00Z",
            "draft": False,
            "prerelease": False,
        },
        {
            "tag_name": "v1.1.0",
            "name": "AnkiForge 1.1.0 (Version supérieure)",
            "published_at": "2026-09-01T12:00:00Z",
            "draft": False,
            "prerelease": False,
        },
        {
            "tag_name": "v1.0.5",
            "name": "AnkiForge 1.0.5",
            "published_at": "2026-08-30T12:00:00Z",
            "draft": False,
            "prerelease": False,
        },
    ]

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = fake_releases

    received_updates: list[UpdateInfo] = []
    worker.signals.update_available.connect(lambda info: received_updates.append(info))

    with patch("requests.get", return_value=fake_response):
        worker.run()

    assert len(received_updates) == 1
    # La version sélectionnée doit être 1.1.0 (et non 1.0.6)
    assert received_updates[0].version == "1.1.0"
    assert received_updates[0].title == "AnkiForge 1.1.0 (Version supérieure)"


def test_update_checker_handles_rate_limit_403_with_tags_fallback() -> None:
    """Vérifie le fallback tags lorsqu'un quota d'API GitHub est dépassé."""
    worker = UpdateCheckerWorker(current_version="v1.0.5", channel="stable", force=True)

    rate_limited = MagicMock(status_code=403)
    tags_response = MagicMock(status_code=200)
    tags_response.json.return_value = [{"name": "v1.1.0"}]
    received_updates: list[UpdateInfo] = []
    worker.signals.update_available.connect(lambda info: received_updates.append(info))

    with patch("requests.get", side_effect=[rate_limited, tags_response]):
        worker.run()

    assert len(received_updates) == 1
    assert received_updates[0].version == "1.1.0"


# ── Tests get_cached_update_info ───────────────────────────────────────────────


def test_get_cached_update_info_returns_none_when_no_cache() -> None:
    """Vérifie que get_cached_update_info retourne None quand le cache QSettings est vide."""
    from ankiforge.services.update_checker import get_cached_update_info

    # get_app_qsettings est importée localement dans get_cached_update_info — on la patche à sa source
    with patch("ankiforge.utils.environment.get_app_qsettings") as mock_settings:
        mock_s = MagicMock()
        mock_s.value.side_effect = lambda key, default="": default
        mock_settings.return_value = mock_s

        result = get_cached_update_info()
        assert result is None


def test_get_cached_update_info_returns_none_when_cache_equals_current() -> None:
    """Vérifie que get_cached_update_info retourne None si la version cachée = version installée."""
    from ankiforge.services.update_checker import get_cached_update_info
    from ankiforge.version import AppVersionInfo

    dummy_version = AppVersionInfo(
        version="1.0.5",
        commit_hash="abc",
        build_date="",
        build_channel="stable",
        platform_str="macOS arm64",
        is_standalone=False,
    )

    with (
        patch("ankiforge.utils.environment.get_app_qsettings") as mock_settings,
        patch("ankiforge.services.update_checker.VERSION_INFO", dummy_version),
    ):
        mock_s = MagicMock()
        mock_s.value.side_effect = lambda key, default="": {"updates/cached_latest_version": "1.0.5"}.get(key, default)
        mock_settings.return_value = mock_s

        result = get_cached_update_info()
        assert result is None


def test_get_cached_update_info_returns_update_info_when_newer_cached() -> None:
    """Vérifie que get_cached_update_info retourne un UpdateInfo valide si version cachée > version installée."""
    from ankiforge.services.update_checker import get_cached_update_info
    from ankiforge.version import AppVersionInfo

    dummy_version = AppVersionInfo(
        version="1.0.5",
        commit_hash="abc",
        build_date="",
        build_channel="stable",
        platform_str="macOS arm64",
        is_standalone=False,
    )

    with (
        patch("ankiforge.utils.environment.get_app_qsettings") as mock_settings,
        patch("ankiforge.services.update_checker.VERSION_INFO", dummy_version),
    ):
        cache = {
            "updates/cached_latest_version": "1.1.0",
            "updates/cached_latest_channel": "stable",
        }
        mock_s = MagicMock()
        mock_s.value.side_effect = lambda key, default="": cache.get(key, default)
        mock_settings.return_value = mock_s

        result = get_cached_update_info()
        assert result is not None
        assert result.version == "1.1.0"
        assert result.channel == "stable"
        assert result.assets == []  # Vides — assets récupérés par le worker HTTP
        assert "github.com" in result.html_url


def test_update_checker_304_updates_last_check_timestamp() -> None:
    """Vérifie qu'une réponse HTTP 304 met bien à jour le timestamp de dernière vérification."""
    worker = UpdateCheckerWorker(current_version="1.0.5", channel="stable", force=False)

    fake_response = MagicMock()
    fake_response.status_code = 304

    settings = get_app_qsettings()
    settings.setValue(SETTINGS_KEY_ETAG_STABLE, 'W/"test-etag"')
    settings.remove(SETTINGS_KEY_LAST_CHECK)

    with patch("requests.get", return_value=fake_response):
        worker.run()

    last_check = settings.value(SETTINGS_KEY_LAST_CHECK)
    assert last_check is not None
    assert int(str(last_check)) > 0


def test_update_checker_unexpected_exception_emits_check_failed() -> None:
    """Vérifie qu'une exception inattendue émet check_failed."""
    worker = UpdateCheckerWorker(current_version="1.0.5", channel="stable", force=True)

    failed_msg = ""

    def on_failed(msg: str) -> None:
        nonlocal failed_msg
        failed_msg = msg

    worker.signals.check_failed.connect(on_failed)

    with patch("requests.get", side_effect=RuntimeError("Erreur réseau critique inattendue")):
        worker.run()

    assert "Erreur réseau critique inattendue" in failed_msg
