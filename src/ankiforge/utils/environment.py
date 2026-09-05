"""
Gestion des Environnements d'Exécution d'AnkiForge (Développement vs Production vs Test).
Garantit le cloisonnement strict :
- Base de données SQLite et profils
- Fichiers multimédias et sauvegardes
- Paramètres système QSettings
- Fichiers de journalisation (logs) et rapports de crash
- Index vectoriels FAISS et cache
- Configuration de l'Auto-Updater
"""

from __future__ import annotations

import enum
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QSettings

logger = logging.getLogger(__name__)


class AppEnvironment(enum.StrEnum):
    """Environnements d'exécution supportés par AnkiForge."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"


_current_env: AppEnvironment | None = None


def set_environment(env: AppEnvironment | str) -> None:
    """Force l'environnement d'exécution actif."""
    global _current_env
    if isinstance(env, str):
        env_clean = env.strip().lower()
        if env_clean in ("dev", "development"):
            _current_env = AppEnvironment.DEVELOPMENT
        elif env_clean in ("prod", "production"):
            _current_env = AppEnvironment.PRODUCTION
        elif env_clean in ("test", "testing"):
            _current_env = AppEnvironment.TESTING
        else:
            raise ValueError(f"Environnement inconnu : '{env}' (valeurs acceptées : dev, prod, test)")
    else:
        _current_env = env

    os.environ["ANKIFORGE_ENV"] = _current_env.value
    logger.debug("Environnement AnkiForge défini sur : %s", _current_env.value)


def get_current_environment() -> AppEnvironment:
    """
    Détermine l'environnement d'exécution actif selon la hiérarchie de priorité :
    1. État forcé en mémoire via set_environment().
    2. Variable d'environnement explicite ANKIFORGE_ENV (development | production | testing).
    3. Environnement pytest actif (PYTEST_CURRENT_TEST ou 'pytest' dans sys.modules).
    4. Drapeaux CLI (--dev | --prod | --test).
    5. Exécutable binaire gelé (Nuitka standalone ou PyInstaller) -> PRODUCTION.
    6. Exécution depuis les sources Python (workspace développeur) -> DEVELOPMENT.
    """
    global _current_env
    if _current_env is not None:
        return _current_env

    # 1. Variable d'environnement explicite
    env_var = os.environ.get("ANKIFORGE_ENV", "").strip().lower()
    if env_var in ("dev", "development"):
        _current_env = AppEnvironment.DEVELOPMENT
        return _current_env
    if env_var in ("prod", "production"):
        _current_env = AppEnvironment.PRODUCTION
        return _current_env
    if env_var in ("test", "testing"):
        _current_env = AppEnvironment.TESTING
        return _current_env

    # 2. Drapeaux CLI (--dev | --prod | --test)
    if "--dev" in sys.argv:
        _current_env = AppEnvironment.DEVELOPMENT
        return _current_env
    if "--prod" in sys.argv:
        _current_env = AppEnvironment.PRODUCTION
        return _current_env
    if "--test" in sys.argv:
        _current_env = AppEnvironment.TESTING
        return _current_env

    # 3. Environnement de test (pytest actif)
    if "PYTEST_CURRENT_TEST" in os.environ:
        _current_env = AppEnvironment.TESTING
        return _current_env

    # 4. Exécutable binaire compilé ou bundle gelé -> Production
    if getattr(sys, "frozen", False) or "__compiled__" in globals() or "__compiled__" in sys.modules:
        _current_env = AppEnvironment.PRODUCTION
        return _current_env

    # 5. Défaut : Exécution depuis les sources Python -> Développement
    _current_env = AppEnvironment.DEVELOPMENT
    return _current_env


def is_development() -> bool:
    """Indique si l'application s'exécute en mode développement."""
    return get_current_environment() == AppEnvironment.DEVELOPMENT


def is_production() -> bool:
    """Indique si l'application s'exécute en mode production."""
    return get_current_environment() == AppEnvironment.PRODUCTION


def is_testing() -> bool:
    """Indique si l'application s'exécute en mode test unitaire ou d'intégration."""
    return get_current_environment() == AppEnvironment.TESTING


def get_environment_display_name() -> str:
    """Retourne une désignation lisible pour l'interface utilisateur."""
    env = get_current_environment()
    if env == AppEnvironment.DEVELOPMENT:
        return "Développement"
    elif env == AppEnvironment.TESTING:
        return "Test"
    return "Production"


def get_settings_org_name() -> str:
    """Retourne le nom d'organisation QSettings pour l'environnement actif."""
    env = get_current_environment()
    if env == AppEnvironment.DEVELOPMENT:
        return "AnkiForgeOrg-Dev"
    elif env == AppEnvironment.TESTING:
        return "AnkiForgeOrg-Test"
    return "AnkiForgeOrg"


def get_settings_app_name() -> str:
    """Retourne le nom d'application QSettings pour l'environnement actif."""
    env = get_current_environment()
    if env == AppEnvironment.DEVELOPMENT:
        return "AnkiForge-Dev"
    elif env == AppEnvironment.TESTING:
        return "AnkiForge-Test"
    return "AnkiForge"


def get_app_qsettings(scope: str | None = None) -> QSettings:
    """
    Instancie et retourne un objet QSettings configuré pour l'environnement actif.
    Permet d'isoler hermétiquement les préférences OS entre Dev, Prod et Test.
    """
    from PySide6.QtCore import QSettings

    org = get_settings_org_name()
    app = get_settings_app_name()
    if scope:
        app = f"{app}_{scope}"
    return QSettings(org, app)


def clone_production_data_to_development(copy_media: bool = True) -> tuple[int, int]:
    """
    Copie de manière sécurisée les profils et bases SQLite de production (~/.ankiforge/profiles/)
    vers l'environnement de développement (~/.ankiforge-dev/profiles/).

    Returns:
        tuple[int, int]: (nombre de profils clonés, nombre de fichiers médias copiés).
    """
    prod_dir = Path.home() / ".ankiforge" / "profiles"
    dev_dir = Path.home() / ".ankiforge-dev" / "profiles"

    if not prod_dir.exists():
        logger.warning("Aucun profil de production trouvé dans %s", prod_dir)
        return (0, 0)

    dev_dir.mkdir(parents=True, exist_ok=True)
    cloned_profiles = 0
    copied_media_count = 0

    for profile_path in prod_dir.iterdir():
        if not profile_path.is_dir():
            continue

        target_profile_dir = dev_dir / profile_path.name
        target_profile_dir.mkdir(parents=True, exist_ok=True)

        # 1. Copie de la base de données
        prod_db = profile_path / "ankiforge.db"
        if prod_db.exists():
            shutil.copy2(prod_db, target_profile_dir / "ankiforge.db")
            cloned_profiles += 1

        # 2. Copie optionnelle des médias
        if copy_media:
            prod_media = profile_path / "media"
            dev_media = target_profile_dir / "media"
            if prod_media.exists() and prod_media.is_dir():
                dev_media.mkdir(parents=True, exist_ok=True)
                for media_file in prod_media.iterdir():
                    if media_file.is_file():
                        shutil.copy2(media_file, dev_media / media_file.name)
                        copied_media_count += 1

    logger.info(
        "Clonage Prod -> Dev achevé : %d profil(s) et %d média(s) copiés vers %s",
        cloned_profiles,
        copied_media_count,
        dev_dir,
    )
    return (cloned_profiles, copied_media_count)
