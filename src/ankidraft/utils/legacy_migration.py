"""Migration automatique et transparente des données historiques AnkiForge vers AnkiDraft.

Ce module garantit qu'un utilisateur effectuant la mise à jour depuis AnkiForge ne perd
aucune de ses données (bases de données Peewee de profils, médias, thèmes, outils d'IA et
préférences QSettings), tout en préservant intacte l'arborescence source pour la sécurité.
"""

from __future__ import annotations

import datetime
import logging
import os
import shutil
from pathlib import Path

from PySide6.QtCore import QSettings

logger = logging.getLogger(__name__)

MIGRATION_MARKER_FILE = ".migrated_from_ankiforge"


def resolve_legacy_app_data_dir() -> Path:
    """Résout le chemin du dossier de données legacy d'AnkiForge selon l'environnement actif.

    Returns:
        Objet Path pointant vers ~/.ankiforge[-dev/-test].
    """
    from ankidraft.utils.environment import AppEnvironment, get_current_environment

    custom_dir = os.environ.get("ANKIFORGE_DATA_DIR")
    if custom_dir:
        return Path(custom_dir)

    env = get_current_environment()
    if env == AppEnvironment.DEVELOPMENT:
        return Path.home() / ".ankiforge-dev"
    elif env == AppEnvironment.TESTING:
        return Path.home() / ".ankiforge-test"
    return Path.home() / ".ankiforge"


