from ankiforge.ui.views.batch_view import BatchTab


def test_batch_views_creation(qtbot):
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    assert view is not None
