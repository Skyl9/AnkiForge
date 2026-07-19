from ankiforge.ui.views.creation_view import CreationView


def test_creation_view_creation(qtbot):
    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)
    assert view is not None
