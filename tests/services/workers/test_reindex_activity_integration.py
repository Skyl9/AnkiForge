"""Tests d'intégration des workers de réindexation sur le hub d'activité (ADR 0021).

Les workers sont exécutés via ``run()`` (thread courant) et ``reindex_document`` est
remplacé par un faux déterministe : ces tests vérifient la mécanique de reporting et
d'annulation, pas la ré-indexation elle-même.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from ankiforge.database.models import DocumentModel
from ankiforge.services.reindex_activity_service import ReindexActivityService
from ankiforge.services.reindex_service import REINDEX_ERROR, REINDEX_OK
from ankiforge.services.workers import coverage_worker as cw
from ankiforge.services.workers import migration_reindex_worker as mrw
from ankiforge.services.workers.coverage_worker import CoverageWorker
from ankiforge.services.workers.migration_reindex_worker import MigrationReindexWorker

pytestmark = pytest.mark.integration


def _fake_reindex(fragment_count: int, status: str = REINDEX_OK) -> Callable[..., str]:
    """Faux ``reindex_document`` rapportant ``fragment_count`` fragments."""

    def _fn(
        document_id: int,
        llm_config_id: int | None = None,
        progress_cb: Callable[[str], None] | None = None,
        fragment_cb: Callable[[int, int], None] | None = None,
    ) -> str:
        if status == REINDEX_OK and fragment_cb is not None:
            for i in range(1, fragment_count + 1):
                fragment_cb(i, fragment_count)
        return status

    return _fn


def _make_docs(count: int) -> list[DocumentModel]:
    return [DocumentModel.create(title=f"Doc {i}", content="Contenu de cours.", file_type="md") for i in range(count)]


def test_migration_worker_reports_each_document_and_recaps(mock_db, monkeypatch) -> None:
    docs = _make_docs(3)
    monkeypatch.setattr(mrw, "reindex_document", _fake_reindex(2))

    activity = ReindexActivityService()
    assert activity.begin(len(docs))
    seen_progress: list[tuple[int, int, str]] = []
    recap: list[tuple[int, int, int, bool]] = []
    activity.progress.connect(lambda n, t, title: seen_progress.append((n, t, title)))
    activity.finished.connect(lambda d, f, e, c: recap.append((d, f, e, c)))

    worker = MigrationReindexWorker(docs, activity=activity)
    worker_progress: list[tuple[int, int, str]] = []
    worker_done: list[tuple[int, int, int]] = []
    worker.progress.connect(lambda n, t, title: worker_progress.append((n, t, title)))
    worker.finished_processing.connect(lambda d, f, e: worker_done.append((d, f, e)))

    worker.run()

    expected = [(i + 1, 3, docs[i].title) for i in range(3)]
    assert worker_progress == expected
    assert seen_progress == expected
    assert worker_done == [(3, 6, 0)]
    assert recap == [(3, 6, 0, False)]
    assert activity.is_active() is False


def test_migration_worker_cancels_between_documents(mock_db, monkeypatch) -> None:
    docs = _make_docs(3)
    calls: list[int] = []

    def _spy(document_id: int, **kwargs: object) -> str:
        calls.append(document_id)
        return REINDEX_OK

    monkeypatch.setattr(mrw, "reindex_document", _spy)

    activity = ReindexActivityService()
    activity.begin(len(docs))
    recap: list[tuple[int, int, int, bool]] = []
    activity.finished.connect(lambda d, f, e, c: recap.append((d, f, e, c)))
    activity.request_cancel()

    worker = MigrationReindexWorker(docs, activity=activity)
    worker.run()

    assert calls == [], "Aucun document ne doit être traité après une annulation armée."
    assert recap == [(0, 0, 0, True)]


def test_migration_worker_counts_errors(mock_db, monkeypatch) -> None:
    docs = _make_docs(2)
    monkeypatch.setattr(mrw, "reindex_document", _fake_reindex(0, status=REINDEX_ERROR))

    activity = ReindexActivityService()
    activity.begin(len(docs))
    worker = MigrationReindexWorker(docs, activity=activity)
    worker_done: list[tuple[int, int, int]] = []
    worker.finished_processing.connect(lambda d, f, e: worker_done.append((d, f, e)))

    worker.run()

    assert worker_done == [(0, 0, 2)]


def test_coverage_worker_reports_single_document(mock_db, monkeypatch) -> None:
    doc = DocumentModel.create(title="Document unique", content="Contenu.", file_type="md")
    monkeypatch.setattr(cw, "reindex_document", _fake_reindex(4))

    activity = ReindexActivityService()
    assert activity.begin(1)
    recap: list[tuple[int, int, int, bool]] = []
    fragments: list[tuple[int, int]] = []
    activity.finished.connect(lambda d, f, e, c: recap.append((d, f, e, c)))
    activity.fragment_progress.connect(lambda cur, tot: fragments.append((cur, tot)))

    worker = CoverageWorker(doc.id, activity=activity)
    done: list[bool] = []
    worker.finished_processing.connect(lambda: done.append(True))

    worker.run()

    assert done == [True]
    assert recap == [(1, 4, 0, False)]
    assert fragments[-1] == (4, 4)


def test_coverage_worker_error_always_closes_the_pass(mock_db, monkeypatch) -> None:
    doc = DocumentModel.create(title="Document en erreur", content="Contenu.", file_type="md")
    monkeypatch.setattr(cw, "reindex_document", _fake_reindex(0, status=REINDEX_ERROR))

    activity = ReindexActivityService()
    activity.begin(1)
    recap: list[tuple[int, int, int, bool]] = []
    activity.finished.connect(lambda d, f, e, c: recap.append((d, f, e, c)))

    worker = CoverageWorker(doc.id, activity=activity)
    errors: list[str] = []
    worker.error_occurred.connect(errors.append)

    worker.run()

    assert errors, "Une erreur d'indexation doit être signalée."
    assert recap == [(0, 0, 1, False)]
    assert activity.is_active() is False
