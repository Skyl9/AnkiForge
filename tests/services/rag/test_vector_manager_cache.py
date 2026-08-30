"""
Unit tests for VectorManager persistent embedding cache.
"""

from __future__ import annotations

import numpy as np

from ankiforge.database.models import DocumentModel, EmbeddingCacheModel
from ankiforge.services.rag.vector_manager import VectorManager


def test_embedding_cache_hit_and_persistence() -> None:
    vm = VectorManager()
    texts = [
        "L'atome d'hydrogène possède un unique proton.",
        "La photosynthèse convertit l'énergie lumineuse en glucose.",
    ]

    # First call: cache miss, saves to EmbeddingCacheModel
    embs1 = vm._get_embeddings(texts)
    assert embs1.shape[0] == 2
    assert embs1.shape[1] > 0

    cached_count = EmbeddingCacheModel.select().count()
    assert cached_count == 2

    # Second call: cache hit, instant re-load from database
    embs2 = vm._get_embeddings(texts)
    assert embs2.shape == embs1.shape
    np.testing.assert_allclose(embs1, embs2, rtol=1e-5)

    # Partial cache hit
    mixed_texts = [
        "L'atome d'hydrogène possède un unique proton.",  # cached
        "Une mitochondrie produit de l'ATP.",  # new
    ]
    embs_mixed = vm._get_embeddings(mixed_texts)
    assert embs_mixed.shape[0] == 2
    np.testing.assert_allclose(embs1[0], embs_mixed[0], rtol=1e-5)
    assert EmbeddingCacheModel.select().count() == 3

    # Clear cache
    cleared = vm.clear_embedding_cache()
    assert cleared == 3
    assert EmbeddingCacheModel.select().count() == 0


def test_document_indexing_with_cache() -> None:
    doc = DocumentModel.create(
        title="Cours de Physique",
        content="Les lois de Newton décrivent le mouvement des corps macroscopiques.\n\nF = ma relie la force à l'accélération.",
        file_type="md",
    )

    vm = VectorManager()
    success = vm.index_document(doc)
    assert success is True
    assert vm.is_indexed(doc.id)

    # Chunks are cached
    cached_count = EmbeddingCacheModel.select().count()
    assert cached_count > 0

    # Re-indexing same document uses cache
    success2 = vm.index_document(doc)
    assert success2 is True
