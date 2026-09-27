"""Tests UI des widgets de linter (cartes de diagnostic documentaire) — Analyse & Audit > Documents."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication

from ankiforge.ui.components.buttons import COMPACT_BUTTON_HEIGHT
from ankiforge.ui.components.linter_widgets import SourceDiagnosticCardWidget
from ankiforge.ui.style_engine import JETBRAINS_DARK, get_style_engine

pytestmark = pytest.mark.ui

_COLOR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}|rgba?\([^)]*\)")


def _diagnostic_data() -> dict[str, Any]:
    return {
        "doc_id": 42,
        "title": "Cours de Droit Constitutionnel",
        "extension": "pdf",
        "coverage_pct": 78.0,
        "is_indexed": True,
        "total_chunks": 24,
        "covered_chunks": 19,
        "orphan_chunks": 5,
        "total_cards": 31,
        "density": 1.3,
        "word_count": 12840,
    }


def _build_card(qtbot: Any) -> SourceDiagnosticCardWidget:
    card = SourceDiagnosticCardWidget(_diagnostic_data())
    qtbot.addWidget(card)
    return card


@contextmanager
def _production_stylesheet() -> Iterator[None]:
    """Applique le QSS global du Design System (comme au runtime) puis le restaure."""
    app = QApplication.instance()
    assert app is not None
    previous = app.styleSheet()
    app.setStyleSheet(get_style_engine().generate_stylesheet(JETBRAINS_DARK))
    try:
        yield
    finally:
        app.setStyleSheet(previous)


def _qss_rule(qss: str, selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{(.*?)\}}", qss, re.DOTALL)
    assert match is not None, f"sélecteur absent du QSS global : {selector}"
    return match.group(1)


def test_compact_density_rule_is_declared_in_the_design_system():
    """La densité compacte est déclarée dans le StyleEngine, sans couleur ni police durcie."""
    rule = _qss_rule(get_style_engine().generate_stylesheet(JETBRAINS_DARK), 'QPushButton[density="compact"]')

    assert f"font-size: {JETBRAINS_DARK.font_size_sm}px" in rule
    assert "padding: 2px 12px" in rule
    assert not _COLOR_LITERAL.search(rule)


def test_source_diagnostic_card_inspect_button_not_vertically_squashed(qtbot):
    """Le pied de carte réserve au bouton une hauteur qui accueille son texte et son icône."""
    with _production_stylesheet():
        card = _build_card(qtbot)
        card.show()
        qtbot.waitExposed(card)
        button = card.btn_inspect

        assert button.property("density") == "compact"
        assert button.styleSheet() == ""
        assert button.height() == COMPACT_BUTTON_HEIGHT
        assert button.height() >= button.minimumSizeHint().height(), f"bouton écrasé : hauteur {button.height()}px < contenu requis {button.minimumSizeHint().height()}px"


def test_source_diagnostic_card_footer_balances_meta_label_and_button(qtbot):
    """Le bouton 'Inspecter l'audit' reste lisible et centré sur la ligne de métadonnées du pied."""
    with _production_stylesheet():
        card = _build_card(qtbot)
        card.show()
        qtbot.waitExposed(card)
        label, button = card.lbl_meta, card.btn_inspect

        assert label.text() == ".PDF · 12,840 mots"
        assert not button.icon().isNull()
        assert label.width() >= label.sizeHint().width()
        assert button.height() >= label.sizeHint().height()
        # QLabel centre son texte verticalement : les deux rects doivent partager l'axe optique.
        assert abs(label.geometry().center().y() - button.geometry().center().y()) <= 1


def test_source_diagnostic_card_inspect_button_emits_document_id(qtbot):
    """Le clic sur le bouton Inspecter l'audit émet l'identifiant du document surveillé."""
    card = _build_card(qtbot)
    emitted: list[int] = []
    card.inspect_requested.connect(emitted.append)

    card.btn_inspect.click()

    assert emitted == [42]


def test_compact_density_renders_the_theme_small_font(qtbot):
    """Le bouton compact hérite de `font_size_sm` du thème, sans police durcie dans le widget."""
    with _production_stylesheet():
        card = _build_card(qtbot)
        card.show()
        qtbot.waitExposed(card)

        assert card.btn_inspect.font().pixelSize() == JETBRAINS_DARK.font_size_sm
