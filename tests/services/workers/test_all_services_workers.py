import json
from unittest.mock import MagicMock, patch

import pytest

from ankiforge.database.models import (
    AuditRecordModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.workers.ab_worker import AbWorker
from ankiforge.services.workers.batch_edit_worker import BatchEditWorker
from ankiforge.services.workers.coverage_worker import CoverageWorker
from ankiforge.services.workers.duplicate_worker import DuplicateWorker
from ankiforge.services.workers.linter_worker import LinterWorker
from ankiforge.services.workers.vector_worker import VectorWorker


@pytest.mark.integration
def test_ab_worker_execution_and_cancellation(qtbot) -> None:
    """Vérifie le cycle de vie du AbWorker : exécution, signaux et annulation."""
    mock_provider_a = MagicMock()
    mock_provider_a.generate.return_value = '{"notes": [{"Recto": "A"}]}'
    mock_provider_b = MagicMock()
    mock_provider_b.generate.return_value = '{"notes": [{"Recto": "B"}]}'

    worker = AbWorker(
        provider_a=mock_provider_a,
        provider_b=mock_provider_b,
        prompts_a=["Prompt A"],
        prompts_b=["Prompt B"],
        source_text="Texte de test",
    )

    # 1. Test d'exécution normale
    with qtbot.waitSignal(worker.finished_signal, timeout=2000):
        worker.start()

    assert mock_provider_a.generate.called
    assert mock_provider_b.generate.called

    # 2. Test d'annulation
    worker_cancel = AbWorker(
        provider_a=mock_provider_a,
        provider_b=mock_provider_b,
        prompts_a=["Prompt A"],
        prompts_b=["Prompt B"],
        source_text="Texte",
    )
    worker_cancel.cancel()
    assert worker_cancel._is_cancelled is True


@pytest.mark.integration
def test_batch_edit_worker_success(mock_db, qtbot) -> None:
    """Vérifie le traitement par lot et la création de versions dans BatchEditWorker."""
    deck = DeckModel.create(name="Deck Batch")
    nt = NoteTypeModel.create(name="Modèle Batch", fields_schema=json.dumps(["Recto", "Verso"]), templates="[]", css_style="")
    note1 = NoteModel.create(deck=deck, note_type=nt)
    NoteVersionModel.create(note=note1, version_number=1, content=json.dumps({"Recto": "Q1", "Verso": "R1"}), is_active=True)
    note2 = NoteModel.create(deck=deck, note_type=nt)
    NoteVersionModel.create(note=note2, version_number=1, content=json.dumps({"Recto": "Q2", "Verso": "R2"}), is_active=True)

    mock_provider = MagicMock()
    mock_provider.generate.return_value = json.dumps(
        [
            {"note_id": note1.id, "Recto": "Q1 traduit", "Verso": "R1 traduit"},
            {"note_id": note2.id, "Recto": "Q2 traduit", "Verso": "R2 traduit"},
        ]
    )

    worker = BatchEditWorker(
        ai_provider=mock_provider,
        note_ids=[note1.id, note2.id],
        user_prompt="Traduis en anglais",
        chunk_size=2,
    )

    with qtbot.waitSignal(worker.finished_signal, timeout=3000) as blocker:
        worker.start()

    assert blocker.args[0] == 2
    # Vérifie que la nouvelle version est bien active en BDD
    v2_note1 = NoteVersionModel.get(note=note1, is_active=True)
    assert v2_note1.version_number == 2
    assert "traduit" in v2_note1.content


@pytest.mark.integration
def test_duplicate_worker_signals(mock_db, qtbot) -> None:
    """Vérifie que DuplicateWorker émet les conflits détectés via son signal."""
    deck = DeckModel.create(name="Deck Doublons")
    nt = NoteTypeModel.create(name="Type", fields_schema=json.dumps(["Recto", "Verso"]), templates="[]", css_style="")
    n1 = NoteModel.create(deck=deck, note_type=nt)
    NoteVersionModel.create(note=n1, version_number=1, content=json.dumps({"Recto": "Capitale France", "Verso": "Paris"}), is_active=True)
    n2 = NoteModel.create(deck=deck, note_type=nt)
    NoteVersionModel.create(note=n2, version_number=1, content=json.dumps({"Recto": "Capitale de France", "Verso": "Paris"}), is_active=True)

    worker = DuplicateWorker(deck_id=deck.id)

    with qtbot.waitSignal(worker.finished_processing, timeout=3000) as blocker:
        worker.start()

    conflicts = blocker.args[0]
    assert isinstance(conflicts, list)


@pytest.mark.integration
def test_linter_worker_flow_and_caching(mock_db, qtbot) -> None:
    """Vérifie l'audit par LinterWorker et la bonne mise en cache des résultats."""
    deck = DeckModel.create(name="Deck Linter")
    nt = NoteTypeModel.create(name="Type Linter", fields_schema=json.dumps(["Recto", "Verso"]), templates="[]", css_style="")
    note = NoteModel.create(deck=deck, note_type=nt)
    NoteVersionModel.create(note=note, version_number=1, content=json.dumps({"Recto": "Question", "Verso": "Réponse"}), is_active=True)

    mock_llm = MagicMock()
    mock_llm.generate.return_value = json.dumps(
        [
            {
                "note_id": note.id,
                "pass": False,
                "rule_broken": "Principe d'Atomicité",
                "category": "cat-atomicite",
                "reason": "Trop verbeux",
                "suggestion": {"Recto": "Q simple", "Verso": "R simple"},
            }
        ]
    )

    from ankiforge.database.models import LLMConfigModel

    cfg = LLMConfigModel.create(display_name="Linter Mock LLM", model_id="mock-model", provider="mock", is_default=True)

    with patch("ankiforge.services.ai.flexible_service.AIManager.create_provider_from_config", return_value=mock_llm):
        worker = LinterWorker(note_ids=[note.id], llm_config_id=cfg.id, force_recheck=True)

        with qtbot.waitSignal(worker.finished_processing, timeout=3000) as blocker:
            worker.start()

        results = blocker.args[0]
        assert len(results) == 1
        assert results[0]["pass"] is False
        assert results[0]["category"] == "cat-atomicite"

        # Vérifie la persistance de l'audit
        audit = AuditRecordModel.get(note=note)
        assert audit.is_compliant is False


@pytest.mark.integration
def test_coverage_worker_execution(mock_db, qtbot) -> None:
    """Vérifie le calcul de couverture documentaire par CoverageWorker."""
    doc = DocumentModel.create(title="Doc Coverage", content="Contenu du document de cours", file_type="md")
    DocumentChunkModel.create(document=doc, chunk_index=1, content="Partie 1", token_count=10)
    DocumentChunkModel.create(document=doc, chunk_index=2, content="Partie 2", token_count=10)

    worker = CoverageWorker(document_id=doc.id)

    with qtbot.waitSignal(worker.finished_processing, timeout=3000):
        worker.start()

    # Vérifie que les chunks ont bien été créés/indexés
    chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc))
    assert len(chunks) >= 1


@pytest.mark.integration
def test_vector_worker_signals(mock_db, qtbot, tmp_path) -> None:
    """Vérifie l'indexation asynchrone par VectorWorker."""
    doc = DocumentModel.create(title="Doc Vector", content="# Chapitre 1\nContenu vectoriel", file_type="md")

    worker = VectorWorker(document_id=doc.id)
    worker.manager.faiss_dir = tmp_path / "faiss_test"
    worker.manager.faiss_dir.mkdir(parents=True, exist_ok=True)

    with qtbot.waitSignal(worker.finished_indexing, timeout=3000) as blocker:
        worker.start()

    collection_name = blocker.args[0]
    assert collection_name == f"doc_{doc.id}"
