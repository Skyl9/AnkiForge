"""
Unit tests for icon loader (Phosphor SVG icons and AnkiForge logo).
"""

from __future__ import annotations

from typing import Any

from ankiforge.utils.icon_loader import (
    clear_icon_cache,
    load_logo_icon,
    load_phosphor_icon,
)


def test_load_phosphor_icon_basic(qapp: Any) -> None:
    clear_icon_cache()
    icon = load_phosphor_icon("house")
    assert not icon.isNull()
    assert len(icon.availableSizes()) > 0


def test_load_phosphor_icon_with_prefix_and_suffix(qapp: Any) -> None:
    clear_icon_cache()
    icon_dot = load_phosphor_icon("ph.cpu")
    assert not icon_dot.isNull()

    icon_colon = load_phosphor_icon("ph:gear")
    assert not icon_colon.isNull()

    icon_svg = load_phosphor_icon("sparkle.svg")
    assert not icon_svg.isNull()


def test_load_phosphor_icon_with_colors_and_weights(qapp: Any) -> None:
    clear_icon_cache()
    icon_red = load_phosphor_icon("trash", color="#ff0000", weight="regular")
    assert not icon_red.isNull()

    icon_bold = load_phosphor_icon("plus", color="#00ff00", weight="bold")
    assert not icon_bold.isNull()

    icon_fill = load_phosphor_icon("cards", color="#6366f1", weight="fill")
    assert not icon_fill.isNull()


def test_load_phosphor_icon_caching(qapp: Any) -> None:
    clear_icon_cache()
    icon1 = load_phosphor_icon("house", color="#ffffff", weight="regular")
    icon2 = load_phosphor_icon("house", color="#ffffff", weight="regular")
    assert icon1 is icon2


def test_load_phosphor_icon_fallback_and_invalid(qapp: Any) -> None:
    clear_icon_cache()
    # Empty string
    empty_icon = load_phosphor_icon("")
    assert empty_icon.isNull()

    # Non-existent icon
    invalid_icon = load_phosphor_icon("non_existent_icon_xyz_123")
    assert invalid_icon.isNull()


def test_load_logo_icon(qapp: Any) -> None:
    clear_icon_cache()
    logo = load_logo_icon(color="#6366f1")
    assert not logo.isNull()
    assert len(logo.availableSizes()) > 0
