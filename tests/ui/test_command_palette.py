from ankiforge.ui.widgets.command_palette import CommandPalette


def test_command_palette_creation(qtbot):
    widget = CommandPalette()
    qtbot.addWidget(widget)
    assert widget is not None
