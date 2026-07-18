from ankiforge.ui.widgets.auto_tag_dialog import AutoTagDialog


def test_auto_tag_dialog_instantiation(qtbot):
    dialog = AutoTagDialog(parent=None, note_ids=[1, 2, 3])
    qtbot.addWidget(dialog)

    assert dialog is not None
    assert dialog.windowTitle() == "🏷️ L'Archiviste IA (Auto-Tagging)"
    assert dialog.stacked_widget.count() == 2
    assert dialog.stacked_widget.currentIndex() == 0
