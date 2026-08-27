import datetime
import logging
import shutil

from ankiforge.utils.paths import get_active_profile
from ankiforge.services.profile_manager import ProfileManager


def backup_database(keep_last: int = 5) -> None:
    """
    Crée une copie de sécurité de la base de données SQLite.
    Conserve uniquement les `keep_last` fichiers les plus récents.
    """
    pm = ProfileManager()
    active_profile = get_active_profile()
    db_path = pm.get_db_path(active_profile)

    if not db_path.exists():
        return

    backup_dir = pm.PROFILES_DIR / active_profile / "backups"
    backup_dir.mkdir(exist_ok=True, parents=True)

    # Création du nom de fichier avec horodatage
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"ankiforge_backup_{timestamp}.db"

    try:
        # Copie physique du fichier SQLite
        shutil.copy2(db_path, backup_file)
        logging.info(f"Sauvegarde de la base de données créée : {backup_file.name}")

        # Rotation : Nettoyage des anciennes sauvegardes
        backups = sorted(backup_dir.glob("ankiforge_backup_*.db"))
        if len(backups) > keep_last:
            for old_backup in backups[:-keep_last]:
                try:
                    old_backup.unlink()
                    logging.info(f"Ancienne sauvegarde supprimée : {old_backup.name}")
                except OSError:
                    pass  # Fichier potentiellement verrouillé, on l'ignorera

    except Exception as e:
        logging.error(f"Échec critique de la sauvegarde de la base de données : {e}")
