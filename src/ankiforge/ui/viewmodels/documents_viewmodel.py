"""
ViewModel for Documents Library, Folder Hierarchy, and File Ingestion.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from ankiforge.database.models import DocumentModel, FolderModel
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.ui.viewmodels.base import BaseViewModel
from ankiforge.utils.event_bus import (
    AppEventBus,
    DocumentAddedEvent,
    DocumentDeletedEvent,
)

logger = logging.getLogger(__name__)


class DocumentsViewModel(BaseViewModel):
    """Encapsulates state and reactive logic for managing documentary sources."""

    data_loaded = Signal()
    document_selected = Signal(object)
    folder_selected = Signal(object)
    documents_list_updated = Signal(list)
    folders_list_updated = Signal(list)

    def __init__(
        self,
        doc_repo: DocumentRepository | None = None,
        bus: AppEventBus | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(bus=bus, parent=parent)
        self._doc_repo = doc_repo or DocumentRepository()

        self._folders: list[FolderModel] = []
        self._selected_folder: FolderModel | None = None
        self._documents: list[DocumentModel] = []
        self._selected_document: DocumentModel | None = None

    @property
    def folders(self) -> list[FolderModel]:
        return self._folders

    @property
    def documents(self) -> list[DocumentModel]:
        return self._documents

    @property
    def selected_document(self) -> DocumentModel | None:
        return self._selected_document

    def load_data(self) -> None:
        """Load folders and documents."""
        try:
            self._folders = self._doc_repo.get_all_folders()
            folder_id = self._selected_folder.id if self._selected_folder else None
            self._documents = self._doc_repo.get_all_documents(folder_id=folder_id)
            self.folders_list_updated.emit(self._folders)
            self.documents_list_updated.emit(self._documents)
            self.data_loaded.emit()
        except Exception as e:
            self.set_error(f"Failed to load documents data: {e}")

    def select_folder(self, folder_id: int | None) -> None:
        """Select folder and refresh document list."""
        if folder_id is not None:
            self._selected_folder = self._doc_repo.get_folder_by_id(folder_id)
        else:
            self._selected_folder = None

        self.folder_selected.emit(self._selected_folder)
        self._documents = self._doc_repo.get_all_documents(folder_id=folder_id)
        self.documents_list_updated.emit(self._documents)

    def select_document_by_id(self, doc_id: int) -> None:
        """Select a document."""
        doc = self._doc_repo.get_document_by_id(doc_id)
        self._selected_document = doc
        self.document_selected.emit(doc)

    def create_document(self, title: str, content: str = "", file_type: str = "md") -> DocumentModel:
        """Create a new document."""
        doc = self._doc_repo.create_document(
            title=title,
            content=content,
            file_type=file_type,
            folder=self._selected_folder,
        )
        self.publish_event(DocumentAddedEvent(doc_id=doc.id, title=doc.title, doc_type=doc.file_type))
        self.load_data()
        self.select_document_by_id(doc.id)
        return doc

    def delete_document(self, doc_id: int) -> bool:
        """Delete a document."""
        success = self._doc_repo.delete_document(doc_id)
        if success:
            self.publish_event(DocumentDeletedEvent(doc_id=doc_id))
            if self._selected_document and self._selected_document.id == doc_id:
                self._selected_document = None
                self.document_selected.emit(None)
            self.load_data()
        return success
