import uuid
from ankiforge.database.models import DocumentModel, DocumentChunkModel
from ankiforge.services.rag.vector_manager import VectorManager
from ankiforge.services.ai.rag_service import RAGService


def test_vector_manager_index_and_search(tmp_path):
    """Vérifie l'indexation FAISS locale et la recherche sémantique."""
    uid = uuid.uuid4().hex[:6]
    content = (
        "# Chapitre 1 : La Cellule\n\n"
        "La cellule est l'unité biologique fondamentale.\n\n"
        "# Chapitre 2 : La Mitochondrie\n\n"
        "La mitochondrie est un organite producteur d'ATP responsable de la respiration cellulaire."
    )
    doc = DocumentModel.create(
        title=f"Cours de Biologie {uid}",
        content=content,
        file_type="md",
    )

    vm = VectorManager(llm_config=None)
    vm.faiss_dir = tmp_path / "faiss_test"
    vm.faiss_dir.mkdir(parents=True, exist_ok=True)

    success = vm.index_document(doc)
    assert success is True

    # Vérifier que les chunks ont été créés
    chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc))
    assert len(chunks) >= 2
    assert any("cellule" in c.content.lower() for c in chunks)

    # Recherche
    results = vm.search(doc.id, "mitochondrie respiration ATP", top_k=2)
    assert len(results) >= 1
    assert any("mitochondrie" in r["content"].lower() for r in results)


def test_rag_service_facade(tmp_path):
    """Vérifie la façade RAGService."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours RAG {uid}",
        content="# Section 1\nContenu sur les algorithmes de tri.\n\n# Section 2\nContenu sur les graphes et le parcours en largeur.",
        file_type="md",
    )

    rag = RAGService(llm_config=None)
    rag.vector_manager.faiss_dir = tmp_path / "faiss_facade"
    rag.vector_manager.faiss_dir.mkdir(parents=True, exist_ok=True)

    res_idx = rag.create_index(doc.id)
    assert res_idx is True

    res_search = rag.search(doc.id, "graphes parcours", top_k=1)
    assert len(res_search) == 1
    assert "graphes" in res_search[0]["content"]
