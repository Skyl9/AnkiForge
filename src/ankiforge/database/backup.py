import contextlib
import datetime
import logging
import shutil
import sqlite3
from pathlib import Path

from ankiforge.services.profile_manager import ProfileManager
from ankiforge.utils.paths import get_active_profile

logger = logging.getLogger(__name__)


def check_db_integrity(db_path: Path) -> bool:
    """Vérifie l'intégrité physique d'une base SQLite (PRAGMA integrity_check)."""
    if not db_path.exists() or db_path.stat().st_size == 0:
        return False
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            res = cursor.execute("PRAGMA integrity_check(1);").fetchone()
            return bool(res and str(res[0]).strip().lower() == "ok")
    except Exception:
        return False


def backup_database(keep_last: int = 5) -> None:
    """
    Crée une copie de sécurité atomique de la base de données SQLite (compatible WAL mode).
    Conserve uniquement les `keep_last` fichiers les plus récents.
    """
    pm = ProfileManager()
    active_profile = get_active_profile()
    db_path: Path = pm.get_db_path(active_profile)

    if not db_path.exists():
        logger.warning("Fichier de base de données introuvable (%s), sauvegarde ignorée.", db_path)
        return

    backup_dir = pm.PROFILES_DIR / active_profile / "backups"
    backup_dir.mkdir(exist_ok=True, parents=True)

    # Création du nom de fichier avec horodatage
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"ankiforge_backup_{timestamp}.db"

    try:
        # Sauvegarde atomique en ligne compatible mode WAL
        try:
            with sqlite3.connect(str(db_path)) as src_conn:
                with contextlib.suppress(Exception):
                    src_conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
                with sqlite3.connect(str(backup_file)) as dst_conn:
                    src_conn.backup(dst_conn)
        except Exception:
            # Repli par copie physique si la connexion SQLite échoue
            shutil.copy2(db_path, backup_file)

        file_size = backup_file.stat().st_size if backup_file.exists() else 0
        logger.info(
            "Sauvegarde de la base de données créée : %s (%d octets) pour le profil '%s'",
            backup_file.name,
            file_size,
            active_profile,
        )

        # Rotation : Nettoyage des anciennes sauvegardes
        backups = sorted(backup_dir.glob("ankiforge_backup_*.db"))
        if len(backups) > keep_last:
            for old_backup in backups[:-keep_last]:
                try:
                    old_backup.unlink()
                    logger.info("Ancienne sauvegarde supprimée (rotation) : %s", old_backup.name)
                except OSError as err:
                    logger.warning(
                        "Impossible de supprimer l'ancienne sauvegarde %s (fichier verrouillé) : %s",
                        old_backup.name,
                        err,
                    )

    except Exception as e:
        logger.error("Échec critique de la sauvegarde de la base de données : %s", e, exc_info=True)


def restore_latest_valid_backup(profile_name: str) -> bool:
    """
    Restaure la sauvegarde la plus récente et saine pour un profil donné en cas de corruption SQLite.
    Isole automatiquement la base corrompue sous un nom horodaté 'ankiforge_corrupt_<timestamp>.db'.
    """
    pm = ProfileManager()
    db_path = pm.get_db_path(profile_name)
    backup_dir = pm.PROFILES_DIR / profile_name / "backups"
    if not backup_dir.exists():
        logger.error("Dossier de sauvegardes inexistant pour le profil '%s'.", profile_name)
        return False

    backups = sorted(backup_dir.glob("ankiforge_backup_*.db"), reverse=True)
    valid_backup: Path | None = None
    for b in backups:
        if check_db_integrity(b):
            valid_backup = b
            break

    if not valid_backup:
        logger.error("Aucune sauvegarde saine trouvée pour le profil '%s'.", profile_name)
        return False

    try:
        # 1. Mise en quarantaine de sécurité de la base corrompue actuelle
        if db_path.exists():
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            quarantine_path = db_path.parent / f"ankiforge_corrupt_{timestamp}.db"
            try:
                shutil.copy2(db_path, quarantine_path)
                logger.warning("Base corrompue mise en quarantaine sous '%s'.", quarantine_path.name)
            except Exception as q_err:
                logger.warning("Impossible de mettre en quarantaine la base corrompue: %s", q_err)

        # 2. Supprimer les éventuels fichiers WAL/SHM orphelins
        Path(f"{db_path}-wal").unlink(missing_ok=True)
        Path(f"{db_path}-shm").unlink(missing_ok=True)

        # 3. Restauration depuis la sauvegarde saine
        shutil.copy2(valid_backup, db_path)
        logger.info(
            "Base de données du profil '%s' restaurée avec succès depuis la sauvegarde '%s'.",
            profile_name,
            valid_backup.name,
        )
        return True
    except Exception as e:
        logger.critical("Échec de la restauration de secours pour le profil '%s': %s", profile_name, e, exc_info=True)
        return False
