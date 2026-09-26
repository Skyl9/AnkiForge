from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtCore import QObject, Signal

from ankiforge.ui.viewmodels.batch_viewmodel import BatchViewModel
from ankiforge.ui.viewmodels.creation_viewmodel import CreationViewModel
from ankiforge.ui.viewmodels.documents_viewmodel import DocumentsViewModel

pytestmark = pytest.mark.ui


class _FakeBatchWorker(QObject):
    """Adaptateur worker simulé : aucun fournisseur, aucune thread."""

    task_progress = Signal(int, int, str)
    batch_finished = Signal(int, int, int)
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.cancel_calls = 0

    def cancel(self) -> None:
        self.cancel_calls += 1


class _FakeOrchestrator:
    """Faux orchestrateur : seule la surface d'annulation est utilisée."""

    def __init__(self) -> None:
        self.cancel_calls = 0

    def cancel(self) -> None:
        self.cancel_calls += 1


def test_creation_viewmodel_restores_scope_and_tracks_generation() -> None:
    view_model = CreationViewModel()
    scope = {
        "selection_mode": "sections",
        "selected_headings": ["Chapitre 2"],
        "selected_chunk_indices": [4, 5],
    }
    states: list[bool] = []
    view_model.busy_changed.connect(states.append)

    view_model.restore_scope(scope)
    assert view_model.scope_result == scope

    view_model.begin_generation()
    view_model.update_generation_progress(40, "Découpage")
    view_model.finish_generation([{"Front": "Question", "Back": "Réponse"}])

    assert states == [True, False]
    assert view_model.generated_cards[0]["Front"] == "Question"
    assert view_model.is_busy is False


def test_creation_viewmodel_clamps_progress_to_percentage_bounds() -> None:
    view_model = CreationViewModel()
    progresses: list[int] = []
    view_model.generation_progress.connect(lambda pct, _detail: progresses.append(pct))

    view_model.update_generation_progress(-15, "démarrage")
    view_model.update_generation_progress(320, "fin")

    assert progresses == [0, 100]


def test_creation_viewmodel_stays_reusable_after_failure() -> None:
    view_model = CreationViewModel()
    failures: list[str] = []
    view_model.generation_failed.connect(failures.append)

    view_model.begin_generation()
    assert view_model.is_busy is True

    view_model.fail_generation("Pipeline interrompu")

    assert failures == ["Pipeline interrompu"]
    assert view_model.is_busy is False
    assert view_model.error_message == "Pipeline interrompu"

    view_model.begin_generation()
    assert view_model.is_busy is True
    assert view_model.error_message is None


def test_creation_viewmodel_cancel_resets_busy_and_cancels_owned_worker() -> None:
    view_model = CreationViewModel()
    orchestrator = _FakeOrchestrator()
    cancellations: list[bool] = []
    view_model.generation_cancelled.connect(lambda: cancellations.append(True))

    view_model.begin_generation()
    view_model.attach_worker(orchestrator)
    view_model.cancel_worker()
    view_model.cancel_generation()

    assert orchestrator.cancel_calls == 1
    assert cancellations == [True]
    assert view_model.is_busy is False


def test_creation_viewmodel_dispose_cancels_worker_and_detaches_it() -> None:
    view_model = CreationViewModel()
    orchestrator = _FakeOrchestrator()
    view_model.attach_worker(orchestrator)

    view_model.dispose()
    assert orchestrator.cancel_calls == 1

    view_model.cancel_worker()
    assert orchestrator.cancel_calls == 1


def test_batch_viewmodel_keeps_queue_identity_when_reordering() -> None:
    view_model = BatchViewModel()
    first, second = view_model.add_tasks([{"title": "A"}, {"title": "B"}])
    first_uid = first["_queue_uid"]
    second_uid = second["_queue_uid"]

    view_model.move_task(0, 1)

    assert [task["title"] for task in view_model.tasks] == ["B", "A"]
    assert view_model.tasks[0]["_queue_uid"] == second_uid
    assert view_model.tasks[1]["_queue_uid"] == first_uid


def test_batch_viewmodel_publishes_removal_with_stable_identity() -> None:
    view_model = BatchViewModel()
    added = view_model.add_tasks([{"title": "A"}, {"title": "B"}])
    removed_uids: list[str] = []
    snapshots: list[list[dict[str, Any]]] = []
    view_model.task_removed.connect(removed_uids.append)
    view_model.queue_changed.connect(snapshots.append)

    removed = view_model.remove_task(0)

    assert removed is added[0]
    assert removed_uids == [str(added[0]["_queue_uid"])]
    assert [task["title"] for task in view_model.tasks] == ["B"]
    assert len(snapshots) == 1


def test_batch_viewmodel_ignores_out_of_bound_mutations() -> None:
    view_model = BatchViewModel()
    view_model.add_tasks([{"title": "A"}])

    assert view_model.remove_task(5) is None
    assert view_model.update_task(-1, progress_pct=10) is None
    view_model.move_task(9, 0)

    assert [task["title"] for task in view_model.tasks] == ["A"]


