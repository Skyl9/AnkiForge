"""Affordance des pastilles KPI de l'onglet Documents (vue Analyse).

Ticket « UI - AnalysisView Affordance Passive Pastilles Statistiques Sources » :

- CA 1 : une métrique s'affiche comme un statistique (fond neutre, typographie
  hiérarchisée, sans bordure de bouton) et non comme une capsule cliquable ;
- CA 2 : curseur « flèche » standard, aucun état ``:hover`` trompeur ;
- CA 3 : les valeurs continuent de suivre le rafraîchissement des diagnostics.

Les pastilles de la barre KPI sont des **indicateurs passifs** : contrairement aux
``FilterChipButton`` de la barre de filtres juste en dessous, elles ne pilotent
aucun filtre. La moindre bordure, le moindre survol ou le moindre curseur de main
promettrait donc une action que rien n'exécute.
"""

import re
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QLabel, QWidget

from ankiforge.database.models import DocumentChunkModel, DocumentModel
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.analysis_view.tabs.sources_tab import AISourcesDiagnosticTab

pytestmark = pytest.mark.ui

#: Bordure fine pleine : la signature visuelle d'un bouton secondaire.
_BUTTON_BORDER = re.compile(r"border\s*:\s*1px", re.IGNORECASE)


def _value_labels(tab: AISourcesDiagnosticTab) -> list[QLabel]:
    """Les quatre compteurs de la barre KPI, dans l'ordre des pastilles."""
    return [tab.lbl_kpi_docs_val, tab.lbl_kpi_coverage_val, tab.lbl_kpi_orphans_val, tab.lbl_kpi_cards_val]


def _font_px(font: QFont) -> int:
    """Corps effectif d'une police, quel que soit l'état du thème.

    Une feuille de style déclare le corps en pixels (``pixelSize``), ``setFont()`` en
    points (``pointSize``) : les deux représentations ne se comparent qu'après cette
    réduction, sinon un widget thématisé et un widget nu se disent « même corps ».
    """
    return font.pixelSize() if font.pixelSize() > 0 else font.pointSize()


def _create_document(order: int, chunk_count: int = 3) -> DocumentModel:
    doc = DocumentModel.create(title=f"Cours KPI {order}", content="x" * 400, file_type="pdf")
    for index in range(chunk_count):
        DocumentChunkModel.create(document=doc, chunk_index=index, heading_path=f"S{index}", content="c", content_hash=f"h{doc.id}_{index}")
    return doc


def test_kpi_stats_are_passive_indicators(qtbot: Any) -> None:
    """CA 1 + CA 2 : rien dans la barre KPI ne doit suggérer un clic."""
    tab = AISourcesDiagnosticTab()
    qtbot.addWidget(tab)

    stats = tab.kpi_stats
    assert len(stats) == 4, "les quatre métriques globales doivent être exposées (seam `kpi_stats`)"

    for stat in stats:
        assert isinstance(stat, QFrame)
        assert stat.cursor().shape() == Qt.CursorShape.ArrowCursor, "la métrique doit garder le curseur de la flèche"

        pointed = [child for child in stat.findChildren(QWidget) if child.cursor().shape() == Qt.CursorShape.PointingHandCursor]
        assert not pointed, f"curseur cliquable sur {[type(child).__name__ for child in pointed]}"

        stylesheets = [stat.styleSheet(), *(child.styleSheet() for child in stat.findChildren(QWidget))]
        for sheet in stylesheets:
            assert ":hover" not in sheet.lower(), f"état de survol trompeur : {sheet!r}"

        assert not _BUTTON_BORDER.search(stat.styleSheet()), "bordure de bouton : la métrique a l'air cliquable"

        # Le conteneur `kpi_header` porte `QFrame { border: 1px }`, et QLabel hérite de
        # QFrame : cette règle s'applique donc à *tous* les descendants du bloc, sauf si
        # chacun déclare la sienne. Sans ce retrait explicite, la métrique se re-
        # bordurerait d'un trait de bouton dès que la feuille du bloc manquerait.
        for framed in [stat, *stat.findChildren(QFrame)]:
            assert "border: none" in framed.styleSheet(), f"{type(framed).__name__} neutralise mal la bordure héritée : {framed.styleSheet()!r}"


def test_kpi_stats_hierarchize_value_over_label(qtbot: Any) -> None:
    """CA 1 : libellé discret en retrait, valeur en gras surdimensionnée et teintée."""
    tab = AISourcesDiagnosticTab()
    qtbot.addWidget(tab)

    values = _value_labels(tab)
    for stat, value in zip(tab.kpi_stats, values, strict=True):
        assert stat.isAncestorOf(value), "la valeur n'est pas portée par sa pastille"

        titles = [lbl for lbl in stat.findChildren(QLabel) if lbl is not value and lbl.text().strip()]
        assert titles, "libellé de la métrique absent"
        title = titles[0]

        # Le corps doit être porté par la feuille du widget : sous la feuille globale
        # `QWidget { font-size }` de StyleEngine, un `setFont()` est ignoré (le gras,
        # lui, survit) et la hiérarchie demandée disparaîtrait à l'exécution.
        assert "font-size" in value.styleSheet(), "corps de la valeur absent de la feuille du widget (setFont() y serait écrasé)"
        assert "font-size" in title.styleSheet(), "corps du libellé absent de la feuille du widget"
        assert _font_px(value.font()) > _font_px(title.font()), "valeur et libellé au même corps : pas de hiérarchie"
        assert _font_px(value.font()) > DesignTokens.FONT_SIZE_BASE, "le compteur ne se dégage pas du texte courant"
        assert value.font().bold(), "la valeur n'est pas en gras"
        assert DesignTokens.TEXT_MUTED in title.styleSheet(), "le libellé n'est pas en retrait (text_muted)"
        assert value.styleSheet() != title.styleSheet(), "valeur et libellé identiques : aucune distinction"


def test_kpi_stats_fit_their_labels_at_regular_width(qtbot: Any) -> None:
    """Le bloc vertical ne doit rogner ni le libellé ni la valeur à 1200 px."""
    _create_document(1)

    tab = AISourcesDiagnosticTab()
    qtbot.addWidget(tab)
    tab.resize(1200, 700)
    tab.show()
    qtbot.waitExposed(tab)
    tab.refresh_data()
    qtbot.wait(60)

    for stat in tab.kpi_stats:
        for label in stat.findChildren(QLabel):
            if not label.text().strip():
                continue
            needed = label.fontMetrics().horizontalAdvance(label.text())
            assert label.width() >= needed, f"libellé rogné : {label.text()!r} ({label.width()} px < {needed} px)"


def test_kpi_values_follow_diagnostic_refresh(qtbot: Any) -> None:
    """CA 3 : les métriques restent fidèles au rafraîchissement des diagnostics."""
    _create_document(1)

    tab = AISourcesDiagnosticTab()
    qtbot.addWidget(tab)
    assert tab.lbl_kpi_docs_val.text() == "1"
    assert tab.lbl_kpi_coverage_val.text().endswith("%")

    _create_document(2)
    tab.refresh_data()

    assert tab.lbl_kpi_docs_val.text() == "2"
    # Le rafraîchissement ne doit pas re-transformer la métrique en commande.
    assert all(stat.cursor().shape() == Qt.CursorShape.ArrowCursor for stat in tab.kpi_stats)
