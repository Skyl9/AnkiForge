"""
Service de re-indexation documentaire (Qt-free).

Fournit la logique déterministe de structuration / indexation RAG d'un document,
réutilisée par CoverageWorker, le bouton « Ré-indexer FAISS » et la re-indexation
migratoire post-mise à jour. Garantit le marquage de chunk_strategy_version afin
de détecter les documents indexés avec une ancienne stratégie de découpage.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    DocumentPageModel,
    LLMConfigModel,
    db,
)
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.services.rag.vector_manager import VectorManager
from ankiforge.services.rag.visual_rag_service import VisualRAGService

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], None]

# Statuts retournés par reindex_document
REINDEX_OK = "ok"
REINDEX_EMPTY = "empty"
REINDEX_ERROR = "error"


def get_stale_documents() -> list[DocumentModel]:
    """Retourne les documents dont les chunks sont antérieurs à la stratégie courante."""
    try:
        return list(
            DocumentModel.select().where(
                DocumentModel.chunk_strategy_version != ChunkingService.CHUNKING_VERSION,
            )
        )
    except Exception as e:  # pragma: no cover - protection si colonne absente (base pré-033)
        logger.warning("Détection des documents stale impossible (%s).", e)
        return []


def mark_document_version(document: DocumentModel) -> None:
    """Stampe le document avec la version actuelle de la stratégie de découpage."""
    document.chunk_strategy_version = ChunkingService.CHUNKING_VERSION
    document.save()


def reindex_document(
    document_id: int,
    llm_config_id: int | None = None,
    progress_cb: ProgressCallback | None = None,
) -> str:
    """Re-structure, re-indexe (FAISS + BM25) et re-synchronise un document complet.

    Logique Qt-free partagée par CoverageWorker et la re-indexation migratoire.

    Args:
        document_id: ID du DocumentModel à indexer.
        llm_config_id: ID du LLMConfigModel à utiliser pour les embeddings (optionnel).
        progress_cb: Callback de progression (message).

    Returns:
        str: Statut de l'opération — ``REINDEX_OK``, ``REINDEX_EMPTY`` ou ``REINDEX_ERROR``.
    """

    def _emit(msg: str) -> None:
        logger.debug("reindex_document(%d): %s", document_id, msg)
        if progress_cb is not None:
            try:
                progress_cb(msg)
            except Exception:
                pass

    t0 = time.perf_counter()
    try:
        _emit("Initialisation de la structuration documentaire...")
        doc = DocumentModel.get_or_none(DocumentModel.id == document_id)
        if not doc:
            logger.error("reindex_document : Document ID=%d introuvable en base.", document_id)
            return REINDEX_ERROR

        cfg = LLMConfigModel.get_or_none(LLMConfigModel.id == llm_config_id) if llm_config_id else None
        vector_mgr = VectorManager(llm_config=cfg)

        # 1. CAS VISUEL : Album d'images ou Document avec pages DocumentPageModel
        has_pages = DocumentPageModel.select().where(DocumentPageModel.document == doc).exists()
        if doc.file_type == "album" or has_pages:
            _emit("Indexation RAG Visuel des planches / pages de l'album...")
            visual_rag = VisualRAGService(llm_config=cfg)

            def _on_visual_progress(cur: int, tot: int, msg: str) -> None:
                _emit(f"[{cur}/{tot}] {msg}")

            success = visual_rag.index_visual_document(
                doc,
                vector_manager=vector_mgr,
                progress_callback=_on_visual_progress,
            )
            if not success:
                logger.warning("Échec de l'indexation RAG Visuel pour '%s'.", doc.title)
                return REINDEX_ERROR

            mark_document_version(doc)
            logger.info(
                "Document visual '%s' ré-indexé avec succès en %.2fs (index_version=%d)",
                doc.title,
                time.perf_counter() - t0,
                ChunkingService.CHUNKING_VERSION,
            )
            return REINDEX_OK

        # 2. CAS TEXTUEL : DÉCOUPAGE DU DOCUMENT via ChunkingService
        strategy = ChunkingService.preferred_strategy(doc.file_type)
        extracted_chunks = ChunkingService.extract_chunks(doc.content, file_type=doc.file_type, strategy=strategy)
        if not extracted_chunks:
            logger.warning("Document '%s' vide ou trop court pour générer des chunks.", doc.title)
            return REINDEX_EMPTY

        _emit(f"Traitement de {len(extracted_chunks)} sections/paragraphes...")

        # 3. Persistance atomique des Chunks en base SQLite
        with db.atomic():
            DocumentChunkModel.delete().where(DocumentChunkModel.document == doc).execute()
            for chunk_data in extracted_chunks:
                DocumentChunkModel.create(
                    document=doc,
                    chunk_index=chunk_data["index"],
                    content=chunk_data["content"],
                    page_number=chunk_data["page_number"],
                    heading_path=chunk_data["heading_path"],
                    content_hash=chunk_data["content_hash"],
                )
        logger.info("Persistance de %d chunks en BDD pour le document '%s'", len(extracted_chunks), doc.title)

        # Marquage précoce : le document n'est plus stale une fois les nouveaux chunks
        # persistés, ce qui permet à sync_coverage_from_tags de se synchroniser contre la
        # nouvelle structure (align_document appelle sync_coverage_from_tags en interne).
        mark_document_version(doc)

        # 4. Construction de l'index vectoriel FAISS local
        _emit("Génération de l'index vectoriel FAISS...")
        vector_mgr.index_document(doc)

        # 5. Synchronisation déterministe des fiches existantes via tags de traçabilité
        _emit("Synchronisation des fiches Anki existantes via les tags...")
        from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService

        align_stats = CoverageAlignmentService.align_document(document_id)
        matched = align_stats.get("matched_notes", 0)
        cov_pct = align_stats.get("coverage_pct", 0.0)

        logger.info(
            "Document '%s' ré-indexé avec succès (%d chunks, indexation FAISS, %d cartes synchronisées, couverture %.1f%%) en %.2fs (index_version=%d)",
            doc.title,
            len(extracted_chunks),
            matched,
            cov_pct,
            time.perf_counter() - t0,
            ChunkingService.CHUNKING_VERSION,
        )
        return REINDEX_OK

    except Exception as e:
        logger.exception("Erreur dans reindex_document pour document ID=%d : %s", document_id, e)
        return REINDEX_ERROR
