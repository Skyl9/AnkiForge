"""
Worker asynchrone pour l'analyse préliminaire et l'importation de collections Anki (.apkg, .colpkg, .txt).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QThread, Signal

from ankiforge.services.cards.import_manager import ImportManager

logger = logging.getLogger(__name__)


class ImportCardsWorker(QThread):
    """
    Worker d'analyse et d'importation en arrière-plan avec rapports de progression.
    """

    progress = Signal(str)
    analysis_ready = Signal(object)  # ImportAnalysisResult
    commit_finished = Signal(dict)  # Dict[str, int]
    finished_signal = Signal()
    error_signal = Signal(str)

    def __init__(
        self,
        path: str | Path,
        mode: str = "analyze",  # 'analyze' ou 'full'
        import_manager: Optional[ImportManager] = None,
        store_manager: Any = None,
        parent: Optional[Any] = None,
    ) -> None:
        super().__init__(parent)
        self.path = Path(path)
        self.mode = mode
        self.import_manager = import_manager or ImportManager()

    def run(self) -> None:
        """Exécute l'analyse ou l'import complet en arrière-plan."""
        try:
            analysis = self.import_manager.analyze_archive(self.path, progress_callback=self.progress.emit)
            self.analysis_ready.emit(analysis)

            if self.mode == "full":
                result = self.import_manager.commit_import(analysis, progress_callback=self.progress.emit)
                self.commit_finished.emit(result)
                self.finished_signal.emit()

        except Exception as e:
            logger.exception("Erreur lors de l'analyse / importation :")
            self.error_signal.emit(str(e))
