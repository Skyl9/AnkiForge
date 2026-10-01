"""
Worker asynchrone pour la transcription OCR et l'analyse visuelle par lot des pages d'albums.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from ankiforge.database.models import DocumentPageModel
from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.ai.ocr_service import OCRService
from ankiforge.services.cards.album_service import AlbumCompileCancelled, AlbumService

logger = logging.getLogger(__name__)


class AlbumOCRWorker(QThread):
    """
    Worker d'arrière-plan pour la transcription OCR d'un album ou d'une sélection de pages.
    Émet des signaux de progression pour l'interface sans bloquer l'Event Loop Qt.
    """

    progress = Signal(int, int)  # (current_page, total_pages)
    page_processed = Signal(int, int, str)  # (page_id, page_number, ocr_text)
    #: (success_count, error_count) — l'ordre est celui du slot, et le dire ici évite
    #: qu'un échange d'arguments fasse annoncer un succès complet sur un album dont la
    #: moitié des planches a échoué.
    finished_signal = Signal(int, int)
    #: (done, total). Signal distinct de `finished_signal` parce qu'un album annulé à
    #: mi-parcours n'est pas un album terminé : l'annoncer comme « achevé » affirmait un
    #: succès sur des planches jamais vues. Une interruption se distingue donc d'un
    #: travail normal, et `error_count` ne sert pas à la maquiller.
    cancelled_signal = Signal(int, int)
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
            error_count = 0
            cancelled_at: int | None = None
            for idx, page in enumerate(pages):
                if self._is_cancelled:
                    cancelled_at = idx
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
                    error_count += 1
                    logger.error("Erreur de transcription pour la page ID %d : %s", page.id, page_err)

                self.progress.emit(idx + 1, total_pages)

            if cancelled_at is not None:
                self.cancelled_signal.emit(cancelled_at, total_pages)
                return

            if error_count:
                logger.warning("AlbumOCRWorker terminé : %d/%d pages transcrites, %d en échec", success_count, total_pages, error_count)
            else:
                logger.info("AlbumOCRWorker terminé : %d/%d pages transcrites avec succès", success_count, total_pages)
            self.finished_signal.emit(success_count, error_count)
        except Exception as e:
            logger.exception("Erreur fatale dans AlbumOCRWorker : %s", e)
            self.error_signal.emit(str(e))


class AlbumPDFWorker(QThread):
    """
    Worker d'arrière-plan pour la compilation PDF d'un album.

    La compilation ouvre chaque planche en pleine résolution : sur 200 planches, la faire
    sur le thread GUI gèle l'interface. La forme des signaux reprend celle
    d'`AlbumOCRWorker` — progression, annulation, compte rendu — parce que les deux
    opérations se lancent depuis la même barre d'outils et doivent se ressembler.
    """

    progress = Signal(int, int)  # (current_page, total_pages)
    finished_signal = Signal(str)  # (output_path)
    cancelled_signal = Signal(int, int)  # (done, total)
    error_signal = Signal(str)

    def __init__(
        self,
        document_id: int,
        output_path: str | Path,
        album_service: AlbumService | None = None,
        parent: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self.document_id = document_id
        self.output_path = output_path
        self.album_service = album_service or AlbumService()
        self._is_cancelled = False

    def cancel(self) -> None:
        """Demande l'annulation de la compilation en cours."""
        self._is_cancelled = True

    def run(self) -> None:
        logger.info("Démarrage d'AlbumPDFWorker pour l'album ID %d -> %s", self.document_id, self.output_path)
        try:
            result = self.album_service.compile_album_to_pdf(
                self.document_id,
                output_path=self.output_path,
                progress_callback=lambda current, total: self.progress.emit(current, total),
                should_cancel=lambda: self._is_cancelled,
            )
        except AlbumCompileCancelled as cancelled:
            logger.info("Compilation PDF annulée : %d/%d planches traitées", cancelled.done, cancelled.total)
            self.cancelled_signal.emit(cancelled.done, cancelled.total)
        except Exception as e:
            logger.exception("Erreur lors de la compilation PDF de l'album %d : %s", self.document_id, e)
            self.error_signal.emit(str(e))
        else:
            self.finished_signal.emit(str(result))
