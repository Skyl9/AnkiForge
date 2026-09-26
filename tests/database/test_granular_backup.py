import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from ankiforge.database.backup import (
    check_db_integrity,
    create_prerestore_backup,
    list_profile_backups,
    restore_granular_backup,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def fake_profile_env(tmp_path: Path):
    profiles_dir = tmp_path / "profiles"
    profile_name = "test_granular"
    profile_dir = profiles_dir / profile_name
    backup_dir = profile_dir / "backups"
    backup_dir.mkdir(parents=True)

    active_db = profile_dir / "ankiforge.db"
    conn = sqlite3.connect(str(active_db))
    conn.execute("CREATE TABLE users (id int, name text);")
    conn.execute("INSERT INTO users VALUES (1, 'Alice');")
    conn.commit()
    conn.close()

    return {
        "profiles_dir": profiles_dir,
        "profile_name": profile_name,
        "profile_dir": profile_dir,
        "backup_dir": backup_dir,
        "active_db": active_db,
    }


def test_list_profile_backups(fake_profile_env):
    backup_dir = fake_profile_env["backup_dir"]
    profile_name = fake_profile_env["profile_name"]
    profiles_dir = fake_profile_env["profiles_dir"]

    # Création d'une sauvegarde saine
    b1 = backup_dir / "ankiforge_backup_20260901_100000.db"
    conn = sqlite3.connect(str(b1))
    conn.execute("CREATE TABLE t1 (id int);")
    conn.commit()
    conn.close()

    # Création d'une sauvegarde pré-restauration
    b2 = backup_dir / "ankiforge_backup_prerestore_20260902_120000.db"
    conn = sqlite3.connect(str(b2))
    conn.execute("CREATE TABLE t2 (id int);")
    conn.commit()
    conn.close()

    # Création d'une sauvegarde corrompue
    b3 = backup_dir / "ankiforge_backup_20260903_140000.db"
    b3.write_text("CORRUPTED BYTES")

    with patch("ankiforge.database.backup.ProfileManager.PROFILES_DIR", profiles_dir):
        backups = list_profile_backups(profile_name)
        assert len(backups) == 3
        # Classé du plus récent au plus ancien
        assert backups[0].filename == b3.name
        assert backups[0].is_valid is False
        assert backups[0].is_prerestore is False

        assert backups[1].filename == b2.name
        assert backups[1].is_valid is True
        assert backups[1].is_prerestore is True

        assert backups[2].filename == b1.name
        assert backups[2].is_valid is True
        assert backups[2].is_prerestore is False


def test_create_prerestore_backup(fake_profile_env):
    profile_name = fake_profile_env["profile_name"]
    profiles_dir = fake_profile_env["profiles_dir"]
    active_db = fake_profile_env["active_db"]

    with (
        patch("ankiforge.database.backup.ProfileManager.PROFILES_DIR", profiles_dir),
        patch("ankiforge.database.backup.ProfileManager.get_db_path", return_value=active_db),
    ):
        prerestore_path = create_prerestore_backup(profile_name)
        assert prerestore_path is not None
        assert prerestore_path.exists()
        assert "prerestore" in prerestore_path.name
        assert check_db_integrity(prerestore_path) is True


def test_restore_granular_backup_success(fake_profile_env):
    profile_name = fake_profile_env["profile_name"]
    profiles_dir = fake_profile_env["profiles_dir"]
    backup_dir = fake_profile_env["backup_dir"]
    active_db = fake_profile_env["active_db"]

    # Créer un backup à restaurer contenant Bob au lieu d'Alice
    backup_target = backup_dir / "ankiforge_backup_20260901_000000.db"
    conn = sqlite3.connect(str(backup_target))
    conn.execute("CREATE TABLE users (id int, name text);")
    conn.execute("INSERT INTO users VALUES (2, 'Bob');")
    conn.commit()
    conn.close()

    # Créer des fichiers temporaires WAL/SHM fantômes
    wal_file = Path(f"{active_db}-wal")
    shm_file = Path(f"{active_db}-shm")
    wal_file.write_text("wal data")
    shm_file.write_text("shm data")

    with (
        patch("ankiforge.database.backup.ProfileManager.PROFILES_DIR", profiles_dir),
        patch("ankiforge.database.backup.ProfileManager.get_db_path", return_value=active_db),
    ):
        success = restore_granular_backup(profile_name, backup_target.name, create_safety_snapshot=True)
        assert success is True

        # Les fichiers WAL/SHM doivent avoir été nettoyés
        assert not wal_file.exists()
        assert not shm_file.exists()

        # La base active doit maintenant contenir Bob
        with sqlite3.connect(str(active_db)) as check_conn:
            res = check_conn.execute("SELECT name FROM users WHERE id=2;").fetchone()
            assert res is not None
            assert res[0] == "Bob"

        # Une sauvegarde pré-restauration doit avoir été créée
        prerestore_files = list(backup_dir.glob("ankiforge_backup_prerestore_*.db"))
        assert len(prerestore_files) == 1


def test_restore_granular_backup_fails_on_corrupted_file(fake_profile_env):
    profile_name = fake_profile_env["profile_name"]
    profiles_dir = fake_profile_env["profiles_dir"]
    backup_dir = fake_profile_env["backup_dir"]
    active_db = fake_profile_env["active_db"]

    corrupt_file = backup_dir / "ankiforge_backup_corrupt.db"
    corrupt_file.write_text("NOT VALID SQLITE")

    with (
        patch("ankiforge.database.backup.ProfileManager.PROFILES_DIR", profiles_dir),
        patch("ankiforge.database.backup.ProfileManager.get_db_path", return_value=active_db),
    ):
        success = restore_granular_backup(profile_name, corrupt_file.name, create_safety_snapshot=True)
        assert success is False

        # La base active contient toujours Alice
        with sqlite3.connect(str(active_db)) as check_conn:
            res = check_conn.execute("SELECT name FROM users WHERE id=1;").fetchone()
            assert res is not None
            assert res[0] == "Alice"
