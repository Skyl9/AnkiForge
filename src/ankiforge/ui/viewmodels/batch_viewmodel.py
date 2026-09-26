"""Frontière d'état du parcours Batch.

La vue conserve la présentation et les callbacks legacy, tandis que cet objet
possède l'identité de la file d'attente et le cycle de vie du worker qui doit
survivre aux rendus successifs du tableau.
"""

from __future__ import annotations

import uuid
from typing import Any

from PySide6.QtCore import QObject, Signal

from ankiforge.ui.viewmodels.base import BaseViewModel


class BatchViewModel(BaseViewModel):
    """Possède la file d'attente batch et ses transitions d'exécution observables."""

    queue_changed = Signal(list)
    task_changed = Signal(str, dict)
    task_removed = Signal(str)
    execution_started = Signal()
    execution_finished = Signal(int, int, int)
    execution_cancelled = Signal()
    execution_progress = Signal(str, int, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent=parent)
        self._tasks: list[dict[str, Any]] = []
        self._worker: Any | None = None

    @property
    def tasks(self) -> list[dict[str, Any]]:
        """Retourne la file vivante consommée par la façade de compatibilité du tableau."""
        return self._tasks

    def add_tasks(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Ajoute des tâches en leur attribuant une identité indépendante de leur rangée."""
        for task in tasks:
            task.setdefault("_queue_uid", str(uuid.uuid4()))
        self._tasks.extend(tasks)
        if tasks:
            self.queue_changed.emit(list(self._tasks))
        return list(tasks)

    def set_tasks(self, tasks: list[dict[str, Any]]) -> None:
        """Adopte une liste de façade quand un appelant remplace l'alias public."""
        self._tasks = tasks
        for task in self._tasks:
            task.setdefault("_queue_uid", str(uuid.uuid4()))
        self.queue_changed.emit(list(self._tasks))

    def remove_task(self, index: int) -> dict[str, Any] | None:
        """Retire une entrée de la file et publie son identité stable."""
        if not 0 <= index < len(self._tasks):
            return None
        task = self._tasks.pop(index)
        self.task_removed.emit(str(task.get("_queue_uid", "")))
        self.queue_changed.emit(list(self._tasks))
        return task

    def clear(self) -> None:
        """Vide la file en attente sans modifier les snapshots de tâches déjà créés."""
        self._tasks.clear()
        self.queue_changed.emit([])

    def move_task(self, source_index: int, target_index: int) -> None:
        """Réordonne les rangées de la file sans changer leurs identités."""
        if not 0 <= source_index < len(self._tasks):
            return
        task = self._tasks.pop(source_index)
        target_index = max(0, min(target_index, len(self._tasks)))
        self._tasks.insert(target_index, task)
        self.queue_changed.emit(list(self._tasks))

    def update_task(self, index: int, **changes: Any) -> dict[str, Any] | None:
        """Met à jour la projection d'une tâche en préservant son identité de file."""
        if not 0 <= index < len(self._tasks):
            return None
        task = self._tasks[index]
        task.update(changes)
        task.setdefault("_queue_uid", str(uuid.uuid4()))
        self.task_changed.emit(str(task["_queue_uid"]), dict(task))
        self.queue_changed.emit(list(self._tasks))
        return task

    def attach_worker(self, worker: Any) -> None:
        """Rattache un adaptateur worker et relaie ses signaux publics."""
        self._worker = worker
        if hasattr(worker, "task_progress"):
            worker.task_progress.connect(self._on_worker_progress)
        if hasattr(worker, "batch_finished"):
            worker.batch_finished.connect(self.finish_execution)
        if hasattr(worker, "cancelled"):
            worker.cancelled.connect(self.cancel_execution)

    def begin_execution(self) -> None:
        self.set_busy(True)
        self.execution_started.emit()

    def finish_execution(self, success_count: int, error_count: int, total_cards: int) -> None:
        self.set_busy(False)
        self.execution_finished.emit(success_count, error_count, total_cards)

    def cancel_execution(self) -> None:
        self.set_busy(False)
        self.execution_cancelled.emit()

    def cancel_worker(self) -> None:
        """Demande l'annulation sans supposer un type de worker particulier."""
        if self._worker is not None and hasattr(self._worker, "cancel"):
            self._worker.cancel()

    def dispose(self) -> None:
        """Annule le worker possédé, libère busy et détache les abonnements du bus."""
        self.cancel_worker()
        self._worker = None
        self.set_busy(False)
        super().dispose()

    def _on_worker_progress(self, task_index: int, progress: int, detail: str) -> None:
        self.execution_progress.emit(str(task_index), int(progress), detail)
