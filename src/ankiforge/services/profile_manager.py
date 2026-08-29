import logging
import shutil
from pathlib import Path

from ankiforge.database.models import db
from ankiforge.utils.paths import get_app_data_dir, set_active_profile

logger = logging.getLogger(__name__)


class ProfileManager:
    """Gère les profils isolés. Chaque profil = 1 DB + 1 dossier médias."""

    # Utilise le dossier de données de l'application (ex: .ankiforge/profiles)
    PROFILES_DIR = get_app_data_dir() / "profiles"

    def list_profiles(self) -> list[str]:
        """Retourne la liste des noms de profils existants."""
        if not self.PROFILES_DIR.exists():
            return []
        return [p.name for p in self.PROFILES_DIR.iterdir() if p.is_dir()]

    def create_profile(self, name: str) -> Path:
        """Crée ~/.ankiforge/profiles/<name>/ankiforge.db + media/"""
        logger.info("Création d'un nouveau profil utilisateur : '%s'", name)
        profile_dir = self.PROFILES_DIR / name
        profile_dir.mkdir(parents=True, exist_ok=True)

        media_dir = profile_dir / "media"
        media_dir.mkdir(exist_ok=True)

        return profile_dir

    def delete_profile(self, name: str) -> None:
        """Supprime un profil et toutes ses données."""
        logger.info("Suppression définitive du profil utilisateur : '%s'", name)
        profile_dir = self.PROFILES_DIR / name
        if profile_dir.exists():
            shutil.rmtree(profile_dir)

    def get_db_path(self, profile_name: str) -> Path:
        """Retourne ~/.ankiforge/profiles/<profile_name>/ankiforge.db"""
        return self.PROFILES_DIR / profile_name / "ankiforge.db"

    def get_media_dir(self, profile_name: str) -> Path:
        """Retourne le chemin du dossier médias pour un profil donné."""
        return self.PROFILES_DIR / profile_name / "media"

    def switch_profile(self, profile_name: str) -> None:
        """Ferme la DB courante, ouvre celle du nouveau profil."""
        if profile_name not in self.list_profiles():
            self.create_profile(profile_name)

        new_path = self.get_db_path(profile_name)
        logger.info("Basculement vers le profil : '%s' (DB: %s)", profile_name, new_path)

        if not db.is_closed():
            db.close()

        # Réinitialise la base de données Peewee avec le nouveau chemin
        db.init(str(new_path))

        set_active_profile(profile_name)

        try:
            from ankiforge.database.migration import run_migrations
            from ankiforge.database.models import init_db, seed_initial_data

            init_db()
            run_migrations()
            seed_initial_data()
            logger.info("Profil '%s' initialisé et prêt avec succès.", profile_name)
        except Exception as e:
            logger.critical(
                "Échec de l'initialisation ou des migrations pour le profil '%s' : %s",
                profile_name,
                e,
                exc_info=True,
            )
            raise
