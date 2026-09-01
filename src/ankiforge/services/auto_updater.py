"""Service d'auto-mise à jour en un clic (Téléchargement en arrière-plan, vérification SHA-256 et swap multi-OS sécurisé)."""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests
from PySide6.QtCore import QObject, QRunnable, Signal

from ankiforge.utils.paths import get_app_data_dir

logger = logging.getLogger(__name__)


def is_standalone_app() -> bool:
    """Détecte si l'application s'exécute sous forme de binaire autonome gelé

    (Nuitka, PyInstaller, macOS App Bundle, Linux AppImage, Windows EXE).
    Retourne False en environnement de développement source (Python / venv / IDE).
    """
    # 1. Flag Nuitka
    if "__compiled__" in globals() or "__compiled__" in sys.modules:
        return True

    # 2. Flag PyInstaller / Freeze standard
    if getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"):
        return True

    # 3. Environnement AppImage Linux
    if "APPIMAGE" in os.environ:
        return True

    # 4. Exécutable situé dans un bundle macOS .app
    exe_path = Path(sys.executable).resolve()
    if sys.platform == "darwin" and "Contents/MacOS" in str(exe_path):
        return True

    return False


def get_updates_storage_dir() -> Path:
    """Retourne le répertoire dédié au stockage des fichiers de mise à jour (~/.ankiforge/updates)."""
    updates_dir = get_app_data_dir() / "updates"
    updates_dir.mkdir(parents=True, exist_ok=True)
    return updates_dir


def get_current_platform_asset_keywords() -> list[str]:
    """Retourne les mots-clés de nom de fichier correspondant à la plateforme actuelle."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        # macOS DMG en priorité, fallback ZIP
        if "arm" in machine or "aarch" in machine:
            return ["macos-arm64.dmg", "macos-arm64.zip", "macos.dmg", ".dmg", ".zip"]
        return ["macos-x86_64.dmg", "macos.dmg", ".dmg", ".zip"]

    if system == "windows":
        return ["Setup-x64.exe", "-windows-x64.zip", ".exe", ".zip"]

    # Linux
    return ["-x86_64.AppImage", ".AppImage", "-linux-x86_64.tar.gz", ".tar.gz"]


def find_asset_for_current_platform(assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Sélectionne l'asset le plus pertinent pour la plateforme actuelle parmi les assets d'une release GitHub."""
    keywords = get_current_platform_asset_keywords()
    for kw in keywords:
        for asset in assets:
            name = str(asset.get("name", "")).lower()
            if kw.lower() in name:
                return asset
    return assets[0] if assets else None


class DownloaderSignals(QObject):
    """Signaux émis lors de la progression et de la fin du téléchargement."""

    progress = Signal(int, int, int)  # percentage (0-100), downloaded_bytes, total_bytes
    download_complete = Signal(object, str)  # (Path destination_file, str sha256_hash)
    download_error = Signal(str)


class UpdateDownloaderWorker(QRunnable):
    """Worker QRunnable téléchargeant un asset de mise à jour avec calcul de hash SHA-256."""

    def __init__(self, download_url: str, filename: str) -> None:
        super().__init__()
        self.download_url = download_url
        self.filename = filename
        self.signals = DownloaderSignals()
        self._is_cancelled = False

    def cancel(self) -> None:
        """Demande l'annulation du téléchargement en cours."""
        self._is_cancelled = True

    def run(self) -> None:
        """Exécute le téléchargement par flux avec émission de progression."""
        target_dir = get_updates_storage_dir()
        dest_path = target_dir / self.filename

        try:
            logger.info("Début du téléchargement de la mise à jour depuis %s vers %s", self.download_url, dest_path)
            headers = {"User-Agent": "AnkiForge-AutoUpdater"}
            with requests.get(self.download_url, headers=headers, stream=True, timeout=10.0) as response:
                if response.status_code != 200:
                    self.signals.download_error.emit(f"Erreur HTTP {response.status_code} lors du téléchargement.")
                    return

                total_size = int(response.headers.get("content-length", 0))
                downloaded_size = 0
                hasher = hashlib.sha256()

                with open(dest_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=65536):
                        if self._is_cancelled:
                            logger.info("Téléchargement annulé par l'utilisateur.")
                            return

                        if chunk:
                            f.write(chunk)
                            hasher.update(chunk)
                            downloaded_size += len(chunk)

                            pct = int((downloaded_size / total_size) * 100) if total_size > 0 else 0
                            self.signals.progress.emit(pct, downloaded_size, total_size)

                computed_hash = hasher.hexdigest()
                logger.info("Téléchargement achevé avec succès. SHA-256: %s", computed_hash)
                self.signals.download_complete.emit(dest_path, computed_hash)

        except Exception as err:
            logger.exception("Erreur lors du téléchargement de la mise à jour : %s", err)
            self.signals.download_error.emit(str(err))