def migrate_legacy_data(target_dir: Path | None = None, legacy_dir: Path | None = None) -> bool:
    """Migre de manière non destructive les données existantes d'AnkiForge vers AnkiDraft.

    Opérations effectuées :
    1. Vérification de l'existence du dossier legacy et absence de migration préalable.
    2. Copie des profils avec renommage transparent de `ankiforge.db` en `ankidraft.db`.
    3. Copie des dossiers médias, staging, artefacts et sauvegardes.
    4. Copie des thèmes personnalisés, modèles d'IA et variables d'environnement.
    5. Dépôt d'un marqueur d'idempotence et d'un fichier informatif dans l'ancien dossier.

    Args:
        target_dir: Dossier cible AnkiDraft (défaut : get_app_data_dir()).
        legacy_dir: Dossier source AnkiForge (défaut : resolve_legacy_app_data_dir()).

    Returns:
        True si une migration a été effectuée, False si ignorée (déjà migrée ou source absente).
    """
    if legacy_dir is None:
        legacy_dir = resolve_legacy_app_data_dir()

    if not legacy_dir.is_dir():
        logger.debug("Aucun dossier legacy AnkiForge trouvé (%s), migration ignorée.", legacy_dir)
        return False

    if target_dir is None:
        from ankidraft.utils.paths import get_app_data_dir

        target_dir = get_app_data_dir()

    # 1. Contrôle d'idempotence : marqueur déjà présent
    marker_path = target_dir / MIGRATION_MARKER_FILE
    if marker_path.exists():
        logger.debug("Migration déjà actée par le marqueur %s.", marker_path)
        return False

    # 2. Contrôle de présence : si la cible contient déjà des profils avec ankidraft.db, ne rien écraser
    target_profiles = target_dir / "profiles"
    if target_profiles.exists():
        has_initialized_profile = any((p / "ankidraft.db").is_file() for p in target_profiles.iterdir() if p.is_dir())
        if has_initialized_profile:
            logger.info("Le dossier cible %s possède déjà des profils initialisés, migration legacy ignorée.", target_dir)
            try:
                marker_path.write_text(f"Skipped on {datetime.datetime.now(datetime.UTC).isoformat()} - profiles present\n", encoding="utf-8")
            except OSError:
                pass
            return False

    logger.info("📦 Démarrage de la migration automatique des données d'AnkiForge vers AnkiDraft...")
    logger.info("Source legacy : %s | Cible : %s", legacy_dir, target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)
    migrated_profiles_count = 0
    migrated_media_count = 0

    try:
        # A. Migration des profils
        legacy_profiles_dir = legacy_dir / "profiles"
        if legacy_profiles_dir.is_dir():
            target_profiles.mkdir(parents=True, exist_ok=True)
            for profile_folder in legacy_profiles_dir.iterdir():
                if not profile_folder.is_dir():
                    continue

                profile_name = profile_folder.name
                dest_profile_dir = target_profiles / profile_name
                dest_profile_dir.mkdir(parents=True, exist_ok=True)

                # 1. Base de données principale
                legacy_db = profile_folder / "ankiforge.db"
                modern_db = profile_folder / "ankidraft.db"
                dest_modern_db = dest_profile_dir / "ankidraft.db"

                if modern_db.is_file():
                    shutil.copy2(modern_db, dest_modern_db)
                    migrated_profiles_count += 1
                elif legacy_db.is_file():
                    shutil.copy2(legacy_db, dest_modern_db)
                    migrated_profiles_count += 1
                    logger.info("Base de données du profil '%s' migrée : ankiforge.db -> ankidraft.db", profile_name)

                # 2. Médias du profil
                legacy_media = profile_folder / "media"
                if legacy_media.is_dir():
                    dest_media = dest_profile_dir / "media"
                    dest_media.mkdir(parents=True, exist_ok=True)
                    for item in legacy_media.iterdir():
                        if item.is_file():
                            shutil.copy2(item, dest_media / item.name)
                            migrated_media_count += 1

                # 3. Dossiers staging et artifacts
                for subfolder_name in ("staging", "artifacts"):
                    src_sub = profile_folder / subfolder_name
                    if src_sub.is_dir():
                        dest_sub = dest_profile_dir / subfolder_name
                        dest_sub.mkdir(parents=True, exist_ok=True)
                        for item in src_sub.iterdir():
                            if item.is_file():
                                shutil.copy2(item, dest_sub / item.name)

                # 4. Sauvegardes de profil (*_backup_*.db)
                for backup_file in profile_folder.glob("*_backup_*.db"):
                    if backup_file.is_file():
                        shutil.copy2(backup_file, dest_profile_dir / backup_file.name)

        # B. Migration de la bibliothèque de thèmes
        legacy_themes = legacy_dir / "themes"
        if legacy_themes.is_dir():
            dest_themes = target_dir / "themes"
            dest_themes.mkdir(parents=True, exist_ok=True)
            for theme_file in legacy_themes.iterdir():
                if theme_file.is_file() and theme_file.suffix.lower() == ".json":
                    shutil.copy2(theme_file, dest_themes / theme_file.name)

        # C. Migration des modèles et outils déportés (tools/)
        legacy_tools = legacy_dir / "tools"
        if legacy_tools.is_dir():
            dest_tools = target_dir / "tools"
            dest_tools.mkdir(parents=True, exist_ok=True)
            for tool_item in legacy_tools.iterdir():
                dest_item = dest_tools / tool_item.name
                if tool_item.is_file() and not dest_item.exists():
                    shutil.copy2(tool_item, dest_item)
                elif tool_item.is_dir() and not dest_item.exists():
                    shutil.copytree(tool_item, dest_item, dirs_exist_ok=True)

        # D. Migration du fichier d'environnement local .env
        legacy_env = legacy_dir / ".env"
        dest_env = target_dir / ".env"
        if legacy_env.is_file() and not dest_env.exists():
            shutil.copy2(legacy_env, dest_env)

        # E. Inscription du marqueur d'idempotence
        now_str = datetime.datetime.now(datetime.UTC).isoformat()
        marker_path.write_text(
            f"AnkiForge -> AnkiDraft migration completed at {now_str}\nProfiles migrated: {migrated_profiles_count}\nMedia files copied: {migrated_media_count}\n",
            encoding="utf-8",
        )

        # F. Fichier d'information laissé dans l'ancien répertoire
        notice_file = legacy_dir / "MIGRATED_TO_ANKIDRAFT.txt"
        notice_file.write_text(
            f"=== MIGRATION VERS ANKIDRAFT EFFECTUÉE ===\n\n"
            f"Date : {now_str}\n"
            f"Vos données AnkiForge ont été migrées avec succès vers le nouvel emplacement AnkiDraft :\n"
            f"  -> {target_dir}\n\n"
            f"Vos fichiers d'origine sous ce dossier restent intacts à titre d'archive de sécurité.\n",
            encoding="utf-8",
        )

        logger.info(
            "✅ Migration AnkiForge -> AnkiDraft réussie : %d profil(s), %d média(s) copiés vers %s",
            migrated_profiles_count,
            migrated_media_count,
            target_dir,
        )
        return True

    except Exception as err:
        logger.error("Erreur inattendue durant la migration des données AnkiForge : %s", err, exc_info=True)
        return False


