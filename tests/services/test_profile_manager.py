import pytest
from unittest.mock import patch
from ankiforge.services.profile_manager import ProfileManager


@pytest.fixture
def mock_profiles_dir(tmp_path):
    with patch("ankiforge.services.profile_manager.ProfileManager.PROFILES_DIR", tmp_path):
        yield tmp_path


def test_list_profiles_empty(mock_profiles_dir):
    pm = ProfileManager()
    assert pm.list_profiles() == []


def test_create_and_list_profile(mock_profiles_dir):
    pm = ProfileManager()
    pm.create_profile("test_prof")
    assert "test_prof" in pm.list_profiles()
    assert (mock_profiles_dir / "test_prof" / "media").exists()


def test_delete_profile(mock_profiles_dir):
    pm = ProfileManager()
    pm.create_profile("to_delete")
    pm.delete_profile("to_delete")
    assert "to_delete" not in pm.list_profiles()
