from ankiforge.ui.views.creation_view import CreationTab


def test_creation_view_creation(qtbot):
    view = CreationTab(ai_manager=None)
    qtbot.addWidget(view)
    assert view is not None
