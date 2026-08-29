from unittest.mock import MagicMock, patch

import pytest

from ankiforge.services.profile_manager import ProfileManager
from ankiforge.ui.main_window import MainWindow
from ankiforge.ui.widgets.profile_selector import ProfileSelectorDialog


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


def test_profile_selector_dialog_init(qtbot, mock_profiles_dir):
    pm = ProfileManager()
    pm.create_profile("profile_1")
    pm.create_profile("profile_2")

    dialog = ProfileSelectorDialog(["profile_1", "profile_2"], current_profile="profile_1")
    qtbot.addWidget(dialog)

    assert dialog.list_widget.count() == 2
    assert dialog.get_selected_profile() == "profile_1"
    assert not dialog.delete_btn.isEnabled()


def test_profile_selector_dialog_filter(qtbot, mock_profiles_dir):
    dialog = ProfileSelectorDialog(["medecine", "droit", "histoire"], current_profile="medecine")
    qtbot.addWidget(dialog)

    dialog.search_input.setText("droit")
    assert not dialog.list_widget.item(1).isHidden()
    assert dialog.list_widget.item(0).isHidden()
    assert dialog.list_widget.item(2).isHidden()


def test_profile_selector_dialog_create(qtbot, mock_profiles_dir):
    dialog = ProfileSelectorDialog(["default"], current_profile="default")
    qtbot.addWidget(dialog)

    dialog.new_profile_input.setText("nouveau_prof")
    dialog._on_create_profile()

    assert "nouveau_prof" in dialog.profiles
    assert dialog.selected_profile == "nouveau_prof"


def test_main_window_switch_profile(qtbot, mock_profiles_dir):
    ai_mock = MagicMock()
    window = MainWindow(ai_manager=ai_mock, profile_name="default")
    qtbot.addWidget(window)

    window.switch_to_profile("test_switch")
    assert window.profile_name == "test_switch"
    if window.sidebar:
        assert "test_switch" in window.sidebar.profile_name
