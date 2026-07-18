from ankiforge.ui.views.edition_view import EditionTab


def test_edition_view_creation(qtbot):
    view = EditionTab()
    qtbot.addWidget(view)
    assert view is not None
