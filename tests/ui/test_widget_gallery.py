"""Tests headless de la galerie de widgets (mode développeur)."""

from __future__ import annotations

import os

import pytest
from PySide6.QtWidgets import QLabel, QWidget

from ankiforge.dev import is_dev_mode
from ankiforge.ui.widget_gallery import (
    WidgetGalleryRegistry,
    WidgetGalleryWindow,
    gallery_widget,
)

pytestmark = pytest.mark.ui


@pytest.fixture(autouse=True)
def reset_registry():
    WidgetGalleryRegistry.clear()
    yield
    WidgetGalleryRegistry.clear()


@pytest.fixture(autouse=True)
def dev_mode():
    os.environ["ANKIFORGE_ENV"] = "development"
    import ankiforge.utils.environment as env_mod

    env_mod._current_env = None
    yield
    env_mod._current_env = None


@pytest.fixture(autouse=True)
def sample_entry():
    @gallery_widget(family="components", name="Label factice")
    def _make_label() -> QWidget:
        return QLabel("Widget factice")

    return None


def test_is_dev_mode_active_in_tests(dev_mode):
    assert is_dev_mode() is True


def test_gallery_window_opens(qtbot):
    win = WidgetGalleryWindow()
    qtbot.addWidget(win)
    win.show()
    assert win is not None
    assert win.tree.topLevelItemCount() >= 1


def test_gallery_instanciates_each_entry(qtbot):
    for entry in WidgetGalleryRegistry.list():
        widget = entry.factory()
        qtbot.addWidget(widget)
        assert isinstance(widget, QWidget)


def test_gallery_search_filters(qtbot):
    win = WidgetGalleryWindow()
    qtbot.addWidget(win)
    win.search_edit.setText("inexistant")
    assert win.tree.topLevelItemCount() == 0
