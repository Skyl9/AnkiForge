"""Service asynchrone de vérification des mises à jour d'AnkiForge via GitHub Releases API."""

import datetime
import logging
from dataclasses import dataclass, field
from typing import Any

import requests
from packaging import version
from PySide6.QtCore import QObject, QRunnable, QSettings, Signal

from ankiforge import __version__

logger = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com/repos/Skyl9/AnkiForge/releases/latest"
SETTINGS_KEY_LAST_CHECK = "updates/last_check_timestamp"
SETTINGS_KEY_CACHED_VERSION = "updates/cached_latest_version"
CHECK_INTERVAL_SECONDS = 86400  # 24 heures


@dataclass
class UpdateInfo:
    """Informations sur une nouvelle mise à jour disponible."""

    version: str
    title: str
    release_notes: str
    html_url: str
    published_at: str
    is_prerelease: bool = False
    assets: list[dict[str, Any]] = field(default_factory=list)


class UpdateCheckerSignals(QObject):
    """Signaux Qt émis par le worker de vérification."""

    update_available = Signal(object)  # UpdateInfo
    no_update = Signal()
    check_failed = Signal(str)


class UpdateCheckerWorker(QRunnable):
    """Worker QRunnable exécuté en arrière-plan dans QThreadPool pour interroger l'API GitHub."""

    def __init__(self, current_version: str = __version__, force: bool = False) -> None:
        super().__init__()
        self.current_version = current_version
        self.force = force
        self.signals = UpdateCheckerSignals()

    def run(self) -> None:
        """Exécute la vérification HTTP non-bloquante."""
        settings = QSettings("AnkiForgeOrg", "AnkiForge")

        # Vérification du cache de 24h si force=False
        if not self.force:
            last_check_val = settings.value(SETTINGS_KEY_LAST_CHECK, 0)
            try:
                last_check_raw = int(str(last_check_val))
            except (ValueError, TypeError):
                last_check_raw = 0
            now_ts = int(datetime.datetime.now(datetime.UTC).timestamp())
            if now_ts - last_check_raw < CHECK_INTERVAL_SECONDS:
                logger.debug("Vérification des mises à jour ignorée (dernière vérification récente).")
                self.signals.no_update.emit()
                return

        try:
            logger.info("Interrogation de l'API GitHub pour les mises à jour : %s", GITHUB_API_URL)
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": f"AnkiForge/{self.current_version}",
            }
            resp = requests.get(GITHUB_API_URL, headers=headers, timeout=4.0)

            if resp.status_code != 200:
                logger.warning("Échec de vérification des mises à jour : HTTP %s", resp.status_code)
                self.signals.check_failed.emit(f"HTTP {resp.status_code}")
                return

            data: dict[str, Any] = resp.json()
            raw_tag = str(data.get("tag_name", ""))
            remote_tag = raw_tag.lstrip("v").strip()

            # Mise à jour du timestamp de dernière vérification
            now_ts = int(datetime.datetime.now(datetime.UTC).timestamp())
            settings.setValue(SETTINGS_KEY_LAST_CHECK, now_ts)
            settings.setValue(SETTINGS_KEY_CACHED_VERSION, remote_tag)

            if not remote_tag:
                self.signals.no_update.emit()
                return

            # Comparaison de version SemVer
            parsed_current = version.parse(self.current_version)
            parsed_remote = version.parse(remote_tag)

            if parsed_remote > parsed_current:
                logger.info("Nouvelle version disponible : v%s (Actuelle : v%s)", remote_tag, self.current_version)
                info = UpdateInfo(
                    version=remote_tag,
                    title=str(data.get("name", f"AnkiForge v{remote_tag}")),
                    release_notes=str(data.get("body", "Une nouvelle version d'AnkiForge est disponible.")),
                    html_url=str(data.get("html_url", "https://github.com/Skyl9/AnkiForge/releases/latest")),
                    published_at=str(data.get("published_at", "")),
                    is_prerelease=bool(data.get("prerelease", False)),
                    assets=data.get("assets", []),
                )
                self.signals.update_available.emit(info)
            else:
                logger.debug("Application à jour (Actuelle : v%s, Distante : v%s)", self.current_version, remote_tag)
                self.signals.no_update.emit()

        except Exception as err:
            logger.debug("Erreur lors de la vérification de mise à jour : %s", err)
            self.signals.check_failed.emit(str(err))
