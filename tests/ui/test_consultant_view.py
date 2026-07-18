from ankiforge.ui.views.consultant_view import ConsultantTab


def test_consultant_view_creation(qtbot):
    view = ConsultantTab(ai_manager=None)
    qtbot.addWidget(view)
    assert view is not None
