"""Registre déclaratif de la galerie de widgets (mode développeur)."""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


GalleryEntryList = list["GalleryEntry"]


@dataclass
class GalleryEntry:
    """Entrée du registre de la galerie."""

    family: str
    name: str
    factory: Callable[[], QWidget]
    module: str = ""


_registry: list[GalleryEntry] = []


def gallery_widget(family: str, name: str) -> Callable[[Callable[[], QWidget]], Callable[[], QWidget]]:
    """Décorateur enregistrant une factory de widget dans la galerie."""

    def decorator(factory: Callable[[], QWidget]) -> Callable[[], QWidget]:
        _registry.append(GalleryEntry(family=family, name=name, factory=factory, module=factory.__module__))
        return factory

    return decorator


class WidgetGalleryRegistry:
    """Registre global des widgets de la galerie."""

    @staticmethod
    def list(family: str | None = None, query: str | None = None) -> GalleryEntryList:
        entries = builtins.list(_registry)
        if family:
            entries = [e for e in entries if e.family == family]
        if query:
            q = query.strip().lower()
            if q:
                entries = [e for e in entries if q in e.name.lower() or q in e.family.lower()]
        return entries

    @staticmethod
    def families() -> builtins.list[str]:
        return sorted({e.family for e in _registry})

    @staticmethod
    def clear() -> None:
        _registry.clear()
