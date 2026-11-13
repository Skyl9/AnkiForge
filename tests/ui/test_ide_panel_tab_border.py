"""Tests de continuité de la ligne de rebord sous IdePanel / TabButton.

Vérifie que l'onglet actif couvre exactement la bordure inférieure de la barre
d'onglets sur toute sa largeur, sans rogner ni déborder de 1px, et que la
géométrie bouton/conteneur est alignée pour une fusion nette avec le contenu.
"""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtWidgets import QLabel, QSplitter

from ankidraft.ui.components.panels import IdePanel
from ankidraft.ui.components.tabs.tab_button import TabButton
from ankidraft.ui.theme import DesignTokens

pytestmark = pytest.mark.ui


class TestIdePanelTabBorderContinuity:
    """La bordure inférieure de l'onglet actif doit coïncider exactement avec celle du panneau."""

    def test_ide_button_and_header_heights_aligned(self, qtbot: Any) -> None:
        """La hauteur du TabButton (36) doit coïncider exactement avec celle du header (36)."""
        splitter = QSplitter()
        panel = IdePanel(parent=splitter)
        splitter.addWidget(panel)
        qtbot.addWidget(splitter)
        splitter.show()

        w = QLabel("Contenu")
        panel.add_tab("Onglet Actif", w, "ph.note", closable=True)

        btn = panel.tabs_bar.tabs[0]
        assert isinstance(btn, TabButton)
        assert btn.height() == panel.header.height() == 36, f"bouton={btn.height()} header={panel.header.height()}"

    def test_checked_ide_tab_covers_bottom_border_exactly(self, qtbot: Any) -> None:
        """L'onglet actif couvre la bordure inférieure sur sa pleine largeur avec BG_PANEL (pas de débord 1px)."""
        splitter = QSplitter()
        panel = IdePanel(parent=splitter)
        splitter.addWidget(panel)
        qtbot.addWidget(splitter)
        splitter.show()

        w = QLabel("Contenu")
        panel.add_tab("Onglet Actif", w, "ph.note", closable=True)

        btn = panel.tabs_bar.tabs[0]
        assert btn.isChecked()

        ss = btn.styleSheet()
        # Le :checked expose une bordure inférieure BG_PANEL sur la largeur exacte du bouton.
        expected = f"border-bottom: 1px solid {DesignTokens.BG_PANEL}"
        assert expected in ss, f"bordure inférieure BG_PANEL absente du :checked :\n{ss}"
        # Le header conserve sa ligne de séparation en BORDER_COLOR pour les onglets inactifs/interstices.
        header_ss = panel.header.styleSheet()
        assert f"border-bottom: 1px solid {DesignTokens.BORDER_COLOR}" in header_ss

    def test_inactive_ide_tab_has_no_bottom_border(self, qtbot: Any) -> None:
        """L'état normal (inactif) ne déclare pas de bordure inférieure propre (ligne gérée par le header)."""
        splitter = QSplitter()
        panel = IdePanel(parent=splitter)
        splitter.addWidget(panel)
        qtbot.addWidget(splitter)
        splitter.show()

        w1 = QLabel("Inactif")
        w2 = QLabel("Actif")
        panel.add_tab("Onglet Inactif", w1, "ph.note", closable=True)
        panel.add_tab("Onglet Actif", w2, "ph.note", closable=True)

        inactive = panel.tabs_bar.tabs[0]
        active = panel.tabs_bar.tabs[1]
        assert not inactive.isChecked()
        assert active.isChecked()

        # Bloc normal (avant le pseudo-état :checked) : pas de border-bottom, fond BG_SIDEBAR.
        normal_block = inactive.styleSheet().split("TabButton:checked")[0]
        assert "border-bottom:" not in normal_block
        assert f"background-color: {DesignTokens.BG_SIDEBAR}" in normal_block
