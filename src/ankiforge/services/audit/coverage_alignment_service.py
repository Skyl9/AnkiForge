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
from ankiforge.utils.paths import get_profile_dir

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
    def align_document(
        cls,
        doc_id: int,
        deck_id: int | None = None,
        min_overlap: int = 2,
        clear_existing: bool = False,
    ) -> dict[str, Any]:
        """
        Aligne les fiches existantes de la base de données avec les fragments d'un document.
        Crée les correspondances dans NoteChunkLinkModel de façon atomique.
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
        if total_chunks == 0:
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

        # Pré-indexation des mots-clés des chunks pour une comparaison ultra-rapide
        chunk_data: list[tuple[DocumentChunkModel, set[str], str]] = []
        for chunk in chunks:
            raw_chunk_text = f"{chunk.heading_path or ''} {chunk.content}"
            kws = cls.extract_keywords(raw_chunk_text)
            clean_full = cls.clean_text_for_matching(raw_chunk_text)
            chunk_data.append((chunk, kws, clean_full))

        # Récupération des notes à évaluer
        query = (
            NoteModel.select(NoteModel, NoteVersionModel.content).join(NoteVersionModel).where(NoteVersionModel.is_active == True)  # noqa: E712
        )
        if deck_id is not None:
            query = query.join(CardModel, on=(CardModel.note == NoteModel.id)).where(CardModel.deck_id == deck_id)

        notes_versions = list(query)
        total_notes = len(notes_versions)
        links_to_create: list[tuple[NoteModel, DocumentChunkModel]] = []

        for note in notes_versions:
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
                links_to_create.append((note, best_chunk))

        with db.atomic():
            for note_obj, target_chunk in links_to_create:
                NoteChunkLinkModel.get_or_create(
                    note=note_obj,
                    chunk=target_chunk,
                    defaults={"is_hallucinating": False},
                )

        linked_chunk_ids = {link.chunk.id for link in NoteChunkLinkModel.select(NoteChunkLinkModel.chunk).join(DocumentChunkModel).where(DocumentChunkModel.document == doc)}
        covered_count = len(linked_chunk_ids)
        coverage_pct = round((covered_count / total_chunks * 100.0), 1) if total_chunks > 0 else 0.0
        total_cards = NoteChunkLinkModel.select().join(DocumentChunkModel).where(DocumentChunkModel.document == doc).count()

        logger.info(
            "CoverageAlignmentService : Alignement terminé pour '%s' : %d cartes liées, %d/%d sections couvertes (%.1f%%)",
            doc.title,
            total_cards,
            covered_count,
            total_chunks,
            coverage_pct,
        )

        return {
            "matched_notes": len(links_to_create),
            "total_notes": total_notes,
            "total_cards": total_cards,
            "covered_chunks": covered_count,
            "total_chunks": total_chunks,
            "coverage_pct": coverage_pct,
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
