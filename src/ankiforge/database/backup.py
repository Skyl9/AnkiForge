import datetime
import logging
from pathlib import Path
import shutil

from ankiforge.services.profile_manager import ProfileManager
from ankiforge.utils.paths import get_active_profile

logger = logging.getLogger(__name__)


def backup_database(keep_last: int = 5) -> None:
    """
    Crée une copie de sécurité de la base de données SQLite.
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
        # Copie physique du fichier SQLite
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
