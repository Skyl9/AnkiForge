import os
from unittest.mock import patch

import pytest

from ankiforge.services.profile_lock_service import ProfileLockService, is_pid_alive


@pytest.fixture
def temp_profiles_dir(tmp_path):
    return tmp_path / "profiles"


def test_acquire_and_release_lock(temp_profiles_dir):
    profile = "test_profile"
    acquired, lock_info = ProfileLockService.acquire_lock(profile, profiles_dir=temp_profiles_dir)
    assert acquired is True
    assert lock_info is None

    # is_locked should report locked
    locked, info = ProfileLockService.is_locked(profile, profiles_dir=temp_profiles_dir)
    assert locked is True
    assert info is not None
    assert info.pid == os.getpid()

    # Release lock
    ProfileLockService.release_lock(profile)
    locked, info = ProfileLockService.is_locked(profile, profiles_dir=temp_profiles_dir)
    assert locked is False
    assert info is None


def test_conflict_when_profile_already_locked(temp_profiles_dir):
    profile = "user1"
    # Acquire with first handler
    lock_path = ProfileLockService.get_lock_file_path(profile, profiles_dir=temp_profiles_dir)
    from PySide6.QtCore import QLockFile

    external_lock = QLockFile(str(lock_path))
    assert external_lock.tryLock(100) is True

    try:
        # ProfileLockService attempts to acquire
        acquired, lock_info = ProfileLockService.acquire_lock(profile, profiles_dir=temp_profiles_dir)
        assert acquired is False
        assert lock_info is not None
        assert lock_info.pid == os.getpid()
    finally:
        external_lock.unlock()


def test_stale_lock_auto_recovery(temp_profiles_dir):
    profile = "crashed_profile"
    lock_path = ProfileLockService.get_lock_file_path(profile, profiles_dir=temp_profiles_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # Write a fake lock file with a non-existent PID
    fake_dead_pid = 999999
    with open(lock_path, "w", encoding="utf-8") as f:
        f.write(f"{fake_dead_pid}\npytest\nhost\n")

    # Should detect dead PID and auto-recover
    with patch("ankiforge.services.profile_lock_service.is_pid_alive", return_value=False):
        acquired, lock_info = ProfileLockService.acquire_lock(profile, profiles_dir=temp_profiles_dir)
        assert acquired is True
        assert lock_info is None

        # Clean release
        ProfileLockService.release_lock(profile)


def test_release_all_locks(temp_profiles_dir):
    p1 = "prof_a"
    p2 = "prof_b"
    assert ProfileLockService.acquire_lock(p1, profiles_dir=temp_profiles_dir)[0] is True
    assert ProfileLockService.acquire_lock(p2, profiles_dir=temp_profiles_dir)[0] is True

    ProfileLockService.release_all_locks()

    assert ProfileLockService.is_locked(p1, profiles_dir=temp_profiles_dir)[0] is False
    assert ProfileLockService.is_locked(p2, profiles_dir=temp_profiles_dir)[0] is False


def test_is_pid_alive():
    assert is_pid_alive(os.getpid()) is True
    assert is_pid_alive(-1) is False
    assert is_pid_alive(99999999) is False
