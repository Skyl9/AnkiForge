"""Service de re-indexation documentaire (Qt-free).

Fournit la logique déterministe de structuration / indexation RAG d'un document,
réutilisée par CoverageWorker, le bouton « Ré-indexer FAISS » et la re-indexation
migratoire post-mise à jour. Garantit le marquage de chunk_strategy_version afin
de détecter les documents indexés avec une ancienne stratégie de découpage.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

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
FragmentCallback = Callable[[int, int], None]

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


def _build_index_and_sync_coverage(
    doc: DocumentModel,
    vector_mgr: VectorManager,
    emit: Callable[[str], None],
) -> dict[str, Any]:
    """Construit l'index vectoriel du document puis resynchronise les fiches existantes.

    Cœur commun à :func:`reindex_document` et :func:`revectorize_document`. Il ne touche
    **jamais** aux fragments (ni découpage, ni suppression) : c'est à l'appelant de décider
    si les fragments doivent être reconstruits.
    """
    emit("Génération de l'index vectoriel FAISS...")
    if not vector_mgr.index_document(doc):
        # Rien d'indexable : un périmètre entièrement écarté laisse le document sans index,
        # ce qui est un résultat et non une panne. Le dire, plutôt que laisser un succès
        # annoncé sur un index absent.
        emit("Aucune matière à indexer : le périmètre du document est entièrement écarté.")

    emit("Synchronisation des fiches Anki existantes via les tags...")
    from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService

    return CoverageAlignmentService.align_document(doc.id)


def reindex_document(
    document_id: int,
    llm_config_id: int | None = None,
    progress_cb: ProgressCallback | None = None,
    fragment_cb: FragmentCallback | None = None,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> str:
    """Re-structure, re-indexe (FAISS + BM25) et re-synchronise un document complet.

    Logique Qt-free partagée par CoverageWorker et la re-indexation migratoire.

    Args:
        document_id: ID du DocumentModel à indexer.
        llm_config_id: ID du LLMConfigModel à utiliser pour les embeddings (optionnel).
        progress_cb: Callback de progression (message).
        fragment_cb: Callback opportuniste de micro-progression ``(traités, total)``.
            Il ne doit jamais faire échouer la ré-indexation ni retarder le niveau macro.
        chunk_size: Taille cible maximale d'un chunk en tokens (optionnel).
        overlap: Nombre de tokens de recouvrement entre chunks consécutifs (optionnel).

    Returns:
        Statut de l'opération — ``REINDEX_OK``, ``REINDEX_EMPTY`` ou ``REINDEX_ERROR``.
    """

    def _emit(msg: str) -> None:
        logger.debug("reindex_document(%d): %s", document_id, msg)
        if progress_cb is not None:
            try:
                progress_cb(msg)
            except Exception as err:
                logger.debug("Callback de progression ignoré : %s", err)

    def _emit_fragments(processed: int, total: int) -> None:
        if fragment_cb is None:
            return
        try:
            fragment_cb(processed, total)
        except Exception as err:
            logger.debug("Callback de fragments ignoré : %s", err)

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
                _emit_fragments(cur, tot)

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
        # Les déclarations de neutralisation sont relues depuis le document : la ré-indexation
        # est une réingestion, et une règle ne doit pas survivre sous forme d'identifiants de
        # fragments — réattribués à chaque découpage. Import local : `document_repository`
        # importe ce module pour `mark_document_version`.
        from ankiforge.repositories.document_repository import DocumentRepository

        extracted_chunks = ChunkingService.extract_chunks(
            doc.content,
            file_type=doc.file_type,
            strategy=strategy,
            declared_addresses=DocumentRepository.get_neutralized_regions(doc),
            chunk_size=chunk_size,
            overlap=overlap,
        )
        if not extracted_chunks:
            logger.warning("Document '%s' vide ou trop court pour générer des chunks.", doc.title)
            return REINDEX_EMPTY

        _emit(f"Traitement de {len(extracted_chunks)} sections/paragraphes...")
        total_fragments = len(extracted_chunks)
        _emit_fragments(0, total_fragments)

        # 3. Persistance atomique des Chunks en base SQLite
        # La micro-progression est « opportuniste » : on la coalesce (~100 émissions max)
        # pour ne pas inonder la boucle d'événements sur un document à milliers de fragments.
        fragment_stride = max(total_fragments // 100, 1)
        with db.atomic():
            DocumentChunkModel.delete().where(DocumentChunkModel.document == doc).execute()
            for chunk_pos, chunk_data in enumerate(extracted_chunks):
                DocumentChunkModel.create(
                    document=doc,
                    chunk_index=chunk_data["index"],
                    content=chunk_data["content"],
                    page_number=chunk_data["page_number"],
                    heading_path=chunk_data["heading_path"],
                    start_time=chunk_data.get("start_time"),
                    end_time=chunk_data.get("end_time"),
                    # Cette ré-indexation EST le mécanisme de mise à jour des documents
                    # d'une version à l'autre : omettre ce drapeau revenait à effacer le
                    # remplissage de la migration 043, puis à stamper la version courante
                    # sans jamais le réparer, ce qui rendait la perte définitive. Le chemin
                    # d'ingestion (`DocumentRepository._regenerate_chunks`) le propageait déjà.
                    is_structural_container=chunk_data.get("is_structural_container", False),
                    container_origin=chunk_data.get("container_origin"),
                    content_hash=chunk_data["content_hash"],
                )
                processed = chunk_pos + 1
                if processed == total_fragments or processed % fragment_stride == 0:
                    _emit_fragments(processed, total_fragments)
        logger.info("Persistance de %d chunks en BDD pour le document '%s'", len(extracted_chunks), doc.title)

        # Marquage précoce : le document n'est plus stale une fois les nouveaux chunks
        # persistés, ce qui permet à sync_coverage_from_tags de se synchroniser contre la
        # nouvelle structure (align_document appelle sync_coverage_from_tags en interne).
        mark_document_version(doc)

        # 4. Construction de l'index vectoriel FAISS puis resynchronisation des fiches
        align_stats = _build_index_and_sync_coverage(doc, vector_mgr, _emit)
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


def revectorize_document(
    document_id: int,
    llm_config_id: int | None = None,
    progress_cb: ProgressCallback | None = None,
    fragment_cb: FragmentCallback | None = None,
) -> str:
    """Reconstruit l'index vectoriel d'un document dont les fragments sont déjà à jour.

    Variante **non destructive** de :func:`reindex_document` : elle ne re-découpe ni ne
    supprime les fragments. C'est la couture adaptée à la rév vectorisation de la
    délimitation, où les fragments viennent d'être mis à jour par
    :meth:`DocumentRepository.sync_extracted_chunks` : un re-découpage destructeur
    emporterait en cascade les liens de couverture (``NoteChunkLinkModel.chunk`` est en
    ``on_delete="CASCADE"``), détruisant précisément ce que la mise à jour différentielle
    venait de préserver.

    Args:
        document_id: ID du DocumentModel dont l'index doit être reconstruit.
        llm_config_id: ID du LLMConfigModel à utiliser pour les embeddings (optionnel).
        progress_cb: Callback de progression (message).
        fragment_cb: Callback opportuniste de micro-progression ``(traités, total)``.

    Returns:
        Statut de l'opération — ``REINDEX_OK`` ou ``REINDEX_ERROR``.
    """

    def _emit(msg: str) -> None:
        logger.debug("revectorize_document(%d): %s", document_id, msg)
        if progress_cb is not None:
            try:
                progress_cb(msg)
            except Exception as err:
                logger.debug("Callback de progression ignoré : %s", err)

    t0 = time.perf_counter()
    try:
        doc = DocumentModel.get_or_none(DocumentModel.id == document_id)
        if not doc:
            logger.error("revectorize_document : Document ID=%d introuvable en base.", document_id)
            return REINDEX_ERROR

        cfg = LLMConfigModel.get_or_none(LLMConfigModel.id == llm_config_id) if llm_config_id else None
        vector_mgr = VectorManager(llm_config=cfg)

        total_fragments = DocumentChunkModel.select().where(DocumentChunkModel.document == doc).count()
        if fragment_cb is not None:
            try:
                fragment_cb(0, total_fragments)
            except Exception as err:
                logger.debug("Callback de fragments ignoré : %s", err)

        _emit("Reconstruction de l'index vectoriel du document...")
        align_stats = _build_index_and_sync_coverage(doc, vector_mgr, _emit)

        if fragment_cb is not None:
            try:
                fragment_cb(total_fragments, total_fragments)
            except Exception as err:
                logger.debug("Callback de fragments ignoré : %s", err)

        logger.info(
            "Document '%s' revéctorisé avec succès (%d chunks, %d cartes synchronisées, couverture %.1f%%) en %.2fs",
            doc.title,
            total_fragments,
            align_stats.get("matched_notes", 0),
            align_stats.get("coverage_pct", 0.0),
            time.perf_counter() - t0,
        )
        return REINDEX_OK

    except Exception as e:
        logger.exception("Erreur dans revectorize_document pour document ID=%d : %s", document_id, e)
        return REINDEX_ERROR
