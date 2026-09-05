import logging
import shutil
from pathlib import Path

from ankiforge.database.models import db
from ankiforge.utils.paths import get_app_data_dir, set_active_profile

logger = logging.getLogger(__name__)


class _ProfileManagerMeta(type):
    _custom_profiles_dir: Path | None = None

    @property
    def PROFILES_DIR(cls) -> Path:
        """Retourne dynamiquement le dossier des profils pour la classe."""
        if cls._custom_profiles_dir is not None:
            return cls._custom_profiles_dir
        return get_app_data_dir() / "profiles"

    @PROFILES_DIR.setter
    def PROFILES_DIR(cls, val: object) -> None:
        if isinstance(val, str | Path):
            cls._custom_profiles_dir = Path(val)
        else:
            cls._custom_profiles_dir = None

    @PROFILES_DIR.deleter
    def PROFILES_DIR(cls) -> None:
        cls._custom_profiles_dir = None


class ProfileManager(metaclass=_ProfileManagerMeta):
    """Gère les profils isolés. Chaque profil = 1 DB + 1 dossier médias."""

    _custom_instance_dir: Path | None = None

    @property
    def profiles_dir(self) -> Path:
        """Retourne dynamiquement le dossier des profils pour l'instance."""
        if self._custom_instance_dir is not None:
            return self._custom_instance_dir
        if ProfileManager._custom_profiles_dir is not None:
            return ProfileManager._custom_profiles_dir
        return get_app_data_dir() / "profiles"

    @profiles_dir.setter
    def profiles_dir(self, val: object) -> None:
        if isinstance(val, str | Path):
            self._custom_instance_dir = Path(val)
        else:
            self._custom_instance_dir = None

    @profiles_dir.deleter
    def profiles_dir(self) -> None:
        self._custom_instance_dir = None

    @property
    def PROFILES_DIR(self) -> Path:
        """Alias rétrocompatible vers profiles_dir."""
        return self.profiles_dir

    @PROFILES_DIR.setter
    def PROFILES_DIR(self, val: object) -> None:
        self.profiles_dir = val

    @PROFILES_DIR.deleter
    def PROFILES_DIR(self) -> None:
        self.profiles_dir = None

    def list_profiles(self) -> list[str]:
        """Retourne la liste des noms de profils existants."""
        if not self.profiles_dir.exists():
            return []
        return [p.name for p in self.profiles_dir.iterdir() if p.is_dir()]

    def create_profile(self, name: str) -> Path:
        """Crée ~/.ankiforge[-dev]/profiles/<name>/ankiforge.db + media/"""
        logger.info("Création d'un nouveau profil utilisateur : '%s'", name)
        profile_dir = self.profiles_dir / name
        profile_dir.mkdir(parents=True, exist_ok=True)

        media_dir = profile_dir / "media"
        media_dir.mkdir(exist_ok=True)

        return profile_dir

    def delete_profile(self, name: str) -> None:
        """Supprime un profil et toutes ses données."""
        logger.info("Suppression définitive du profil utilisateur : '%s'", name)
        profile_dir = self.profiles_dir / name
        if profile_dir.exists():
            shutil.rmtree(profile_dir)

    def get_db_path(self, profile_name: str) -> Path:
        """Retourne ~/.ankiforge[-dev]/profiles/<profile_name>/ankiforge.db"""
        return self.profiles_dir / profile_name / "ankiforge.db"

    def get_media_dir(self, profile_name: str) -> Path:
        """Retourne le chemin du dossier médias pour un profil donné."""
        return self.profiles_dir / profile_name / "media"

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

    def clone_production_to_development(self, copy_media: bool = True) -> tuple[int, int]:
        """Clone la base de données et les médias de production vers l'environnement de développement."""
        from ankiforge.utils.environment import clone_production_data_to_development

        return clone_production_data_to_development(copy_media=copy_media)
