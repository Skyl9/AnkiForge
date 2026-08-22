import pytest
from unittest.mock import patch
from ankiforge.ui.main_window import MainWindow
from ankiforge.ui.views.batch_view import BatchView
from ankiforge.ui.views.edition_view import EditionView
from ankiforge.database.models import NoteModel, NoteTypeModel, NoteVersionModel


@pytest.mark.slow
@pytest.mark.ui
def test_main_window_creation(qtbot, mock_db):
    with patch("ankiforge.services.background_daemon.BackgroundDaemon"), patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None)
        qtbot.addWidget(window)
        assert window is not None
        assert window.topbar is not None
        assert hasattr(window.topbar, "breadcrumb_lbl")
        assert window.topbar.breadcrumb_lbl.text() == "Tableau de bord"


@pytest.mark.slow
@pytest.mark.ui
def test_main_window_breadcrumb_navigation(qtbot, mock_db):
    with patch("ankiforge.services.background_daemon.BackgroundDaemon"), patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None)
        qtbot.addWidget(window)

        window._on_view_selected("batch")
        assert window.topbar is not None
        assert window.topbar.breadcrumb_lbl.text() == "Batch Factory"

        window._on_view_selected("creation")
        assert window.topbar is not None
        assert window.topbar.breadcrumb_lbl.text() == "Studio de Création"


def test_batch_view_terminal_drawer_toggle(qtbot, mock_db):
    view = BatchView()
    qtbot.addWidget(view)
    view.show()

    assert view._terminal_expanded is True
    assert not view.terminal_content.isHidden()

    # Click toggle button to fold
    view.btn_toggle_terminal.click()
    assert view._terminal_expanded is False
    assert view.terminal_content.isHidden()

    # Click toggle button to unfold
    view.btn_toggle_terminal.click()
    assert view._terminal_expanded is True
    assert not view.terminal_content.isHidden()


def test_edition_view_placeholder_stack(qtbot, mock_db):
    import uuid

    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(
        name=f"Basic Model {uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}"}]',
        css_style=".card {}",
    )
    note = NoteModel.create(guid=f"guid_{uid}", note_type=nt, tags='["test"]')
    NoteVersionModel.create(note=note, version_number=1, content='{"Front": "Q1", "Back": "A1"}', is_active=True)

    view = EditionView()
    qtbot.addWidget(view)

    # Initial state: no card selected -> placeholder index 0
    view.refresh_data()
    assert view.editor_stack.currentIndex() == 0

    # Select note -> flips to editor index 1
    view.select_note_by_id(note.id)
    assert view.editor_stack.currentIndex() == 1
