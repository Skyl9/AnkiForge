"""
Module de Recherche RAG Hybride combinant FAISS (Dense Retrieval) et BM25 (Sparse Retrieval)
avec fusion par rang réciproque (Reciprocal Rank Fusion - RRF).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ankiforge.database.models import DocumentChunkModel

logger = logging.getLogger(__name__)

DEFAULT_RRF_K: int = 60
DEFAULT_WEIGHT_DENSE: float = 0.6
DEFAULT_WEIGHT_SPARSE: float = 0.4


@dataclass
class RRFScoreBreakdown:
    """Structure détaillée des scores pour un fragment récupéré via le RAG Hybride."""

    chunk_id: int
    chunk_index: int
    content: str
    heading_path: str
    page_number: int | None
    dense_score: float = 0.0
    dense_rank: int | None = None
    sparse_score: float = 0.0
    sparse_rank: int | None = None
    rrf_score: float = 0.0
    relevance_pct: int = 0
    retrieval_channel: str = "hybrid"  # "hybrid", "dense_only", "sparse_only"

    def to_dict(self) -> dict[str, Any]:
        """Convertit l'objet en dictionnaire enrichi compatible avec l'API existante."""
        return {
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "heading_path": self.heading_path,
            "page_number": self.page_number,
            "score": self.rrf_score,  # Clé standard pour rétrocompatibilité
            "dense_score": round(self.dense_score, 4),
            "dense_rank": self.dense_rank,
            "sparse_score": round(self.sparse_score, 4),
            "sparse_rank": self.sparse_rank,
            "rrf_score": round(self.rrf_score, 6),
            "relevance_pct": self.relevance_pct,
            "channel": self.retrieval_channel,
        }


class HybridRAGRetriever:
    """
    Moteur de fusion et de classement hybride Dense (FAISS) + Sparse (BM25) avec RRF.
    """

    @staticmethod
    def compute_rrf_score(
        rank: int | None,
        weight: float = 1.0,
        k: int = DEFAULT_RRF_K,
    ) -> float:
        """
        Calcule la contribution au score RRF pour un rang donné (1-indexé).
        Si rank est None (document absent de ce canal), retourne 0.0.
        """
        if rank is None or rank <= 0:
            return 0.0
        return weight / (k + rank)

    @classmethod
    def fuse_rankings(
        cls,
        dense_results: list[tuple[int, float]],  # [(chunk_id, dense_score), ...]
        sparse_results: list[tuple[int, float]],  # [(chunk_id, bm25_score), ...]
        k: int = DEFAULT_RRF_K,
        w_dense: float = DEFAULT_WEIGHT_DENSE,
        w_sparse: float = DEFAULT_WEIGHT_SPARSE,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Fusionne les listes de résultats Dense (FAISS) et Sparse (BM25) par Reciprocal Rank Fusion.

        dense_results : liste triée de (chunk_id, distance_or_score)
        sparse_results : liste triée de (chunk_id, bm25_score)
        """
        total_w = w_dense + w_sparse
        norm_w_dense = (w_dense / total_w) if total_w > 0 else 0.5
        norm_w_sparse = (w_sparse / total_w) if total_w > 0 else 0.5

        # 1. Cartographie des rangs et scores denses
        dense_map: dict[int, tuple[int, float]] = {}  # chunk_id -> (rank_1_indexed, score)
        for idx, (cid, score) in enumerate(dense_results):
            dense_map[cid] = (idx + 1, float(score))

        # 2. Cartographie des rangs et scores sparses
        sparse_map: dict[int, tuple[int, float]] = {}  # chunk_id -> (rank_1_indexed, score)
        for idx, (cid, score) in enumerate(sparse_results):
            sparse_map[cid] = (idx + 1, float(score))

        # 3. Union de tous les chunk_ids
        all_chunk_ids = set(dense_map.keys()).union(sparse_map.keys())
        if not all_chunk_ids:
            return []

        # 4. Calcul du score RRF combiné
        combined_scores: list[dict[str, Any]] = []
        max_possible_rrf = (norm_w_dense / (k + 1)) + (norm_w_sparse / (k + 1))

        for cid in all_chunk_ids:
            dense_info = dense_map.get(cid)
            sparse_info = sparse_map.get(cid)

            dense_rank = dense_info[0] if dense_info else None
            dense_score = dense_info[1] if dense_info else 0.0

            sparse_rank = sparse_info[0] if sparse_info else None
            sparse_score = sparse_info[1] if sparse_info else 0.0

            rrf_dense = cls.compute_rrf_score(dense_rank, weight=norm_w_dense, k=k)
            rrf_sparse = cls.compute_rrf_score(sparse_rank, weight=norm_w_sparse, k=k)
            total_rrf = rrf_dense + rrf_sparse

            # Canal d'origine
            if dense_rank is not None and sparse_rank is not None:
                channel = "hybrid"
            elif dense_rank is not None:
                channel = "dense_only"
            else:
                channel = "sparse_only"

            # Normalisation en pourcentage de pertinence (0-100%)
            rel_pct = int(min(100.0, max(0.0, (total_rrf / max_possible_rrf) * 100.0))) if max_possible_rrf > 0 else 50

            combined_scores.append(
                {
                    "chunk_id": cid,
                    "dense_score": dense_score,
                    "dense_rank": dense_rank,
                    "sparse_score": sparse_score,
                    "sparse_rank": sparse_rank,
                    "rrf_score": total_rrf,
                    "relevance_pct": rel_pct,
                    "channel": channel,
                }
            )

        # 5. Tri décroissant par score RRF
        combined_scores.sort(key=lambda x: x["rrf_score"], reverse=True)
        top_candidates = combined_scores[:top_k]

        # 6. Hydratation Peewee depuis la base de données
        candidate_ids = [c["chunk_id"] for c in top_candidates]
        chunks_by_id = {chunk.id: chunk for chunk in DocumentChunkModel.select().where(DocumentChunkModel.id.in_(candidate_ids))}

        results: list[dict[str, Any]] = []
        for cand in top_candidates:
            cid = cand["chunk_id"]
            chunk = chunks_by_id.get(cid)
            if chunk:
                breakdown = RRFScoreBreakdown(
                    chunk_id=chunk.id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    heading_path=chunk.heading_path or "",
                    page_number=chunk.page_number,
                    dense_score=cand["dense_score"],
                    dense_rank=cand["dense_rank"],
                    sparse_score=cand["sparse_score"],
                    sparse_rank=cand["sparse_rank"],
                    rrf_score=cand["rrf_score"],
                    relevance_pct=cand["relevance_pct"],
                    retrieval_channel=cand["channel"],
                )
                results.append(breakdown.to_dict())

        return results
