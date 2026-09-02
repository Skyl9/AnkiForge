"""Service asynchrone de vérification des mises à jour d'AnkiForge via GitHub Releases API."""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from typing import Any

import requests
from packaging import version
from PySide6.QtCore import QObject, QRunnable, QSettings, Signal

from ankiforge.version import VERSION_INFO

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com/repos/Skyl9/AnkiForge/releases"
GITHUB_LATEST_URL = f"{GITHUB_API_BASE}/latest"
GITHUB_NIGHTLY_URL = f"{GITHUB_API_BASE}/tags/nightly"

SETTINGS_KEY_LAST_CHECK = "updates/last_check_timestamp"
SETTINGS_KEY_CACHED_VERSION = "updates/cached_latest_version"
SETTINGS_KEY_CHANNEL = "updates/channel"
CHECK_INTERVAL_SECONDS = 86400  # 24 heures


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
        self.current_version = current_version or VERSION_INFO.version
        self.channel = channel
        self.force = force
        self.signals = UpdateCheckerSignals()

    def run(self) -> None:
        """Exécute la vérification HTTP non-bloquante."""
        settings = QSettings("AnkiForgeOrg", "AnkiForge")

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

        target_url = GITHUB_NIGHTLY_URL if active_channel == "nightly" else GITHUB_LATEST_URL

        try:
            logger.info("Interrogation des mises à jour [%s] : %s", active_channel, target_url)
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": f"AnkiForge/{self.current_version} ({VERSION_INFO.platform_str})",
            }
            resp = requests.get(target_url, headers=headers, timeout=4.0)

            if resp.status_code != 200:
                logger.warning("Échec de vérification des mises à jour : HTTP %s", resp.status_code)
                self.signals.check_failed.emit(f"HTTP {resp.status_code}")
                return

            data: dict[str, Any] = resp.json()
            raw_tag = str(data.get("tag_name", ""))
            remote_tag = raw_tag.lstrip("v").strip()
            published_at = str(data.get("published_at", ""))

            # Mise à jour du timestamp de dernière vérification
            now_ts = int(datetime.datetime.now(datetime.UTC).timestamp())
            settings.setValue(SETTINGS_KEY_LAST_CHECK, now_ts)
            settings.setValue(SETTINGS_KEY_CACHED_VERSION, remote_tag)

            if not remote_tag:
                self.signals.no_update.emit(self.current_version)
                return

            is_update_available = False

            if active_channel == "nightly":
                # Pour le canal Nightly, on vérifie si la release distante est plus récente que la date de build
                if published_at and VERSION_INFO.build_date:
                    try:
                        remote_dt = datetime.datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                        local_dt = datetime.datetime.fromisoformat(VERSION_INFO.build_date.replace("Z", "+00:00"))
                        if remote_dt > local_dt:
                            is_update_available = True
                    except Exception:
                        is_update_available = True
                else:
                    is_update_available = True
            else:
                # Canal Stable : Comparaison SemVer stricte
                try:
                    parsed_current = version.parse(self.current_version)
                    parsed_remote = version.parse(remote_tag)
                    if parsed_remote > parsed_current:
                        is_update_available = True
                except Exception as parse_err:
                    logger.warning("Erreur de parsing SemVer (%s vs %s) : %s", self.current_version, remote_tag, parse_err)

            if is_update_available:
                logger.info("Nouvelle version disponible : v%s [%s] (Actuelle : v%s)", remote_tag, active_channel, self.current_version)
                info = UpdateInfo(
                    version=remote_tag,
                    title=str(data.get("name", f"AnkiForge v{remote_tag}")),
                    release_notes=str(data.get("body", "Une nouvelle version d'AnkiForge est disponible.")),
                    html_url=str(data.get("html_url", target_url)),
                    published_at=published_at,
                    channel=active_channel,
                    is_prerelease=bool(data.get("prerelease", False)),
                    assets=data.get("assets", []),
                )
                self.signals.update_available.emit(info)
            else:
                logger.debug("Application à jour (Actuelle : v%s, Distante : v%s)", self.current_version, remote_tag)
                self.signals.no_update.emit(self.current_version)

        except Exception as err:
            logger.debug("Erreur lors de la vérification de mise à jour : %s", err)
            self.signals.check_failed.emit(str(err))
