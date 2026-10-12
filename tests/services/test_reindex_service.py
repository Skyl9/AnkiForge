"""
Tests unitaires pour reindex_service (Re-indexation migratoire des documents stale).
"""

import uuid

import pytest

from ankiforge.database.models import DocumentChunkModel, DocumentModel
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.services.reindex_service import (
    REINDEX_EMPTY,
    REINDEX_ERROR,
    REINDEX_OK,
    get_stale_documents,
    mark_document_version,
    reindex_document,
    revectorize_document,
)

pytestmark = pytest.mark.integration


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


def test_reindex_document_preserves_structural_container_flag(mock_db, monkeypatch) -> None:
    """La ré-indexation doit persister `is_structural_container` au lieu de l'effacer.

    Régression : `reindex_document` recréait les fragments sans ce drapeau, puis
    stamperait la version courante. La migration 043 remplissait le drapeau, la
    ré-indexation migratoire l'effaçait aussitôt, et le document était alors
    déclaré à jour : aucun mécanisme ne pouvait plus le réparer.
    """
    uid = uuid.uuid4().hex[:6]
    content = "# Chapitre\n\nIntro courte.\n\n## Sous-section\n\n" + "Contenu de cours suffisamment développé pour être une unité. " * 3
    doc = DocumentModel.create(title=f"Doc conteneur {uid}", content=content, file_type="md")
    doc.chunk_strategy_version = 0
    doc.save()

    monkeypatch.setattr("ankiforge.services.reindex_service.VectorManager", MockVectorManager)
    monkeypatch.setattr("ankiforge.services.audit.coverage_alignment_service.CoverageAlignmentService", MockAlignmentService)

    assert reindex_document(doc.id) == REINDEX_OK

    chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc))
    flagged = [c for c in chunks if c.is_structural_container]
    assert flagged, "Le titre parent (< 25 mots propres et ouvrant une sous-section) doit rester marqué conteneur."

    # Le conteneur est bien le parent, et non la sous-section qui porte le contenu.
    assert all("Chapitre" in (c.heading_path or "") for c in flagged)
    assert any("Sous-section" in (c.heading_path or "") and not c.is_structural_container for c in chunks)


def test_reindex_document_preserves_audio_timestamps(mock_db, monkeypatch) -> None:
    """La ré-indexation ne doit pas perdre `start_time`/`end_time` des fragments audio.

    Ces colonnes pilotent la position de lecture dans `DocumentsView` ; les perdre
    faisait reculer la ré-indexation d'un document audio déjà indexé.
    """
    uid = uuid.uuid4().hex[:6]
    content = "<!-- TIME:0.0 - 30.0 -->\n\nPremière partie bien développée du cours.\n\n<!-- TIME:30.0 - 60.0 -->\n\nDeuxième partie bien développée du cours."
    doc = DocumentModel.create(title=f"Doc audio {uid}", content=content, file_type="mp3")
    doc.chunk_strategy_version = 0
    doc.save()

    monkeypatch.setattr("ankiforge.services.reindex_service.VectorManager", MockVectorManager)
    monkeypatch.setattr("ankiforge.services.audit.coverage_alignment_service.CoverageAlignmentService", MockAlignmentService)

    assert reindex_document(doc.id) == REINDEX_OK

    chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc))
    assert chunks, "Le document audio doit produire des fragments."
    assert all(c.start_time is not None and c.end_time is not None for c in chunks), "Les horodatages audio doivent survivre à la ré-indexation."


def test_reindex_document_reports_fragment_progress(mock_db, monkeypatch) -> None:
    """La couture expose une micro-progression opportuniste ``(traités, total)`` des fragments."""
    uid = uuid.uuid4().hex[:6]
    content = "# Chapitre\n\nIntro.\n\n## Section A\n\nContenu A.\n\n## Section B\n\nContenu B."
    doc = DocumentModel.create(title=f"Doc fragments {uid}", content=content, file_type="md")
    doc.chunk_strategy_version = 0
    doc.save()

    monkeypatch.setattr("ankiforge.services.reindex_service.VectorManager", MockVectorManager)
    monkeypatch.setattr("ankiforge.services.audit.coverage_alignment_service.CoverageAlignmentService", MockAlignmentService)

    seen: list[tuple[int, int]] = []
    assert reindex_document(doc.id, fragment_cb=lambda cur, tot: seen.append((cur, tot))) == REINDEX_OK

    chunk_count = DocumentChunkModel.select().where(DocumentChunkModel.document == doc).count()
    assert seen, "Au moins une micro-progression doit être émise."
    assert seen[0] == (0, chunk_count)
    assert seen[-1] == (chunk_count, chunk_count)
    assert all(0 <= cur <= tot == chunk_count for cur, tot in seen)


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


def _chunks_snapshot(doc: DocumentModel) -> list[tuple[int, str]]:
    """Instantané (id, contenu) des fragments, dans l'ordre — prouve l'identité des lignes."""
    return [(c.id, c.content) for c in DocumentChunkModel.select().where(DocumentChunkModel.document == doc).order_by(DocumentChunkModel.chunk_index)]


def test_revectorize_document_preserves_existing_chunks(mock_db, monkeypatch) -> None:
    """La rév vectorisation ne re-découpe ni ne supprime les fragments.

    C'est l'invariant qui distingue `revectorize_document` de `reindex_document` : la
    rév vectorisation de la délimitation s'exécute après `sync_extracted_chunks` et doit
    préserver les identifiants de fragments, faute de quoi les liens de couverture en
    cascade (`NoteChunkLinkModel.chunk` est en CASCADE) seraient détruits.
    """
    uid = uuid.uuid4().hex[:6]
    content = "# Chapitre\n\nIntro.\n\n## Section A\n\nContenu A.\n\n## Section B\n\nContenu B."
    doc = DocumentModel.create(title=f"Doc revec {uid}", content=content, file_type="md")

    monkeypatch.setattr("ankiforge.services.reindex_service.VectorManager", MockVectorManager)
    monkeypatch.setattr("ankiforge.services.audit.coverage_alignment_service.CoverageAlignmentService", MockAlignmentService)
    assert reindex_document(doc.id) == REINDEX_OK

    before = _chunks_snapshot(doc)
    assert before, "Le document doit avoir des fragments avant la rév vectorisation."

    seen: list[tuple[int, int]] = []
    status = revectorize_document(doc.id, fragment_cb=lambda cur, tot: seen.append((cur, tot)))

    assert status == REINDEX_OK
    assert _chunks_snapshot(doc) == before, "Les fragments (id compris) doivent être strictement préservés."
    assert seen and seen[0] == (0, len(before)) and seen[-1] == (len(before), len(before))


def test_revectorize_document_missing_doc_returns_error(mock_db, monkeypatch) -> None:
    monkeypatch.setattr("ankiforge.services.reindex_service.VectorManager", MockVectorManager)
    monkeypatch.setattr("ankiforge.services.audit.coverage_alignment_service.CoverageAlignmentService", MockAlignmentService)
    assert revectorize_document(9_999_999) == REINDEX_ERROR