SYSTEM_SETTING_PREFIXES = (
    "Apple",
    "NS",
    "AK",
    "KB_",
    "com/apple",
    "cloud",
    "_HI",
    "PKF",
    "NavPanel",
    "Country",
    "ContextMenuGesture",
    "shouldShowRSVPDataDetectors",
)


def is_app_setting_key(key: str) -> bool:
    """Ignore les clés système injectées automatiquement par l'OS (notamment macOS) dans QSettings."""
    return not key.startswith(SYSTEM_SETTING_PREFIXES)


def migrate_legacy_qsettings(
    legacy_org: str | None = None,
    legacy_app: str | None = None,
    target_org: str | None = None,
    target_app: str | None = None,
) -> bool:
    """Migre les préférences système QSettings d'AnkiForge vers AnkiDraft.

    Ne copie les clés que si le registre AnkiDraft est actuellement vierge.

    Args:
        legacy_org: Nom d'organisation AnkiForge (défaut : calculé selon l'environnement).
        legacy_app: Nom d'application AnkiForge (défaut : calculé selon l'environnement).
        target_org: Nom d'organisation AnkiDraft (défaut : calculé selon l'environnement).
        target_app: Nom d'application AnkiDraft (défaut : calculé selon l'environnement).

    Returns:
        True si des clés ont été copiées, False sinon.
    """
    from ankidraft.utils.environment import (
        AppEnvironment,
        get_current_environment,
        get_settings_app_name,
        get_settings_org_name,
    )

    if target_org is None:
        target_org = get_settings_org_name()
    if target_app is None:
        target_app = get_settings_app_name()

    if legacy_org is None:
        env = get_current_environment()
        if env == AppEnvironment.DEVELOPMENT:
            legacy_org = "AnkiForgeOrg-Dev"
        elif env == AppEnvironment.TESTING:
            legacy_org = "AnkiForgeOrg-Test"
        else:
            legacy_org = "AnkiForgeOrg"

    if legacy_app is None:
        env = get_current_environment()
        if env == AppEnvironment.DEVELOPMENT:
            legacy_app = "AnkiForge-Dev"
        elif env == AppEnvironment.TESTING:
            legacy_app = "AnkiForge-Test"
        else:
            legacy_app = "AnkiForge"

    target_settings = QSettings(target_org, target_app)

    # 1. Vérification sentinelle ou présence de clés applicatives existantes
    if target_settings.value("migration/legacy_settings_imported", False, type=bool):
        logger.debug("Préférences QSettings déjà migrées pour %s/%s.", target_org, target_app)
        return False

    existing_target_keys = [k for k in target_settings.allKeys() if is_app_setting_key(k)]
    if existing_target_keys:
        logger.debug("Les réglages applicatifs QSettings de %s/%s existent déjà, migration ignorée.", target_org, target_app)
        return False

    legacy_settings = QSettings(legacy_org, legacy_app)
    keys_to_migrate = [k for k in legacy_settings.allKeys() if is_app_setting_key(k)]
    if not keys_to_migrate:
        logger.debug("Aucune clé QSettings applicative trouvée dans %s/%s.", legacy_org, legacy_app)
        return False

    logger.info("Copie de %d préférence(s) QSettings depuis %s/%s vers %s/%s...", len(keys_to_migrate), legacy_org, legacy_app, target_org, target_app)
    copied_count = 0
    for key in keys_to_migrate:
        val = legacy_settings.value(key)
        target_settings.setValue(key, val)
        copied_count += 1

    target_settings.setValue("migration/legacy_settings_imported", True)
    target_settings.sync()
    logger.info("✅ Migration des préférences QSettings achevée avec succès (%d clés migrées).", copied_count)
    return True


def ensure_legacy_migration() -> None:
    """Point d'entrée unique de contrôle et migration transparente au démarrage de l'application."""
    try:
        migrate_legacy_data()
    except Exception as err:
        logger.warning("Échec non bloquant de migrate_legacy_data : %s", err)

    try:
        migrate_legacy_qsettings()
    except Exception as err:
        logger.warning("Échec non bloquant de migrate_legacy_qsettings : %s", err)
