"""
Façade de Service RAG (Retrieval-Augmented Generation) pour l'orchestrateur DAG et l'UI.
Délègue l'indexation matricielle et la recherche hybride à VectorManager (FAISS + BM25 + RRF).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ankiforge.database.models import DocumentModel, LLMConfigModel
from ankiforge.services.rag.hybrid_retriever import (
    DEFAULT_RRF_K,
    DEFAULT_WEIGHT_DENSE,
    DEFAULT_WEIGHT_SPARSE,
)
from ankiforge.services.rag.vector_manager import VectorManager

logger = logging.getLogger(__name__)


class RAGService:
    """
    Façade de Service RAG Hybride pour l'ensemble d'AnkiForge.
    """

    def __init__(self, llm_config: Optional[LLMConfigModel] = None) -> None:
        self.vector_manager = VectorManager(llm_config=llm_config)

    def create_index(self, doc_id: int | str, text: Optional[str] = None) -> bool:
        """Crée ou met à jour l'index hybride (FAISS Dense + BM25 Sparse) pour un document."""
        try:
            doc_id_int = int(doc_id)
            doc = DocumentModel.get_or_none(DocumentModel.id == doc_id_int)
            if not doc:
                logger.warning("Document %s introuvable pour la création de l'index RAG.", doc_id)
                return False
            return self.vector_manager.index_document(doc)
        except Exception as e:
            logger.error("Erreur RAGService.create_index : %s", e)
            return False

    def search(
        self,
        doc_id: int | str,
        query: str,
        top_k: int = 5,
        mode: str = "hybrid",
        w_dense: float = DEFAULT_WEIGHT_DENSE,
        w_sparse: float = DEFAULT_WEIGHT_SPARSE,
        rrf_k: int = DEFAULT_RRF_K,
    ) -> List[Dict[str, Any]]:
        """
        Recherche sémantique, lexicale ou hybride (RRF) dans un document.
        - mode="hybrid" : FAISS + BM25 combinés par Reciprocal Rank Fusion
        - mode="dense"  : FAISS vectoriel sémantique pur
        - mode="sparse" : BM25 lexical exact pur
        """
        try:
            doc_id_int = int(doc_id)
        except (ValueError, TypeError):
            logger.warning("ID de document non numérique fourni à RAGService.search : %s", doc_id)
            return []

        try:
            return self.vector_manager.search(
                document_id=doc_id_int,
                query=query,
                top_k=top_k,
                mode=mode,
                w_dense=w_dense,
                w_sparse=w_sparse,
                rrf_k=rrf_k,
            )
        except Exception as e:
            logger.error("Erreur RAGService.search : %s", e)
            return []

    def is_indexed(self, doc_id: int | str) -> bool:
        """Vérifie si le document dispose d'index prêts pour la recherche."""
        try:
            return self.vector_manager.is_indexed(int(doc_id))
        except Exception:
            return False

    def get_index_stats(self, doc_id: int | str) -> Dict[str, Any]:
        """Retourne les métriques d'indexation du document."""
        try:
            return self.vector_manager.get_index_stats(int(doc_id))
        except Exception:
            return {}