def apply_update_and_restart(update_file: Path) -> tuple[bool, str]:
    """Exécute le processus de remplacement sécurisé (Swap) et planifie le redémarrage.

    Protège rigoureusement l'environnement de développement.

    Returns:
        tuple[bool, str]: (Succès du déclenchement, Message d'information)
    """
    if not update_file.exists():
        return False, f"Fichier de mise à jour introuvable : {update_file}"

    # 1. Sécurité Mode Développement
    if not is_standalone_app():
        msg = f"Mode Développement Détecté : Le fichier de mise à jour a été téléchargé dans {update_file}.\nLe remplacement automatique est désactivé en environnement source pour protéger le code."
        logger.info(msg)
        return True, msg

    system = platform.system().lower()

    # 2. Windows : Lancement de l'installeur Inno Setup silencieux
    if system == "windows":
        try:
            logger.info("Lancement de l'installeur Windows en mode silencieux : %s", update_file)
            # Flags Inno Setup pour fermer et redémarrer l'application proprement
            cmd = [
                str(update_file),
                "/SILENT",
                "/CLOSEAPPLICATIONS",
                "/RESTARTAPPLICATIONS",
                "/SP-",
            ]
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
            subprocess.Popen(cmd, creationflags=flags)
            return True, "Installeur Windows démarré. Redémarrage en cours..."
        except Exception as err:
            logger.exception("Échec du lancement de l'installeur Windows : %s", err)
            return False, f"Erreur Windows: {err}"

    # 3. macOS : Script shell détaché pour monter le DMG et mettre à jour /Applications/AnkiForge.app
    if system == "darwin":
        try:
            script_path = get_updates_storage_dir() / "apply_update_macos.sh"
            mount_point = "/tmp/ankiforge_update_mount"

            script_content = f"""#!/bin/sh
sleep 1.2
mkdir -p "{mount_point}"
hdiutil attach "{update_file}" -nobrowse -mountpoint "{mount_point}" -quiet

if [ -d "{mount_point}/AnkiForge.app" ]; then
    rm -rf "/Applications/AnkiForge.app"
    cp -R "{mount_point}/AnkiForge.app" "/Applications/AnkiForge.app"
fi

hdiutil detach "{mount_point}" -quiet || true
open -a "/Applications/AnkiForge.app"
"""
            script_path.write_text(script_content, encoding="utf-8")
            script_path.chmod(0o755)

            logger.info("Exécution du script de swap macOS : %s", script_path)
            subprocess.Popen(["/bin/sh", str(script_path)], start_new_session=True)
            return True, "Mise à jour macOS planifiée. Redémarrage en cours..."
        except Exception as err:
            logger.exception("Échec de la mise à jour macOS : %s", err)
            return False, f"Erreur macOS: {err}"

    # 4. Linux (AppImage)
    if system == "linux":
        try:
            current_appimage = os.environ.get("APPIMAGE")
            update_file.chmod(0o755)

            if current_appimage and Path(current_appimage).exists():
                script_path = get_updates_storage_dir() / "apply_update_linux.sh"
                script_content = f"""#!/bin/sh
sleep 1.0
mv -f "{update_file}" "{current_appimage}"
chmod +x "{current_appimage}"
exec "{current_appimage}" "$@"
"""
                script_path.write_text(script_content, encoding="utf-8")
                script_path.chmod(0o755)
                subprocess.Popen(["/bin/sh", str(script_path)], start_new_session=True)
                return True, "Mise à jour AppImage planifiée. Redémarrage..."
            else:
                subprocess.Popen([str(update_file)], start_new_session=True)
                return True, "Nouvelle AppImage lancée."
        except Exception as err:
            logger.exception("Échec de la mise à jour Linux : %s", err)
            return False, f"Erreur Linux: {err}"

    return False, "Plateforme non supportée pour le swap automatique."
