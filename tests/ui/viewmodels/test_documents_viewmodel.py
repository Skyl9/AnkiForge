"""
Unit tests for DocumentsViewModel.
"""

from __future__ import annotations

from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.ui.viewmodels.documents_viewmodel import DocumentsViewModel
from ankiforge.utils.event_bus import AppEventBus, DocumentAddedEvent, DocumentDeletedEvent


def test_documents_viewmodel_management() -> None:
    bus = AppEventBus()
    doc_repo = DocumentRepository()
    vm = DocumentsViewModel(doc_repo=doc_repo, bus=bus)

    # Folders
    folder = doc_repo.create_folder("AI Papers")

    vm.load_data()
    assert len(vm.folders) == 1

    # Select folder
    vm.select_folder(folder.id)
    assert vm._selected_folder is not None
    assert vm._selected_folder.id == folder.id

    # Create document
    added_events: list = []
    bus.subscribe(DocumentAddedEvent, lambda e: added_events.append(e))

    doc = vm.create_document(title="Attention Is All You Need", content="Transformer architecture...")
    assert doc is not None
    assert len(added_events) == 1
    assert len(vm.documents) == 1

    # Select document
    vm.select_document_by_id(doc.id)
    assert vm.selected_document is not None

    # Delete document
    deleted_events: list = []
    bus.subscribe(DocumentDeletedEvent, lambda e: deleted_events.append(e))

    vm.delete_document(doc.id)
    assert len(deleted_events) == 1
    assert vm.selected_document is None

    vm.dispose()
