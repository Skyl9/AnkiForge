"""Service asynchrone de vérification des mises à jour d'AnkiForge via GitHub Releases API."""

from __future__ import annotations

import datetime
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import requests
from packaging import version
from PySide6.QtCore import QObject, QRunnable, Signal

from ankiforge.version import VERSION_INFO

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com/repos/Skyl9/AnkiForge/releases"
GITHUB_RELEASES_LIST_URL = f"{GITHUB_API_BASE}?per_page=100"
GITHUB_LATEST_URL = f"{GITHUB_API_BASE}/latest"
GITHUB_NIGHTLY_URL = f"{GITHUB_API_BASE}/tags/nightly"
GITHUB_TAGS_URL = "https://api.github.com/repos/Skyl9/AnkiForge/tags?per_page=30"

SETTINGS_KEY_LAST_CHECK = "updates/last_check_timestamp"
SETTINGS_KEY_CACHED_VERSION = "updates/cached_latest_version"
SETTINGS_KEY_CACHED_CHANNEL = "updates/cached_latest_channel"
SETTINGS_KEY_CACHED_METADATA = "updates/cached_latest_metadata"
SETTINGS_KEY_ETAG_STABLE = "updates/etag/stable"
SETTINGS_KEY_ETAG_NIGHTLY = "updates/etag/nightly"
SETTINGS_KEY_CHANNEL = "updates/channel"
CHECK_INTERVAL_SECONDS = 86400  # 24 heures


