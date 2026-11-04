from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from ankiforge.database.base import db
from ankiforge.database.migration import run_migrations
from ankiforge.services.profile_manager import ProfileManager
from ankiforge.ui.main_window import MainWindow
from ankiforge.ui.widgets.profile_selector import ProfileSelectorDialog
from ankiforge.ui.widgets.profile_switch_overlay import ProfileSwitchOverlay

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


def _appliquer_toutes_les_migrations(pm: ProfileManager, profile_name: str) -> None:
    """Initialise pour de vrai une base de profil sur fichier (toutes les migrations)."""
    db_path = pm.get_db_path(profile_name)
    if not db.is_closed():
        db.close()
    db.init(str(db_path))
    db.connect()
    try:
        run_migrations()
    finally:
        db.close()


def test_is_db_ready_faux_pour_db_inexistante(mock_profiles_dir):
    pm = ProfileManager()
    db_path = pm.get_db_path("inexistant")
    assert not pm._is_db_ready(db_path)


def test_is_db_ready_faux_pour_db_vide(mock_profiles_dir):
    pm = ProfileManager()
    pm.create_profile("vide")
    db_path = pm.get_db_path("vide")
    assert not db_path.exists()
    assert not pm._is_db_ready(db_path)


def test_is_db_ready_faux_pour_db_sans_table_coeur(mock_profiles_dir):
    pm = ProfileManager()
    pm.create_profile("brute")
    db_path = pm.get_db_path("brute")
    db_path.write_bytes(b"ceci n'est pas une base sqlite valide")
    assert not pm._is_db_ready(db_path)


def test_is_db_ready_vrai_apres_migrations(mock_profiles_dir):
    pm = ProfileManager()
    profile = "ready_prof"
    pm.create_profile(profile)
    db_path = pm.get_db_path(profile)
    _appliquer_toutes_les_migrations(pm, profile)
    assert pm._is_db_ready(db_path) is True


def test_switch_profile_fast_path_ne_lance_pas_migrations_ni_seed(mock_profiles_dir):
    """Quand la base est déjà à jour, run_migrations/seed_initial_data ne doivent pas être appelés."""
    pm = ProfileManager()
    profile = "fast_path"
    pm.create_profile(profile)
    new_path = pm.get_db_path(profile)

    with (
        patch.object(ProfileManager, "_is_db_ready", return_value=True),
        patch("ankiforge.database.migration.run_migrations") as m_run,
        patch("ankiforge.database.models.seed_initial_data") as m_seed,
        patch("ankiforge.database.models.init_db") as m_init,
    ):
        pm.switch_profile(profile)
        m_run.assert_not_called()
        m_seed.assert_not_called()
        m_init.assert_not_called()
        assert db.database == str(new_path)


@pytest.mark.ui
def test_profile_switch_overlay_affiche_message_et_spinner(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)

    overlay = ProfileSwitchOverlay(parent, profile_name="Mon Espace")
    qtbot.addWidget(overlay)

    parent.show()
    QApplication.processEvents()

    assert overlay.isVisible()
    labels = [lbl.text() for lbl in overlay.findChildren(QLabel)]
    assert any("Changement de profil en cours" in t for t in labels)
    assert any("Mon Espace" in t for t in labels)
    assert overlay.spinner is not None

    overlay.close_overlay()
    QApplication.processEvents()
