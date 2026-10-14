"""
Tests unitaires pour le composant HierarchyBreadcrumbBar (fil d'Ariane prévisionnel interactif).
"""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtCore import Qt

from ankiforge.ui.components.hierarchy_breadcrumb_bar import (
    BreadcrumbSegmentButton,
    HierarchyBreadcrumbBar,
)

pytestmark = pytest.mark.ui


def test_breadcrumb_bar_empty_init(qtbot: Any) -> None:
    """Vérifie l'état initial par défaut d'une barre vide."""
    bar = HierarchyBreadcrumbBar()
    qtbot.addWidget(bar)

    assert bar.current_path() == ""
    assert bar.segments() == []
    assert bar.subpaths() == []
    assert bar.segment_count() == 0


def test_breadcrumb_bar_set_path_simple(qtbot: Any) -> None:
    """Vérifie le découpage d'un chemin hiérarchique avec distinction existant/nouveau."""
    existing = {"Sciences", "Sciences::Physique"}
    bar = HierarchyBreadcrumbBar(existing_paths=existing)
    qtbot.addWidget(bar)

    bar.set_path("Sciences::Physique::Thermodynamique")

    assert bar.current_path() == "Sciences::Physique::Thermodynamique"
    assert bar.segments() == ["Sciences", "Physique", "Thermodynamique"]
    assert bar.subpaths() == [
        "Sciences",
        "Sciences::Physique",
        "Sciences::Physique::Thermodynamique",
    ]
    assert bar.segment_count() == 3

    # Segment 0 (Sciences) -> existant
    assert bar.is_segment_existing(0) is True
    # Segment 1 (Physique) -> existant
    assert bar.is_segment_existing(1) is True
    # Segment 2 (Thermodynamique) -> nouveau
    assert bar.is_segment_existing(2) is False


def test_breadcrumb_bar_buttons_and_chevrons(qtbot: Any) -> None:
    """Vérifie que les boutons de segments et les séparateurs sont correctement insérés."""
    bar = HierarchyBreadcrumbBar()
    qtbot.addWidget(bar)
    bar.set_path("Langues::Japonais::Grammaire")

    buttons = bar.segment_buttons()
    assert len(buttons) == 3
    assert [btn.segment_name for btn in buttons] == ["Langues", "Japonais", "Grammaire"]
    assert [btn.subpath for btn in buttons] == [
        "Langues",
        "Langues::Japonais",
        "Langues::Japonais::Grammaire",
    ]

    # Vérification des séparateurs chevrons
    separators = bar.separator_labels()
    # Pour 3 segments, il doit y avoir 2 chevrons intercalaires
    assert len(separators) == 2


def test_breadcrumb_bar_click_emits_subpath(qtbot: Any) -> None:
    """Vérifie que le clic sur un segment émet le signal segment_clicked avec le sous-chemin tronqué."""
    bar = HierarchyBreadcrumbBar()
    qtbot.addWidget(bar)
    bar.set_path("A::B::C")

    buttons = bar.segment_buttons()
    assert len(buttons) == 3

    # Clic sur le segment 0 ("A")
    with qtbot.waitSignal(bar.segment_clicked, timeout=1000) as blocker:
        qtbot.mouseClick(buttons[0], Qt.MouseButton.LeftButton)
    assert blocker.args == ["A"]

    # Clic sur le segment 1 ("B")
    with qtbot.waitSignal(bar.segment_clicked, timeout=1000) as blocker:
        qtbot.mouseClick(buttons[1], Qt.MouseButton.LeftButton)
    assert blocker.args == ["A::B"]

    # Clic sur le segment 2 ("C")
    with qtbot.waitSignal(bar.segment_clicked, timeout=1000) as blocker:
        qtbot.mouseClick(buttons[2], Qt.MouseButton.LeftButton)
    assert blocker.args == ["A::B::C"]


def test_breadcrumb_bar_clearing_and_updating(qtbot: Any) -> None:
    """Vérifie la mise à jour réactive sans duplication et le vidage complet."""
    bar = HierarchyBreadcrumbBar(initial_path="Maths::Algebre")
    qtbot.addWidget(bar)

    assert bar.segment_count() == 2

    # Changement vers un chemin plus court
    bar.set_path("Maths")
    assert bar.segment_count() == 1
    assert bar.segments() == ["Maths"]

    # Vidage
    bar.clear()
    assert bar.segment_count() == 0
    assert bar.current_path() == ""
    assert bar.segments() == []
    assert bar.subpaths() == []


def test_breadcrumb_bar_whitespace_and_empty_segments(qtbot: Any) -> None:
    """Vérifie la résilience face aux séparateurs traînants et espaces superflus."""
    bar = HierarchyBreadcrumbBar()
    qtbot.addWidget(bar)

    bar.set_path("  Informatique ::   Reseaux  ::  ")
    assert bar.segments() == ["Informatique", "Reseaux"]
    assert bar.subpaths() == ["Informatique", "Informatique::Reseaux"]
    assert bar.segment_count() == 2

    # Chaîne vide ou uniquement blanche
    bar.set_path("   ::   ")
    assert bar.segment_count() == 0
    assert bar.segments() == []


def test_breadcrumb_bar_custom_separator(qtbot: Any) -> None:
    """Vérifie le support d'un séparateur personnalisé (ex: slash)."""
    bar = HierarchyBreadcrumbBar(separator="/")
    qtbot.addWidget(bar)

    bar.set_path("root/sub/leaf")
    assert bar.segments() == ["root", "sub", "leaf"]
    assert bar.subpaths() == ["root", "root/sub", "root/sub/leaf"]

    with qtbot.waitSignal(bar.segment_clicked, timeout=1000) as blocker:
        qtbot.mouseClick(bar.segment_buttons()[1], Qt.MouseButton.LeftButton)
    assert blocker.args == ["root/sub"]


def test_breadcrumb_bar_dynamic_existing_paths_update(qtbot: Any) -> None:
    """Vérifie la mise à jour dynamique des chemins existants via set_existing_paths."""
    bar = HierarchyBreadcrumbBar(initial_path="Projet::AnkiForge")
    qtbot.addWidget(bar)

    assert bar.is_segment_existing(0) is False
    assert bar.is_segment_existing(1) is False

    # Mise à jour avec le parent existant
    bar.set_existing_paths(["Projet"])
    assert bar.is_segment_existing(0) is True
    assert bar.is_segment_existing(1) is False

    # Mise à jour avec les deux existants
    bar.set_existing_paths(["Projet", "Projet::AnkiForge"])
    assert bar.is_segment_existing(0) is True
    assert bar.is_segment_existing(1) is True


def test_breadcrumb_segment_button_accessibility_and_tooltips(qtbot: Any) -> None:
    """Vérifie les attributs d'accessibilité et infobulles descriptives des badges."""
    existing_btn = BreadcrumbSegmentButton(
        segment_name="Parent",
        subpath="Parent",
        is_existing=True,
    )
    qtbot.addWidget(existing_btn)

    assert "Parent" in existing_btn.toolTip()
    assert existing_btn.accessibleName() != ""
    assert existing_btn.is_existing is True

    new_btn = BreadcrumbSegmentButton(
        segment_name="Enfant",
        subpath="Parent::Enfant",
        is_existing=False,
    )
    qtbot.addWidget(new_btn)

    assert "Enfant" in new_btn.toolTip()
    assert new_btn.is_existing is False
