"""
Repository for Folders, Documents, Chunks, and Note-Chunk Traceability Links.
"""

from __future__ import annotations

import logging
from typing import Any

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    FolderModel,
    MediaModel,
    NoteChunkLinkModel,
    NoteModel,
)
from ankiforge.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class DocumentRepository(BaseRepository):
    """Data access repository for documents, folders, and RAG chunk linkages."""

    def get_all_folders(self) -> list[FolderModel]:
        """Retrieve all document library folders."""
        return list(FolderModel.select().order_by(FolderModel.name.asc()))

    def get_folder_by_id(self, folder_id: int) -> FolderModel | None:
        """Retrieve a folder by its ID."""
        try:
            return FolderModel.get_or_none(FolderModel.id == folder_id)
        except Exception as e:
            logger.error("Failed to get folder %s: %s", folder_id, e)
            return None

    def get_folder_by_name(self, name: str) -> FolderModel | None:
        """Retrieve a folder by its name."""
        try:
            return FolderModel.get_or_none(FolderModel.name == name)
        except Exception as e:
            logger.error("Failed to get folder by name '%s': %s", name, e)
            return None

    def create_folder(self, name: str) -> FolderModel:
        """Create a new folder."""
        with self.atomic():
            return FolderModel.create(name=name)

    def delete_folder(self, folder_id: int) -> bool:
        """Delete a folder and cascade deletion."""
        folder = self.get_folder_by_id(folder_id)
        if not folder:
            return False

        with self.atomic():
            folder.delete_instance(recursive=True)
            return True

    def get_all_documents(self, folder_id: int | None = None) -> list[DocumentModel]:
        """Retrieve all documents, optionally filtered by folder."""
        query = DocumentModel.select().order_by(DocumentModel.created_at.desc())
        if folder_id is not None:
            query = query.where(DocumentModel.folder == folder_id)
        return list(query)

    def get_document_by_id(self, doc_id: int) -> DocumentModel | None:
        """Retrieve a document by its ID."""
        try:
            return DocumentModel.get_or_none(DocumentModel.id == doc_id)
        except Exception as e:
            logger.error("Failed to get document %s: %s", doc_id, e)
            return None

    def get_document_by_title(self, title: str) -> DocumentModel | None:
        """Retrieve a document by its exact title."""
        try:
            return DocumentModel.get_or_none(DocumentModel.title == title)
        except Exception as e:
            logger.error("Failed to get document by title '%s': %s", title, e)
            return None

    def create_document(
        self,
        title: str,
        content: str = "",
        file_type: str = "md",
        folder: FolderModel | None = None,
        source_url: str | None = None,
        chroma_collection_name: str | None = None,
        original_media: MediaModel | None = None,
    ) -> DocumentModel:
        """Create a new document."""
        with self.atomic():
            return DocumentModel.create(
                title=title,
                content=content,
                file_type=file_type,
                folder=folder,
                source_url=source_url,
                chroma_collection_name=chroma_collection_name,
                original_media=original_media,
            )

    def update_document(self, doc_id: int, **kwargs: Any) -> DocumentModel | None:
        """Update fields of an existing document."""
        doc = self.get_document_by_id(doc_id)
        if not doc:
            return None

        with self.atomic():
            for key, val in kwargs.items():
                if hasattr(doc, key):
                    setattr(doc, key, val)
            doc.save()
            return doc

    def delete_document(self, doc_id: int) -> bool:
        """Delete a document and cascade to its chunks and links."""
        doc = self.get_document_by_id(doc_id)
        if not doc:
            return False

        with self.atomic():
            doc.delete_instance(recursive=True)
            return True

    def get_chunks_for_document(self, doc_id: int) -> list[DocumentChunkModel]:
        """Retrieve chunks for a document ordered by index."""
        return list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc_id).order_by(DocumentChunkModel.chunk_index.asc()))

    def create_chunks(self, doc: DocumentModel, chunks_data: list[dict[str, Any]]) -> list[DocumentChunkModel]:
        """Batch create document chunks."""
        created_chunks: list[DocumentChunkModel] = []
        with self.atomic():
            for idx, data in enumerate(chunks_data):
                chunk = DocumentChunkModel.create(
                    document=doc,
                    chunk_index=data.get("chunk_index", idx),
                    content=data.get("content", ""),
                    content_hash=data.get("content_hash", ""),
                    page_number=data.get("page_number"),
                    heading_path=data.get("heading_path"),
                    is_profiled=data.get("is_profiled", False),
                )
                created_chunks.append(chunk)
        return created_chunks

    def delete_chunks_by_document(self, doc_id: int) -> int:
        """Delete all chunks for a document."""
        with self.atomic():
            return int(DocumentChunkModel.delete().where(DocumentChunkModel.document == doc_id).execute())

    def link_note_to_chunk(
        self,
        note: NoteModel,
        chunk: DocumentChunkModel,
        is_hallucinating: bool = False,
    ) -> NoteChunkLinkModel:
        """Create or update traceability link between a note and a source chunk."""
        with self.atomic():
            link, _ = NoteChunkLinkModel.get_or_create(
                note=note,
                chunk=chunk,
                defaults={"is_hallucinating": is_hallucinating},
            )
            return link

    def get_linked_notes_for_chunk(self, chunk_id: int) -> list[NoteModel]:
        """Retrieve notes linked to a specific chunk."""
        return list(NoteModel.select().join(NoteChunkLinkModel).where(NoteChunkLinkModel.chunk == chunk_id))

    def get_coverage_stats(self, doc_id: int) -> dict[str, Any]:
        """Calculate coverage and gap metrics for a document."""
        chunks = self.get_chunks_for_document(doc_id)
        total_chunks = len(chunks)
        if total_chunks == 0:
            return {"total_chunks": 0, "covered_chunks": 0, "coverage_pct": 0.0, "total_cards": 0}

        linked_chunk_ids = {
            link.chunk.id if hasattr(link.chunk, "id") else link.chunk
            for link in NoteChunkLinkModel.select(NoteChunkLinkModel.chunk).join(DocumentChunkModel).where(DocumentChunkModel.document == doc_id)
        }
        covered_count = len(linked_chunk_ids)
        total_cards = NoteChunkLinkModel.select().join(DocumentChunkModel).where(DocumentChunkModel.document == doc_id).count()

        return {
            "total_chunks": total_chunks,
            "covered_chunks": covered_count,
            "coverage_pct": round((covered_count / total_chunks) * 100.0, 1),
            "total_cards": total_cards,
        }
