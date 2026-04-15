import logging
from typing import Any

from PySide6.QtCore import QThread, Signal


logger = logging.getLogger(__name__)


class AbWorker(QThread):
    """
    Thread exécutant un test A/B entre deux configurations d'IA.

    Permet de comparer les réponses de deux modèles ou deux prompts différents
    sur un même texte source, de manière asynchrone pour ne pas figer l'interface.
    """

    progress = Signal(str)
    result_a = Signal(str)
    result_b = Signal(str)
    finished_signal = Signal()
    error_signal = Signal(str)
    cancelled = Signal()

    def __init__(self, provider_a: Any, provider_b: Any, prompt_a: str, prompt_b: str, source_text: str):
        """
        Initialise le worker de test A/B.

        Args:
            provider_a (Any): Fournisseur IA pour le sujet A.
            provider_b (Any): Fournisseur IA pour le sujet B.
            prompt_a (str): Prompt système pour le sujet A.
            prompt_b (str): Prompt système pour le sujet B.
            source_text (str): Le texte utilisateur commun aux deux tests.
        """
        super().__init__()
        self.provider_a = provider_a
        self.provider_b = provider_b
        self.prompt_a = prompt_a
        self.prompt_b = prompt_b
        self.source_text = source_text
        self._is_cancelled = False

    def cancel(self):
        """Demande l'arrêt prématuré du test."""
        self._is_cancelled = True

    def run(self):
        """Exécute les deux générations séquentiellement et émet les résultats."""
        try:
            user_input = f"TEXTE SOURCE :\n{self.source_text}"

            if self._is_cancelled:
                self.cancelled.emit()
                return

            self.progress.emit("⏳ Sujet A en cours de génération...")
            res_a = self.provider_a.generate(system_prompt=self.prompt_a, user_prompt=user_input)

            if self._is_cancelled:
                self.cancelled.emit()
                return
            self.result_a.emit(res_a)

            self.progress.emit("⏳ Sujet B en cours de génération...")
            res_b = self.provider_b.generate(system_prompt=self.prompt_b, user_prompt=user_input)

            if self._is_cancelled:
                self.cancelled.emit()
                return
            self.result_b.emit(res_b)

            self.finished_signal.emit()

        except Exception as e:
            logger.exception("Erreur lors de l'exécution du test A/B :")
            self.error_signal.emit(str(e))
