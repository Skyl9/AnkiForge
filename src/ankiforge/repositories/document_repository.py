"""
Repository for Folders, Documents, Chunks, and Note-Chunk Traceability Links.
"""

from __future__ import annotations

import json
import logging
import re
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
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.services.reindex_service import mark_document_version

logger = logging.getLogger(__name__)


class DocumentRepository(BaseRepository):
    """Data access repository for documents, folders, and RAG chunk linkages."""

    _PAGE_LABEL_RE = re.compile(r"^\s*page\s*\d+\s*$", re.IGNORECASE)

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

    def ensure_folder_hierarchy(self, full_path: str) -> FolderModel:
        """Garantit l'existence de chaque niveau de l'arborescence et retourne le dossier feuille."""
        from ankiforge.utils.hierarchy import join_hierarchy, split_hierarchy

        parts = split_hierarchy(full_path)
        if not parts:
            raise ValueError("Le chemin hiérarchique du dossier ne peut être vide.")

        with self.atomic():
            leaf_folder: FolderModel | None = None
            for i in range(1, len(parts) + 1):
                level_path = join_hierarchy(parts[:i])
                leaf_folder, _ = FolderModel.get_or_create(name=level_path)

            if leaf_folder is None:
                raise RuntimeError(f"Échec de création du dossier hiérarchique pour le chemin : {full_path}")
            return leaf_folder

    def heal_folder_hierarchies(self) -> int:
        """Détecte et instancie tous les dossiers parents intermédiaires manquants de manière idempotente."""
        from ankiforge.utils.hierarchy import join_hierarchy, split_hierarchy

        created_count = 0
        all_folders = self.get_all_folders()
        existing_names = {f.name for f in all_folders}

        needed_parents: set[str] = set()
        for folder in all_folders:
            parts = split_hierarchy(folder.name)
            for i in range(1, len(parts)):
                parent_name = join_hierarchy(parts[:i])
                if parent_name not in existing_names:
                    needed_parents.add(parent_name)

        if needed_parents:
            with self.atomic():
                for p_name in sorted(needed_parents):
                    if p_name not in existing_names:
                        FolderModel.get_or_create(name=p_name)
                        existing_names.add(p_name)
                        created_count += 1

        return created_count

    def rename_folder(self, folder_id: int, new_leaf_or_full_name: str) -> FolderModel:
        """Renomme un dossier et répercute en cascade la modification sur tous ses sous-dossiers."""
        from ankiforge.utils.hierarchy import (
            descendants_prefix,
            join_hierarchy,
            parent_path,
            split_hierarchy,
        )

        folder = self.get_folder_by_id(folder_id)
        if not folder:
            raise ValueError(f"Dossier introuvable (id={folder_id})")

        old_name = folder.name
        if "::" in new_leaf_or_full_name:
            target_name = join_hierarchy(split_hierarchy(new_leaf_or_full_name))
        else:
            parent = parent_path(old_name)
            target_name = join_hierarchy((parent, new_leaf_or_full_name.strip())) if parent else new_leaf_or_full_name.strip()

        if target_name == old_name:
            return folder

        existing = self.get_folder_by_name(target_name)
        if existing and existing.id != folder.id:
            raise ValueError(f"Un dossier nommé '{target_name}' existe déjà.")

        with self.atomic():
            old_prefix = descendants_prefix(old_name)
            new_prefix = descendants_prefix(target_name)
            descendants = list(FolderModel.select().where(FolderModel.name.startswith(old_prefix)))

            folder.name = target_name
            folder.save()

            for desc in descendants:
                suffix = desc.name[len(old_prefix) :]
                desc.name = f"{new_prefix}{suffix}"
                desc.save()

        return folder

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

    def get_document_by_source_url(self, source_url: str) -> DocumentModel | None:
        """Retrieve the most recent document associated with a source URL (dédoublonnage web)."""
        try:
            return DocumentModel.select().where(DocumentModel.source_url == source_url).order_by(DocumentModel.created_at.desc()).first()
        except Exception as e:
            logger.error("Failed to get document by source_url '%s': %s", source_url, e)
            return None

    def save_imported_document(
        self,
        title: str,
        content: str,
        file_type: str = "md",
        source_url: str | None = None,
        doc_id_to_update: int | None = None,
        folder: FolderModel | None = None,
        original_media: MediaModel | None = None,
    ) -> DocumentModel:
        """Crée (ou met à jour) un document importé et régénère ses chunks RAG.

        Garantit l'unicité du titre (contrainte DB) et préserve le titre original
        lors d'une mise à jour d'un document existant.
        """
        if doc_id_to_update:
            doc = self.get_document_by_id(doc_id_to_update)
            if doc is None:
                doc = DocumentModel()
                doc.title = self._unique_title(title, source_url)
        else:
            doc = DocumentModel()
            doc.title = self._unique_title(title, source_url)

        doc.content = content
        doc.file_type = file_type
        if source_url:
            doc.source_url = source_url
        if folder is not None:
            doc.folder = folder
        if original_media is not None:
            doc.original_media = original_media

        with self.atomic():
            doc.save(force_insert=not doc.id)
        self._regenerate_chunks(doc, content, file_type)
        return doc

    def _unique_title(self, base_title: str, source_url: str | None = None) -> str:
        """Retourne un titre unique en suffixant « (N) » en cas de collision (title unique=True)."""
        candidate = (base_title or "Document importé").strip() or "Document importé"
        if not DocumentModel.select().where(DocumentModel.title == candidate).exists():
            return candidate
        n = 2
        while n < 1000:
            suffixed = f"{candidate} ({n})"
            if not DocumentModel.select().where(DocumentModel.title == suffixed).exists():
                return suffixed
            n += 1
        return f"{candidate} ({n})"

    def _regenerate_chunks(self, doc: DocumentModel, content: str, file_type: str) -> None:
        """Recalcule les fragments RAG du document et marque sa version d'indexation."""
        extracted_chunks = ChunkingService.extract_chunks(content, file_type=file_type, strategy=ChunkingService.preferred_strategy(file_type))
        with self.atomic():
            DocumentChunkModel.delete().where(DocumentChunkModel.document == doc).execute()
            for idx, chunk_data in enumerate(extracted_chunks):
                DocumentChunkModel.create(
                    document=doc,
                    chunk_index=idx,
                    content=chunk_data["content"],
                    page_number=chunk_data.get("page_number"),
                    heading_path=chunk_data.get("heading_path"),
                    start_time=chunk_data.get("start_time"),
                    end_time=chunk_data.get("end_time"),
                    content_hash=chunk_data.get("content_hash") or ChunkingService.hash_content(chunk_data["content"]),
                )
        mark_document_version(doc)

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
        mark_document_version(doc)
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

    @staticmethod
    def _parse_excluded_headings(doc: DocumentModel | None) -> list[str]:
        """Parse la liste JSON des sections exclues (délimitation) persistée sur le document."""
        if doc is None:
            return []
        raw_excl = getattr(doc, "excluded_headings", None)
        if not raw_excl:
            return []
        try:
            parsed = json.loads(raw_excl)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item]
        except Exception:
            return []
        return []

    @staticmethod
    def _is_heading_excluded(heading_path: str, low_exclusions: set[str]) -> bool:
        """Vérifie si une section correspond à une exclusion (titre exact ou sous-chaîne du fil d'Ariane)."""
        low_path = heading_path.lower().strip()
        if low_path in low_exclusions:
            return True
        return any(ex and ex in low_path for ex in low_exclusions)

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
        if not is_paginated and file_type not in ("md", "markdown", "txt", "text", "web", "youtube", "yt", "audio", "mp3", "wav", "m4a", "ipynb", "py"):
            is_paginated = bool(doc and doc.total_pages and doc.total_pages > 1)

        start_p = getattr(doc, "start_page", None)
        end_p = getattr(doc, "end_page", None)

        # Sections fines : dès qu'un fragment porte un heading_path réel (≠ libellé
        # générique "Page N" auto-généré), on privilégie la granularité section plutôt
        # que la page — cas des PDF indexés par Marker et des Markdown structurés.
        headings_in_chunks = [c.heading_path for c in chunks if c.heading_path]
        fine_headings = [h for h in headings_in_chunks if not self._PAGE_LABEL_RE.match(h)]
        use_section_units = bool(fine_headings) or (bool(headings_in_chunks) and not is_paginated)

        if use_section_units:
            distinct_headings = list(dict.fromkeys(headings_in_chunks))
            covered_headings = {c.heading_path for c in chunks if c.id in linked_chunk_ids and c.heading_path}
            low_exclusions = {e.lower().strip() for e in self._parse_excluded_headings(doc)}
            active_headings = [h for h in distinct_headings if not self._is_heading_excluded(h, low_exclusions)]
            covered_active = {h for h in covered_headings if not self._is_heading_excluded(h, low_exclusions)}
            total_sections = len(active_headings)
            covered_sections = len(covered_active & set(active_headings))
            cov_pct = round((covered_sections / total_sections) * 100.0, 1) if total_sections > 0 else 0.0
            orphan_headings = [h for h in active_headings if h not in covered_active]

            return {
                "total_chunks": total_chunks,
                "covered_chunks": covered_count,
                "coverage_pct": cov_pct,
                "total_cards": total_cards,
                "unit_type": "sections",
                "total_units": total_sections,
                "covered_units": covered_sections,
                "orphan_units": orphan_headings,
                "excluded_units": len(low_exclusions),
            }

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

    def normalize_orphan_units(self, stats: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalise la liste des unités non couvertes en entrées homogènes {kind, label, unit_id}."""
        orphan_units = stats.get("orphan_units", [])
        normalized: list[dict[str, Any]] = []
        for unit in orphan_units:
            if isinstance(unit, dict):
                normalized.append(unit)
            elif isinstance(unit, int):
                normalized.append({"kind": "page", "label": f"Page {unit}", "unit_id": unit})
            elif isinstance(unit, str):
                normalized.append({"kind": "section", "label": unit, "unit_id": unit})
        return normalized
