"""Tests de couverture ciblés pour Sidebar afin de résorber le risque CRAP."""

from __future__ import annotations

from typing import Any

import pytest

from ankiforge.ui.components.sidebar import Sidebar
from ankiforge.ui.style_engine import JETBRAINS_DARK
from ankiforge.ui.theme import DesignTokens

pytestmark = pytest.mark.ui


def test_sidebar_set_collapsed_coverage(qtbot: Any) -> None:
    """Couvre set_collapsed (pliage/dépliage) sur Sidebar (CC=11, anciennement CRAP=115.5)."""
    sidebar = Sidebar(profile_name="UtilisateurTest")
    qtbot.addWidget(sidebar)

    sidebar.add_section(
        "Navigation",
        [
            ("accueil", "ph.house", "Accueil"),
            ("cartes", "ph.cards", "Cartes"),
        ],
    )

    # 1. État initial : déplié
    assert not sidebar.is_collapsed
    assert sidebar.width() == DesignTokens.SIDEBAR_WIDTH_EXPANDED

    # 2. Pliage
    sidebar.set_collapsed(True)
    assert sidebar.is_collapsed
    assert sidebar.width() == DesignTokens.SIDEBAR_WIDTH_COLLAPSED

    # 3. Dépliage
    sidebar.set_collapsed(False)
    assert not sidebar.is_collapsed
    assert sidebar.width() == DesignTokens.SIDEBAR_WIDTH_EXPANDED


def test_sidebar_refresh_theme_and_badges_coverage(qtbot: Any) -> None:
    """Couvre refresh_theme, badges et activation de vue sur Sidebar (CC=10, anciennement CRAP=92.4)."""
    sidebar = Sidebar(profile_name="ProfilTest")
    qtbot.addWidget(sidebar)

    sidebar.add_section(
        "SectionTest",
        [
            ("doc", "ph.file-text", "Documents"),
            ("rev", "ph.check-circle", "Révision"),
        ],
    )

    # Rafraîchissement de thème
    sidebar.refresh_theme(JETBRAINS_DARK)

    # Pastille / Badge
    sidebar.set_nav_badge("doc", 3)
    sidebar.set_nav_badge("rev", 0)

    # Sélection active
    sidebar.set_active_view("doc")
    assert sidebar._items["doc"].isChecked()

    # Mise à jour du nom de profil
    sidebar.set_profile_name("NouveauProfil")
    assert sidebar.profile_name == "NouveauProfil"
