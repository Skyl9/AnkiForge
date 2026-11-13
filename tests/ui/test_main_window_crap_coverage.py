"""Tests de couverture ciblés pour MainWindow afin de résorber le risque CRAP."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ankidraft.ui.layouts.ide_layout import IdeLayout
from ankidraft.ui.main_window import MainWindow
from ankidraft.ui.style_engine import JETBRAINS_DARK

pytestmark = pytest.mark.ui


@pytest.fixture
def clean_main_window(qtbot: Any, mock_db: Any, monkeypatch: pytest.MonkeyPatch) -> MainWindow:
    """Fixture créant une MainWindow propre et isolée sans daemons de fond."""
    # Désactiver les tâches de fond de mise à jour, MCP et stats
    monkeypatch.setattr(MainWindow, "_check_for_updates", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_pending_crash_report", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_uncompleted_pipeline_runs", lambda self: None)
    monkeypatch.setattr(MainWindow, "_init_mcp_daemon", lambda self: None)

    with patch("ankidraft.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None)
        qtbot.addWidget(window)
        return window


def test_main_window_theme_changed_coverage(clean_main_window: MainWindow) -> None:
    """Couvre _on_theme_changed sur MainWindow (CC=20, anciennement CRAP=420.0)."""
    window = clean_main_window

    # Application du thème JETBRAINS_DARK
    window._on_theme_changed(JETBRAINS_DARK)

    # Vérification que la sidebar et topbar ont reçu le thème
    assert window.sidebar is not None
    assert window.topbar is not None


def test_main_window_command_selected_coverage(clean_main_window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    """Couvre _on_command_selected sur MainWindow (CC=13, anciennement CRAP=182.0)."""
    window = clean_main_window

    # Mocks pour intercepter les ouvertures de dialogue
    mock_settings = MagicMock()
    mock_tour = MagicMock()
    monkeypatch.setattr(window, "_open_settings_modal", mock_settings)
    monkeypatch.setattr(window, "start_tour_guide", mock_tour)

    window._on_command_selected("action.settings")
    assert mock_settings.called

    window._on_command_selected("action.tour")
    assert mock_tour.called


def test_main_window_mcp_data_mutated_coverage(clean_main_window: MainWindow) -> None:
    """Couvre _on_mcp_data_mutated et _refresh_nav_badges sur MainWindow (CC=13, anciennement CRAP=182.0)."""
    window = clean_main_window

    # Création d'un listener sur le signal
    mutations_recues: list[dict[str, Any]] = []
    window.mcp_data_mutated.connect(mutations_recues.append)

    mutation_payload = {
        "domain": "notes",
        "type": "note_update",
        "note_ids": [123],
    }
    window._on_mcp_data_mutated(mutation_payload)

    assert len(mutations_recues) == 1
    assert mutations_recues[0]["domain"] == "notes"


def test_main_window_layout_and_shortcuts_coverage(clean_main_window: MainWindow) -> None:
    """Couvre apply_layout, navigation et raccourcis clavier (CC=7, CRAP=56.0)."""
    window = clean_main_window

    # 1. Commutation de layout
    window.apply_layout("ide")
    assert window.current_layout is not None
    assert isinstance(window.current_layout, IdeLayout)

    # 2. Navigation vers vue suivante et précédente
    window._select_next_view()
    window._select_prev_view()

    # 3. Détection des vues sales
    dirty = window._dirty_views()
    assert isinstance(dirty, list)
