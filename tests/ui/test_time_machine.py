from ankiforge.ui.widgets.time_machine_dialog import TimeMachineDialog


def test_time_machine_creation(qtbot):
    dialog = TimeMachineDialog(note_id=1)
    qtbot.addWidget(dialog)
    assert dialog is not None
