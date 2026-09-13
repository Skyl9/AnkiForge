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
        """Calculate coarse-grained coverage and gap metrics for a document (by page or section)."""
        doc = self.get_document_by_id(doc_id)
        chunks = self.get_chunks_for_document(doc_id)
        total_chunks = len(chunks)

        linked_chunk_ids = {link.chunk_id for link in NoteChunkLinkModel.select(NoteChunkLinkModel.chunk_id).join(DocumentChunkModel).where(DocumentChunkModel.document_id == doc_id)}
        covered_count = len(linked_chunk_ids)
        total_cards = NoteChunkLinkModel.select().join(DocumentChunkModel).where(DocumentChunkModel.document_id == doc_id).count()

        if total_chunks == 0 and (not doc or not doc.total_pages):
            return {
                "total_chunks": 0,
                "covered_chunks": 0,
                "coverage_pct": 0.0,
                "total_cards": 0,
                "unit_type": "sections",
                "total_units": 0,
                "covered_units": 0,
                "orphan_units": [],
            }

        file_type = (doc.file_type or "").lower() if doc else ""
        pages_in_chunks = {c.page_number for c in chunks if c.page_number is not None and c.page_number > 0}
        is_paginated = file_type in ("pdf", "album", "pptx", "epub") or bool(pages_in_chunks)
        if not is_paginated and file_type not in ("md", "markdown", "txt", "text", "web", "youtube", "yt", "audio", "mp3", "wav", "m4a"):
            is_paginated = bool(doc and doc.total_pages and doc.total_pages > 1)

        start_p = getattr(doc, "start_page", None)
        end_p = getattr(doc, "end_page", None)

        if is_paginated:
            doc_total = doc.total_pages if doc and doc.total_pages else 0
            total_raw_pages = max(doc_total, max(pages_in_chunks)) if pages_in_chunks else (doc_total or total_chunks or 1)

            effective_start = start_p if (start_p is not None and start_p > 0) else 1
            effective_end = end_p if (end_p is not None and end_p >= effective_start) else total_raw_pages
            effective_end = min(effective_end, total_raw_pages)

            active_pages_set = set(range(effective_start, effective_end + 1))
            total_active_pages = len(active_pages_set)

            covered_pages_set = {c.page_number for c in chunks if c.id in linked_chunk_ids and c.page_number is not None and c.page_number in active_pages_set}
            covered_pages_count = len(covered_pages_set)
            cov_pct = round((covered_pages_count / total_active_pages) * 100.0, 1) if total_active_pages > 0 else 0.0
            orphan_pages = sorted(list(active_pages_set - covered_pages_set))
            excluded_pages_count = max(0, total_raw_pages - total_active_pages)

            return {
                "total_chunks": total_chunks,
                "covered_chunks": covered_count,
                "coverage_pct": cov_pct,
                "total_cards": total_cards,
                "unit_type": "pages",
                "total_units": total_active_pages,
                "covered_units": covered_pages_count,
                "orphan_units": orphan_pages,
                "total_pages": total_active_pages,
                "covered_pages": sorted(list(covered_pages_set)),
                "excluded_units": excluded_pages_count,
                "start_page": effective_start,
                "end_page": effective_end,
            }

        # Document continu (Markdown, Web, texte, audio)
        headings_in_chunks = [c.heading_path for c in chunks if c.heading_path]
        if headings_in_chunks:
            distinct_headings = list(dict.fromkeys(headings_in_chunks))
            covered_headings = {c.heading_path for c in chunks if c.id in linked_chunk_ids and c.heading_path}
            total_sections = len(distinct_headings)
            covered_sections = len(covered_headings)
            cov_pct = round((covered_sections / total_sections) * 100.0, 1) if total_sections > 0 else 0.0
            orphan_headings = [h for h in distinct_headings if h not in covered_headings]

            import json

            raw_excl = getattr(doc, "excluded_headings", None)
            excluded_count = 0
            if raw_excl:
                try:
                    parsed_excl = json.loads(raw_excl)
                    if isinstance(parsed_excl, list):
                        excluded_count = len(parsed_excl)
                except Exception:
                    excluded_count = 0

            return {
                "total_chunks": total_chunks,
                "covered_chunks": covered_count,
                "coverage_pct": cov_pct,
                "total_cards": total_cards,
                "unit_type": "sections",
                "total_units": total_sections,
                "covered_units": covered_sections,
                "orphan_units": orphan_headings,
                "excluded_units": excluded_count,
            }

        cov_pct = round((covered_count / total_chunks) * 100.0, 1) if total_chunks > 0 else 0.0
        orphan_chunks = [c.chunk_index + 1 for c in chunks if c.id not in linked_chunk_ids]
        return {
            "total_chunks": total_chunks,
            "covered_chunks": covered_count,
            "coverage_pct": cov_pct,
            "total_cards": total_cards,
            "unit_type": "sections",
            "total_units": total_chunks,
            "covered_units": covered_count,
            "orphan_units": orphan_chunks,
        }
