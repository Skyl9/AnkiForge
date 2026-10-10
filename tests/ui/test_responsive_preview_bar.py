"""
Tests UI headless pour la barre d'aperçu responsive dans DocumentPreviewWidget,
DocumentScopeWidget et BatchSliceComposerDialog sur petits écrans (1280px, 1024px, 960px).
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from ankiforge.database.models import DocumentModel
from ankiforge.ui.components.flow_layout import FlowLayout
from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeWidget
from ankiforge.ui.views.batch_view.dialogs import BatchSliceComposerDialog
from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import (
    DocumentDelimitationDialog,
    DocumentPreviewWidget,
)

pytestmark = pytest.mark.ui


def test_preview_header_uses_flow_layout(qtbot: pytest.Item) -> None:
    """Vérifie que la barre d'aperçu utilise FlowLayout et ses clusters logiques."""
    doc = DocumentModel(title="Cours de Neuroanatomie.pdf", file_type="pdf", total_pages=15, start_page=1, end_page=15)
    preview = DocumentPreviewWidget(doc)
    qtbot.addWidget(preview)
    preview.show()

    assert isinstance(preview.header_frame.layout(), FlowLayout)
    assert hasattr(preview, "title_cluster")
    assert hasattr(preview, "scope_cluster")
    assert hasattr(preview, "controls_cluster")
    assert hasattr(preview, "nav_box")
    assert hasattr(preview, "zoom_box")

    # Contraintes de taille minimale : le minimumSizeHint ne doit plus dépasser 400px
    min_hint = preview.header_frame.minimumSizeHint()
    assert min_hint.width() <= 400, f"Le minimumSizeHint ({min_hint.width()}) doit être <= 400px"


def test_preview_header_responsiveness_narrow_widths(qtbot: pytest.Item) -> None:
    """Vérifie qu'à des largeurs réduites (600px, 480px, 400px), aucun bouton ou label n'est écrasé."""
    doc = DocumentModel(title="Manuel de Physique.pdf", file_type="pdf", total_pages=25, start_page=1, end_page=25)
    preview = DocumentPreviewWidget(doc)
    qtbot.addWidget(preview)
    preview.show()

    for width in [650, 480, 400]:
        preview.resize(width, 600)
        QApplication.processEvents()

        # Le header doit avoir calculé une hauteur suffisante pour le retour à la ligne
        header = preview.header_frame
        assert header.width() > 0
        assert header.height() >= 30

        # Vérifier que le statut de portée et le bouton d'exclusion conservent une largeur lisible
        if preview.lbl_scope_status.isVisible():
            assert preview.lbl_scope_status.width() >= 120, f"lbl_scope_status tronqué à {preview.lbl_scope_status.width()}px pour largeur {width}"
        if preview.btn_toggle_page_scope.isVisible():
            assert preview.btn_toggle_page_scope.width() >= 100, f"btn_toggle_page_scope tronqué à {preview.btn_toggle_page_scope.width()}px pour largeur {width}"

        # Les boutons de zoom et de navigation restent utilisables
        assert preview.btn_prev_page.width() == 26
        assert preview.btn_next_page.width() == 26
        assert preview.btn_zoom_fit.width() >= 45


