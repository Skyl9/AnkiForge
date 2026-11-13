"""Tests unitaires pour la migration automatique des données legacy AnkiForge vers AnkiDraft."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QSettings

from ankidraft.utils.legacy_migration import (
    MIGRATION_MARKER_FILE,
    migrate_legacy_data,
    migrate_legacy_qsettings,
)


@pytest.mark.unit
def test_migrate_legacy_data_full_migration(tmp_path: Path) -> None:
    """Vérifie la migration complète et transparente d'une arborescence legacy AnkiForge."""
    legacy_dir = tmp_path / ".ankiforge"
    target_dir = tmp_path / ".ankidraft"

    # 1. Préparation de l'ancienne arborescence AnkiForge
    legacy_profiles = legacy_dir / "profiles"
    default_profile = legacy_profiles / "default"
    default_profile.mkdir(parents=True)

    # Création d'une base SQLite legacy avec table et données
    legacy_db = default_profile / "ankiforge.db"
    conn = sqlite3.connect(str(legacy_db))
    conn.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, name TEXT);")
    conn.execute("INSERT INTO test_data (name) VALUES ('carte_test_1');")
    conn.commit()
    conn.close()

    # Création de médias
    media_dir = default_profile / "media"
    media_dir.mkdir()
    (media_dir / "image1.png").write_text("fake_png_data", encoding="utf-8")

    # Création de thèmes et tools
    themes_dir = legacy_dir / "themes"
    themes_dir.mkdir()
    (themes_dir / "custom_dark.json").write_text("{}", encoding="utf-8")

    tools_dir = legacy_dir / "tools"
    tools_dir.mkdir()
    (tools_dir / "piper_model.onnx").write_text("model_bytes", encoding="utf-8")

    # 2. Exécution de la migration
    migrated = migrate_legacy_data(target_dir=target_dir, legacy_dir=legacy_dir)
    assert migrated is True

    # 3. Assertions sur le dossier cible
    target_db = target_dir / "profiles" / "default" / "ankidraft.db"
    assert target_db.is_file(), "La base de données doit avoir été renommée en ankidraft.db"

    # Vérification de l'intégrité de la base copiée
    target_conn = sqlite3.connect(str(target_db))
    rows = target_conn.execute("SELECT name FROM test_data").fetchall()
    assert rows == [("carte_test_1",)], "Les données SQLite doivent être préservées à l'identique"
    target_conn.close()

    # Vérification des médias et assets
    target_media = target_dir / "profiles" / "default" / "media" / "image1.png"
    assert target_media.is_file()
    assert target_media.read_text(encoding="utf-8") == "fake_png_data"

    assert (target_dir / "themes" / "custom_dark.json").is_file()
    assert (target_dir / "tools" / "piper_model.onnx").is_file()

    # Vérification du marqueur d'idempotence
    assert (target_dir / MIGRATION_MARKER_FILE).is_file()

    # Vérification du message d'information dans l'ancien dossier
    assert (legacy_dir / "MIGRATED_TO_ANKIDRAFT.txt").is_file()


@pytest.mark.unit
def test_migrate_legacy_data_idempotent(tmp_path: Path) -> None:
    """Vérifie que la migration est strictement idempotente et ne re-migre pas deux fois."""
    legacy_dir = tmp_path / ".ankiforge"
    target_dir = tmp_path / ".ankidraft"

    legacy_profiles = legacy_dir / "profiles" / "default"
    legacy_profiles.mkdir(parents=True)
    (legacy_profiles / "ankiforge.db").write_text("db_content", encoding="utf-8")

    # Premier passage
    assert migrate_legacy_data(target_dir=target_dir, legacy_dir=legacy_dir) is True

    # Deuxième passage immédiat
    assert migrate_legacy_data(target_dir=target_dir, legacy_dir=legacy_dir) is False


@pytest.mark.unit
def test_migrate_legacy_data_no_legacy_dir(tmp_path: Path) -> None:
    """Vérifie qu'aucun traitement n'est fait si le dossier legacy n'existe pas."""
    legacy_dir = tmp_path / ".ankiforge_nonexistent"
    target_dir = tmp_path / ".ankidraft"

    assert migrate_legacy_data(target_dir=target_dir, legacy_dir=legacy_dir) is False
    assert not target_dir.exists()