def test_batch_viewmodel_set_tasks_backfills_missing_identities() -> None:
    view_model = BatchViewModel()

    view_model.set_tasks([{"title": "Legacy"}])

    task = view_model.tasks[0]
    assert task["_queue_uid"]
    view_model.set_tasks([task])
    assert view_model.tasks[0]["_queue_uid"] == task["_queue_uid"]


def test_batch_viewmodel_execution_lifecycle_is_observable() -> None:
    view_model = BatchViewModel()
    events: list[tuple[str, object]] = []
    busy: list[bool] = []
    view_model.execution_started.connect(lambda: events.append(("started", None)))
    view_model.execution_finished.connect(lambda ok, ko, cards: events.append(("finished", (ok, ko, cards))))
    view_model.execution_cancelled.connect(lambda: events.append(("cancelled", None)))
    view_model.busy_changed.connect(busy.append)

    view_model.begin_execution()
    assert view_model.is_busy is True

    view_model.finish_execution(2, 1, 17)
    assert view_model.is_busy is False

    view_model.begin_execution()
    view_model.cancel_execution()
    assert view_model.is_busy is False

    assert events == [("started", None), ("finished", (2, 1, 17)), ("started", None), ("cancelled", None)]
    assert busy == [True, False, True, False]


def test_batch_viewmodel_relays_worker_signals_without_duplicating_them() -> None:
    view_model = BatchViewModel()
    worker = _FakeBatchWorker()
    progresses: list[tuple[str, int, str]] = []
    finished: list[tuple[int, int, int]] = []
    cancelled: list[bool] = []
    view_model.execution_progress.connect(lambda *args: progresses.append(args))  # type: ignore[misc]
    view_model.execution_finished.connect(lambda *args: finished.append(args))  # type: ignore[misc]
    view_model.execution_cancelled.connect(lambda: cancelled.append(True))
    view_model.attach_worker(worker)

    worker.task_progress.emit(0, 42, "Découpage")
    worker.batch_finished.emit(1, 0, 5)
    worker.cancelled.emit()

    assert progresses == [("0", 42, "Découpage")]
    assert finished == [(1, 0, 5)]
    assert cancelled == [True]
    assert view_model.is_busy is False


def test_batch_viewmodel_dispose_cancels_owned_worker() -> None:
    view_model = BatchViewModel()
    worker = _FakeBatchWorker()
    view_model.attach_worker(worker)

    view_model.dispose()

    assert worker.cancel_calls == 1


def test_documents_viewmodel_reports_import_lifecycle() -> None:
    view_model = DocumentsViewModel()
    events: list[tuple[str, object]] = []
    view_model.operation_started.connect(lambda name: events.append(("started", name)))
    view_model.progress_changed.connect(lambda message: events.append(("progress", message)))
    view_model.operation_succeeded.connect(lambda message: events.append(("success", message)))

    view_model.begin_operation("import")
    view_model.report_progress("Extraction terminée")
    view_model.complete_operation("Document importé")

    assert events == [
        ("started", "import"),
        ("progress", "Extraction terminée"),
        ("success", "Document importé"),
    ]
    assert view_model.is_busy is False


def test_documents_viewmodel_stays_reusable_after_operation_failure() -> None:
    view_model = DocumentsViewModel()
    failures: list[str] = []
    view_model.operation_failed.connect(failures.append)

    view_model.begin_operation("coverage")
    assert view_model.is_busy is True

    view_model.fail_operation("Indexation impossible")

    assert failures == ["Indexation impossible"]
    assert view_model.is_busy is False
    assert view_model.error_message == "Indexation impossible"

    view_model.begin_operation("coverage")
    assert view_model.is_busy is True
    assert view_model.error_message is None


def test_documents_viewmodel_cancellation_resets_busy() -> None:
    view_model = DocumentsViewModel()
    cancellations: list[bool] = []
    view_model.operation_cancelled.connect(lambda: cancellations.append(True))

    view_model.begin_operation("import")
    view_model.cancel_operation()

    assert cancellations == [True]
    assert view_model.is_busy is False


def test_documents_viewmodel_clear_selection_emits_empty_document() -> None:
    view_model = DocumentsViewModel()
    emitted: list[object] = []
    view_model.document_selected.connect(emitted.append)

    view_model.clear_selection()

    assert view_model.selected_document is None
    assert emitted == [None]


@pytest.mark.parametrize(
    ("target_index", "expected_titles"),
    [
        (0, ["A", "B", "C"]),
        (2, ["B", "C", "A"]),
        (3, ["B", "C", "A"]),
        (-1, ["A", "B", "C"]),
    ],
)
def test_batch_viewmodel_move_task_clamps_target_index(target_index: int, expected_titles: list[str]) -> None:
    view_model = BatchViewModel()
    added = view_model.add_tasks([{"title": "A"}, {"title": "B"}, {"title": "C"}])
    uids_before = [str(task["_queue_uid"]) for task in added]

    view_model.move_task(0, target_index)

    assert [task["title"] for task in view_model.tasks] == expected_titles
    assert sorted(str(task["_queue_uid"]) for task in view_model.tasks) == sorted(uids_before)
