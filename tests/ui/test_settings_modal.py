from ankiforge.ui.widgets.settings_modal import (
    AIEnginesTab,
    GeneralTab,
    MaintenanceTab,
    SettingsModal,
    StatisticsTab,
)


def test_settings_modal_creation_and_tabs(qtbot):
    modal = SettingsModal()
    qtbot.addWidget(modal)
    assert modal is not None

    assert isinstance(modal.general_tab, GeneralTab)
    assert isinstance(modal.ai_tab, AIEnginesTab)
    assert isinstance(modal.maint_tab, MaintenanceTab)
    assert isinstance(modal.stats_tab, StatisticsTab)

    # Vérifie le basculement entre onglets
    for i in range(4):
        modal.stacked_widget.setCurrentIndex(i)
        assert modal.stacked_widget.currentIndex() == i
