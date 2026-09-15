"""Service d'auto-mise à jour durci et sécurisé pour AnkiForge.

Caractéristiques de sécurité :
1. Confinement strict des fichiers dans ~/.ankiforge/updates/ (Protection Path Traversal).
2. Interdiction des liens symboliques (Symlink Hijacking protection).
3. Zéro génération de script shell (.sh) interpolé : exécution directe des binaires système.
4. Création atomique de répertoires temporaires privés (0700 via tempfile.mkdtemp).
5. Protection absolue de l'environnement de développement (Aucun swap en mode source).
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import subprocess  # nosec: B404
import sys
import tempfile
from pathlib import Path
from typing import Any

import requests
from PySide6.QtCore import QObject, QRunnable, Signal

from ankiforge.utils.paths import get_app_data_dir

logger = logging.getLogger(__name__)

MAX_DOWNLOAD_SIZE_BYTES = 2 * 1024 * 1024 * 1024  # 2 Go — plafond de sécurité pour les binaires applicatifs

_TRUSTED_DOWNLOAD_DOMAINS = frozenset(
    {
        "github.com",
        "objects.githubusercontent.com",
        "codeload.github.com",
    }
)


def _validate_download_url(url: str) -> None:
    """Valide que l'URL de téléchargement est HTTPS et pointe vers un domaine GitHub de confiance.

    Lève ValueError si l'URL est suspecte.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"URL de téléchargement invalide : le schéma '{parsed.scheme}' n'est pas autorisé (HTTPS requis).")
    if parsed.netloc not in _TRUSTED_DOWNLOAD_DOMAINS:
        raise ValueError(f"URL de téléchargement invalide : le domaine '{parsed.netloc}' n'est pas dans la liste de confiance.")


def _find_current_macos_app_bundle() -> Path:
    """Résout dynamiquement le chemin du bundle .app courant sur macOS.

    Remonte depuis Contents/MacOS/<binary> vers le .app parent.
    Retourne /Applications/AnkiForge.app comme fallback si non détectable.
    """
    fallback = Path("/Applications/AnkiForge.app")
    exe = Path(sys.executable).resolve()
    try:
        parts = exe.parts
        for i, part in enumerate(parts):
            if part.endswith(".app"):
                return Path(*parts[: i + 1])
        if "Contents" in parts:
            idx = list(parts).index("Contents")
            return Path(*parts[:idx])
    except (ValueError, TypeError):
        pass
    return fallback


def is_standalone_app() -> bool:
    """Détecte de manière fiable si l'application s'exécute en binaire autonome gelé

    (Nuitka, PyInstaller, macOS App Bundle, Linux AppImage, Windows EXE).
    Retourne False en environnement de développement source (Python / venv / IDE).
    """
    from ankiforge.utils.environment import is_development

    if is_development():
        return False

    from ankiforge.utils.environment import is_standalone_runtime

    return is_standalone_runtime()


def get_updates_storage_dir() -> Path:
    """Retourne le répertoire confiné et sécurisé dédié aux mises à jour (~/.ankiforge/updates)."""
    updates_dir = (get_app_data_dir() / "updates").resolve()
    updates_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    return updates_dir


def validate_update_file_confinement(update_file: Path) -> Path:
    """Valide rigoureusement que le fichier de mise à jour est confiné dans le dossier autorisé.

    Lève ValueError si le chemin est suspect ou échappe au confinement (Path Traversal / Symlinks).
    """
    # 1. Interdiction des liens symboliques (Symlink Hijacking)
    if update_file.is_symlink():
        raise ValueError(f"Alerte de sécurité : Le fichier '{update_file}' est un lien symbolique non autorisé.")

    resolved_file = update_file.resolve()
    trusted_dir = get_updates_storage_dir().resolve()

    # 2. Vérification stricte du confinement dans ~/.ankiforge/updates/
    if trusted_dir not in resolved_file.parents and resolved_file != trusted_dir:
        raise ValueError(f"Alerte de sécurité : Le fichier '{resolved_file}' est situé hors du répertoire sécurisé '{trusted_dir}'.")

    # 3. Vérification de l'existence et du type de fichier
    if not resolved_file.is_file():
        raise ValueError(f"Fichier de mise à jour introuvable ou invalide : '{resolved_file}'.")

    return resolved_file


