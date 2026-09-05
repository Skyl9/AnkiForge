"""Service asynchrone de vérification des mises à jour d'AnkiForge via GitHub Releases API."""

from __future__ import annotations

import datetime
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
GITHUB_RELEASES_LIST_URL = f"{GITHUB_API_BASE}?per_page=30"
GITHUB_LATEST_URL = f"{GITHUB_API_BASE}/latest"
GITHUB_NIGHTLY_URL = f"{GITHUB_API_BASE}/tags/nightly"

SETTINGS_KEY_LAST_CHECK = "updates/last_check_timestamp"
SETTINGS_KEY_CACHED_VERSION = "updates/cached_latest_version"
SETTINGS_KEY_CHANNEL = "updates/channel"
CHECK_INTERVAL_SECONDS = 86400  # 24 heures


def parse_semver_tuple(version_str: str) -> tuple[int, int, int] | None:
    """Extrait (majeure, mineure, patch) selon la spécification vx.x.x ou x.x.x."""
    cleaned = version_str.strip().lstrip("vV").strip()
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", cleaned)
    if match:
        return (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return None


def is_version_strictly_greater(remote: str, current: str) -> bool:
    """Vérifie si la version distante est strictement supérieure à la version locale selon SemVer vx.x.x."""
    rem_tuple = parse_semver_tuple(remote)
    cur_tuple = parse_semver_tuple(current)
    if rem_tuple is not None and cur_tuple is not None:
        return rem_tuple > cur_tuple

    # Repli sur packaging.version pour les formats avec suffixe (ex: alpha/beta/rc)
    try:
        r = remote.strip().lstrip("vV").strip()
        c = current.strip().lstrip("vV").strip()
        return version.parse(r) > version.parse(c)
    except Exception:
        return False


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
        except Exception as err:
            logger.debug("Erreur lors de la vérification de mise à jour : %s", err)
            self.signals.check_failed.emit(str(err))

    def _check_stable_update(self, headers: dict[str, str], active_channel: str, settings: Any) -> None:
        """Interroge la liste des releases pour identifier la version maximale selon SemVer vx.x.x."""
        logger.info("Interrogation des releases stables AnkiForge : %s", GITHUB_RELEASES_LIST_URL)
        resp = requests.get(GITHUB_RELEASES_LIST_URL, headers=headers, timeout=10.0)

        if resp.status_code == 403:
            logger.warning("Échec de vérification : Quota d'API GitHub dépassé (HTTP 403).")
            self.signals.check_failed.emit("Limite de requêtes GitHub atteinte (HTTP 403). Veuillez réessayer plus tard.")
            return

        if resp.status_code != 200:
            logger.warning("Échec de vérification des mises à jour : HTTP %s", resp.status_code)
            self.signals.check_failed.emit(f"HTTP {resp.status_code}")
            return

        data = resp.json()
        releases_list: list[dict[str, Any]] = data if isinstance(data, list) else [data]

        candidates: list[tuple[tuple[int, int, int], str, dict[str, Any]]] = []
        for r in releases_list:
            if r.get("draft") or r.get("prerelease"):
                continue
            raw_tag = str(r.get("tag_name", ""))
            clean_tag = raw_tag.strip().lstrip("vV").strip()
            parsed_tuple = parse_semver_tuple(clean_tag)
            if parsed_tuple is not None:
                candidates.append((parsed_tuple, clean_tag, r))

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

    def _check_nightly_update(self, headers: dict[str, str], active_channel: str, settings: Any) -> None:
        """Interroge l'endpoint Nightly."""
        logger.info("Interrogation des mises à jour Nightly : %s", GITHUB_NIGHTLY_URL)
        resp = requests.get(GITHUB_NIGHTLY_URL, headers=headers, timeout=10.0)

        if resp.status_code != 200:
            logger.warning("Échec de vérification Nightly : HTTP %s", resp.status_code)
            self.signals.check_failed.emit(f"HTTP {resp.status_code}")
            return

        data: dict[str, Any] = resp.json()
        raw_tag = str(data.get("tag_name", "nightly"))
        remote_tag = raw_tag.strip().lstrip("vV").strip() or "nightly"
        published_at = str(data.get("published_at", ""))

        now_ts = int(datetime.datetime.now(datetime.UTC).timestamp())
        settings.setValue(SETTINGS_KEY_LAST_CHECK, now_ts)
        settings.setValue(SETTINGS_KEY_CACHED_VERSION, remote_tag)

        is_available = False
        if published_at and VERSION_INFO.build_date:
            try:
                remote_dt = datetime.datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                local_dt = datetime.datetime.fromisoformat(VERSION_INFO.build_date.replace("Z", "+00:00"))
                if remote_dt > local_dt:
                    is_available = True
            except Exception:
                is_available = True
        else:
            is_available = True

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
