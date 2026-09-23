import uuid

import pytest
from PySide6.QtCore import Qt

from ankiforge.database.models import DocumentModel, FolderModel
from ankiforge.ui.components.document_select_window import DocumentSelectWindow

pytestmark = pytest.mark.ui


def test_document_select_window_load_and_filter(qtbot):
    """Vérifie le chargement des documents, la recherche et la validation dans DocumentSelectWindow."""
    uid = uuid.uuid4().hex[:6]
    folder = FolderModel.create(name=f"Dossier Medecine {uid}")
    doc1 = DocumentModel.create(title=f"Cardiologie Fondamentale {uid}", file_type="pdf", folder=folder)
    doc2 = DocumentModel.create(title=f"Neurologie Clinique {uid}", file_type="md")

    window = DocumentSelectWindow()
    qtbot.addWidget(window)

    # Vérification que les documents sont présents
    assert doc1.id in window._doc_items_by_id
    assert doc2.id in window._doc_items_by_id

    # Colonne métadonnées : type, volume et estimation de tokens pour choisir en connaissance de cause
    item1 = window._doc_items_by_id[doc1.id]
    item2 = window._doc_items_by_id[doc2.id]
    assert "PDF" in item1.text(1)
    assert "page(s)" in item1.text(1)
    assert "Markdown" in item2.text(1)
    assert "mots" in item2.text(1)
    assert "tokens" in item1.text(1)
    assert "Volume" in item1.toolTip(0)
    assert "Fichier" not in item1.text(1)
    assert "Volume" in item2.toolTip(0)

    # Test du filtre de recherche
    window.search_input.setText("Cardio")
    item1 = window._doc_items_by_id[doc1.id]
    item2 = window._doc_items_by_id[doc2.id]
    assert not item1.isHidden()
    assert item2.isHidden()

    # Reset recherche
    window.search_input.setText("")
    assert not item1.isHidden()
    assert not item2.isHidden()

    # Test sélection et émission
    selected_docs = []
    window.document_selected.connect(lambda d_id, d_title: selected_docs.append((d_id, d_title)))

    window.tree.setCurrentItem(item1)
    assert window.btn_confirm.isEnabled()

    qtbot.mouseClick(window.btn_confirm, Qt.MouseButton.LeftButton)
    assert len(selected_docs) == 1
    assert selected_docs[0][0] == doc1.id
