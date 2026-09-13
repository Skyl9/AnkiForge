"""
Service d'alignement intelligent et de traçabilité entre documents sources et fiches Anki.
Permet d'établir les correspondances NoteModel <-> DocumentChunkModel (NoteChunkLinkModel)
par similarité textuelle, analyse des lemmes et détection de mots-clés.
Conforme aux Règles 2, 8, 9 et 19 de GEMINI.md.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from typing import Any

from peewee import fn

from ankiforge.database.models import (
    CardModel,
    DocumentChunkModel,
    DocumentModel,
    MediaModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteVersionModel,
    db,
)
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.utils.paths import get_profile_dir
from ankiforge.utils.tags import clean_source_slug, extract_tag_metadata

logger = logging.getLogger(__name__)

# Stopwords français et anglais courants à exclure lors de l'extraction de mots discriminants
DEFAULT_STOPWORDS = {
    "alors",
    "ainsi",
    "apres",
    "après",
    "aussi",
    "autre",
    "autres",
    "avant",
    "avec",
    "avoir",
    "cette",
    "celles",
    "celui",
    "ceux",
    "chaque",
    "comme",
    "dans",
    "deja",
    "déjà",
    "depuis",
    "donc",
    "dont",
    "elle",
    "elles",
    "encore",
    "entre",
    "faire",
    "fait",
    "faut",
    "leurs",
    "leur",
    "mais",
    "meme",
    "même",
    "moins",
    "notre",
    "nous",
    "parce",
    "pendant",
    "peut",
    "plus",
    "pour",
    "pourquoi",
    "quand",
    "quel",
    "quelle",
    "quelles",
    "quels",
    "sans",
    "selon",
    "serait",
    "sont",
    "sous",
    "tous",
    "tout",
    "toute",
    "toutes",
    "tres",
    "très",
    "vers",
    "votre",
    "vous",
    "with",
    "from",
    "this",
    "that",
    "these",
    "those",
    "have",
    "been",
    "which",
    "where",
    "what",
    "when",
    "their",
    "there",
    "about",
    "other",
}


class CoverageAlignmentService:
    """Moteur d'alignement intelligent et automatique de couverture documentaire."""

    @staticmethod
    def clean_text_for_matching(raw_text: str) -> str:
        """Nettoie le HTML, les formules KaTeX/LaTeX et la ponctuation d'un texte."""
        if not raw_text:
            return ""
        clean = re.sub(r"<[^>]+>", " ", raw_text)
        clean = clean.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
        clean = re.sub(r"\\[\(\)\[\]]", " ", clean)
        clean = clean.replace("$", " ")
        return clean.lower()

    @classmethod
    def extract_keywords(cls, text: str, min_len: int = 4) -> set[str]:
        """Extrait l'ensemble des termes discriminants d'un texte."""
        cleaned = cls.clean_text_for_matching(text)
        words = re.findall(r"\b\w+\b", cleaned)
        return {w for w in words if len(w) >= min_len and not w.isdigit() and w not in DEFAULT_STOPWORDS}

    @classmethod
    def sync_coverage_from_tags(cls, doc_id: int | None = None) -> dict[str, Any]:
        """
        Synchronise déterministement les liaisons NoteModel <-> DocumentChunkModel à partir des tags des notes.

        Recherche et exploite les tags :
        - doc:<id> ou source:<slug>
        - page:<num>
        - section:<slug>

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

        all_notes = list(NoteModel.select())
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
                    if not target_chunk:
                        max_idx = DocumentChunkModel.select(fn.MAX(DocumentChunkModel.chunk_index)).where(DocumentChunkModel.document == matched_doc).scalar() or 0
                        target_chunk = DocumentChunkModel.create(
                            document=matched_doc,
                            chunk_index=max_idx + 1,
                            content=f"Page {page_num}",
                            page_number=page_num,
                            heading_path=f"Page {page_num}",
                        )
                elif section_slug:
                    candidates = list(DocumentChunkModel.select().where(DocumentChunkModel.document == matched_doc))
                    for c in candidates:
                        if c.heading_path and clean_source_slug(c.heading_path) == section_slug:
                            target_chunk = c
                            break
                    if not target_chunk and candidates:
                        target_chunk = candidates[0]
                else:
                    target_chunk = DocumentChunkModel.select().where(DocumentChunkModel.document == matched_doc).order_by(DocumentChunkModel.chunk_index.asc()).first()
                    if not target_chunk:
                        target_chunk = DocumentChunkModel.create(
                            document=matched_doc,
                            chunk_index=0,
                            content=f"Document {matched_doc.title}",
                            heading_path="Section Principale",
                        )

                if target_chunk:
                    matched_notes += 1
                    _, created = NoteChunkLinkModel.get_or_create(
                        note=note,
                        chunk=target_chunk,
                        defaults={"is_hallucinating": False},
                    )
                    if created:
                        newly_linked += 1

        if doc_id is not None:
            stats = doc_repo.get_coverage_stats(doc_id)
            return {
                "matched_notes": matched_notes,
                "newly_linked": newly_linked,
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

    @classmethod
    def align_document(
        cls,
        doc_id: int,
        deck_id: int | None = None,
        min_overlap: int = 2,
        clear_existing: bool = False,
    ) -> dict[str, Any]:
        """
        Aligne les fiches existantes de la base de données avec les fragments d'un document.
        Effectue d'abord une synchronisation déterministe par tags, puis un repli lexical.
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

        # 1. Étape Déterministe : Synchronisation par tags
        tag_res = cls.sync_coverage_from_tags(doc_id=doc_id)
        matched_from_tags = tag_res.get("matched_notes", 0)

        # 2. Étape Repli Lexical (uniquement pour les notes non encore liées à ce document)
        linked_note_ids = {link.note_id for link in NoteChunkLinkModel.select(NoteChunkLinkModel.note_id).join(DocumentChunkModel).where(DocumentChunkModel.document == doc)}

        # Pré-indexation des mots-clés des chunks pour comparaison
        chunk_data: list[tuple[DocumentChunkModel, set[str], str]] = []
        for chunk in chunks:
            raw_chunk_text = f"{chunk.heading_path or ''} {chunk.content}"
            kws = cls.extract_keywords(raw_chunk_text)
            clean_full = cls.clean_text_for_matching(raw_chunk_text)
            chunk_data.append((chunk, kws, clean_full))

        query = (
            NoteModel.select(NoteModel, NoteVersionModel.content).join(NoteVersionModel).where(NoteVersionModel.is_active == True)  # noqa: E712
        )
        if deck_id is not None:
            query = query.join(CardModel, on=(CardModel.note == NoteModel.id)).where(CardModel.deck_id == deck_id)

        notes_versions = list(query)
        total_notes = len(notes_versions)
        lexical_links: list[tuple[NoteModel, DocumentChunkModel]] = []

        if chunk_data and min_overlap > 0:
            for note in notes_versions:
                if note.id in linked_note_ids:
                    continue

                content_json = getattr(note, "noteversionmodel", None)
                raw_content = content_json.content if content_json else ""
                try:
                    data = json.loads(raw_content)
                    text_combined = " ".join(str(v) for v in data.values() if v)
                except Exception:
                    text_combined = raw_content

                note_kws = cls.extract_keywords(text_combined)
                if len(note_kws) < min_overlap:
                    continue

                best_chunk: DocumentChunkModel | None = None
                best_score = 0

                for chunk_obj, c_kws, _c_clean in chunk_data:
                    overlap = len(note_kws & c_kws)
                    if overlap < min_overlap:
                        continue

                    score = overlap
                    if chunk_obj.heading_path:
                        heading_clean = chunk_obj.heading_path.lower()
                        heading_matches = sum(1 for w in note_kws if w in heading_clean)
                        score += heading_matches * 2

                    if score > best_score:
                        best_score = score
                        best_chunk = chunk_obj

                if best_chunk is not None and best_score >= min_overlap:
                    lexical_links.append((note, best_chunk))

            if lexical_links:
                with db.atomic():
                    for note_obj, target_chunk in lexical_links:
                        NoteChunkLinkModel.get_or_create(
                            note=note_obj,
                            chunk=target_chunk,
                            defaults={"is_hallucinating": False},
                        )

        doc_repo = DocumentRepository()
        stats = doc_repo.get_coverage_stats(doc_id)

        logger.info(
            "CoverageAlignmentService : Alignement terminé pour '%s' : %d cartes liées via tags, %d via lexique (Couverture : %.1f%%)",
            doc.title,
            matched_from_tags,
            len(lexical_links),
            stats.get("coverage_pct", 0.0),
        )

        return {
            "matched_notes": matched_from_tags + len(lexical_links),
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
        """Exécute l'alignement intelligent sur tous les documents de la bibliothèque du profil courant."""
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
        """Trouve le fragment de document le plus pertinent pour une note donnée."""
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

        active_ver = NoteVersionModel.get_or_none(
            NoteVersionModel.note == note,
            NoteVersionModel.is_active == True,  # noqa: E712
        )
        if not active_ver:
            return None

        try:
            data = json.loads(active_ver.content)
            text_combined = " ".join(str(v) for v in data.values() if v)
        except Exception:
            text_combined = active_ver.content

        note_kws = cls.extract_keywords(text_combined)
        if len(note_kws) < min_overlap:
            return None

        chunks = list(DocumentChunkModel.select())
        best_chunk: DocumentChunkModel | None = None
        best_score = 0

        for chunk in chunks:
            raw_chunk_text = f"{chunk.heading_path or ''} {chunk.content}"
            c_kws = cls.extract_keywords(raw_chunk_text)
            overlap = len(note_kws & c_kws)
            if overlap > best_score and overlap >= min_overlap:
                best_score = overlap
                best_chunk = chunk

        return best_chunk

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
