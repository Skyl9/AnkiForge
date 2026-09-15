"""
Worker asynchrone pour la transcription OCR et l'analyse visuelle par lot des pages d'albums.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import QThread, Signal

from ankiforge.database.models import DocumentPageModel
from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.ai.ocr_service import OCRService

logger = logging.getLogger(__name__)


class AlbumOCRWorker(QThread):
    """
    Worker d'arrière-plan pour la transcription OCR d'un album ou d'une sélection de pages.
    Émet des signaux de progression pour l'interface sans bloquer l'Event Loop Qt.
    """

    progress = Signal(int, int)  # (current_page, total_pages)
    page_processed = Signal(int, int, str)  # (page_id, page_number, ocr_text)
    finished_signal = Signal(int, int)  # (total_pages, success_count)
    error_signal = Signal(str)  # (error_message)

    def __init__(
        self,
        document_id: int,
        page_ids: Sequence[int] | None = None,
        category_id: str = "structured",
        ocr_service: OCRService | None = None,
        provider_override: LLMProvider | None = None,
        parent: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self.document_id = document_id
        self.page_ids = list(page_ids) if page_ids is not None else None
        self.category_id = category_id
        self.ocr_service = ocr_service or OCRService()
        self.provider_override = provider_override
        self._is_cancelled = False

    def cancel(self) -> None:
        """Demande l'annulation du traitement en cours."""
        self._is_cancelled = True

    def run(self) -> None:
        """Exécute la transcription séquentielle de chaque page en arrière-plan."""
        logger.info("Démarrage d'AlbumOCRWorker pour l'album ID %d (catégorie: '%s')", self.document_id, self.category_id)

        try:
            query = DocumentPageModel.select().where(DocumentPageModel.document == self.document_id)
            if self.page_ids:
                query = query.where(DocumentPageModel.id.in_(self.page_ids))

            pages = list(query.order_by(DocumentPageModel.page_number.asc()))
            total_pages = len(pages)

            if total_pages == 0:
                logger.warning("Aucune page trouvée pour l'album ID %d", self.document_id)
                self.finished_signal.emit(0, 0)
                return

            success_count = 0
            for idx, page in enumerate(pages):
                if self._is_cancelled:
                    logger.info("AlbumOCRWorker annulé par l'utilisateur à la page %d/%d", idx + 1, total_pages)
                    break

                try:
                    updated_page = self.ocr_service.transcribe_page(
                        page.id,
                        category_id=self.category_id,
                        provider_override=self.provider_override,
                    )
                    success_count += 1
                    self.page_processed.emit(updated_page.id, updated_page.page_number, updated_page.ocr_text)
                except Exception as page_err:
                    logger.error("Erreur de transcription pour la page ID %d : %s", page.id, page_err)

                self.progress.emit(idx + 1, total_pages)

            logger.info("AlbumOCRWorker terminé : %d/%d pages transcrites avec succès", success_count, total_pages)
            self.finished_signal.emit(total_pages, success_count)
        except Exception as e:
            logger.exception("Erreur fatale dans AlbumOCRWorker : %s", e)
            self.error_signal.emit(str(e))
