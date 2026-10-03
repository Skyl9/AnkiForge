from unittest.mock import MagicMock, patch

import pytest

from ankiforge.services.profile_manager import ProfileManager
from ankiforge.ui.main_window import MainWindow
from ankiforge.ui.widgets.profile_selector import ProfileSelectorDialog

pytestmark = pytest.mark.integration


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


def test_list_profiles_is_stable_and_sorted(mock_profiles_dir):
    pm = ProfileManager()
    pm.create_profile("zeta")
    pm.create_profile("alpha")

    assert pm.list_profiles() == ["alpha", "zeta"]


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


def test_profile_selector_dialog_normalizes_current_profile(qtbot):
    dialog = ProfileSelectorDialog(["zeta", "alpha", "alpha"], current_profile="missing")
    qtbot.addWidget(dialog)

    assert dialog.profiles == ["alpha", "zeta"]
    assert dialog.get_selected_profile() == "alpha"
    assert dialog.list_widget.currentRow() == 0


def test_profile_selector_dialog_filter(qtbot, mock_profiles_dir):
    dialog = ProfileSelectorDialog(["medecine", "droit", "histoire"], current_profile="medecine")
    qtbot.addWidget(dialog)

    dialog.search_input.setText("droit")
    assert not dialog.list_widget.item(0).isHidden()
    assert dialog.list_widget.item(1).isHidden()
    assert dialog.list_widget.item(2).isHidden()


def test_profile_selector_dialog_create(qtbot, mock_profiles_dir):
    dialog = ProfileSelectorDialog(["default"], current_profile="default")
    qtbot.addWidget(dialog)

    dialog.new_profile_input.setText("nouveau_prof")
    dialog._on_create_profile()

    assert "nouveau_prof" in dialog.profiles
    assert dialog.selected_profile == "nouveau_prof"


@pytest.mark.ui
@pytest.mark.parametrize(
    ("is_startup", "expected_cancel", "expected_select", "expected_tip_keyword"),
    [
        (False, "Annuler", "Basculer vers cet Espace", "Fermer"),
        (True, "Quitter", "Ouvrir cet Espace", "Quitter"),
    ],
)
def test_profile_selector_dialog_semantics(qtbot, is_startup, expected_cancel, expected_select, expected_tip_keyword):
    dialog = ProfileSelectorDialog(["default", "work"], current_profile="default", is_startup=is_startup)
    qtbot.addWidget(dialog)

    assert dialog.is_startup is is_startup
    assert dialog.btn_cancel.text() == expected_cancel
    assert dialog.btn_select.text() == expected_select
    assert expected_tip_keyword in dialog.btn_cancel.toolTip()


@pytest.mark.ui
def test_profile_selector_dialog_secondary_actions_bar(qtbot):
    dialog = ProfileSelectorDialog(["default", "work"], current_profile="default")
    qtbot.addWidget(dialog)

    assert hasattr(dialog, "delete_btn")
    assert hasattr(dialog, "btn_transfer")
    assert "Supprimer" in dialog.delete_btn.text()
    assert "Transférer" in dialog.btn_transfer.text()
    assert dialog.delete_btn.property("density") == "compact"
    assert dialog.btn_transfer.property("density") == "compact"

    # Vérification que le pied de boîte (dernier item du layout) ne contient que les boutons de décision
    main_layout = dialog.layout()
    assert main_layout is not None
    bottom_item = main_layout.itemAt(main_layout.count() - 1)
    bottom_layout = bottom_item.layout()
    assert bottom_layout is not None

    bottom_widgets = [bottom_layout.itemAt(i).widget() for i in range(bottom_layout.count()) if bottom_layout.itemAt(i).widget()]
    assert dialog.delete_btn not in bottom_widgets
    assert dialog.btn_transfer not in bottom_widgets
    assert dialog.btn_cancel in bottom_widgets
    assert dialog.btn_select in bottom_widgets


@pytest.mark.slow
def test_main_window_switch_profile(qtbot, mock_profiles_dir):
    ai_mock = MagicMock()
    window = MainWindow(ai_manager=ai_mock, profile_name="default")
    qtbot.addWidget(window)

    window.switch_to_profile("test_switch")
    assert window.profile_name == "test_switch"
    if window.sidebar:
        assert "test_switch" in window.sidebar.profile_name