def parse_semver_tuple(version_str: str) -> tuple[int, int, int] | None:
    """Extrait (majeure, mineure, patch) selon la spécification vx.x.x ou x.x.x."""
    cleaned = version_str.strip().lstrip("vV").strip()
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:$|[-+])", cleaned)
    if match:
        return (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return None


def is_version_strictly_greater(remote: str, current: str) -> bool:
    """Vérifie si la version distante est strictement supérieure à la version locale selon SemVer vx.x.x."""
    try:
        r = remote.strip().lstrip("vV").strip()
        c = current.strip().lstrip("vV").strip()
        return version.Version(r) > version.Version(c)
    except version.InvalidVersion:
        return False


def _parse_stable_version(raw_tag: str) -> version.Version | None:
    """Parse une version stable et rejette explicitement les pré-releases."""
    try:
        parsed = version.Version(raw_tag.strip().lstrip("vV"))
    except version.InvalidVersion:
        return None
    return None if parsed.is_prerelease else parsed


@dataclass
class UpdateInfo:
    """Informations sur une nouvelle mise à jour disponible."""

    version: str
    title: str
    release_notes: str
    html_url: str
    published_at: str
    channel: str = "stable"
    is_prerelease: bool = False
    assets: list[dict[str, Any]] = field(default_factory=list)


def get_cached_update_info() -> UpdateInfo | None:
    """Lit instantanément le cache QSettings pour restituer la dernière mise à jour connue.

    Aucun appel réseau — appelé au démarrage pour afficher immédiatement le badge
    si une mise à jour avait déjà été détectée lors d'une session précédente.

    Returns:
        UpdateInfo si la version en cache est strictement supérieure à la version installée,
        None sinon (application à jour ou cache vide).
    """
    from ankiforge.utils.environment import get_app_qsettings

    settings = get_app_qsettings()
    cached_version = str(settings.value(SETTINGS_KEY_CACHED_VERSION, "")).strip().lstrip("vV")
    current_version = VERSION_INFO.version.strip().lstrip("vV")

    cached_channel = str(settings.value(SETTINGS_KEY_CACHED_CHANNEL, "stable"))
    metadata_raw = str(settings.value(SETTINGS_KEY_CACHED_METADATA, ""))
    try:
        metadata = json.loads(metadata_raw) if metadata_raw else {}
    except json.JSONDecodeError:
        metadata = {}
    if cached_channel == "nightly":
        published_at = str(metadata.get("published_at", ""))
        if not published_at or not VERSION_INFO.build_date:
            return None
        try:
            if datetime.datetime.fromisoformat(published_at.replace("Z", "+00:00")) <= datetime.datetime.fromisoformat(VERSION_INFO.build_date.replace("Z", "+00:00")):
                return None
        except ValueError:
            return None
    elif not cached_version or not is_version_strictly_greater(cached_version, current_version):
        return None
    html_url = str(metadata.get("html_url", f"https://github.com/Skyl9/AnkiForge/releases/tag/v{cached_version}"))

    logger.debug(
        "Cache de mise à jour restauré : v%s [%s] (Actuelle : v%s)",
        cached_version,
        cached_channel,
        current_version,
    )
    return UpdateInfo(
        version=cached_version,
        title=str(metadata.get("title", f"AnkiForge v{cached_version}")),
        release_notes=str(metadata.get("release_notes", "Une nouvelle version d'AnkiForge est disponible.")),
        html_url=html_url,
        published_at=str(metadata.get("published_at", "")),
        channel=cached_channel,
        is_prerelease=bool(metadata.get("is_prerelease", cached_channel == "nightly")),
        assets=list(metadata.get("assets", [])),
    )


class UpdateCheckerSignals(QObject):
    """Signaux Qt émis par le worker de vérification."""

    update_available = Signal(object)  # UpdateInfo
    no_update = Signal(str)  # current_version
    check_failed = Signal(str)


class UpdateCheckerWorker(QRunnable):
    """Worker QRunnable exécuté en arrière-plan dans QThreadPool pour interroger l'API GitHub."""

    def __init__(
        self,
        current_version: str | None = None,
        channel: str | None = None,
        force: bool = False,
    ) -> None:
        super().__init__()
        self.current_version = (current_version or VERSION_INFO.version).strip().lstrip("vV")
        self.channel = channel
        self.force = force
        self.signals = UpdateCheckerSignals()

    def run(self) -> None:
        """Exécute la vérification HTTP non-bloquante."""
        from ankiforge.utils.environment import get_app_qsettings, is_development

        if is_development() and not self.force:
            logger.debug("[DEV] Vérification des mises à jour désactivée en mode Développement.")
            self.signals.no_update.emit(self.current_version)
            return

        settings = get_app_qsettings()

        # Résolution du canal actif (Paramètres utilisateur ou métadonnées de build)
        active_channel = self.channel or str(settings.value(SETTINGS_KEY_CHANNEL, VERSION_INFO.build_channel if VERSION_INFO.build_channel in ("stable", "nightly") else "stable"))

        # Vérification du cache de 24h si force=False
        if not self.force:
            last_check_val = settings.value(SETTINGS_KEY_LAST_CHECK, 0)
            try:
                last_check_raw = int(str(last_check_val))
            except (ValueError, TypeError):
                last_check_raw = 0
            now_ts = int(datetime.datetime.now(datetime.UTC).timestamp())
            if now_ts - last_check_raw < CHECK_INTERVAL_SECONDS:
                logger.debug("Vérification des mises à jour ignorée (dernière vérification récente il y a < 24h).")
                self.signals.no_update.emit(self.current_version)
                return

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": f"AnkiForge/v{self.current_version} ({VERSION_INFO.platform_str})",
        }

        try:
            if active_channel == "nightly":
                self._check_nightly_update(headers, active_channel, settings)
            else:
                self._check_stable_update(headers, active_channel, settings)
        except requests.RequestException as err:
            logger.warning("Vérification de mise à jour indisponible hors ligne : %s", err)
            self.signals.no_update.emit(self.current_version)
        except Exception as err:
            logger.debug("Erreur lors de la vérification de mise à jour : %s", err)
            self.signals.check_failed.emit(str(err))

    def _check_stable_update(self, headers: dict[str, str], active_channel: str, settings: Any) -> None:
        """Interroge la liste des releases pour identifier la version maximale selon SemVer vx.x.x."""
        logger.info("Interrogation de la release stable courante AnkiForge : %s", GITHUB_LATEST_URL)
        etag = "" if self.force else str(settings.value(SETTINGS_KEY_ETAG_STABLE, "")).strip()
        if etag:
            headers = {**headers, "If-None-Match": etag}
        resp = requests.get(GITHUB_LATEST_URL, headers=headers, timeout=10.0)

        if resp.status_code == 304:
            self._emit_cached_result(settings)
            return

        if resp.status_code in (403, 429):
            logger.warning("API Releases limitée (HTTP %s), repli sur les tags publics.", resp.status_code)
            self._check_stable_tags(headers, active_channel, settings)
            return

        if resp.status_code != 200:
            logger.warning("Échec de vérification des mises à jour : HTTP %s", resp.status_code)
            self._check_stable_tags(headers, active_channel, settings)
            return

        response_etag = resp.headers.get("ETag")
        if isinstance(response_etag, str) and response_etag:
            settings.setValue(SETTINGS_KEY_ETAG_STABLE, response_etag)

        data = resp.json()

        # /latest retourne un objet. Une liste reste acceptée pour compatibilité
        # avec les miroirs/API historiques et les intégrations existantes.
        if isinstance(data, dict) and data.get("tag_name"):
            releases_list = [data]
        elif isinstance(data, list):
            releases_list = data
        else:
            api_msg = str(data.get("message", "Réponse d'API GitHub inattendue (objet JSON non-liste).")) if isinstance(data, dict) else "Réponse d'API GitHub invalide."
            logger.warning("Réponse GitHub inattendue (non-liste) : %s", api_msg)
            logger.warning("Réponse Releases inexploitable, repli sur les tags : %s", api_msg)
            self._check_stable_tags(headers, active_channel, settings)
            return

        candidates: list[tuple[version.Version, str, dict[str, Any]]] = []
        for r in releases_list:
            if r.get("draft") or r.get("prerelease"):
                continue
            raw_tag = str(r.get("tag_name", ""))
            clean_tag = raw_tag.strip().lstrip("vV").strip()
            parsed_version = _parse_stable_version(clean_tag)
            if parsed_version is not None:
                candidates.append((parsed_version, clean_tag, r))

        # Enregistrement du timestamp de vérification
        now_ts = int(datetime.datetime.now(datetime.UTC).timestamp())
        settings.setValue(SETTINGS_KEY_LAST_CHECK, now_ts)

        if not candidates:
            logger.debug("Aucune release stable trouvée sur GitHub.")
            self.signals.no_update.emit(self.current_version)
            return

        # Tri strict par SemVer (Majeure, Mineure, Patch) décroissant
        candidates.sort(key=lambda x: x[0], reverse=True)
        _, highest_tag, highest_release = candidates[0]
        settings.setValue(SETTINGS_KEY_CACHED_VERSION, highest_tag)
        settings.setValue(SETTINGS_KEY_CACHED_CHANNEL, active_channel)
        self._cache_metadata(settings, highest_release, active_channel)

        if is_version_strictly_greater(highest_tag, self.current_version):
            logger.info("Nouvelle version disponible : v%s [%s] (Actuelle : v%s)", highest_tag, active_channel, self.current_version)
            info = UpdateInfo(
                version=highest_tag,
                title=str(highest_release.get("name", f"AnkiForge v{highest_tag}")),
                release_notes=str(highest_release.get("body", "Une nouvelle version d'AnkiForge est disponible.")),
                html_url=str(highest_release.get("html_url", GITHUB_LATEST_URL)),
                published_at=str(highest_release.get("published_at", "")),
                channel=active_channel,
                is_prerelease=bool(highest_release.get("prerelease", False)),
                assets=highest_release.get("assets", []),
            )
            self.signals.update_available.emit(info)
        else:
            logger.debug("Application à jour (Actuelle : v%s, Distante : v%s)", self.current_version, highest_tag)
            self.signals.no_update.emit(self.current_version)

    def _cache_metadata(self, settings: Any, release: dict[str, Any], channel: str) -> None:
        """Conserve les métadonnées utiles au dialogue affiché depuis le cache."""
        metadata = {
            "title": str(release.get("name", "")),
            "release_notes": str(release.get("body", "Une nouvelle version d'AnkiForge est disponible.")),
            "html_url": str(release.get("html_url", GITHUB_LATEST_URL)),
            "published_at": str(release.get("published_at", "")),
            "is_prerelease": bool(release.get("prerelease", channel == "nightly")),
            "assets": release.get("assets", []),
        }
        settings.setValue(SETTINGS_KEY_CACHED_METADATA, json.dumps(metadata))

    def _emit_cached_result(self, settings: Any) -> None:
        """Traite une réponse HTTP 304 à partir des métadonnées locales."""
        cached_version = str(settings.value(SETTINGS_KEY_CACHED_VERSION, "")).strip().lstrip("vV")
        metadata_raw = str(settings.value(SETTINGS_KEY_CACHED_METADATA, ""))
        try:
            metadata = json.loads(metadata_raw) if metadata_raw else {}
        except json.JSONDecodeError:
            metadata = {}
        if cached_version and is_version_strictly_greater(cached_version, self.current_version):
            self.signals.update_available.emit(
                UpdateInfo(
                    version=cached_version,
                    title=str(metadata.get("title", f"AnkiForge v{cached_version}")),
                    release_notes=str(metadata.get("release_notes", "Une nouvelle version d'AnkiForge est disponible.")),
                    html_url=str(metadata.get("html_url", GITHUB_LATEST_URL)),
                    published_at=str(metadata.get("published_at", "")),
                    channel="stable",
                    is_prerelease=bool(metadata.get("is_prerelease", False)),
                    assets=list(metadata.get("assets", [])),
                )
            )
        else:
            self.signals.no_update.emit(self.current_version)

    def _check_stable_tags(self, headers: dict[str, str], active_channel: str, settings: Any) -> None:
        """Utilise les tags publics, non soumis à l'endpoint Releases, en secours."""
        resp = requests.get(GITHUB_TAGS_URL, headers=headers, timeout=10.0)
        if resp.status_code != 200:
            logger.warning("Fallback tags indisponible : HTTP %s", resp.status_code)
            self.signals.no_update.emit(self.current_version)
            return
        data = resp.json()
        if not isinstance(data, list):
            self.signals.no_update.emit(self.current_version)
            return
        candidates: list[tuple[version.Version, str]] = []
        for tag in data:
            raw_tag = str(tag.get("name", "")) if isinstance(tag, dict) else ""
            parsed = _parse_stable_version(raw_tag)
            if parsed is not None:
                candidates.append((parsed, raw_tag.strip().lstrip("vV")))
        now_ts = int(datetime.datetime.now(datetime.UTC).timestamp())
        settings.setValue(SETTINGS_KEY_LAST_CHECK, now_ts)
        if not candidates:
            self.signals.no_update.emit(self.current_version)
            return
        _, highest_tag = max(candidates, key=lambda item: item[0])
        settings.setValue(SETTINGS_KEY_CACHED_VERSION, highest_tag)
        settings.setValue(SETTINGS_KEY_CACHED_CHANNEL, active_channel)
        info = UpdateInfo(
            version=highest_tag,
            title=f"AnkiForge v{highest_tag}",
            release_notes="Une nouvelle version d'AnkiForge est disponible. Consultez GitHub pour les notes et les téléchargements.",
            html_url=f"https://github.com/Skyl9/AnkiForge/releases/tag/v{highest_tag}",
            published_at="",
            channel=active_channel,
            assets=[],
        )
        self._cache_metadata(settings, {"name": info.title, "body": info.release_notes, "html_url": info.html_url}, active_channel)
        if is_version_strictly_greater(highest_tag, self.current_version):
            self.signals.update_available.emit(info)
        else:
            self.signals.no_update.emit(self.current_version)

    def _check_nightly_update(self, headers: dict[str, str], active_channel: str, settings: Any) -> None:
        """Interroge l'endpoint Nightly."""
        logger.info("Interrogation des mises à jour Nightly : %s", GITHUB_NIGHTLY_URL)
        etag = "" if self.force else str(settings.value(SETTINGS_KEY_ETAG_NIGHTLY, "")).strip()
        if etag:
            headers = {**headers, "If-None-Match": etag}
        resp = requests.get(GITHUB_NIGHTLY_URL, headers=headers, timeout=10.0)

        if resp.status_code == 304:
            self.signals.no_update.emit(self.current_version)
            return
        if resp.status_code != 200:
            logger.warning("Échec de vérification Nightly : HTTP %s", resp.status_code)
            self.signals.check_failed.emit(f"HTTP {resp.status_code}")
            return
        response_etag = resp.headers.get("ETag")
        if isinstance(response_etag, str) and response_etag:
            settings.setValue(SETTINGS_KEY_ETAG_NIGHTLY, response_etag)

        data: dict[str, Any] = resp.json()
        raw_tag = str(data.get("tag_name", "nightly"))
        remote_tag = raw_tag.strip().lstrip("vV").strip() or "nightly"
        published_at = str(data.get("published_at", ""))

        now_ts = int(datetime.datetime.now(datetime.UTC).timestamp())
        settings.setValue(SETTINGS_KEY_LAST_CHECK, now_ts)
        settings.setValue(SETTINGS_KEY_CACHED_VERSION, remote_tag)
        settings.setValue(SETTINGS_KEY_CACHED_CHANNEL, "nightly")
        self._cache_metadata(settings, data, "nightly")

        is_available = False
        if published_at and VERSION_INFO.build_date:
            try:
                remote_dt = datetime.datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                local_dt = datetime.datetime.fromisoformat(VERSION_INFO.build_date.replace("Z", "+00:00"))
                if remote_dt > local_dt:
                    is_available = True
            except Exception:
                # Dates mal formées : conservateur — on n'émet pas de fausse alerte
                logger.warning("Impossible de comparer les dates de build nightly (format inattendu). Mise à jour ignorée.")
                is_available = False
        else:
            # build_date absent (build incomplet ou _version.py manquant) :
            # comportement conservateur — ne pas spammer l'utilisateur à chaque démarrage.
            logger.debug("Nightly : build_date local absent. Comparaison de dates impossible, mise à jour non signalée.")

        if is_available:
            info = UpdateInfo(
                version=remote_tag,
                title=str(data.get("name", "AnkiForge Nightly")),
                release_notes=str(data.get("body", "Nouvelle version Nightly disponible.")),
                html_url=str(data.get("html_url", GITHUB_NIGHTLY_URL)),
                published_at=published_at,
                channel="nightly",
                is_prerelease=True,
                assets=data.get("assets", []),
            )
            self.signals.update_available.emit(info)
        else:
            self.signals.no_update.emit(self.current_version)
