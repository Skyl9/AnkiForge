"""Famille « layouts » de la galerie : dispositions d'interface enfichables.

Chaque factory instancie un layout réel, lui fournit un ``QStackedWidget`` de
substituts et un registre de navigation réduit, afin d'observer la coquille complète
(barre supérieure, navigation, zone centrale) sans instancier les vues métier.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QStackedWidget, QWidget

from ankiforge.ui.layouts.base_layout import BaseLayout
from ankiforge.ui.layouts.dashboard_layout import DashboardLayout
from ankiforge.ui.layouts.glass_layout import GlassmorphismLayout
from ankiforge.ui.layouts.ide_layout import IdeLayout
from ankiforge.ui.layouts.macos_layout import MacosLayout
from ankiforge.ui.widget_gallery.registry import gallery_widget
from ankiforge.utils.i18n import tr

logger = logging.getLogger(__name__)


def _demo_view_registry() -> dict[str, tuple[str, str, str, type[QWidget]]]:
    """Registre de navigation réduit, suffisant pour éprouver chaque disposition."""
    return {
        "dashboard": (tr("Général"), "squares-four", tr("Tableau de bord"), QWidget),
        "edition": (tr("Forge & Outils"), "cards", tr("Édition & Navigateur"), QWidget),
        "documents": (tr("Bibliothèque"), "file-text", tr("My Documents"), QWidget),
    }


def _preview_layout(layout_class: type[BaseLayout]) -> QWidget:
    layout = layout_class(profile_name="galerie")
    registry = _demo_view_registry()

    stacked = QStackedWidget(layout)
    for _view_id, (_category, _icon, title, _cls) in registry.items():
        placeholder = QLabel(tr("Aperçu de la vue « %1 ».", title), stacked)
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stacked.addWidget(placeholder)

    layout.populate_navigation(registry)
    layout.set_stacked_widget(stacked)
    layout.set_active_view("dashboard")
    return layout


def _make_ide_layout() -> QWidget:
    return _preview_layout(IdeLayout)


def _make_macos_layout() -> QWidget:
    return _preview_layout(MacosLayout)


def _make_dashboard_layout() -> QWidget:
    return _preview_layout(DashboardLayout)


def _make_glassmorphism_layout() -> QWidget:
    return _preview_layout(GlassmorphismLayout)


# Correspondance classe de layout → factory, source unique de la couverture.
LAYOUT_FACTORIES: dict[str, Callable[[], QWidget]] = {
    "IdeLayout": _make_ide_layout,
    "MacosLayout": _make_macos_layout,
    "DashboardLayout": _make_dashboard_layout,
    "GlassmorphismLayout": _make_glassmorphism_layout,
}


def layout_labels() -> dict[str, str]:
    """Libellés français affichés dans l'arbre de la galerie (extractibles par lupdate)."""
    return {
        "IdeLayout": tr("Disposition IDE"),
        "MacosLayout": tr("Disposition macOS"),
        "DashboardLayout": tr("Disposition tableau de bord"),
        "GlassmorphismLayout": tr("Disposition glassmorphism"),
    }


def register() -> None:
    """Enregistre les layouts dans la galerie (idempotent)."""
    labels = layout_labels()
    for class_name, factory in LAYOUT_FACTORIES.items():
        label = labels.get(class_name)
        if label is None:
            logger.warning("Libellé de galerie manquant pour le layout « %s »", class_name)
            label = class_name
        gallery_widget(family="layouts", name=label)(factory)
