"""
Worker asynchrone pour l'analyse préliminaire et l'importation de collections Anki (.apkg, .colpkg, .txt).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from ankiforge.services.cards.import_manager import ImportAnalysisResult, ImportManager

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
        path: str | Path | None = None,
        mode: str = "analyze",  # 'analyze', 'commit' ou 'full'
        import_manager: ImportManager | None = None,
        analysis: ImportAnalysisResult | None = None,
        conflict_resolutions: dict[str, dict[str, Any]] | None = None,
        target_deck_id: int | None = None,
        store_manager: Any = None,
        parent: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self.path = Path(path) if path else None
        self.mode = mode
        self.import_manager = import_manager or ImportManager()
        self.analysis = analysis
        self.conflict_resolutions = conflict_resolutions
        self.target_deck_id = target_deck_id

    def run(self) -> None:
        """Exécute l'analyse ou l'import complet en arrière-plan."""
        source_name = self.path.name if self.path else "en mémoire"
        logger.info("ImportCardsWorker démarré (mode='%s', source='%s')", self.mode, source_name)
        t0 = time.perf_counter()
        try:
            if self.mode == "commit":
                if not self.analysis:
                    raise ValueError("Aucun résultat d'analyse fourni pour le mode commit.")
                result = self.import_manager.commit_import(
                    analysis=self.analysis,
                    conflict_resolutions=self.conflict_resolutions,
                    target_deck_id=self.target_deck_id,
                    progress_callback=self.progress.emit,
                )
                elapsed = time.perf_counter() - t0
                logger.info("Commit d'importation achevé en %.2fs : %s", elapsed, result)
                self.commit_finished.emit(result)
                self.finished_signal.emit()
                return

            if not self.path:
                raise ValueError("Chemin de fichier manquant pour l'analyse d'importation.")

            analysis = self.import_manager.analyze_archive(self.path, progress_callback=self.progress.emit)
            notes_count = len(analysis.new_notes) + len(analysis.silent_updates) + len(analysis.conflicts)
            logger.info("Analyse d'archive complétée pour '%s' : %d note(s) identifiée(s)", self.path.name, notes_count)
            self.analysis_ready.emit(analysis)

            if self.mode == "full":
                result = self.import_manager.commit_import(analysis, progress_callback=self.progress.emit)
                elapsed = time.perf_counter() - t0
                logger.info("Importation complète achevée pour '%s' en %.2fs : %s", self.path.name, elapsed, result)
                self.commit_finished.emit(result)
                self.finished_signal.emit()

        except Exception as e:
            logger.exception("Erreur lors de l'opération d'importation (mode='%s') : %s", self.mode, e)
            self.error_signal.emit(str(e))