def get_current_platform_asset_keywords() -> list[str]:
    """Retourne les mots-clés de nom de fichier correspondant à la plateforme actuelle."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
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
    return None


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
        safe_filename = Path(self.filename).name  # Élimine toute tentative de Path Traversal dans le nom
        dest_path = (target_dir / safe_filename).resolve()

        try:
            # ISSUE 6 : Validation HTTPS + domaine de confiance avant tout appel réseau
            _validate_download_url(self.download_url)

            logger.info("Début du téléchargement de la mise à jour depuis %s vers %s", self.download_url, dest_path)
            headers = {"User-Agent": "AnkiForge-AutoUpdater"}
            # ISSUE 9 : timeout en tuple (connexion, lecture) — évite les blocages sur connexions très lentes
            with requests.get(self.download_url, headers=headers, stream=True, timeout=(10.0, 120.0)) as response:
                if response.status_code != 200:
                    self.signals.download_error.emit(f"Erreur HTTP {response.status_code} lors du téléchargement.")
                    return

                total_size = int(response.headers.get("content-length", 0))

                # ISSUE 7 : Refus préventif si Content-Length dépasse le plafond de sécurité
                if total_size > MAX_DOWNLOAD_SIZE_BYTES:
                    self.signals.download_error.emit(f"Taille annoncée ({total_size / (1024**3):.1f} Go) dépasse le plafond autorisé de 2 Go.")
                    return

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

                            # ISSUE 7 : Vérification en continu de la taille réelle reçue
                            if downloaded_size > MAX_DOWNLOAD_SIZE_BYTES:
                                logger.error("Taille réelle téléchargée dépasse le plafond de 2 Go. Abandon.")
                                self.signals.download_error.emit("Taille reçue dépasse le plafond de sécurité de 2 Go. Téléchargement abandonné.")
                                return

                            pct = int((downloaded_size / total_size) * 100) if total_size > 0 else 0
                            self.signals.progress.emit(pct, downloaded_size, total_size)

            computed_hash = hasher.hexdigest()
            logger.info("Téléchargement achevé avec succès. SHA-256: %s", computed_hash)
            self.signals.download_complete.emit(dest_path, computed_hash)

        except ValueError as err:
            # Erreur de validation URL (ISSUE 6) — non critique, pas de stack trace complète
            logger.error("URL de téléchargement rejetée pour raison de sécurité : %s", err)
            self.signals.download_error.emit(str(err))
        except Exception as err:
            logger.exception("Erreur lors du téléchargement de la mise à jour : %s", err)
            self.signals.download_error.emit(str(err))


def apply_update_and_restart(update_file: Path) -> tuple[bool, str]:
    """Exécute le processus de remplacement sécurisé sans aucun script shell interpolé.

    Protège rigoureusement l'environnement de développement et applique le confinement.

    Returns:
        tuple[bool, str]: (Succès du déclenchement, Message d'information)
    """
    try:
        validated_file = validate_update_file_confinement(update_file)
    except ValueError as err:
        logger.error("Rejet de sécurité lors de la mise à jour : %s", err)
        return False, str(err)

    # 1. Protection absolue du mode développement
    if not is_standalone_app():
        msg = f"Mode Développement Détecté : Le fichier '{validated_file.name}' a été vérifié et téléchargé.\nLe remplacement automatique est désactivé en environnement source pour protéger le code."
        logger.info(msg)
        return True, msg

    system = platform.system().lower()

    # 2. Windows : Lancement direct de l'installeur Inno Setup (sans shell)
    if system == "windows":
        try:
            logger.info("Lancement sécurisé de l'installeur Windows : %s", validated_file)
            cmd = [
                str(validated_file),
                "/SILENT",
                "/CLOSEAPPLICATIONS",
                "/RESTARTAPPLICATIONS",
                "/SP-",
            ]
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
            subprocess.Popen(cmd, creationflags=flags, close_fds=True)  # nosec: B603
            return True, "Installeur Windows démarré. Redémarrage en cours..."
        except Exception as err:
            logger.exception("Échec du lancement de l'installeur Windows : %s", err)
            return False, f"Erreur Windows: {err}"

    # 3. macOS : Montage direct via /usr/bin/hdiutil et copie /usr/bin/ditto (Zéro script shell)
    if system == "darwin":
        mount_dir: str | None = None
        try:
            # Création atomique d'un dossier de montage temporaire unique et privé (0700)
            mount_dir = tempfile.mkdtemp(prefix="ankiforge_mount_")

            logger.info("Montage direct du DMG dans %s", mount_dir)
            subprocess.run(  # nosec: B603
                ["/usr/bin/hdiutil", "attach", str(validated_file), "-nobrowse", "-mountpoint", mount_dir, "-quiet"],
                check=True,
                capture_output=True,
            )

            source_app = Path(mount_dir) / "AnkiForge.app"

            # BUG 4 : Résolution dynamique du chemin d'installation réel (au lieu de /Applications/ codé en dur)
            dest_app = _find_current_macos_app_bundle()
            logger.info("Destination d'installation résolue dynamiquement : %s", dest_app)

            if not source_app.is_dir():
                raise FileNotFoundError(f"AnkiForge.app introuvable dans le DMG monté ({mount_dir}).")

            logger.info("Copie sécurisée de l'application vers %s via ditto", dest_app)
            subprocess.run(["/usr/bin/ditto", str(source_app), str(dest_app)], check=True)  # nosec: B603

            # Démontage propre
            subprocess.run(["/usr/bin/hdiutil", "detach", mount_dir, "-quiet"], check=False)  # nosec: B603
            try:
                os.rmdir(mount_dir)
                mount_dir = None
            except OSError:
                pass

            # Relance de l'application mise à jour
            logger.info("Lancement de la nouvelle version : %s", dest_app)
            subprocess.Popen(["/usr/bin/open", "-a", str(dest_app)], start_new_session=True)  # nosec: B603
            return True, "Mise à jour macOS effectuée. Redémarrage en cours..."
        except Exception as err:
            logger.exception("Échec de la mise à jour macOS : %s", err)
            if mount_dir and Path(mount_dir).exists():
                subprocess.run(["/usr/bin/hdiutil", "detach", mount_dir, "-quiet"], check=False)  # nosec: B603
                try:
                    os.rmdir(mount_dir)
                except OSError:
                    pass
            return False, f"Erreur macOS: {err}"

    # 4. Linux (AppImage) : Remplacement atomique de fichier sans script shell
    if system == "linux":
        try:
            current_appimage_str = os.environ.get("APPIMAGE", "")
            validated_file.chmod(0o755)

            if current_appimage_str:
                # ISSUE 13 : Validation stricte du chemin $APPIMAGE avant remplacement
                target_path = Path(current_appimage_str).resolve()
                if target_path.is_symlink():
                    raise ValueError(f"$APPIMAGE '{target_path}' est un lien symbolique non autorisé.")
                if not target_path.exists():
                    raise FileNotFoundError(f"$APPIMAGE '{target_path}' introuvable.")
                # Vérification basique que la cible est dans un répertoire utilisateur (pas /etc, /usr, /bin...)
                dangerous_prefixes = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/proc", "/sys")
                if any(str(target_path).startswith(prefix) for prefix in dangerous_prefixes):
                    raise ValueError(f"$APPIMAGE '{target_path}' pointe vers un répertoire système protégé.")

                logger.info("Remplacement atomique de l'AppImage : %s -> %s", validated_file, target_path)
                os.replace(validated_file, target_path)
                subprocess.Popen([str(target_path)], start_new_session=True)  # nosec: B603
                return True, "AppImage mise à jour. Redémarrage..."
            else:
                subprocess.Popen([str(validated_file)], start_new_session=True)  # nosec: B603
                return True, "Nouvelle AppImage démarrée."
        except Exception as err:
            logger.exception("Échec de la mise à jour Linux : %s", err)
            return False, f"Erreur Linux: {err}"

    return False, "Plateforme non supportée pour le swap automatique."
