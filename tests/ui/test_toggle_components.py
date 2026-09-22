"""Tests unitaires et UI pour les composants ToggleSwitch et OptionToggleRow."""

from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from ankiforge.ui.components.inputs import OptionToggleRow, ToggleSwitch

pytestmark = pytest.mark.ui


def test_toggle_switch_initial_state_and_instant_set(qtbot: Any) -> None:
    """Vérifie l'état initial sans animation et le positionnement instantané du curseur."""
    sw_off = ToggleSwitch()
    qtbot.addWidget(sw_off)
    assert not sw_off.is_checked()
    assert sw_off.get_thumb_pos() == 2.0

    sw_on = ToggleSwitch()
    qtbot.addWidget(sw_on)
    sw_on.set_checked(True, animated=False)
    assert sw_on.is_checked()
    assert sw_on.get_thumb_pos() == 18.0


def test_toggle_switch_animated_transition(qtbot: Any) -> None:
    """Vérifie que l'animation glisse le curseur de 2.0 à 18.0."""
    sw = ToggleSwitch()
    qtbot.addWidget(sw)
    sw.show()

    signals: list[bool] = []
    sw.toggled.connect(signals.append)

    sw.set_checked(True, animated=True)
    assert sw.is_checked()

    # Attendre la fin de l'animation (~150ms)
    qtbot.waitUntil(lambda: sw.get_thumb_pos() == 18.0, timeout=500)
    assert signals == [True]

    # Revenir en arrière
    sw.set_checked(False, animated=True)
    assert not sw.is_checked()
    qtbot.waitUntil(lambda: sw.get_thumb_pos() == 2.0, timeout=500)
    assert signals == [True, False]


def test_toggle_switch_mid_flight_reversal(qtbot: Any) -> None:
    """Vérifie qu'un clic à mi-course inverse l'animation sans gel ni saut brutal."""
    sw = ToggleSwitch()
    qtbot.addWidget(sw)
    sw.show()

    sw.set_checked(True, animated=True)
    # Attendre un déplacement intermédiaire
    qtbot.waitUntil(lambda: sw.get_thumb_pos() > 4.0, timeout=200)
    mid_pos = sw.get_thumb_pos()
    assert 2.0 < mid_pos < 18.0

    # Inversion en vol
    sw.set_checked(False, animated=True)
    assert not sw.is_checked()

    # Le curseur doit revenir en douceur à 2.0
    qtbot.waitUntil(lambda: sw.get_thumb_pos() == 2.0, timeout=500)


def test_toggle_switch_mouse_events(qtbot: Any) -> None:
    """Vérifie que le clic direct sur ToggleSwitch déclenche la bascule."""
    sw = ToggleSwitch()
    qtbot.addWidget(sw)
    sw.show()

    QTest.mouseClick(sw, Qt.MouseButton.LeftButton)
    assert sw.is_checked()

    QTest.mouseClick(sw, Qt.MouseButton.LeftButton)
    assert not sw.is_checked()


def test_option_toggle_row_single_click_toggle(qtbot: Any) -> None:
    """Vérifie qu'un clic sur la rangée ou sur l'interrupteur ne produit qu'une seule bascule (pas de double toggle)."""
    row = OptionToggleRow("Vision (PDF)", icon_name="ph.eye", checked=True)
    qtbot.addWidget(row)
    row.show()

    signals: list[bool] = []
    row.toggled.connect(signals.append)

    # 1. Clic sur le libellé texte
    QTest.mouseClick(row.title_lbl, Qt.MouseButton.LeftButton)
    assert not row.is_checked()
    assert signals == [False]

    # 2. Clic sur l'icône
    if hasattr(row, "icon_lbl"):
        QTest.mouseClick(row.icon_lbl, Qt.MouseButton.LeftButton)
        assert row.is_checked()
        assert signals == [False, True]

    # 3. Clic sur l'interrupteur lui-même (test anti-régression double toggle)
    QTest.mouseClick(row.switch, Qt.MouseButton.LeftButton)
    # L'interrupteur étant transparent aux événements souris dans la rangée,
    # le clic traverse vers OptionToggleRow et bascule exactement une fois.
    assert not row.is_checked()
    assert signals == [False, True, False]


def test_option_toggle_row_set_checked_programmatic(qtbot: Any) -> None:
    """Vérifie le pilotage programmatique de OptionToggleRow."""
    row = OptionToggleRow("Validation auto", icon_name="ph.shield-check", checked=False)
    qtbot.addWidget(row)

    row.set_checked(True, animated=False)
    assert row.is_checked()
    assert row.switch.is_checked()
    assert row.switch.get_thumb_pos() == 18.0

    row.setChecked(False)
    assert not row.isChecked()


def test_option_toggle_row_theme_profile_application(qtbot: Any) -> None:
    """Vérifie l'application d'un profil de thème personnalisé sur OptionToggleRow et ToggleSwitch."""
    from ankiforge.ui.style_engine.themes import JETBRAINS_DARK

    profile = JETBRAINS_DARK

    row = OptionToggleRow("Thème dynamique", icon_name="ph.palette", checked=True)
    qtbot.addWidget(row)

    row.apply_theme_profile(profile)
    assert row._profile == profile
    assert row.switch._profile == profile


def test_toggle_switch_paint_event_antialiased(qtbot: Any) -> None:
    """Vérifie que paintEvent s'exécute sans exception aux positions extrêmes et intermédiaires."""
    sw = ToggleSwitch()
    qtbot.addWidget(sw)
    sw.resize(36, 20)

    # Test avec position intermédiaire (interpolation couleur active)
    sw.set_thumb_pos(10.0)
    sw.repaint()

    sw.set_thumb_pos(2.0)
    sw.repaint()

    sw.set_thumb_pos(18.0)
    sw.repaint()
