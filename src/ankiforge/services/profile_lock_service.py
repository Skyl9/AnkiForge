"""Service de verrouillage exclusif par profil utilisateur (anti double-instance)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import NamedTuple

from PySide6.QtCore import QLockFile

from ankiforge.services.profile_manager import ProfileManager

logger = logging.getLogger(__name__)


class LockInfo(NamedTuple):
    pid: int
    hostname: str
    appname: str


def is_pid_alive(pid: int) -> bool:
    """Vérifie si un processus avec le PID donné est actif sur le système hôte."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            synchronize = 0x00100000
            process = kernel32.OpenProcess(synchronize, False, pid)
            if process:
                kernel32.CloseHandle(process)
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class ProfileLockService:
    """Gère l'acquisition, la vérification et la libération du verrou exclusif par profil."""

    _active_locks: dict[str, QLockFile] = {}

    @classmethod
    def get_lock_file_path(cls, profile_name: str, profiles_dir: Path | None = None) -> Path:
        """Retourne le chemin canonique du fichier de verrou pour un profil."""
        base_dir = profiles_dir or ProfileManager().profiles_dir
        profile_dir = base_dir / profile_name
        profile_dir.mkdir(parents=True, exist_ok=True)
        return profile_dir / ".profile.lock"

    @classmethod
    def is_locked(cls, profile_name: str, profiles_dir: Path | None = None) -> tuple[bool, LockInfo | None]:
        """
        Vérifie si le profil est verrouillé par un processus actif.
        Si un verrou orphelin (stale lock avec PID inactif) est détecté, le nettoie et retourne (False, None).
        """
        lock_path = cls.get_lock_file_path(profile_name, profiles_dir)
        lock_file = QLockFile(str(lock_path))

        if lock_file.tryLock(0):
            lock_file.unlock()
            return False, None

        info = lock_file.getLockInfo()
        pid = int(info[0]) if info and len(info) > 0 else 0
        hostname = str(info[1]) if info and len(info) > 1 else ""
        appname = str(info[2]) if info and len(info) > 2 else ""
        lock_info = LockInfo(pid=pid, hostname=hostname, appname=appname)

        if not is_pid_alive(pid):
            logger.info(
                "Verrou orphelin détecté sur le profil '%s' (PID %d inactif). Nettoyage automatique.",
                profile_name,
                pid,
            )
            lock_file.removeStaleLockFile()
            return False, None

        return True, lock_info

    @classmethod
    def acquire_lock(cls, profile_name: str, profiles_dir: Path | None = None) -> tuple[bool, LockInfo | None]:
        """
        Tente d'acquérir le verrou exclusif sur le profil.
        Retourne (True, None) si le verrou est acquis.
        Retourne (False, lock_info) si le profil est déjà verrouillé par un processus vivant.
        """
        if profile_name in cls._active_locks and cls._active_locks[profile_name].isLocked():
            return True, None

        lock_path = cls.get_lock_file_path(profile_name, profiles_dir)
        lock_file = QLockFile(str(lock_path))

        if lock_file.tryLock(100):
            cls._active_locks[profile_name] = lock_file
            logger.info("Verrou exclusif acquis pour le profil '%s' (PID %d)", profile_name, os.getpid())
            return True, None

        info = lock_file.getLockInfo()
        pid = int(info[0]) if info and len(info) > 0 else 0
        hostname = str(info[1]) if info and len(info) > 1 else ""
        appname = str(info[2]) if info and len(info) > 2 else ""
        lock_info = LockInfo(pid=pid, hostname=hostname, appname=appname)

        if not is_pid_alive(pid):
            logger.info(
                "Suppression du verrou orphelin sur le profil '%s' (PID %d inactif) et réacquisition...",
                profile_name,
                pid,
            )
            lock_file.removeStaleLockFile()
            if lock_file.tryLock(100):
                cls._active_locks[profile_name] = lock_file
                logger.info("Verrou exclusif réacquis avec succès pour le profil '%s'", profile_name)
                return True, None

        logger.warning(
            "Impossible d'acquérir le verrou pour le profil '%s' : déjà utilisé par le PID %d (%s)",
            profile_name,
            pid,
            hostname,
        )
        return False, lock_info

    @classmethod
    def release_lock(cls, profile_name: str) -> None:
        """Libère le verrou détenu sur le profil donné."""
        lock_file = cls._active_locks.pop(profile_name, None)
        if lock_file is not None and lock_file.isLocked():
            lock_file.unlock()
            logger.info("Verrou exclusif libéré pour le profil '%s'", profile_name)

    @classmethod
    def release_all_locks(cls) -> None:
        """Libère tous les verrous détenus par l'instance en cours."""
        for profile_name in list(cls._active_locks.keys()):
            cls.release_lock(profile_name)
