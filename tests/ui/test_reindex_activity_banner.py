"""Tests UI headless du bandeau d'activité global de réindexation (ADR 0021)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from ankiforge.ui.widgets.reindex_activity_banner import ReindexActivityBanner

pytestmark = pytest.mark.ui


def test_banner_hidden_at_rest(qtbot) -> None:
    banner = ReindexActivityBanner()
    qtbot.addWidget(banner)
    banner.show()
    banner.reset()
    assert banner.isVisible() is False


def test_handle_started_shows_banner_and_sets_range(qtbot) -> None:
    banner = ReindexActivityBanner()
    qtbot.addWidget(banner)
    banner.show()

    banner.handle_started(4)

    assert banner.isVisible() is True
    assert banner.progress_bar.maximum() == 4
    assert banner.progress_bar.value() == 0
    assert banner.badge_percent.text() == "0 %"


def test_handle_progress_reports_document_and_percentage(qtbot) -> None:
    banner = ReindexActivityBanner()
    qtbot.addWidget(banner)

    banner.handle_started(4)
    banner.handle_progress(2, 4, "Chapitre 2")

    assert banner.lbl_title.text() == "Réindexation 2/4 : Chapitre 2"
    # Pourcentage calculé sur les documents *terminés* (1 sur 4), jamais sur les fragments.
    assert banner.badge_percent.text() == "25 %"
    assert banner.progress_bar.value() == 1


def test_handle_fragments_shows_micro_progress(qtbot) -> None:
    banner = ReindexActivityBanner()
    qtbot.addWidget(banner)

    banner.handle_started(1)
    banner.handle_fragments(3, 10)

    assert banner.lbl_fragments.isVisible() is True
    assert banner.lbl_fragments.text() == "Fragments : 3/10"


def test_reset_hides_and_clears(qtbot) -> None:
    banner = ReindexActivityBanner()
    qtbot.addWidget(banner)
    banner.handle_started(2)
    banner.handle_progress(2, 2, "Doc")

    banner.reset()

    assert banner.isVisible() is False
    assert banner.badge_percent.text() == "0 %"
    assert banner.lbl_fragments.isVisible() is False


def test_cancel_button_emits_signal(qtbot) -> None:
    banner = ReindexActivityBanner()
    qtbot.addWidget(banner)

    with qtbot.waitSignal(banner.cancel_requested, timeout=1000):
        banner.btn_cancel.click()


def test_cancel_button_hidden_for_single_document_pass(qtbot) -> None:
    """L'annulation est coopérative entre documents : rien à annuler sur une passe mono-document."""
    banner = ReindexActivityBanner()
    qtbot.addWidget(banner)
    banner.show()

    banner.handle_started(1)
    assert banner.btn_cancel.isHidden() is True

    banner.handle_started(3)
    assert banner.btn_cancel.isHidden() is False


def test_refresh_theme_reapplies_current_tokens(qtbot, monkeypatch) -> None:
    """Le bandeau se recolore au changement de thème (jetons réassignés à chaud)."""
    from ankiforge.ui.theme import DesignTokens

    banner = ReindexActivityBanner()
    qtbot.addWidget(banner)

    monkeypatch.setattr(DesignTokens, "BG_PANEL", "#123456", raising=False)
    banner.refresh_theme(None)

    assert "#123456" in banner.styleSheet()


def test_labels_use_no_emoji(qtbot, contains_forbidden_glyph: Callable[[str], bool]) -> None:
    banner = ReindexActivityBanner()
    qtbot.addWidget(banner)

    banner.handle_started(2)
    banner.handle_progress(2, 2, "Cours de statistiques")
    banner.handle_fragments(3, 10)

    for label in (banner.lbl_title.text(), banner.lbl_fragments.text(), banner.badge_percent.text()):
        assert not contains_forbidden_glyph(label), f"Pictogramme interdit dans « {label} »"


@pytest.mark.slow
def test_banner_hosted_outside_layouts_and_survives_switch(qtbot, mock_db) -> None:
    """Le bandeau vit dans MainWindow, hors des layouts enfichables, et y survit (ADR 0021)."""
    from unittest.mock import patch

    from ankiforge.ui.main_window import MainWindow

    with patch("ankiforge.ui.views.dashboard_view.StatsWorker.start"):
        window = MainWindow(ai_manager=None)
    qtbot.addWidget(window)

    banner = window.reindex_banner
    first_layout = window._hosted_layout
    assert first_layout is not None
    assert banner.parentWidget() is window._central_container
    assert banner.parentWidget() is not first_layout

    window.apply_layout("macos")

    assert window.reindex_banner is banner
    assert window._hosted_layout is not first_layout
    assert banner.parentWidget() is window._central_container

    # Le hub alimente bien l'hôte : un démarrage de passe rend le bandeau visible.
    window.reindex_activity.started.emit(3)
    assert banner.isHidden() is False
