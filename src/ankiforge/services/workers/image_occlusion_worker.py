"""
Worker asynchrone pour la détection IA des légendes et zones de masquage (Image Occlusion).
Exécute l'inférence de vision en arrière-plan sans bloquer l'interface graphique Qt.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.cards.image_occlusion_service import ImageOcclusionService, OcclusionBox

logger = logging.getLogger(__name__)


class ImageOcclusionDetectionWorker(QThread):
    """
    Worker d'arrière-plan pour la détection des légendes via le modèle de vision.
    Émet des signaux pour informer l'interface du résultat ou des erreurs.
    """

    finished_signal = Signal(list)  # list[OcclusionBox]
    error_signal = Signal(str)  # error_message
    status_signal = Signal(str)  # message informatif

    def __init__(
        self,
        image_path: str | Path,
        service: ImageOcclusionService | None = None,
        provider: LLMProvider | None = None,
        provider_name: str | None = None,
        model_id: str | None = None,
        parent: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self.image_path = Path(image_path)
        self.service = service or ImageOcclusionService()
        self.provider = provider
        self.provider_name = provider_name
        self.model_id = model_id

    def run(self) -> None:
        """Exécute la détection de vision en arrière-plan."""
        logger.info("Démarrage de la détection IA d'occlusion sur : %s", self.image_path.name)
        self.status_signal.emit("Analyse de l'image par le modèle de vision...")

        try:
            boxes: list[OcclusionBox] = self.service.detect_labels_with_vision(
                image_path=self.image_path,
                provider=self.provider,
                provider_name=self.provider_name,
                model_id=self.model_id,
            )
            logger.info("Détection d'occlusion terminée avec succès : %d boîtes trouvées.", len(boxes))
            self.finished_signal.emit(boxes)
        except Exception as err:
            logger.exception("Erreur lors de la détection d'occlusion sur %s : %s", self.image_path.name, err)
            self.error_signal.emit(str(err))
