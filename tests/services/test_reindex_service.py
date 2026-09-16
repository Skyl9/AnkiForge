"""
Tests unitaires pour reindex_service (Re-indexation migratoire des documents stale).
"""

import uuid

from ankiforge.database.models import DocumentChunkModel, DocumentModel
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.services.reindex_service import (
    REINDEX_EMPTY,
    REINDEX_ERROR,
    REINDEX_OK,
    get_stale_documents,
    mark_document_version,
    reindex_document,
)


def test_mark_document_version(mock_db) -> None:
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Doc version {uid}", content="Texte", file_type="md")
    doc.chunk_strategy_version = 0
    doc.save()

    mark_document_version(doc)

    refreshed = DocumentModel.get_by_id(doc.id)
    assert refreshed.chunk_strategy_version == ChunkingService.CHUNKING_VERSION


def test_get_stale_documents_detects_legacy_migration_default(mock_db) -> None:
    uid = uuid.uuid4().hex[:6]
    stale = DocumentModel.create(title=f"Doc stale {uid}", content="Ancien contenu", file_type="md")
    stale.chunk_strategy_version = 0  # valeur défaut SQL de la migration 033
    stale.save()

    current = DocumentModel.create(title=f"Doc à jour {uid}", content="Nouveau contenu", file_type="md")

    stale_ids = [d.id for d in get_stale_documents()]
    assert stale.id in stale_ids
    assert current.id not in stale_ids


def test_reindex_document_stamps_version_and_rebuilds_chunks(mock_db, monkeypatch) -> None:
    """Ré-indexe un document, recrée des chunks conforme à la stratégie fine (H4) et stampe la version."""
    uid = uuid.uuid4().hex[:6]
    content = "# Chapitre principal\n\nIntro du chapitre.\n\n### Sous-partie A\n\n#### Détail fin A\n\nContenu du détail A.\n\n#### Détail fin B\n\nContenu du détail B."
    doc = DocumentModel.create(title=f"Doc reindex {uid}", content=content, file_type="md")
    doc.chunk_strategy_version = 0
    doc.save()

    monkeypatch.setattr("ankiforge.services.reindex_service.VectorManager", MockVectorManager)
    monkeypatch.setattr("ankiforge.services.audit.coverage_alignment_service.CoverageAlignmentService", MockAlignmentService)

    events: list[str] = []
    status = reindex_document(doc.id, progress_cb=events.append)

    assert status == REINDEX_OK
    assert events, "Des messages de progression doivent être émis."

    refreshed = DocumentModel.get_by_id(doc.id)
    assert refreshed.chunk_strategy_version == ChunkingService.CHUNKING_VERSION

    chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc))
    assert len(chunks) >= 4
    headings = [c.heading_path or "" for c in chunks]
    assert any("Sous-partie A" in h for h in headings)
    assert any("Détail fin A" in h for h in headings)
    assert any("Détail fin B" in h for h in headings)


def test_reindex_document_empty_returns_empty_status(mock_db, monkeypatch) -> None:
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Doc vide {uid}", content="", file_type="md")
    doc.chunk_strategy_version = 0
    doc.save()

    monkeypatch.setattr("ankiforge.services.reindex_service.VectorManager", MockVectorManager)
    monkeypatch.setattr("ankiforge.services.audit.coverage_alignment_service.CoverageAlignmentService", MockAlignmentService)

    status = reindex_document(doc.id)
    assert status == REINDEX_EMPTY


def test_reindex_document_missing_doc_returns_error(mock_db, monkeypatch) -> None:
    monkeypatch.setattr("ankiforge.services.reindex_service.VectorManager", MockVectorManager)
    monkeypatch.setattr("ankiforge.services.audit.coverage_alignment_service.CoverageAlignmentService", MockAlignmentService)

    status = reindex_document(9_999_999)
    assert status == REINDEX_ERROR


def test_reindex_document_preserves_note_links_through_tags(mock_db, monkeypatch) -> None:
    """Après re-indexation, la synchro par tags est appelée (mock) avec des chunks persistés."""
    uid = uuid.uuid4().hex[:6]
    content = "# Intro\n\nPremier paragraphe.\n\n## Section B\n\nDeuxième paragraphe."
    doc = DocumentModel.create(title=f"Doc sync {uid}", content=content, file_type="md")
    doc.chunk_strategy_version = 0
    doc.save()

    class _MockAlignment:
        @classmethod
        def align_document(cls, doc_id: int):
            ctx.doc_id_seen = doc_id
            return {"matched_notes": 5, "coverage_pct": 100.0}

    class _Ctx:
        pass

    ctx = _Ctx()
    monkeypatch.setattr("ankiforge.services.reindex_service.VectorManager", MockVectorManager)
    monkeypatch.setattr("ankiforge.services.audit.coverage_alignment_service.CoverageAlignmentService", _MockAlignment)

    status = reindex_document(doc.id)
    assert status == REINDEX_OK
    assert ctx.doc_id_seen == doc.id
    assert DocumentChunkModel.select().where(DocumentChunkModel.document == doc).count() > 0


class MockVectorManager:
    """Mock minimal de VectorManager pour les tests Qt-free."""

    def __init__(self, llm_config=None) -> None:
        self.llm_config = llm_config

    def index_document(self, document) -> None:
        return None


class MockAlignmentService:
    @classmethod
    def align_document(cls, doc_id: int) -> dict:
        return {"matched_notes": 0, "coverage_pct": 0.0}
