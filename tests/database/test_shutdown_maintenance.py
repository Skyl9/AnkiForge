import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from ankiforge.database.maintenance import execute_clean_shutdown, fast_wal_checkpoint_and_optimize

pytestmark = pytest.mark.integration


@pytest.fixture
def fake_shutdown_env(tmp_path: Path):
    profiles_dir = tmp_path / "profiles"
    profile_name = "test_shutdown"
    profile_dir = profiles_dir / profile_name
    profile_dir.mkdir(parents=True)
    media_dir = profile_dir / "media"
    media_dir.mkdir()

    active_db = profile_dir / "ankiforge.db"
    conn = sqlite3.connect(str(active_db))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("CREATE TABLE items (id int);")
    conn.execute("INSERT INTO items VALUES (42);")
    conn.commit()
    conn.close()

    return {
        "profiles_dir": profiles_dir,
        "profile_name": profile_name,
        "profile_dir": profile_dir,
        "media_dir": media_dir,
        "active_db": active_db,
    }


def test_fast_wal_checkpoint_and_optimize(fake_shutdown_env):
    active_db = fake_shutdown_env["active_db"]
    # Fast checkpoint should succeed without error
    fast_wal_checkpoint_and_optimize(active_db)
    assert active_db.exists()


def test_execute_clean_shutdown_without_media_cleaning(fake_shutdown_env):
    profile_name = fake_shutdown_env["profile_name"]
    profiles_dir = fake_shutdown_env["profiles_dir"]
    active_db = fake_shutdown_env["active_db"]

    with (
        patch("ankiforge.services.profile_manager.ProfileManager.PROFILES_DIR", profiles_dir),
        patch("ankiforge.services.profile_manager.ProfileManager.get_db_path", return_value=active_db),
    ):
        report = execute_clean_shutdown(profile_name=profile_name, clean_orphan_media=False)
        assert report["profile"] == profile_name
        assert report["wal_checkpoint"] is True
        assert report["orphan_media_cleaned"] == 0


def test_execute_clean_shutdown_with_media_cleaning(fake_shutdown_env):
    profile_name = fake_shutdown_env["profile_name"]
    profiles_dir = fake_shutdown_env["profiles_dir"]
    active_db = fake_shutdown_env["active_db"]
    media_dir = fake_shutdown_env["media_dir"]

    # Faux média orphelin sur disque
    orphan_file = media_dir / "orphan.png"
    orphan_file.write_bytes(b"image data")

    with (
        patch("ankiforge.services.profile_manager.ProfileManager.PROFILES_DIR", profiles_dir),
        patch("ankiforge.services.profile_manager.ProfileManager.get_db_path", return_value=active_db),
        patch("ankiforge.services.profile_manager.ProfileManager.get_media_dir", return_value=media_dir),
        patch("ankiforge.services.cards.media_manager.MediaManager.clean_orphan_media", return_value=1),
    ):
        report = execute_clean_shutdown(profile_name=profile_name, clean_orphan_media=True)
        assert report["wal_checkpoint"] is True
        assert report["orphan_media_cleaned"] == 1


def test_optimize_database_ferme_connexion(tmp_path: Path, monkeypatch):
    """optimize_database utilise contextlib.closing : aucune connexion SQLite ne reste ouverte (régression Windows)."""
    from ankiforge.database.maintenance import optimize_database

    db_path = tmp_path / "maint.db"
    seed = sqlite3.connect(str(db_path))
    seed.execute("CREATE TABLE t (id int);")
    seed.commit()
    seed.close()

    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def tracking_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr("ankiforge.database.maintenance.sqlite3.connect", tracking_connect)

    optimize_database(db_path)

    assert opened, "optimize_database doit ouvrir une connexion SQLite"
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1;")


def test_execute_clean_shutdown_wal_checkpoint_seulement_si_succes(fake_shutdown_env, monkeypatch):
    """report["wal_checkpoint"] ne passe à True que si le checkpoint WAL réussit réellement."""
    from ankiforge.database.maintenance import execute_clean_shutdown

    profile_name = fake_shutdown_env["profile_name"]
    profiles_dir = fake_shutdown_env["profiles_dir"]
    active_db = fake_shutdown_env["active_db"]

    monkeypatch.setattr(
        "ankiforge.database.maintenance.fast_wal_checkpoint_and_optimize",
        lambda _: False,
    )

    with (
        patch("ankiforge.services.profile_manager.ProfileManager.PROFILES_DIR", profiles_dir),
        patch("ankiforge.services.profile_manager.ProfileManager.get_db_path", return_value=active_db),
    ):
        report = execute_clean_shutdown(profile_name=profile_name, clean_orphan_media=False)
        assert report["profile"] == profile_name
        assert report["wal_checkpoint"] is False
        assert report["orphan_media_cleaned"] == 0


def test_execute_clean_shutdown_wal_checkpoint_vrai_quando_checkpoint_reussi(fake_shutdown_env, monkeypatch):
    """report["wal_checkpoint"] vaut True quand le checkpoint WAL rapporte succès."""
    from ankiforge.database.maintenance import execute_clean_shutdown

    profile_name = fake_shutdown_env["profile_name"]
    profiles_dir = fake_shutdown_env["profiles_dir"]
    active_db = fake_shutdown_env["active_db"]

    monkeypatch.setattr(
        "ankiforge.database.maintenance.fast_wal_checkpoint_and_optimize",
        lambda _: True,
    )

    with (
        patch("ankiforge.services.profile_manager.ProfileManager.PROFILES_DIR", profiles_dir),
        patch("ankiforge.services.profile_manager.ProfileManager.get_db_path", return_value=active_db),
    ):
        report = execute_clean_shutdown(profile_name=profile_name, clean_orphan_media=False)
        assert report["wal_checkpoint"] is True
