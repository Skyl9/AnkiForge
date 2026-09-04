"""Tests unitaires pour VisualRAGService et l'indexation sémantique dense multimodale."""

import pytest

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    DocumentPageModel,
    db,
)
from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.ai.vision_category_service import VisionCategoryService
from ankiforge.services.cards.media_manager import MediaManager
from ankiforge.services.rag.vector_manager import VectorManager
from ankiforge.services.rag.visual_rag_service import VisualRAGService


class FakeVisionProvider(LLMProvider):
    """Fournisseur LLM simulé pour les tests de description visuelle dense."""

    def __init__(self, description: str = "Schéma de la cellule eucaryote avec mitochondries et noyau."):
        self.description = description
        self.called_with: list[dict] = []

    def generate(self, system_prompt: str, user_prompt: str | list[dict], response_format: str = "text") -> str:
        self.called_with.append({"system": system_prompt, "user": user_prompt})
        return self.description


@pytest.fixture
def test_album_doc(mock_db, tmp_path):
    """Crée un album de test avec 2 pages associées à des médias réels."""
    media_mgr = MediaManager()
    media_mgr.media_dir = tmp_path / "media"
    media_mgr.media_dir.mkdir(parents=True, exist_ok=True)
    img1 = tmp_path / "slide_1.png"
    img2 = tmp_path / "slide_2.png"
    img1.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
    img2.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

    with db.atomic():
        doc = DocumentModel.create(title="Atlas d'Histologie", file_type="album", total_pages=2)
        m1 = media_mgr.store_document_source(str(img1))
        m2 = media_mgr.store_document_source(str(img2))
        assert m1 is not None and m2 is not None

        p1 = DocumentPageModel.create(document=doc, media=m1, page_number=1, ocr_text="")
        p2 = DocumentPageModel.create(document=doc, media=m2, page_number=2, ocr_text="")

    return {"doc": doc, "pages": [p1, p2], "media_mgr": media_mgr}


@pytest.mark.unit
def test_vision_category_visual_rag_registered():
    """Vérifie que la catégorie visual_rag est bien déclarée et disponible par défaut."""
    vr_cat = VisionCategoryService.get_category_by_id("visual_rag")
    assert vr_cat is not None
    assert vr_cat.name == "RAG Visuel & Indexation Dense"
    assert "visuel" in vr_cat.custom_instructions.lower()


@pytest.mark.unit
def test_generate_dense_description_with_provider_mock(tmp_path):
    """Vérifie que generate_dense_description interroge le provider multimodal et extrait le texte dense."""
    fake_img = tmp_path / "schema.png"
    fake_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 30)

    expected_text = "### Titre : Cycle de Krebs\n- Entités : Acétyl-CoA, Citrate, Oxaloacétate"
    provider = FakeVisionProvider(description=expected_text)

    service = VisualRAGService()
    res = service.generate_dense_description(fake_img, provider_override=provider)

    assert res == expected_text
    assert len(provider.called_with) == 1


@pytest.mark.unit
def test_generate_dense_description_missing_file():
    """Vérifie la robustesse si le fichier image est introuvable."""
    service = VisualRAGService()
    res = service.generate_dense_description("/path/to/missing_image_xyz.png")
    assert res == ""


@pytest.mark.integration
def test_prepare_visual_chunks_album(test_album_doc):
    """Vérifie la préparation des DocumentChunkModel et le renseignement de doc.content."""
    doc = test_album_doc["doc"]
    media_mgr = test_album_doc["media_mgr"]
    provider = FakeVisionProvider(description="Description dense de la planche histologique.")

    service = VisualRAGService(media_manager=media_mgr)
    progress_calls = []

    chunks = service.prepare_visual_chunks(
        document=doc,
        provider_override=provider,
        progress_callback=lambda cur, tot, msg: progress_calls.append((cur, tot)),
    )

    assert len(chunks) == 2
    assert len(progress_calls) == 2
    assert chunks[0].page_number == 1
    assert chunks[1].page_number == 2
    assert chunks[0].media_id is not None
    assert chunks[0].heading_path == "Page 1"
    assert "Description dense de la planche histologique" in chunks[0].content

    # Vérifie la persistance du contenu agrégé dans DocumentModel
    refreshed_doc = DocumentModel.get_by_id(doc.id)
    assert "<!-- PAGE: 1 -->" in (refreshed_doc.content or "")
    assert "<!-- PAGE: 2 -->" in (refreshed_doc.content or "")


@pytest.mark.integration
def test_index_visual_document_full_flow(test_album_doc, tmp_path):
    """Vérifie le cycle complet d'indexation d'un album dans FAISS et BM25."""
    doc = test_album_doc["doc"]
    media_mgr = test_album_doc["media_mgr"]
    provider = FakeVisionProvider(description="Coupe transversale du foie montrant la triade portale.")

    faiss_dir = tmp_path / "faiss_index"
    vm = VectorManager()
    vm.faiss_dir = faiss_dir

    service = VisualRAGService(media_manager=media_mgr)
    success = service.index_visual_document(
        document=doc,
        vector_manager=vm,
        provider_override=provider,
    )

    assert success is True
    assert vm.is_indexed(doc.id) is True

    # Vérification des statistiques de l'index
    stats = vm.get_index_stats(doc.id)
    assert stats["chunk_count"] == 2
    assert stats["has_faiss"] is True
    assert stats["has_bm25"] is True


@pytest.mark.integration
def test_search_visual_document_returns_media(test_album_doc, tmp_path):
    """Vérifie que la recherche RAG renvoie bien les références média (media_id, media_filename)."""
    doc = test_album_doc["doc"]
    media_mgr = test_album_doc["media_mgr"]
    provider = FakeVisionProvider(description="Anatomie vasculaire et système porte hépatique.")

    faiss_dir = tmp_path / "faiss_index"
    vm = VectorManager()
    vm.faiss_dir = faiss_dir

    service = VisualRAGService(media_manager=media_mgr)
    service.index_visual_document(doc, vector_manager=vm, provider_override=provider)

    results = vm.search(document_id=doc.id, query="système porte", top_k=2, mode="hybrid")
    assert len(results) > 0
    first_res = results[0]

    assert first_res["media_id"] is not None
    assert first_res["media_filename"] is not None
    assert "Page" in first_res["heading_path"]


@pytest.mark.integration
def test_vector_manager_delegation_for_album(test_album_doc, tmp_path):
    """Vérifie que VectorManager.index_document délègue automatiquement la préparation à VisualRAG."""
    doc = test_album_doc["doc"]

    # S'assurer qu'aucun chunk n'existe encore
    DocumentChunkModel.delete().where(DocumentChunkModel.document == doc).execute()

    vm = VectorManager()
    vm.faiss_dir = tmp_path / "faiss_index"

    success = vm.index_document(doc)
    assert success is True

    # Des chunks ont été créés avec leurs pages
    chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc))
    assert len(chunks) == 2
    assert chunks[0].media_id is not None
