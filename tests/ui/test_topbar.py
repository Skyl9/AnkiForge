"""
Tests unitaires pour la TopBar d'AnkiForge, en particulier la capsule des dépenses IA.
"""

import pytest
from PySide6.QtWidgets import QFrame

from ankiforge.ui.components.topbar import TopBar
from ankiforge.ui.style_engine import JETBRAINS_DARK, JETBRAINS_LIGHT

pytestmark = pytest.mark.ui


def test_topbar_token_tracker_is_qframe_with_panel_properties(qtbot) -> None:
    """Vérifie que token_container est un QFrame avec les attributs de panel du Design System."""
    topbar = TopBar()
    qtbot.addWidget(topbar)

    assert isinstance(topbar.token_container, QFrame)
    assert topbar.token_container.objectName() == "TopBarTokenTracker"
    assert topbar.token_container.property("card-style") == "panel"
    assert topbar.token_container.height() == 28

    assert topbar.dollar_icon.objectName() == "TopBarDollarIcon"
    assert topbar.token_lbl.objectName() == "TopBarTokenLabel"
    assert "Dépenses :" in topbar.token_lbl.text()


def test_topbar_token_tracker_update(qtbot) -> None:
    """Vérifie la mise à jour du texte des dépenses et tokens."""
    topbar = TopBar()
    qtbot.addWidget(topbar)

    topbar.update_token_tracker("0.12", "1 500")
    assert topbar.token_lbl.text() == "Dépenses : 0.12 $ (1 500 tk)"


def test_topbar_token_tracker_refresh_theme(qtbot) -> None:
    """Vérifie que refresh_theme réapplique la couleur verte sur l'icône dollar."""
    topbar = TopBar()
    qtbot.addWidget(topbar)

    topbar.refresh_theme(JETBRAINS_DARK)
    assert not topbar.dollar_icon.pixmap().isNull()

    topbar.refresh_theme(JETBRAINS_LIGHT)
    assert not topbar.dollar_icon.pixmap().isNull()