@pytest.mark.unit
def test_migrate_legacy_data_target_already_has_profiles(tmp_path: Path) -> None:
    """Vérifie que si target a déjà un profil existant, la migration legacy n'écrase rien."""
    legacy_dir = tmp_path / ".ankiforge"
    target_dir = tmp_path / ".ankidraft"

    (legacy_dir / "profiles" / "default").mkdir(parents=True)
    (legacy_dir / "profiles" / "default" / "ankiforge.db").write_text("old_db", encoding="utf-8")

    (target_dir / "profiles" / "default").mkdir(parents=True)
    (target_dir / "profiles" / "default" / "ankidraft.db").write_text("new_db", encoding="utf-8")

    assert migrate_legacy_data(target_dir=target_dir, legacy_dir=legacy_dir) is False
    # La DB existante n'a pas été écrasée
    assert (target_dir / "profiles" / "default" / "ankidraft.db").read_text(encoding="utf-8") == "new_db"


@pytest.mark.unit
def test_migrate_legacy_qsettings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie la migration transparente des préférences QSettings d'AnkiForge vers AnkiDraft."""
    test_scope = "unit_migration_test"

    legacy_settings = QSettings("AnkiForgeOrg-Test", f"AnkiForge-Test-{test_scope}")
    target_settings = QSettings("AnkiDraftOrg-Test", f"AnkiDraft-Test-{test_scope}")

    legacy_settings.clear()
    target_settings.clear()

    try:
        # 1. Écriture de réglages dans l'ancien QSettings AnkiForge
        legacy_settings.setValue("theme/active", "dracula")
        legacy_settings.setValue("profiles/default_startup_profile", "medecine")
        legacy_settings.setValue("window/maximized", True)
        legacy_settings.sync()

        # 2. Exécution de la migration QSettings
        migrated = migrate_legacy_qsettings(
            legacy_org="AnkiForgeOrg-Test",
            legacy_app=f"AnkiForge-Test-{test_scope}",
            target_org="AnkiDraftOrg-Test",
            target_app=f"AnkiDraft-Test-{test_scope}",
        )
        assert migrated is True

        # 3. Assertions sur le nouveau QSettings AnkiDraft
        assert target_settings.value("theme/active") == "dracula"
        assert target_settings.value("profiles/default_startup_profile") == "medecine"
        assert target_settings.value("window/maximized", type=bool) is True

        # 4. Deuxième appel : idempotent car target a déjà des clés
        assert (
            migrate_legacy_qsettings(
                legacy_org="AnkiForgeOrg-Test",
                legacy_app=f"AnkiForge-Test-{test_scope}",
                target_org="AnkiDraftOrg-Test",
                target_app=f"AnkiDraft-Test-{test_scope}",
            )
            is False
        )
    finally:
        legacy_settings.clear()
        target_settings.clear()


@pytest.mark.unit
def test_ensure_legacy_migration_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie que ensure_legacy_migration s'exécute de façon fail-safe même en cas d'erreur interne."""
    from ankidraft.utils.legacy_migration import ensure_legacy_migration

    # Simuler une exception dans migrate_legacy_data
    monkeypatch.setattr(
        "ankidraft.utils.legacy_migration.migrate_legacy_data",
        MagicMock(side_effect=RuntimeError("Erreur simulée")),
    )
    monkeypatch.setattr(
        "ankidraft.utils.legacy_migration.migrate_legacy_qsettings",
        MagicMock(side_effect=RuntimeError("Erreur simulée QSettings")),
    )

    # ensure_legacy_migration ne doit pas lever d'exception
    ensure_legacy_migration()


@pytest.mark.unit
def test_paths_get_app_data_dir_triggers_migration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie que paths.get_app_data_dir déclenche la migration si le dossier cible est nouveau."""
    import ankidraft.utils.paths as paths_mod

    legacy_dir = tmp_path / "legacy_custom"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "profiles" / "default").mkdir(parents=True)
    (legacy_dir / "profiles" / "default" / "ankiforge.db").write_text("migrated_content", encoding="utf-8")

    target_dir = tmp_path / "target_custom"
    # S'assurer que le dossier cible n'existe pas encore
    assert not target_dir.exists()

    monkeypatch.setenv("ANKIDRAFT_DATA_DIR", str(target_dir))
    monkeypatch.setenv("ANKIFORGE_DATA_DIR", str(legacy_dir))
    monkeypatch.setattr(paths_mod, "_legacy_migration_checked", False)

    resolved_dir = paths_mod.get_app_data_dir()
    assert resolved_dir == target_dir
    assert (target_dir / "profiles" / "default" / "ankidraft.db").is_file()
    assert (target_dir / "profiles" / "default" / "ankidraft.db").read_text(encoding="utf-8") == "migrated_content"