def test_batch_slice_composer_direct_mode_preview_bar_at_1280_and_1024(qtbot: pytest.Item) -> None:
    """Vérifie la barre d'aperçu dans le compositeur de tranches batch à 1280px, 1024px et 960px."""
    doc = DocumentModel(title="Biologie Cellulaire.pdf", file_type="pdf", total_pages=30, start_page=1, end_page=30)
    dlg = BatchSliceComposerDialog(doc)
    qtbot.addWidget(dlg)
    dlg.select_mode("direct")
    dlg._on_next()  # Étape 2 : Choix des parties
    dlg.show()

    for test_width in [1280, 1024, 960]:
        dlg.resize(test_width, 700)
        QApplication.processEvents()

        scope = dlg.scope_widget
        assert scope is not None
        preview = scope.preview_widget
        header = preview.header_frame

        # Vérifier que le minimumSizeHint du header ne bloque pas le splitter
        assert header.minimumSizeHint().width() <= 400

        # Vérifier que le statut de portée est visible et n'est pas tronqué
        assert preview.lbl_scope_status.isVisible()
        assert "INCLUSE" in preview.lbl_scope_status.text()
        assert preview.lbl_scope_status.width() >= 120

        # Vérifier que le bouton d'exclusion est visible et lisible
        assert preview.btn_toggle_page_scope.isVisible()
        assert preview.btn_toggle_page_scope.width() >= 100

        # Vérifier la présence des contrôles de zoom et pagination
        assert preview.btn_zoom_fit.isVisible()
        assert preview.btn_zoom_fit.width() >= 45
        assert preview.spin_page.isVisible()


def test_document_scope_widget_preview_bar_at_small_screen(qtbot: pytest.Item) -> None:
    """Vérifie DocumentScopeWidget seul à 1024px et 1280px."""
    doc = DocumentModel(title="Histoire Contemporaine.pdf", file_type="pdf", total_pages=10, start_page=1, end_page=10)
    widget = DocumentScopeWidget(doc)
    qtbot.addWidget(widget)
    widget.show()

    for w in [1280, 1024]:
        widget.resize(w, 650)
        QApplication.processEvents()

        preview = widget.preview_widget
        assert preview.lbl_scope_status.isVisible()
        assert preview.lbl_scope_status.width() >= 120
        assert preview.btn_toggle_page_scope.width() >= 100
        assert preview.btn_zoom_fit.width() >= 45


def test_document_delimitation_dialog_preview_bar_at_small_screen(qtbot: pytest.Item) -> None:
    """Vérifie DocumentDelimitationDialog à 1024px et 1280px."""
    doc = DocumentModel(title="Analyse Mathématique.pdf", file_type="pdf", total_pages=12, start_page=1, end_page=12)
    dlg = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg)
    dlg.show()

    for w in [1280, 1024]:
        dlg.resize(w, 650)
        QApplication.processEvents()

        preview = dlg.preview_widget
        assert preview.lbl_scope_status.isVisible()
        assert preview.lbl_scope_status.width() >= 120
        assert preview.btn_toggle_page_scope.width() >= 100
        assert preview.btn_zoom_fit.width() >= 45


def test_sections_selection_unaffected(qtbot: pytest.Item) -> None:
    """Vérifie la non-régression explicite sur la logique de sélection des sections."""
    doc = DocumentModel(
        title="Guide de survie.md",
        file_type="md",
        content="# Intro\nTexte introductif.\n\n# Chapitre 1\nContenu chap 1.\n\n# Chapitre 2\nContenu chap 2.",
    )
    widget = DocumentScopeWidget(doc)
    qtbot.addWidget(widget)
    widget.show()

    # Le mode sélection par sections fonctionne et met à jour le résultat sans régression
    widget.activate_scope_mode("sections")
    res = widget.get_result()
    assert res is not None
    assert "selection_mode" in res
    assert res["selection_mode"] == "sections"


def test_non_paginated_markdown_preview_header(qtbot: pytest.Item) -> None:
    """Vérifie que pour un document texte non paginé, la barre d'aperçu masque la pagination et le badge de scope proprement."""
    doc = DocumentModel(
        title="Notes de Recherche.md",
        file_type="md",
        content="# Notes\nQuelques notes utiles.",
    )
    preview = DocumentPreviewWidget(doc)
    qtbot.addWidget(preview)
    preview.show()

    assert not preview._is_paginated
    assert preview.scope_cluster.isHidden()
    assert preview.nav_box.isHidden()
    assert preview.title_cluster.isVisible()
    assert preview.lbl_title.text() == "Aperçu"
