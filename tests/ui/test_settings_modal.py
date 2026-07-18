from ankiforge.ui.widgets.settings_modal import SettingsModal


def test_settings_modal_creation(qtbot):
    modal = SettingsModal(ai_manager=None)
    qtbot.addWidget(modal)
    assert modal is not None
