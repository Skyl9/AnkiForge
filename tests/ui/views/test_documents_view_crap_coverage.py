"""Tests de couverture ciblés pour DocumentsView afin de résorber le risque CRAP."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox, QTreeWidgetItem

from ankidraft.database.models import DocumentModel, FolderModel
from ankidraft.ui.style_engine import JETBRAINS_DARK
from ankidraft.ui.views.documents_view import DocumentsView
from ankidraft.ui.views.documents_view.dialogs import FolderCreateDialog

pytestmark = pytest.mark.ui


def test_documents_view_refresh_theme_coverage(qtbot: Any, mock_db: Any) -> None:
    """Couvre refresh_theme sur DocumentsView (CC=21, anciennement CRAP=427)."""
    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)

    view.refresh_theme(JETBRAINS_DARK)
    assert view.tree_explorer.styleSheet() != ""


def test_documents_view_item_moved_coverage(qtbot: Any, mock_db: Any) -> None:
    """Couvre _on_item_moved (document vers dossier, dossier vers dossier, auto-imbrication)."""
    uid = uuid.uuid4().hex[:6]
    f1 = FolderModel.create(name=f"Parent_{uid}")
    f2 = FolderModel.create(name=f"Target_{uid}")
    doc = DocumentModel.create(title=f"Doc_{uid}", content="Test content", folder=f1)

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)

    # 1. Déplacer doc de f1 vers f2
    view._on_item_moved(
        source_data={"type": "doc", "id": doc.id},
        target_data={"type": "folder", "id": f2.id},
    )
    doc_reloaded = DocumentModel.get_by_id(doc.id)
    assert doc_reloaded.folder_id == f2.id

    # 2. Déplacer doc vers la racine (target_data=None)
    view._on_item_moved(
        source_data={"type": "doc", "id": doc.id},
        target_data=None,
    )
    doc_root = DocumentModel.get_by_id(doc.id)
    assert doc_root.folder is None

    # 3. Déplacer dossier f2 dans lui-même (interdit, couvert par toast)
    view._on_item_moved(
        source_data={"type": "folder", "id": f2.id},
        target_data={"type": "folder", "id": f2.id},
    )


def test_documents_view_delete_item_coverage(qtbot: Any, mock_db: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Couvre _on_delete_item pour documents et dossiers avec confirmation mockée."""
    uid = uuid.uuid4().hex[:6]
    folder = FolderModel.create(name=f"DeleteFolder_{uid}")
    doc = DocumentModel.create(title=f"DeleteDoc_{uid}", content="Delete me", folder=folder)

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # Simuler sélection du document dans l'arbre
    tree_item = QTreeWidgetItem()
    tree_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "doc", "id": doc.id})
    view.tree_explorer.selectedItems = MagicMock(return_value=[tree_item])  # type: ignore[method-assign]

    # Refus de confirmation
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)
    view._on_delete_item()
    assert DocumentModel.get_or_none(DocumentModel.id == doc.id) is not None

    # Acceptation de confirmation
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    view._on_delete_item()
    assert DocumentModel.get_or_none(DocumentModel.id == doc.id) is None


def test_documents_view_new_folder_coverage(qtbot: Any, mock_db: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Couvre _on_new_folder et _on_new_subfolder."""
    uid = uuid.uuid4().hex[:6]
    folder = FolderModel.create(name=f"BaseFolder_{uid}")

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)

    # Rejet du dialogue de création
    monkeypatch.setattr(FolderCreateDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    view._on_new_subfolder(parent_folder_id=folder.id)

    # Acceptation du dialogue de création
    created_f = FolderModel.create(name=f"SubFolder_{uid}")
    monkeypatch.setattr(FolderCreateDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(FolderCreateDialog, "get_created_folder", lambda self: created_f)
    monkeypatch.setattr(FolderCreateDialog, "get_full_path", lambda self: created_f.name)
    view._on_new_subfolder(parent_folder_id=folder.id)


def test_documents_view_scroll_editor_to_page_coverage(qtbot: Any, mock_db: Any) -> None:
    """Couvre _scroll_editor_to_page avec marqueurs de page."""
    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)

    markdown = "# Titre\n\nPage 1 intro.\n\n<!-- page: 2 -->\n\nPage 2 contenu.\n"
    view.text_editor.set_content(markdown)

    # Défilement vers la page 2
    view._scroll_editor_to_page(2)


def test_documents_view_sandbox_search_coverage(qtbot: Any, mock_db: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Couvre _on_sandbox_search avec résultats RAG mockés."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"RAGDoc_{uid}", content="Test content")

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)
    view._current_doc_id = doc.id
    view.rag_sandbox_input.setText("test query")

    fake_results = [
        {
            "heading_path": "Chapitre 1 > Section A",
            "relevance_pct": 85,
            "score": 0.15,
            "content": "Ceci est un extrait pertinent trouvé par RAG.",
        }
    ]

    from ankidraft.services.ai.rag_service import RAGService

    monkeypatch.setattr(RAGService, "search", lambda self, doc_id, query, top_k=4: fake_results)
    view._on_sandbox_search()
    assert view.rag_sandbox_results.count() == 1
