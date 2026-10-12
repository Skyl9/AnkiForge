"""Hub singleton Qt d'une passe de réindexation RAG (ADR 0021).

Voie d'alimentation **unique** : les trois déclencheurs de réindexation (migration
au démarrage, bouton « Ré-indexer FAISS », rév vectorisation de la délimitation)
publient ici leur avancement, et le *bandeau d'activité global* hébergé par
:class:`~ankiforge.ui.main_window.MainWindow` s'y abonne.

Le service est un ``QObject`` **de thread principal** : la progression macro est
publiée par les workers via des signaux (les connexions inter-threads sont
automatiquement mises en file par Qt), tandis que l'état interne de la passe est
protégé par un verrou, car ``report_document`` et ``finish`` sont également appelés
depuis les threads workers.

Le service porte deux niveaux de granularité, volontairement découplés :

- **macro** (toujours fiable) : document courant, index sur total, libellé ;
- **micro** (opportuniste) : fragments traités du document courant.

Une seule passe peut être active à la fois : ``begin`` refuse toute concurrence, et
le refus est signalé par ``refused`` (toast discret côté interface). L'annulation est
**coopérative entre documents** : ``request_cancel`` arme un drapeau que les workers
consultent avant chaque document, jamais en cours de document.
"""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class ReindexActivityService(QObject):
    """Hub d'état et de signaux d'une passe de réindexation.

    Le service ne connaît ni les workers ni l'interface : il reçoit des faits
    (démarrage, document traité, fragments, fin) et les rediffuse. Il est de ce
    fait testable sans base de données ni thread.
    """

    #: Nombre total de documents de la passe qui démarre.
    started = Signal(int)
    #: ``document_number`` (1-based), ``total``, ``titre`` du document entrant.
    progress = Signal(int, int, str)
    #: ``fragments_traités``, ``fragments_total`` du document courant (micro opportuniste).
    fragment_progress = Signal(int, int)
    #: ``documents_réindexés``, ``fragments_réindexés``, ``erreurs``, ``annulée``.
    finished = Signal(int, int, int, bool)
    #: Déclenchement refusé alors qu'une passe tourne : ``document_courant``, ``total``.
    refused = Signal(int, int)

    _instance: ReindexActivityService | None = None

    @classmethod
    def get_instance(cls) -> ReindexActivityService:
        """Retourne le singleton de processus (créé à la demande)."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._lock = threading.RLock()
        self._active = False
        self._total = 0
        self._current_number = 0
        self._current_title = ""
        self._cancel = threading.Event()

    # ─── État ───

    def is_active(self) -> bool:
        """Indique si une passe est en cours."""
        with self._lock:
            return self._active

    def current_position(self) -> tuple[int, int]:
        """Retourne ``(document_courant, total)`` de la passe active."""
        with self._lock:
            return self._current_number, self._total

    # ─── Cycle de vie de la passe ───

    def begin(self, total_documents: int) -> bool:
        """Démarre une passe de ``total_documents`` documents.

        Retourne ``False`` (et émet ``refused``) si une passe tourne déjà : deux
        bandeaux concurrents seraient plus trompeurs qu'informatifs.
        """
        with self._lock:
            if self._active:
                logger.info(
                    "Passe de réindexation refusée : une passe est déjà en cours (%d/%d).",
                    self._current_number,
                    self._total,
                )
                self.refused.emit(self._current_number, self._total)
                return False
            self._active = True
            self._total = max(int(total_documents), 0)
            self._current_number = 0
            self._current_title = ""
            self._cancel.clear()
            logger.info("Démarrage d'une passe de réindexation de %d document(s).", self._total)
            self.started.emit(self._total)
            return True

    def report_document(self, number: int, total: int, title: str) -> None:
        """Publie le document macro en cours (niveau toujours fiable)."""
        with self._lock:
            if not self._active:
                return
            self._total = max(int(total), 0)
            self._current_number = int(number)
            self._current_title = title
            self.progress.emit(self._current_number, self._total, title)

    def report_fragments(self, processed: int, total: int) -> None:
        """Publie la micro-progression (fragments) du document courant, sans bloquer le macro."""
        with self._lock:
            if not self._active:
                return
            self.fragment_progress.emit(int(processed), int(total))

    def finish(self, documents: int, fragments: int, errors: int) -> None:
        """Clôt la passe et diffuse le récapitulatif (documents, fragments, erreurs)."""
        with self._lock:
            if not self._active:
                return
            cancelled = self._cancel.is_set()
            self._active = False
            self._cancel.clear()
            logger.info(
                "Passe de réindexation terminée : %d document(s), %d fragment(s), %d erreur(s)%s.",
                documents,
                fragments,
                errors,
                " (annulée)" if cancelled else "",
            )
            self.finished.emit(int(documents), int(fragments), int(errors), cancelled)

    # ─── Annulation coopérative ───

    def request_cancel(self) -> None:
        """Arme l'annulation : effective entre deux documents, jamais au milieu d'un document."""
        with self._lock:
            if self._active:
                logger.info("Annulation de la passe de réindexation demandée.")
                self._cancel.set()

    def is_cancel_requested(self) -> bool:
        """Indique si une annulation a été demandée (lu par les workers)."""
        return self._cancel.is_set()
