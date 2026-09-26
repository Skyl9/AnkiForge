"""Non-régression des façades publiques après extraction des ViewModels de parcours.

Ces tests montent les vues réelles et vérifient que le découpage MVVM n'a pas
introduit de désynchronisation entre les ViewModels et les attributs historiques
consommés par MainWindow et par la suite de tests existante.
"""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtCore import QObject, Signal

from ankiforge.ui.viewmodels.batch_viewmodel import BatchViewModel
from ankiforge.ui.views.batch_view import BatchTab

pytestmark = pytest.mark.ui


class _FakeBatchWorker(QObject):
    """Worker batch simulé : aucun pipeline, aucun fournisseur réel."""

    task_progress = Signal(int, int, str)
    batch_finished = Signal(int, int, int)
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.cancel_calls = 0

    def cancel(self) -> None:
        self.cancel_calls += 1


def _task(title: str) -> dict[str, Any]:
    return {"doc_title": title, "doc_content": "contenu", "status": "En attente"}


def test_batch_view_exposes_viewmodel_owning_the_queue(qtbot: Any) -> None:
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)

    assert isinstance(view.batch_view_model, BatchViewModel)
    assert view.queue_tasks_data is view.batch_view_model.tasks


def test_batch_view_public_alias_reassignment_is_owned_by_viewmodel(qtbot: Any) -> None:
    """Les tests existants réassignent l'attribut public : le ViewModel doit adopter la liste."""
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    view.queue_tasks_data = [_task("A"), _task("B")]

    assert view.batch_view_model.tasks is view.queue_tasks_data
    assert all(task.get("_queue_uid") for task in view.batch_view_model.tasks)


def test_batch_view_clear_queue_empties_public_alias(qtbot: Any) -> None:
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    view.queue_tasks_data = [_task("A"), _task("B")]

    view._on_clear_queue()

    assert view.queue_tasks_data == []
    assert view.batch_view_model.tasks == []


def test_batch_view_remove_from_queue_keeps_alias_and_viewmodel_aligned(qtbot: Any) -> None:
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    view.queue_tasks_data = [_task("A"), _task("B")]

    view._remove_from_queue(0)

    assert [task["doc_title"] for task in view.queue_tasks_data] == ["B"]
    assert [task["doc_title"] for task in view.batch_view_model.tasks] == ["B"]


def test_batch_view_in_place_alias_mutation_is_visible_to_viewmodel(qtbot: Any) -> None:
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    view.queue_tasks_data = [_task("A"), _task("B")]

    removed = view.queue_tasks_data.pop(0)

    assert removed["doc_title"] == "A"
    assert [task["doc_title"] for task in view.batch_view_model.tasks] == ["B"]


def test_batch_view_publishes_worker_progress_exactly_once(qtbot: Any) -> None:
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    events: list[tuple[str, int, str]] = []
    view.batch_view_model.execution_progress.connect(lambda *args: events.append(args))  # type: ignore[misc]
    worker = _FakeBatchWorker()
    view.worker = worker  # type: ignore[assignment]
    view.batch_view_model.attach_worker(worker)
    view.queue_tasks_data = [_task("A")]

    worker.task_progress.emit(0, 42, "Découpage")

    assert events == [("0", 42, "Découpage")]


def test_batch_view_shutdown_cancels_owned_worker(qtbot: Any) -> None:
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    worker = _FakeBatchWorker()
    view.worker = worker  # type: ignore[assignment]
    view.batch_view_model.attach_worker(worker)

    view.shutdown()

    assert worker.cancel_calls == 1
    assert view.batch_view_model.is_busy is False


def test_creation_view_publishes_scope_change_exactly_once(qtbot: Any) -> None:
    from ankiforge.ui.views.creation_view import CreationView

    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)
    view._skip_close_dialog = True
    scopes: list[dict[str, Any]] = []
    view.view_model.scope_changed.connect(scopes.append)

    scope = {"selection_mode": "chunks", "selected_chunk_indices": [1]}
    view._apply_scope_result(scope)

    assert scopes == [scope]
    assert view.view_model.scope_result == scope


def test_creation_view_tracks_generation_failure_through_viewmodel(qtbot: Any) -> None:
    from ankiforge.ui.views.creation_view import CreationView

    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)
    view._skip_close_dialog = True
    failures: list[str] = []
    view.view_model.generation_failed.connect(failures.append)

    view.view_model.begin_generation()
    view._on_generation_error("Orchestrateur interrompu")

    assert failures == ["Orchestrateur interrompu"]
    assert view.view_model.is_busy is False


def test_creation_view_shutdown_releases_workflow(qtbot: Any) -> None:
    from ankiforge.ui.views.creation_view import CreationView

    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)
    view._skip_close_dialog = True
    view.view_model.begin_generation()

    view.close()

    assert view.view_model.is_busy is False


def test_documents_view_shutdown_releases_operation_state(qtbot: Any) -> None:
    from ankiforge.ui.views.documents_view import DocumentsView

    view = DocumentsView(ai_manager=None, profile_name="default")
    qtbot.addWidget(view)
    view.view_model.begin_operation("import")

    view.shutdown()

    assert view.view_model.is_busy is False


def test_documents_view_tracks_worker_failure_through_viewmodel(qtbot: Any) -> None:
    from ankiforge.ui.views.documents_view import DocumentsView

    view = DocumentsView(ai_manager=None, profile_name="default")
    qtbot.addWidget(view)
    failures: list[str] = []
    view.view_model.operation_failed.connect(failures.append)

    view.view_model.begin_operation("import")
    view._on_worker_error("PDF illisible")

    assert failures == ["PDF illisible"]
    assert view.view_model.is_busy is False
    assert view.btn_import.isEnabled() is True
