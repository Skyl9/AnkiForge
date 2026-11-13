"""Galerie de widgets (mode développeur)."""

from __future__ import annotations

from ankidraft.ui.widget_gallery.registry import (
    GalleryEntry,
    WidgetGalleryRegistry,
    gallery_widget,
)
from ankidraft.ui.widget_gallery.widget_gallery_window import WidgetGalleryWindow

__all__ = [
    "GalleryEntry",
    "WidgetGalleryRegistry",
    "WidgetGalleryWindow",
    "gallery_widget",
]
