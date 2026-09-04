"""
Package des services RAG (Retrieval-Augmented Generation) d'AnkiForge.
Fournit le moteur d'indexation vectorielle dense FAISS, l'indexation lexicale sparse BM25
et le fusionneur par rang réciproque (Reciprocal Rank Fusion - RRF).
"""

from .bm25_index import BM25OkapiIndex, normalize_text, tokenize
from .hybrid_retriever import (
    DEFAULT_RRF_K,
    DEFAULT_WEIGHT_DENSE,
    DEFAULT_WEIGHT_SPARSE,
    HybridRAGRetriever,
    RRFScoreBreakdown,
)
from .vector_manager import VectorManager
from .visual_rag_service import VisualRAGService

__all__ = [
    "VectorManager",
    "VisualRAGService",
    "BM25OkapiIndex",
    "tokenize",
    "normalize_text",
    "HybridRAGRetriever",
    "RRFScoreBreakdown",
    "DEFAULT_RRF_K",
    "DEFAULT_WEIGHT_DENSE",
    "DEFAULT_WEIGHT_SPARSE",
]
