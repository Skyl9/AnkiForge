"""Worker QThread de réalignement global de couverture documentaire.

Réaligne l'ensemble des documents du profil courant en arrière-plan, sans bloquer
la boucle d'événements Qt, afin d'éviter le verrou SQLite concurrentiel
(``database is locked``) sur le thread UI pendant une synchronisation globale.
Délègue la logique métier à :meth:`CoverageAlignmentService.align_all_documents`.
"""

import logging

from PySide6.QtCore import QObject, QThread, Signal

logger = logging.getLogger(__name__)


class AlignmentWorker(QThread):
    """Réaligne la couverture de tous les documents en arrière-plan.

    Émet :attr:`finished_alignment` avec le rapport de réconciliation une fois la
    passe terminée, ou :attr:`error_occurred` en cas d'exception.
    """

    finished_alignment = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    def run(self) -> None:
        """Exécute le réalignement global dans le thread worker."""
        logger.info("AlignmentWorker démarré : réalignement global de couverture")
        try:
            from ankiforge.services.audit.coverage_alignment_service import (
                CoverageAlignmentService,
            )

            report = CoverageAlignmentService.align_all_documents()
            self.finished_alignment.emit(report)
        except Exception as exc:  # pragma: no cover - sécurité worker
            logger.exception("Échec du réalignement global de couverture : %s", exc)
            self.error_occurred.emit(str(exc))
