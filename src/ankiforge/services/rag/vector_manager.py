"""
Gestionnaire d'Indexation et de Recherche RAG Hybride (FAISS Dense + BM25 Sparse + RRF).
Fournit une recherche sémantique et lexicale 100% locale, sans fuite de données,
et compatible avec les contraintes d'exécutable autonome Nuitka.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import faiss
import numpy as np
from openai import OpenAI

from ankiforge.database.models import DocumentChunkModel, DocumentModel, LLMConfigModel
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.services.rag.bm25_index import BM25OkapiIndex
from ankiforge.services.rag.hybrid_retriever import (
    DEFAULT_RRF_K,
    DEFAULT_WEIGHT_DENSE,
    DEFAULT_WEIGHT_SPARSE,
    HybridRAGRetriever,
)
from ankiforge.utils.paths import get_app_data_dir

logger = logging.getLogger(__name__)


class VectorManager:
    """
    Gestionnaire d'Indexation et de Recherche RAG Hybride avec FAISS et BM25 100% local.
    S'appuie sur Peewee DocumentChunkModel pour le stockage des métadonnées.
    """

    def __init__(self, llm_config: Optional[LLMConfigModel] = None) -> None:
        self.llm_config = llm_config
        self.faiss_dir: Path = get_app_data_dir() / "faiss_indexes"
        self.faiss_dir.mkdir(parents=True, exist_ok=True)

        if llm_config:
            p_name = str(llm_config.provider).lower()
            base_url = "https://api.openai.com/v1" if p_name == "openai" else "http://localhost:11434/v1"
            api_key_str = str(llm_config.api_key) if llm_config.api_key else "dummy_key"
            self.client: Optional[OpenAI] = OpenAI(base_url=base_url, api_key=api_key_str)
            self.embedding_model = "mxbai-embed-large" if p_name == "ollama" else "text-embedding-3-small"
        else:
            self.client = None
            self.embedding_model = "mxbai-embed-large"

    def _get_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Récupère les embeddings pour une liste de textes.
        Si aucun client API n'est configuré (ex: hors ligne ou tests), utilise un fallback déterministe.
        """
        if self.client:
            try:
                response = self.client.embeddings.create(model=self.embedding_model, input=texts)
                embeddings = [data.embedding for data in response.data]
                return np.array(embeddings, dtype=np.float32)
            except Exception as e:
                logger.warning("Impossible de contacter l'API d'embeddings (%s). Repli sur hash vectoriel.", e)

        # Fallback local pseudo-embedding (vecteur normalisé basé sur hash de fréquence)
        dim = 128
        vectors = []
        for text in texts:
            vec = np.zeros(dim, dtype=np.float32)
            for word in text.lower().split():
                h = hash(word) % dim
                vec[h] += 1.0
            norm = float(np.linalg.norm(vec))
            if norm > 0:
                vec = vec / norm
            vectors.append(vec)
        return np.array(vectors, dtype=np.float32)

    def is_indexed(self, document_id: int) -> bool:
        """Indique si les index (FAISS ou BM25) sont disponibles sur le disque pour ce document."""
        doc_dir = self.faiss_dir / f"doc_{document_id}"
        faiss_ready = (doc_dir / "index.faiss").exists() and (doc_dir / "chunk_ids.json").exists()
        bm25_ready = (doc_dir / "bm25_index.json").exists()
        return faiss_ready or bm25_ready

    def get_index_stats(self, document_id: int) -> Dict[str, Any]:
        """Retourne les métriques détaillées de l'indexation pour un document."""
        doc_dir = self.faiss_dir / f"doc_{document_id}"
        stats: Dict[str, Any] = {
            "document_id": document_id,
            "has_faiss": (doc_dir / "index.faiss").exists(),
            "has_bm25": (doc_dir / "bm25_index.json").exists(),
            "chunk_count": 0,
            "embedding_dimension": 0,
            "bm25_vocabulary_size": 0,
        }

        if stats["has_faiss"]:
            try:
                index = faiss.read_index(str(doc_dir / "index.faiss"))
                stats["chunk_count"] = index.ntotal
                stats["embedding_dimension"] = index.d
            except Exception as e:
                logger.warning("Erreur lecture index FAISS doc %d: %s", document_id, e)

        if stats["has_bm25"]:
            try:
                bm25 = BM25OkapiIndex.load(doc_dir / "bm25_index.json")
                stats["bm25_vocabulary_size"] = len(bm25.doc_freqs)
                if stats["chunk_count"] == 0:
                    stats["chunk_count"] = bm25.total_docs
            except Exception as e:
                logger.warning("Erreur lecture index BM25 doc %d: %s", document_id, e)

        return stats

    def index_document(self, document: DocumentModel) -> bool:
        """
        Découpe un DocumentModel en DocumentChunkModel (s'ils n'existent pas encore),
        construit l'index binaire FAISS (Dense) ET l'index lexical BM25 (Sparse).
        """
        try:
            chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == document).order_by(DocumentChunkModel.chunk_index))

            # Si aucun chunk n'existe en base, on utilise ChunkingService
            if not chunks:
                extracted = ChunkingService.extract_chunks(document.content, file_type=document.file_type)
                with DocumentChunkModel._meta.database.atomic():
                    for item in extracted:
                        c = DocumentChunkModel.create(
                            document=document,
                            chunk_index=item["index"],
                            content=item["content"],
                            page_number=item["page_number"],
                            heading_path=item["heading_path"],
                            content_hash=item["content_hash"],
                        )
                        chunks.append(c)

            if not chunks:
                logger.warning("Aucun fragment à indexer pour le document %s", document.id)
                return False

            doc_dir = self.faiss_dir / f"doc_{document.id}"
            doc_dir.mkdir(parents=True, exist_ok=True)

            # ── 1. Indexation Dense FAISS ──
            chunk_texts = [c.content for c in chunks]
            embeddings = self._get_embeddings(chunk_texts)

            dimension = embeddings.shape[1]
            index = faiss.IndexFlatL2(dimension)
            index.add(embeddings)

            index_path = doc_dir / "index.faiss"
            faiss.write_index(index, str(index_path))

            chunk_ids = [c.id for c in chunks]
            with open(doc_dir / "chunk_ids.json", "w", encoding="utf-8") as f:
                json.dump(chunk_ids, f)

            # ── 2. Indexation Lexicale BM25 ──
            corpus_dict: Dict[int, str] = {c.id: c.content for c in chunks}
            bm25 = BM25OkapiIndex()
            bm25.fit(corpus_dict)
            bm25.save(doc_dir / "bm25_index.json")

            logger.info(
                "Document %s (%d fragments) indexé avec succès (FAISS Dense + BM25 Sparse).",
                document.id,
                len(chunks),
            )
            return True

        except Exception as e:
            logger.exception("Erreur lors de l'indexation RAG hybride du document %s : %s", document.id, e)
            return False

    def search(
        self,
        document_id: int,
        query: str,
        top_k: int = 5,
        mode: str = "hybrid",
        w_dense: float = DEFAULT_WEIGHT_DENSE,
        w_sparse: float = DEFAULT_WEIGHT_SPARSE,
        rrf_k: int = DEFAULT_RRF_K,
    ) -> List[Dict[str, Any]]:
        """
        Recherche RAG multimodale dans un document :
        - mode="hybrid" (défaut) : Fusion Dense (FAISS) + Sparse (BM25) par RRF
        - mode="dense" : Recherche vectorielle sémantique pure FAISS
        - mode="sparse" : Recherche lexicale pure BM25
        """
        if not query or not query.strip():
            return []

        doc_dir = self.faiss_dir / f"doc_{document_id}"
        index_path = doc_dir / "index.faiss"
        map_path = doc_dir / "chunk_ids.json"
        bm25_path = doc_dir / "bm25_index.json"

        # Fallback si aucun index n'existe du tout
        if not index_path.exists() and not bm25_path.exists():
            logger.info("Index RAG inexistant pour le document %d, recherche directe en base de données.", document_id)
            return self._db_fallback_search(document_id, query, top_k)

        # ── 1. Récupération des candidats Denses (FAISS) ──
        dense_results: List[Tuple[int, float]] = []
        candidate_count = max(top_k * 3, 20)

        if mode in ("hybrid", "dense") and index_path.exists() and map_path.exists():
            try:
                faiss_index = faiss.read_index(str(index_path))
                with open(map_path, "r", encoding="utf-8") as f:
                    chunk_ids = json.load(f)

                query_emb = self._get_embeddings([query])
                actual_k = min(candidate_count, faiss_index.ntotal)
                if actual_k > 0:
                    distances, indices = faiss_index.search(query_emb, actual_k)
                    for rank, idx in enumerate(indices[0]):
                        if idx != -1 and idx < len(chunk_ids):
                            cid = chunk_ids[idx]
                            raw_dist = float(distances[0][rank])
                            # Conversion distance L2 -> score de similarité (plus haut = meilleur)
                            dense_sim = 1.0 / (1.0 + raw_dist)
                            dense_results.append((cid, dense_sim))
            except Exception as e:
                logger.warning("Erreur recherche Dense FAISS pour doc %d: %s", document_id, e)

        # ── 2. Récupération des candidats Sparses (BM25) ──
        sparse_results: List[Tuple[int, float]] = []
        if mode in ("hybrid", "sparse"):
            if bm25_path.exists():
                try:
                    bm25 = BM25OkapiIndex.load(bm25_path)
                    sparse_results = bm25.search(query, top_k=candidate_count)
                except Exception as e:
                    logger.warning("Erreur recherche Sparse BM25 pour doc %d: %s", document_id, e)
            else:
                # Si BM25 n'a pas encore été sérialisé, on le construit à la volée depuis la BDD
                try:
                    chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document_id == document_id))
                    if chunks:
                        corpus_dict = {c.id: c.content for c in chunks}
                        bm25 = BM25OkapiIndex()
                        bm25.fit(corpus_dict)
                        bm25.save(bm25_path)
                        sparse_results = bm25.search(query, top_k=candidate_count)
                except Exception as e:
                    logger.warning("Erreur construction BM25 à la volée pour doc %d: %s", document_id, e)

        # ── 3. Routage selon le mode sélectionné ──
        if mode == "dense":
            if not dense_results and sparse_results:
                # Bascule de secours si FAISS vide
                return self._format_sparse_only_results(sparse_results[:top_k])
            return self._format_dense_only_results(dense_results[:top_k])

        if mode == "sparse":
            if not sparse_results and dense_results:
                # Bascule de secours si BM25 vide
                return self._format_dense_only_results(dense_results[:top_k])
            return self._format_sparse_only_results(sparse_results[:top_k])

        # Mode Hybrid (défaut) avec Reciprocal Rank Fusion
        if not dense_results and not sparse_results:
            return self._db_fallback_search(document_id, query, top_k)

        return HybridRAGRetriever.fuse_rankings(
            dense_results=dense_results,
            sparse_results=sparse_results,
            k=rrf_k,
            w_dense=w_dense,
            w_sparse=w_sparse,
            top_k=top_k,
        )

    def _format_dense_only_results(self, dense_results: List[Tuple[int, float]]) -> List[Dict[str, Any]]:
        """Formate les résultats du canal Dense seul."""
        candidate_ids = [cid for cid, _ in dense_results]
        chunks_by_id = {c.id: c for c in DocumentChunkModel.select().where(DocumentChunkModel.id.in_(candidate_ids))}

        results = []
        for rank, (cid, sim) in enumerate(dense_results):
            chunk = chunks_by_id.get(cid)
            if chunk:
                rel_pct = int(min(100.0, max(0.0, sim * 100.0)))
                results.append(
                    {
                        "chunk_id": chunk.id,
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content,
                        "heading_path": chunk.heading_path or "",
                        "page_number": chunk.page_number,
                        "score": round(sim, 4),
                        "dense_score": round(sim, 4),
                        "dense_rank": rank + 1,
                        "sparse_score": 0.0,
                        "sparse_rank": None,
                        "rrf_score": round(sim, 6),
                        "relevance_pct": rel_pct,
                        "channel": "dense_only",
                    }
                )
        return results

    def _format_sparse_only_results(self, sparse_results: List[Tuple[int, float]]) -> List[Dict[str, Any]]:
        """Formate les résultats du canal Sparse seul."""
        candidate_ids = [cid for cid, _ in sparse_results]
        chunks_by_id = {c.id: c for c in DocumentChunkModel.select().where(DocumentChunkModel.id.in_(candidate_ids))}

        max_bm25 = max([s for _, s in sparse_results], default=1.0)
        results = []
        for rank, (cid, bm25_s) in enumerate(sparse_results):
            chunk = chunks_by_id.get(cid)
            if chunk:
                rel_pct = int(min(100.0, max(0.0, (bm25_s / max_bm25) * 100.0))) if max_bm25 > 0 else 50
                results.append(
                    {
                        "chunk_id": chunk.id,
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content,
                        "heading_path": chunk.heading_path or "",
                        "page_number": chunk.page_number,
                        "score": round(bm25_s, 4),
                        "dense_score": 0.0,
                        "dense_rank": None,
                        "sparse_score": round(bm25_s, 4),
                        "sparse_rank": rank + 1,
                        "rrf_score": round(bm25_s, 6),
                        "relevance_pct": rel_pct,
                        "channel": "sparse_only",
                    }
                )
        return results

    def _db_fallback_search(self, document_id: int, query: str, top_k: int) -> List[Dict[str, Any]]:
        """Recherche par mots-clés de secours directement sur Peewee DocumentChunkModel."""
        terms = [t.lower() for t in query.split() if len(t) > 2]
        query_filter = None
        for t in terms:
            cond = DocumentChunkModel.content.contains(t)
            query_filter = cond if query_filter is None else (query_filter | cond)

        q = DocumentChunkModel.select().where(DocumentChunkModel.document_id == document_id)
        if query_filter is not None:
            q = q.where(query_filter)
        chunks = list(q.limit(top_k))

        return [
            {
                "chunk_id": c.id,
                "chunk_index": c.chunk_index,
                "content": c.content,
                "heading_path": c.heading_path or "",
                "page_number": c.page_number,
                "score": 1.0,
                "dense_score": 0.0,
                "dense_rank": None,
                "sparse_score": 1.0,
                "sparse_rank": idx + 1,
                "rrf_score": 1.0,
                "relevance_pct": 100,
                "channel": "db_fallback",
            }
            for idx, c in enumerate(chunks)
        ]
