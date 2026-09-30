"""
Tests d'intégration pour VectorManager et RAGService avec support RAG Hybride (FAISS + BM25 + RRF).
"""

import uuid
from pathlib import Path

import pytest

from ankiforge.database.models import DocumentChunkModel, DocumentModel
from ankiforge.services.ai.rag_service import RAGService
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.services.rag.vector_manager import VectorManager
from ankiforge.utils.region_address import RegionAddress, RegionScope, render_region_addresses

pytestmark = pytest.mark.integration


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


@pytest.mark.integration
def test_rag_excludes_excluded_regions_from_every_retrieval_path(tmp_path: Path):
    """Une région écartée ne doit revenir par aucune porte de récupération.

    L'écartement est non destructif : le fragment reste en base, réintégrable. Mais l'index et
    le repli en base sont des artefacts dérivés — s'ils servaient la matière écartée, une
    exclusion se réduirait à un commentaire et une carte pourrait être produite depuis une
    section que l'utilisateur a retirée du document. Le comportement ne doit pas dépendre du
    fait qu'un index existe ou non : d'où les deux portes vérifiées ici.
    """
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Exclu {uid}",
        content="# Mitochondrie\nLa mitochondrie produit de l'ATP par respiration cellulaire.\n\n# Lissithapie\nLa lissithapie lisse les troubles du rythme cardiaque.",
        file_type="md",
    )
    doc = DocumentModel.get_by_id(doc.id)
    chunks = ChunkingService.extract_chunks(str(doc.content), file_type="md", strategy=ChunkingService.preferred_strategy("md"))
    for item in chunks:
        DocumentChunkModel.create(
            document=doc,
            chunk_index=item["index"],
            content=item["content"],
            page_number=item["page_number"],
            heading_path=item["heading_path"],
            content_hash=item["content_hash"],
        )
    # Exclusion typée de la seconde section, et seulement elle.
    doc.excluded_headings = render_region_addresses([RegionAddress(RegionScope.HEADING, "Lissithapie")])
    doc.save(only=["excluded_headings"])

    vm = VectorManager(llm_config=None)
    vm.faiss_dir = tmp_path / "faiss_exclu"
    vm.faiss_dir.mkdir(parents=True, exist_ok=True)

    # Porte 1 : index persisté (FAISS + BM25).
    assert vm.index_document(doc) is True
    results = vm.search(doc.id, "lissithapie troubles du rythme cardiaque", top_k=5, mode="hybrid")
    assert all("Lissithapie" not in (r.get("heading_path") or "") for r in results), results

    # Porte 2 : repli en base, sans aucun index sur disque.
    vm.faiss_dir = tmp_path / "faiss_vide"
    fallback = vm.search(doc.id, "lissithapie troubles du rythme cardiaque", top_k=5)
    assert all("Lissithapie" not in (r.get("heading_path") or "") for r in fallback), fallback

    # La matière, elle, est intacte et réintégrable.
    assert DocumentChunkModel.select().where(DocumentChunkModel.document == doc, DocumentChunkModel.heading_path == "Lissithapie").exists()


def test_reindexing_a_fully_excluded_document_retires_the_previous_index(mock_db, tmp_path, monkeypatch):
    """Un périmètre entièrement écarté ne doit pas laisser l'ancien index répondre à sa place.

    L'index est un artefact dérivé : le rebuild qui découvre qu'il n'a plus rien à dire doit
    effacer ce qu'il disait, sinon la règle d'exclusion ne s'applique qu'aux documents qu'on
    réindexe *après* l'avoir posée — l'inverse exact de ce qu'on attend d'elle.
    """
    from ankiforge.database.models import DocumentChunkModel, DocumentModel
    from ankiforge.repositories.document_repository import DocumentRepository
    from ankiforge.utils.region_address import RegionAddress, RegionScope

    manager = VectorManager()
    manager.faiss_dir = tmp_path / "faiss"

    doc = DocumentModel.create(title="Cours Entierement Ecarte", content="# A\nAlpha.", file_type="md")
    kept = DocumentChunkModel.create(document=doc, chunk_index=0, heading_path="A", content="Alpha le contrat.", content_hash="h_keep")
    stale = DocumentChunkModel.create(document=doc, chunk_index=1, heading_path="B", content="Beta la clause.", content_hash="h_stale")

    assert manager.index_document(doc) is True
    assert (manager.faiss_dir / f"doc_{doc.id}" / "index.faiss").exists()
    assert stale.id in [hit["chunk_id"] for hit in manager.search(doc.id, "la clause", top_k=5)]

    DocumentRepository().set_region_excluded(doc.id, RegionAddress(RegionScope.HEADING, "A"), True)
    DocumentRepository().set_region_excluded(doc.id, RegionAddress(RegionScope.HEADING, "B"), True)

    assert manager.index_document(DocumentModel.get_by_id(doc.id)) is False

    assert manager.search(doc.id, "la clause", top_k=5) == []
    assert not (manager.faiss_dir / f"doc_{doc.id}" / "index.faiss").exists()
    assert kept.id != stale.id


def test_search_honours_an_exclusion_set_after_the_index_was_built(mock_db, tmp_path):
    """Poser une exclusion s'applique sans attendre une réindexation.

    L'index est un artefact figé : s'il était la seule porte d'entrée du filtre, une exclusion
    resterait inerte jusqu'au rebuild suivant — c'est-à-dire jusqu'à une action que l'utilisateur
    n'a pas demandée, et qui est optionnelle dans la délimitation. La règle doit être évaluée au
    moment où l'on répond, pas seulement au moment où l'on indexe.
    """
    from ankiforge.database.models import DocumentChunkModel, DocumentModel
    from ankiforge.repositories.document_repository import DocumentRepository
    from ankiforge.utils.region_address import RegionAddress, RegionScope

    manager = VectorManager()
    manager.faiss_dir = tmp_path / "faiss"

    doc = DocumentModel.create(title="Cours Exclusion Tardive", content="# A\nAlpha le contrat.", file_type="md")
    DocumentChunkModel.create(document=doc, chunk_index=0, heading_path="A", content="Alpha le contrat.", content_hash="h_late")

    assert manager.index_document(doc) is True
    assert manager.search(doc.id, "le contrat", top_k=3) != []

    DocumentRepository().set_region_excluded(doc.id, RegionAddress(RegionScope.HEADING, "A"), True)

    assert manager.search(doc.id, "le contrat", top_k=3) == []
