"""
Service de réconciliation déterministe et de traçabilité entre documents sources et fiches Anki.

Établit les correspondances NoteModel <-> DocumentChunkModel (NoteChunkLinkModel)
exclusivement à partir des tags de traçabilité (doc:<id>, source:<slug>, page:<num>, section:<slug>).
Conforme aux Règles 2, 8, 19 et 20 de GEMINI.md.
"""

from __future__ import annotations

import logging
import shutil
from typing import Any

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    MediaModel,
    NoteChunkLinkModel,
    NoteModel,
    db,
)
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.utils.paths import get_profile_dir
from ankiforge.utils.tags import clean_source_slug, extract_tag_metadata

logger = logging.getLogger(__name__)


class CoverageAlignmentService:
    """Moteur de réconciliation déterministe de couverture documentaire par tags."""

    @classmethod
    def sync_coverage_from_tags(cls, doc_id: int | None = None) -> dict[str, Any]:
        """
        Synchronise déterministement les liaisons NoteModel <-> DocumentChunkModel à partir des tags des notes.

        Recherche et exploite les tags :
        - doc:<id> ou source:<slug>
        - page:<num>
        - section:<slug>

        En mode ciblé (doc_id), les liens résiduels dont la note ne porte plus de tags
        concordants vers ce document sont retirés (déliaison des liens "stale").

        Args:
            doc_id: Optionnel. Si spécifié, restreint la réconciliation à ce document.

        Returns:
            dict[str, Any]: Rapport statistique de réconciliation.
        """
        doc_repo = DocumentRepository()

        if doc_id is not None:
            target_doc = DocumentModel.get_or_none(DocumentModel.id == doc_id)
            if not target_doc:
                return {"matched_notes": 0, "newly_linked": 0, "covered_chunks": 0, "total_chunks": 0, "coverage_pct": 0.0}
            docs_by_id = {target_doc.id: target_doc}
            docs_by_slug = {clean_source_slug(target_doc.title): target_doc}
        else:
            all_docs = list(DocumentModel.select())
            if not all_docs:
                return {"matched_notes": 0, "newly_linked": 0, "covered_chunks": 0, "total_chunks": 0, "coverage_pct": 0.0}
            docs_by_id = {d.id: d for d in all_docs}
            docs_by_slug = {clean_source_slug(d.title): d for d in all_docs}

        # Seules les notes portant des tags de traçabilité sont concernées : évite le scan O(N*M)
        all_notes = list(NoteModel.select().where((NoteModel.tags.contains("doc:")) | (NoteModel.tags.contains("source:"))))
        newly_linked = 0
        matched_notes = 0

        with db.atomic():
            for note in all_notes:
                if not note.tags:
                    continue
                meta = extract_tag_metadata(note.tags)
                matched_doc: DocumentModel | None = None
                if meta["doc_id"] is not None and meta["doc_id"] in docs_by_id:
                    matched_doc = docs_by_id[meta["doc_id"]]
                elif meta["source_slug"] is not None and meta["source_slug"] in docs_by_slug:
                    matched_doc = docs_by_slug[meta["source_slug"]]

                if not matched_doc:
                    continue

                target_chunk: DocumentChunkModel | None = None
                page_num = meta["page_number"]
                section_slug = meta["section_slug"]

                if page_num is not None and page_num > 0:
                    target_chunk = DocumentChunkModel.select().where(DocumentChunkModel.document == matched_doc, DocumentChunkModel.page_number == page_num).first()
                elif section_slug:
                    for c in DocumentChunkModel.select().where(DocumentChunkModel.document == matched_doc):
                        if c.heading_path and clean_source_slug(c.heading_path) == section_slug:
                            target_chunk = c
                            break
                else:
                    target_chunk = DocumentChunkModel.select().where(DocumentChunkModel.document == matched_doc).order_by(DocumentChunkModel.chunk_index.asc()).first()

                if target_chunk:
                    matched_notes += 1
                    _, created = NoteChunkLinkModel.get_or_create(
                        note=note,
                        chunk=target_chunk,
                        defaults={"is_hallucinating": False},
                    )
                    if created:
                        newly_linked += 1

        stale_removed = 0
        if doc_id is not None and target_doc is not None:
            with db.atomic():
                stale_removed = cls._remove_stale_links(target_doc, docs_by_id, docs_by_slug)

        if doc_id is not None:
            stats = doc_repo.get_coverage_stats(doc_id)
            return {
                "matched_notes": matched_notes,
                "newly_linked": newly_linked,
                "stale_removed": stale_removed,
                "covered_chunks": stats.get("covered_chunks", 0),
                "total_chunks": stats.get("total_chunks", 0),
                "coverage_pct": stats.get("coverage_pct", 0.0),
                "unit_type": stats.get("unit_type", "pages"),
                "total_units": stats.get("total_units", 0),
                "covered_units": stats.get("covered_units", 0),
            }

        return {
            "matched_notes": matched_notes,
            "newly_linked": newly_linked,
            "total_documents": len(docs_by_id),
        }

    @staticmethod
    def _remove_stale_links(
        target_doc: DocumentModel,
        docs_by_id: dict[int, DocumentModel],
        docs_by_slug: dict[str, DocumentModel],
    ) -> int:
        """Retire les liens vers un document dont la note garde des tags ne pointant plus vers ce document."""
        removed = 0
        doc_links = NoteChunkLinkModel.select().join(DocumentChunkModel).where(DocumentChunkModel.document == target_doc)
        for link in doc_links:
            note = link.note
            if not note.tags:
                continue
            meta = extract_tag_metadata(note.tags)
            resolved_doc: DocumentModel | None = None
            if meta["doc_id"] is not None and meta["doc_id"] in docs_by_id:
                resolved_doc = docs_by_id[meta["doc_id"]]
            elif meta["source_slug"] is not None and meta["source_slug"] in docs_by_slug:
                resolved_doc = docs_by_slug[meta["source_slug"]]
            if resolved_doc is None or resolved_doc.id != target_doc.id:
                link.delete_instance()
                removed += 1
        return removed

    @classmethod
    def align_document(
        cls,
        doc_id: int,
        deck_id: int | None = None,
        min_overlap: int = 2,
        clear_existing: bool = False,
    ) -> dict[str, Any]:
        """
        Réconcilie les fiches existantes de la base de données avec les fragments d'un document.

        Effectue une synchronisation déterministe par tags (doc:<id>, source:<slug>, page:<num>, section:<slug>).
        Les paramètres deck_id et min_overlap sont conservés pour la compatibilité des appelants mais sans effet :
        aucun matching sémantique/lexical n'est réalisé.

        Args:
            doc_id: ID du document cible.
            deck_id: Ignoré (compatibilité). Réservé à une réconciliation par paquet.
            min_overlap: Ignoré (compatibilité).
            clear_existing: Si True, supprime tous les liens existants du document avant réconciliation.

        Returns:
            dict[str, Any]: Rapport statistique de réconciliation et de couverture.
        """
        doc = DocumentModel.get_or_none(DocumentModel.id == doc_id)
        if not doc:
            logger.warning("CoverageAlignmentService : Document ID=%d introuvable.", doc_id)
            return {
                "error": f"Document {doc_id} introuvable",
                "matched_notes": 0,
                "total_notes": 0,
                "covered_chunks": 0,
                "total_chunks": 0,
                "coverage_pct": 0.0,
            }

        chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc).order_by(DocumentChunkModel.chunk_index))
        total_chunks = len(chunks)
        if total_chunks == 0 and not doc.total_pages:
            logger.info("CoverageAlignmentService : Aucun fragment pour le document '%s'.", doc.title)
            return {
                "matched_notes": 0,
                "total_notes": 0,
                "covered_chunks": 0,
                "total_chunks": 0,
                "coverage_pct": 0.0,
            }

        if clear_existing:
            with db.atomic():
                chunk_ids = [c.id for c in chunks]
                NoteChunkLinkModel.delete().where(NoteChunkLinkModel.chunk.in_(chunk_ids)).execute()

        tag_res = cls.sync_coverage_from_tags(doc_id=doc_id)
        matched = tag_res.get("matched_notes", 0)

        doc_repo = DocumentRepository()
        stats = doc_repo.get_coverage_stats(doc_id)
        total_notes = NoteChunkLinkModel.select().join(DocumentChunkModel).where(DocumentChunkModel.document == doc).count()

        logger.info(
            "CoverageAlignmentService : Réconciliation terminée pour '%s' : %d cartes liées via tags (Couverture : %.1f%%)",
            doc.title,
            matched,
            stats.get("coverage_pct", 0.0),
        )

        return {
            "matched_notes": matched,
            "total_notes": total_notes,
            "total_cards": stats.get("total_cards", 0),
            "covered_chunks": stats.get("covered_chunks", 0),
            "total_chunks": stats.get("total_chunks", 0),
            "coverage_pct": stats.get("coverage_pct", 0.0),
            "unit_type": stats.get("unit_type", "pages"),
            "total_units": stats.get("total_units", 0),
            "covered_units": stats.get("covered_units", 0),
        }

    @classmethod
    def align_all_documents(cls, min_overlap: int = 2) -> dict[str, Any]:
        """Exécute la réconciliation déterministe sur tous les documents de la bibliothèque du profil courant."""
        all_docs = list(DocumentModel.select())
        summary: dict[str, Any] = {
            "total_documents": len(all_docs),
            "total_matched_links": 0,
            "details": [],
        }

        for doc in all_docs:
            res = cls.align_document(doc.id, min_overlap=min_overlap)
            summary["total_matched_links"] += res.get("matched_notes", 0)
            summary["details"].append({"doc_id": doc.id, "title": doc.title, "result": res})

        return summary

    @classmethod
    def find_matching_chunk_for_note(cls, note_id: int, min_overlap: int = 2) -> DocumentChunkModel | None:
        """Trouve le fragment de document le plus pertinent pour une note donnée via sa traçabilité par tags."""
        note = NoteModel.get_or_none(NoteModel.id == note_id)
        if not note:
            return None

        existing_link = NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == note).first()
        if existing_link:
            return existing_link.chunk

        # Recherche déterministe via les tags de la note
        if note.tags:
            meta = extract_tag_metadata(note.tags)
            doc_target: DocumentModel | None = None
            if meta["doc_id"] is not None:
                doc_target = DocumentModel.get_or_none(DocumentModel.id == meta["doc_id"])
            elif meta["source_slug"]:
                for d in DocumentModel.select():
                    if clean_source_slug(d.title) == meta["source_slug"]:
                        doc_target = d
                        break

            if doc_target:
                if meta["page_number"] is not None:
                    chunk = (
                        DocumentChunkModel.select()
                        .where(
                            DocumentChunkModel.document == doc_target,
                            DocumentChunkModel.page_number == meta["page_number"],
                        )
                        .first()
                    )
                    if chunk:
                        return chunk
                if meta["section_slug"]:
                    for c in DocumentChunkModel.select().where(DocumentChunkModel.document == doc_target):
                        if c.heading_path and clean_source_slug(c.heading_path) == meta["section_slug"]:
                            return c
                first_chunk = DocumentChunkModel.select().where(DocumentChunkModel.document == doc_target).order_by(DocumentChunkModel.chunk_index.asc()).first()
                if first_chunk:
                    return first_chunk

        return None

    @classmethod
    def copy_document_from_profile(
        cls,
        source_profile: str,
        target_profile: str,
        doc_id: int,
    ) -> DocumentModel | None:
        """
        Copie un DocumentModel et ses chunks d'un profil source vers le profil cible.
        Copie également les fichiers physiques associés (original_media).
        """
        import sqlite3

        src_dir = get_profile_dir(source_profile)
        src_db_path = src_dir / "ankiforge.db"
        if not src_db_path.exists():
            logger.warning("Base source introuvable pour profil '%s' : %s", source_profile, src_db_path)
            return None

        src_con = sqlite3.connect(src_db_path)
        src_con.row_factory = sqlite3.Row
        src_cur = src_con.cursor()

        doc_row = src_cur.execute("SELECT * FROM documentmodel WHERE id = ?", (doc_id,)).fetchone()
        if not doc_row:
            src_con.close()
            return None

        media_filename = None
        orig_name = None
        mime = None
        chksum = None
        if doc_row["original_media_id"]:
            m_row = src_cur.execute("SELECT * FROM mediamodel WHERE id = ?", (doc_row["original_media_id"],)).fetchone()
            if m_row:
                media_filename = m_row["filename"]
                orig_name = m_row["original_name"]
                mime = m_row["mime_type"]
                chksum = m_row["checksum"]

        chunks_rows = src_cur.execute(
            "SELECT * FROM document_chunks WHERE document_id = ? ORDER BY chunk_index",
            (doc_id,),
        ).fetchall()
        src_con.close()

        target_media_id = None
        target_media_dir = get_profile_dir(target_profile) / "media"
        target_media_dir.mkdir(parents=True, exist_ok=True)

        if media_filename:
            src_media_file = src_dir / "media" / media_filename
            if src_media_file.exists():
                dst_media_file = target_media_dir / media_filename
                if not dst_media_file.exists():
                    shutil.copy2(src_media_file, dst_media_file)

            target_media, _ = MediaModel.get_or_create(
                checksum=chksum or media_filename,
                defaults={
                    "filename": media_filename,
                    "original_name": orig_name or media_filename,
                    "mime_type": mime or "application/octet-stream",
                },
            )
            target_media_id = target_media.id

        doc_dict = dict(doc_row)
        new_doc, _ = DocumentModel.get_or_create(
            title=doc_dict["title"],
            defaults={
                "content": doc_dict["content"],
                "file_type": doc_dict["file_type"],
                "source_url": doc_dict["source_url"],
                "total_pages": doc_dict.get("total_pages", 1),
                "original_media_id": target_media_id,
            },
        )

        with db.atomic():
            DocumentChunkModel.delete().where(DocumentChunkModel.document == new_doc).execute()
            for r in chunks_rows:
                r_dict = dict(r)
                DocumentChunkModel.create(
                    document=new_doc,
                    chunk_index=r_dict["chunk_index"],
                    content=r_dict["content"],
                    content_hash=r_dict["content_hash"],
                    page_number=r_dict.get("page_number"),
                    heading_path=r_dict.get("heading_path"),
                    start_time=r_dict.get("start_time"),
                    end_time=r_dict.get("end_time"),
                )

        logger.info(
            "Document '%s' et %d chunks copiés avec succès de '%s' vers '%s'.",
            new_doc.title,
            len(chunks_rows),
            source_profile,
            target_profile,
        )
        return new_doc
