"""Pastilles de filtre de format de l'onglet Sources (composant, hauteur, icônes, état actif).

Ticket « UI - AnalysisView Pastilles Filtrage Format Ecrasees et Icones » :

- CA 1 : hauteur 32px via ``apply_compact_style`` (26px écrasait le texte sous le
  QSS global ``padding: 8px 16px``) ;
- CA 2 : icônes Phosphor canoniques par format ;
- CA 3 : mise en évidence nette du filtre en vigueur.
"""

from typing import Any

import pytest

from ankiforge.ui.components.buttons import FilterChipButton
from ankiforge.ui.views.analysis_view.tabs.sources_tab import AISourcesDiagnosticTab

pytestmark = pytest.mark.ui

EXPECTED_ICONS = {
    "all": "ph.squares-four",
    "pdf": "ph.file-pdf",
    "md": "ph.file-text",
    "web": "ph.globe",
}


def test_format_filter_buttons_use_the_documented_chip_component(qtbot: Any) -> None:
    """DESIGN.md, « Boutons Filtres & Chips » : le composant de filtre est ``FilterChipButton``.

    C'est lui qui porte l'état ``:checked`` documenté (fond ``accent_bg``, texte et bordure
    ``accent_primary``) ainsi que l'icône Phosphor re-teintée à la sélection et au changement
    de thème via ``refresh_theme`` : recréer cette recette sur ``SecondaryButton`` dupliquerait
    le design system et ajouterait un état QSS non consigné.
    """
    tab = AISourcesDiagnosticTab()
    qtbot.addWidget(tab)

    assert set(tab.format_buttons) == set(EXPECTED_ICONS)
    for fmt, btn in tab.format_buttons.items():
        assert isinstance(btn, FilterChipButton), f"{fmt}: {type(btn).__name__} n'est pas la pastille documentée"
        assert btn.isCheckable(), f"{fmt}: pastille non basculable"


def test_format_filter_buttons_are_compact_32px_with_canonical_icons(qtbot: Any) -> None:
    """CA 1 + CA 2 : 32px en densité compacte et icône Phosphor canonique par format."""
    tab = AISourcesDiagnosticTab()
    qtbot.addWidget(tab)

    for fmt, expected_icon in EXPECTED_ICONS.items():
        btn = tab.format_buttons[fmt]
        assert btn.height() == 32, f"{fmt}: hauteur {btn.height()} != 32 (texte/icône rognés)"
        assert btn.property("density") == "compact"
        assert btn.icon_name == expected_icon, f"{fmt}: icône {btn.icon_name!r} != {expected_icon!r}"
        assert not btn.icon().isNull(), f"{fmt}: icône absente"


def test_only_the_current_format_filter_is_checked(qtbot: Any) -> None:
    """CA 3 : une seule pastille est active, elle suit le filtre en vigueur."""
    tab = AISourcesDiagnosticTab()
    qtbot.addWidget(tab)

    assert tab.current_format_filter == "all"
    assert [fmt for fmt, btn in tab.format_buttons.items() if btn.isChecked()] == ["all"]

    tab.format_buttons["pdf"].click()

    assert tab.current_format_filter == "pdf"
    assert [fmt for fmt, btn in tab.format_buttons.items() if btn.isChecked()] == ["pdf"]

    # Recliquer sur la pastille active ne doit jamais laisser aucun filtre actif.
    tab.format_buttons["pdf"].click()
    assert [fmt for fmt, btn in tab.format_buttons.items() if btn.isChecked()] == ["pdf"]
