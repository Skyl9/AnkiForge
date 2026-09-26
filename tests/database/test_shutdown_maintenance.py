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
