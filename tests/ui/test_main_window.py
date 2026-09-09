from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QLabel

from ankiforge.database.models import NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.ui.components.topbar import TopBar
from ankiforge.ui.main_window import MainWindow
from ankiforge.ui.views.batch_view import BatchView
from ankiforge.ui.views.edition_view import EditionView


@pytest.mark.slow
@pytest.mark.ui
def test_main_window_creation(qtbot, mock_db):
    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None)
        qtbot.addWidget(window)
        assert window is not None
        assert window.topbar is not None
        assert hasattr(window.topbar, "breadcrumb_lbl")
        assert window.topbar.breadcrumb_lbl.text() == "Tableau de bord"


def test_topbar_notification_badge_is_not_clipped(qtbot):
    """La pastille de notification est contenue dans un wrapper plus large."""
    topbar = TopBar()
    qtbot.addWidget(topbar)

    topbar.update_notif_badge(4)

    assert topbar.notif_container.size().width() == 34
    assert topbar.notif_container.size().height() == 34
    assert topbar.notif_badge.parentWidget() is topbar.notif_container
    assert topbar.notif_badge.geometry().right() < topbar.notif_container.width()
    assert topbar.notif_badge.geometry().top() >= 0


@pytest.mark.slow
@pytest.mark.ui
def test_main_window_breadcrumb_navigation(qtbot, mock_db):
    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
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


def test_open_consultant_event_switches_main_window_tab(qtbot, mock_db):
    """Vérifie que la publication de OpenConsultantRequestedEvent bascule MainWindow sur la vue Consultant."""
    from ankiforge.utils.event_bus import OpenConsultantRequestedEvent, event_bus

    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None)
        qtbot.addWidget(window)

        event_bus.publish(OpenConsultantRequestedEvent(context_item="card_42", initial_prompt="Analyse"))
        assert window._current_view_id == "consultant"


def test_main_window_injects_addon_custom_view(qtbot, mock_db):
    class AddonAPI:
        class UI:
            @staticmethod
            def get_registered_custom_views():
                return [
                    {
                        "view_id": "demo_addon:overview",
                        "title": "Vue démo",
                        "icon_name": "sparkle",
                        "widget_factory": lambda: QLabel("Addon content"),
                    }
                ]

        ui = UI()

    class AddonInfo:
        id = "demo_addon"

    class PluginManagerStub:
        @staticmethod
        def get_all_addons():
            return [AddonInfo()]

        @staticmethod
        def get_addon_api(addon_id):
            assert addon_id == "demo_addon"
            return AddonAPI()

    with (
        patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"),
        patch(
            "ankiforge.services.plugins.plugin_manager.get_plugin_manager",
            return_value=PluginManagerStub(),
        ),
    ):
        window = MainWindow(ai_manager=None)
        qtbot.addWidget(window)

        assert "demo_addon:overview" in window._view_registry
        window._on_view_selected("demo_addon:overview")

        assert window._current_view_id == "demo_addon:overview"
        assert isinstance(window._view_widgets["demo_addon:overview"], QLabel)


def test_open_export_dialog_instantiates_and_shows_dialog(qtbot, mock_db):
    """Vérifie que l'appel à _open_export_dialog instancie bien ExportDialog et l'exécute."""
    from ankiforge.ui.dialogs.export_dialog import ExportDialog

    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None)
        qtbot.addWidget(window)

        assert not hasattr(window, "_export_dialog") or window._export_dialog is None

        with patch.object(ExportDialog, "exec") as mock_exec:
            window._open_export_dialog()
            mock_exec.assert_called_once()

        assert hasattr(window, "_export_dialog")
        assert isinstance(window._export_dialog, ExportDialog)
