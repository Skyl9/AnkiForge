from typing import Any
from unittest.mock import Mock

import pytest

from ankiforge.database.models import NoteTypeModel
from ankiforge.ui.main_window import MainWindow
from ankiforge.ui.views.card_models_view import CardModelsView

pytestmark = pytest.mark.ui


def test_card_models_view_filter_notes_emits_edition_navigation(qtbot: Any, mock_db: Any) -> None:
    model = NoteTypeModel.create(name="Navigation", fields_schema='["Front", "Back"]')
    view = CardModelsView()
    qtbot.addWidget(view)
    received: list[tuple[str, dict[str, object]]] = []
    view.request_navigation.connect(lambda target, payload: received.append((target, payload)))

    view._on_filter_notes_by_model(model)

    assert received == [
        (
            "edition",
            {"note_type_id": model.id, "note_type_name": "Navigation"},
        )
    ]


def test_main_window_routes_note_type_navigation_to_edition() -> None:
    window = MainWindow.__new__(MainWindow)
    edition = Mock()
    window._view_registry = {}
    window._view_widgets = {"edition": edition}
    window._current_view_id = None
    window.stacked_widget = Mock()
    window.shortcut_manager = None
    window.current_layout = None

    window._on_view_selected(
        "edition",
        {"note_type_id": 42, "note_type_name": "Navigation"},
    )

    edition._on_model_selected.assert_called_once_with(42, "Navigation")
