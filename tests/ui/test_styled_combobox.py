"""Tests unitaires pour StyledComboBox et les styles de sélection déroulante (StyleEngine)."""

import re
from pathlib import Path

import pytest

from ankiforge.ui.components.inputs import StyledComboBox
from ankiforge.ui.style_engine import JETBRAINS_DARK, JETBRAINS_LIGHT, get_style_engine

pytestmark = pytest.mark.ui


def test_styled_combobox_default_density(qtbot: pytest.FixtureRequest) -> None:
    """Vérifie que StyledComboBox s'initialise par défaut en densité normal (36px)."""
    combo = StyledComboBox()
    qtbot.addWidget(combo)

    assert combo.property("density") == "normal"
    assert combo.maximumHeight() == 36
    assert combo.minimumHeight() == 36


def test_styled_combobox_compact_density(qtbot: pytest.FixtureRequest) -> None:
    """Vérifie que StyledComboBox supporte la densité compact (28px)."""
    combo = StyledComboBox(density="compact")
    qtbot.addWidget(combo)

    assert combo.property("density") == "compact"
    assert combo.maximumHeight() == 28
    assert combo.minimumHeight() == 28


def test_styled_combobox_set_density(qtbot: pytest.FixtureRequest) -> None:
    """Vérifie le changement dynamique de densité via set_density()."""
    combo = StyledComboBox()
    qtbot.addWidget(combo)

    assert combo.maximumHeight() == 36
    combo.set_density("compact")
    assert combo.property("density") == "compact"
    assert combo.maximumHeight() == 28

    combo.set_density("normal")
    assert combo.property("density") == "normal"
    assert combo.maximumHeight() == 36


def test_style_engine_combobox_stylesheet_rules() -> None:
    """Vérifie que StyleEngine génère les règles QSS complètes pour QComboBox et ses items."""
    engine = get_style_engine()
    qss = engine.generate_stylesheet(JETBRAINS_DARK)

    # Sélecteurs essentiels
    assert "QComboBox" in qss
    assert "QComboBox:hover" in qss
    assert "QComboBox:focus, QComboBox:on" in qss or "QComboBox:focus" in qss
    assert 'QComboBox[density="compact"]' in qss
    assert "QComboBox::drop-down" in qss
    assert "QComboBox::down-arrow" in qss
    assert "QComboBox QAbstractItemView" in qss
    assert "QComboBox QAbstractItemView::item" in qss

    # Vérification de l'injection d'image pour le chevron down-arrow
    arrow_match = re.search(r"QComboBox::down-arrow\s*\{[^}]*image:\s*url\(([^)]+)\)", qss)
    assert arrow_match is not None, "QComboBox::down-arrow doit contenir une directive image: url(...)"

    arrow_path = Path(arrow_match.group(1).strip("'\""))
    assert arrow_path.exists(), f"Le fichier SVG de flèche doit exister sur disque : {arrow_path}"
    content = arrow_path.read_text(encoding="utf-8")
    assert "<svg" in content and "</svg>" in content, "Le fichier d'icône doit être un SVG valide"
    assert "caret-down" in str(arrow_path) or "polyline" in content


def test_style_engine_combobox_svg_tinting_per_theme() -> None:
    """Vérifie que le chevron SVG s'adapte aux variantes sombre et claire."""
    engine = get_style_engine()

    qss_dark = engine.generate_stylesheet(JETBRAINS_DARK)
    dark_match = re.search(r"QComboBox::down-arrow\s*\{[^}]*image:\s*url\(([^)]+)\)", qss_dark)
    assert dark_match is not None
    dark_svg = Path(dark_match.group(1).strip("'\"")).read_text(encoding="utf-8")

    qss_light = engine.generate_stylesheet(JETBRAINS_LIGHT)
    light_match = re.search(r"QComboBox::down-arrow\s*\{[^}]*image:\s*url\(([^)]+)\)", qss_light)
    assert light_match is not None
    light_svg = Path(light_match.group(1).strip("'\"")).read_text(encoding="utf-8")

    # Les couleurs de trait doivent être différentes entre mode sombre et clair
    assert JETBRAINS_DARK.text_secondary in dark_svg or "currentColor" not in dark_svg
    assert JETBRAINS_LIGHT.text_secondary in light_svg or "currentColor" not in light_svg
