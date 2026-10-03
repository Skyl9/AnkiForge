"""Tests unitaires pour FilterChipButton (composant capsule / pill)."""

from typing import Any

import pytest
from PySide6.QtCore import QSize, Qt

from ankiforge.ui.components.buttons import FilterChipButton

pytestmark = pytest.mark.ui


def test_filter_chip_button_init_default(qtbot: Any) -> None:
    """Vérifie l'initialisation par défaut d'un FilterChipButton sans icône."""
    btn = FilterChipButton("Catégorie & Filtre")
    qtbot.addWidget(btn)

    assert btn.isCheckable()
    assert btn.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert btn.height() == 26 or btn.maximumHeight() == 26
    # Vérification que le & est échappé pour ne pas être interprété comme mnémonique Qt
    assert "&&" in btn.text()
    assert btn.icon_name is None
    assert btn.icon().isNull()


def test_filter_chip_button_with_icon_and_toggle(qtbot: Any) -> None:
    """Vérifie le chargement de l'icône Phosphor et sa réactivité au basculement checked/unchecked."""
    btn = FilterChipButton("Pipeline", icon_name="ph.lightning")
    qtbot.addWidget(btn)

    assert btn.icon_name == "ph.lightning"
    assert not btn.icon().isNull()
    assert btn.iconSize() == QSize(14, 14)
    assert not btn.isChecked()

    # Basculer l'état à checked
    btn.setChecked(True)
    assert btn.isChecked()
    assert not btn.icon().isNull()

    # Rebasculer à unchecked
    btn.setChecked(False)
    assert not btn.isChecked()
    assert not btn.icon().isNull()


def test_filter_chip_button_set_icon_name(qtbot: Any) -> None:
    """Vérifie la mise à jour dynamique de l'icône via set_icon_name."""
    btn = FilterChipButton("Test")
    qtbot.addWidget(btn)

    assert btn.icon_name is None
    assert btn.icon().isNull()

    btn.set_icon_name("ph.sparkle")
    assert btn.icon_name == "ph.sparkle"
    assert not btn.icon().isNull()

    btn.set_icon_name(None)
    assert btn.icon_name is None
    assert btn.icon().isNull()


def test_filter_chip_button_refresh_theme(qtbot: Any) -> None:
    """Vérifie la réactivité au changement de thème via refresh_theme."""
    btn = FilterChipButton("Tous", icon_name="ph.sparkle")
    qtbot.addWidget(btn)

    from ankiforge.ui.style_engine import JETBRAINS_LIGHT

    btn.setChecked(True)
    btn.refresh_theme(JETBRAINS_LIGHT)
    assert not btn.icon().isNull()

    btn.setChecked(False)
    assert not btn.icon().isNull()


def test_filter_chip_button_set_text_escapes_ampersand(qtbot: Any) -> None:
    """Vérifie que setText échappe aussi les ampersands."""
    btn = FilterChipButton("Initial")
    qtbot.addWidget(btn)

    btn.setText("Audit & MCP")
    assert btn.text() == "Audit && MCP"
