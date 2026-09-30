"""Worker Qt d'import documentaire par lot (extraction seule — aucune écriture DB).

Chaque fichier de la file est extrait séquentiellement dans un thread dédié : le
thread UI n'est jamais bloqué et un échec unitaire (format non supporté, fichier
verrouillé, permissions) est journalisé puis le lot se poursuit.
"""

import logging
import pathlib
import time
from collections.abc import Iterable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal

from ankiforge.services.parsing.document_parser import DocumentParser
from ankiforge.services.workers.document_worker import derive_document_title

logger = logging.getLogger(__name__)

# Respiration entre deux documents : laisse respirer le thread UI et les verrous fichiers.
INTER_TASK_DELAY_S = 0.02


@dataclass(frozen=True)
class DocumentBatchTask:
    """Un document à extraire dans la file d'attente.

    index: position stable dans le lot (permet au consumer d'afficher « X sur N »).
    path: chemin local du fichier source.
    """

    index: int
    path: str


@dataclass(frozen=True)
class BatchPlan:
    """File d'attente planifiée + ce qui a été écarté de la sélection initiale."""

    tasks: list[DocumentBatchTask]
    skipped: list[str]


def plan_batch_tasks(paths: Iterable[str]) -> BatchPlan:
    """Construit la file d'attente depuis une sélection brute (dialogue ou glisser-déposer).

    Les entrées vides et les doublons sont écartés silencieusement (une sélection
    en double ne doit pas importer deux fois la même fiche) ; l'ordre de sélection
    est conservé pour que l'aperçu « X sur N » reste prévisible. Les chemins introuvables
    sont renvoyés dans ``skipped`` pour que l'interface puisse les signaler.
    """
    tasks: list[DocumentBatchTask] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        candidate = str(raw).strip()
        if not candidate or candidate in seen:
            continue
        if not pathlib.Path(candidate).is_file():
            logger.warning("Import par lot : fichier introuvable, ignoré : %s", candidate)
            skipped.append(candidate)
            continue
        seen.add(candidate)
        tasks.append(DocumentBatchTask(index=len(tasks), path=candidate))
    return BatchPlan(tasks=tasks, skipped=skipped)


class DocumentBatchWorker(QThread):
    """Extraction séquentielle et résiliente d'un lot de documents."""

    document_started = Signal(int, str)  # index, chemin
    document_finished = Signal(int, str, str, str)  # index, chemin, titre, contenu
    document_failed = Signal(int, str, str)  # index, chemin, message d'erreur
    log_signal = Signal(str)
    batch_finished = Signal(int, int)  # succès, échecs
    cancelled = Signal()

    def __init__(self, tasks: list[DocumentBatchTask], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.tasks = list(tasks)
        self._is_cancelled = False

    def cancel(self) -> None:
        """Demande l'annulation entre deux documents du lot."""
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        """Vérifie si la file doit s'arrêter."""
        return self._is_cancelled

    def run(self) -> None:
        """Enchaîne l'extraction de chaque document sans interrompre le lot sur échec."""
        parser = DocumentParser()
        ok = 0
        failed = 0
        try:
            for task in self.tasks:
                if self._is_cancelled:
                    self.cancelled.emit()
                    return

                self.document_started.emit(task.index, task.path)
                try:
                    title = derive_document_title(task.path)
                    content = parser.parse_document(
                        task.path,
                        progress_callback=self.log_signal.emit,
                        check_cancel=self.is_cancelled,
                    )
                except InterruptedError as e:
                    logger.info("Import par lot annulé pendant '%s' : %s", task.path, e)
                    self.cancelled.emit()
                    return
                except Exception as e:
                    logger.exception("Erreur lors de l'analyse du document (%s) : %s", task.path, e)
                    failed += 1
                    self.document_failed.emit(task.index, task.path, str(e))
                    continue

                if self._is_cancelled:
                    self.cancelled.emit()
                    return

                ok += 1
                self.document_finished.emit(task.index, task.path, title, content)
                time.sleep(INTER_TASK_DELAY_S)
        finally:
            self.batch_finished.emit(ok, failed)
