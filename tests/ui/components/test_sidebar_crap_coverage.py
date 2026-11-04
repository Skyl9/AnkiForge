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


def test_sidebar_collapsed_layout_margins(qtbot: Any) -> None:
    """En mode replié, les marges latérales des sections et du footer passent de 12px à 8px."""
    sidebar = Sidebar(profile_name="UtilisateurTest")
    qtbot.addWidget(sidebar)
    sidebar.add_section("Navigation", [("accueil", "ph.house", "Accueil")])

    # État déplié : marges latérales 12px
    assert sidebar.sections_layout.contentsMargins().left() == DesignTokens.SIDEBAR_SECTION_MARGIN_EXPANDED
    assert sidebar.footer.layout().contentsMargins().left() == DesignTokens.SIDEBAR_SECTION_MARGIN_EXPANDED

    sidebar.set_collapsed(True)
    assert sidebar.sections_layout.contentsMargins().left() == DesignTokens.SIDEBAR_SECTION_MARGIN_COLLAPSED
    assert sidebar.sections_layout.contentsMargins().right() == DesignTokens.SIDEBAR_SECTION_MARGIN_COLLAPSED
    assert sidebar.footer.layout().contentsMargins().left() == DesignTokens.SIDEBAR_SECTION_MARGIN_COLLAPSED

    sidebar.set_collapsed(False)
    assert sidebar.sections_layout.contentsMargins().left() == DesignTokens.SIDEBAR_SECTION_MARGIN_EXPANDED


def test_sidebar_item_collapsed_width_centre_icone(qtbot: Any) -> None:
    """En mode replié, les boutons de navigation prennent une largeur fixe carrée centrant l'icône."""
    sidebar = Sidebar(profile_name="UtilisateurTest")
    qtbot.addWidget(sidebar)
    sidebar.add_section("Navigation", [("accueil", "ph.house", "Accueil")])

    btn = sidebar._items["accueil"]
    sidebar.set_collapsed(True)
    assert btn.property("collapsed") is True
    assert btn.width() == DesignTokens.SIDEBAR_ITEM_WIDTH_COLLAPSED

    sidebar.set_collapsed(False)
    assert btn.property("collapsed") is False


def test_sidebar_item_collapsed_style_declare_dans_engine() -> None:
    """La règle QSS d'icône centrée en mode replié est déclarée dans StyleEngine (zéro style en dur)."""
    from ankiforge.ui.style_engine import StyleEngine

    stylesheet = StyleEngine.instance().generate_stylesheet()
    assert 'SidebarItem[collapsed="true"]' in stylesheet
    block = stylesheet.split('SidebarItem[collapsed="true"]')[1].split("}")[0]
    assert "text-align: center" in block
    assert "padding-left: 0" in block
    assert "padding-right: 0" in block
