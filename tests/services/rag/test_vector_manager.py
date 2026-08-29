"""
Tests d'intégration pour VectorManager et RAGService avec support RAG Hybride (FAISS + BM25 + RRF).
"""

import uuid
from pathlib import Path

import pytest

from ankiforge.database.models import DocumentChunkModel, DocumentModel
from ankiforge.services.ai.rag_service import RAGService
from ankiforge.services.rag.vector_manager import VectorManager


@pytest.mark.integration
def test_vector_manager_hybrid_index_and_search(tmp_path: Path):
    """Vérifie l'indexation hybride (FAISS + BM25) et les différents modes de recherche."""
    uid = uuid.uuid4().hex[:6]
    content = (
        "# Chapitre 1 : La Cellule et la Membrane\n\n"
        "La membrane plasmique régule les échanges d'ions Na+ et K+.\n\n"
        "# Chapitre 2 : La Mitochondrie et l'Énergie\n\n"
        "La mitochondrie est un organite producteur d'ATP responsable de la respiration cellulaire et du cycle de Krebs.\n\n"
        "# Chapitre 3 : Pharmacologie Cardiaque\n\n"
        "Le traitement de l'arythmie repose sur les bêta-bloquants et l'amiodarone agissant sur le myocarde."
    )
    doc = DocumentModel.create(
        title=f"Cours de Médecine {uid}",
        content=content,
        file_type="md",
    )

    vm = VectorManager(llm_config=None)
    vm.faiss_dir = tmp_path / "faiss_test"
    vm.faiss_dir.mkdir(parents=True, exist_ok=True)

    # 1. Vérification état avant indexation
    assert vm.is_indexed(doc.id) is False

    # 2. Indexation hybride
    success = vm.index_document(doc)
    assert success is True
    assert vm.is_indexed(doc.id) is True

    # Vérification des fichiers générés sur le disque
    doc_dir = vm.faiss_dir / f"doc_{doc.id}"
    assert (doc_dir / "index.faiss").exists()
    assert (doc_dir / "chunk_ids.json").exists()
    assert (doc_dir / "bm25_index.json").exists()

    # Vérification des statistiques d'indexation
    stats = vm.get_index_stats(doc.id)
    assert stats["has_faiss"] is True
    assert stats["has_bm25"] is True
    assert stats["chunk_count"] == 3
    assert stats["bm25_vocabulary_size"] > 5

    # 3. Recherche en Mode Hybride (FAISS + BM25 + RRF)
    res_hybrid = vm.search(doc.id, "ATP respiration mitochondrie", top_k=2, mode="hybrid")
    assert len(res_hybrid) >= 1
    assert "mitochondrie" in res_hybrid[0]["content"].lower()
    assert "rrf_score" in res_hybrid[0]
    assert res_hybrid[0]["channel"] in ("hybrid", "dense_only", "sparse_only")

    # 4. Recherche en Mode Sparse (BM25 pur) sur terme médical exact
    res_sparse = vm.search(doc.id, "amiodarone bêta-bloquants", top_k=1, mode="sparse")
    assert len(res_sparse) == 1
    assert "amiodarone" in res_sparse[0]["content"].lower()
    assert res_sparse[0]["channel"] == "sparse_only"

    # 5. Recherche en Mode Dense (FAISS pur)
    res_dense = vm.search(doc.id, "membrane échanges ions", top_k=1, mode="dense")
    assert len(res_dense) == 1
    assert "membrane" in res_dense[0]["content"].lower()
    assert res_dense[0]["channel"] == "dense_only"


@pytest.mark.integration
def test_vector_manager_fallback_unindexed(tmp_path: Path):
    """Vérifie le comportement de secours (fallback direct BDD) pour un document non indexé."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Doc Non Indexé {uid}", content="Test de contenu", file_type="md")
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        content="Informatique quantique et qubits supraconducteurs.",
        page_number=1,
        heading_path="Physique",
    )

    vm = VectorManager(llm_config=None)
    vm.faiss_dir = tmp_path / "faiss_fallback"
    vm.faiss_dir.mkdir(parents=True, exist_ok=True)
    # L'index n'a pas été créé
    results = vm.search(doc.id, "quantique", top_k=1)
    assert len(results) == 1
    assert "quantique" in results[0]["content"]
    assert results[0]["channel"] == "db_fallback"


@pytest.mark.integration
def test_rag_service_hybrid_facade(tmp_path: Path):
    """Vérifie la façade RAGService avec les modes hybrides et les helpers."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Algorithmique {uid}",
        content="# Section 1\nContenu sur les arbres binaires de recherche et AVL.\n\n# Section 2\nContenu sur les graphes et le parcours de Dijkstra.",
        file_type="md",
    )

    rag = RAGService(llm_config=None)
    rag.vector_manager.faiss_dir = tmp_path / "faiss_facade"
    rag.vector_manager.faiss_dir.mkdir(parents=True, exist_ok=True)

    assert rag.is_indexed(doc.id) is False

    res_idx = rag.create_index(doc.id)
    assert res_idx is True
    assert rag.is_indexed(doc.id) is True

    # Recherche hybride
    res_search = rag.search(doc.id, "Dijkstra graphes", top_k=1, mode="hybrid")
    assert len(res_search) == 1
    assert "Dijkstra" in res_search[0]["content"]
    assert "relevance_pct" in res_search[0]

    # Stats
    stats = rag.get_index_stats(doc.id)
    assert stats["chunk_count"] == 2
