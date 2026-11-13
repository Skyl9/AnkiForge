"""Tests de couverture ciblés pour RAGService afin de résorber le risque CRAP."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from ankidraft.database.models import DocumentModel
from ankidraft.services.ai.rag_service import RAGService

pytestmark = pytest.mark.unit


def test_rag_service_search_modes_and_error_handling(mock_db: Any) -> None:
    """Couvre search sur RAGService (CC=6, anciennement CRAP=36.3)."""
    rag = RAGService(llm_config=None)

    # 1. Gestion d'ID invalide
    assert rag.search("not_a_number", "query") == []

    # 2. Recherche avec mock de vector_manager
    fake_results = [
        {
            "chunk_id": 1,
            "content": "Contenu trouvé",
            "score": 0.85,
            "relevance_pct": 85,
        }
    ]
    rag.vector_manager.search = MagicMock(return_value=fake_results)  # type: ignore[method-assign]

    res_hybrid = rag.search(10, "intelligence artificielle", mode="hybrid")
    assert len(res_hybrid) == 1
    assert res_hybrid[0]["content"] == "Contenu trouvé"

    res_dense = rag.search(10, "intelligence artificielle", mode="dense")
    assert len(res_dense) == 1

    res_sparse = rag.search(10, "intelligence artificielle", mode="sparse")
    assert len(res_sparse) == 1

    # 3. Exception gérée dans vector_manager
    rag.vector_manager.search = MagicMock(side_effect=RuntimeError("Erreur FAISS simulée"))  # type: ignore[method-assign]
    assert rag.search(10, "test") == []


def test_rag_service_create_index_and_stats(mock_db: Any) -> None:
    """Couvre create_index, is_indexed et get_index_stats."""
    rag = RAGService(llm_config=None)

    # 1. Document inexistant
    assert rag.create_index(999999) is False

    # 2. Document existant
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Doc_{uid}", content="Test content")

    rag.vector_manager.index_document = MagicMock(return_value=True)  # type: ignore[method-assign]
    assert rag.create_index(doc.id) is True

    # 3. is_indexed et stats
    rag.vector_manager.is_indexed = MagicMock(return_value=True)  # type: ignore[method-assign]
    assert rag.is_indexed(doc.id) is True

    rag.vector_manager.get_index_stats = MagicMock(return_value={"total_chunks": 42})  # type: ignore[method-assign]
    stats = rag.get_index_stats(doc.id)
    assert stats.get("total_chunks") == 42
