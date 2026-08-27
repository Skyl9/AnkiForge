import logging
import time
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

    def __init__(
        self,
        provider_a: Any,
        provider_b: Any,
        prompts_a: list[str],
        prompts_b: list[str],
        source_text: str,
    ):
        """
        Initialise le worker de test A/B.

        Args:
            provider_a (Any): Fournisseur IA pour le sujet A.
            provider_b (Any): Fournisseur IA pour le sujet B.
            prompts_a (list[str]): Liste des prompts système (1 prompt = Agent, >1 = Pipeline) pour A.
            prompts_b (list[str]): Liste des prompts système pour B.
            source_text (str): Le texte utilisateur initial.
        """
        super().__init__()
        self.provider_a = provider_a
        self.provider_b = provider_b
        self.prompts_a = prompts_a
        self.prompts_b = prompts_b
        self.source_text = source_text
        self._is_cancelled = False

    def cancel(self) -> None:
        """Demande l'arrêt prématuré du test."""
        logger.info("Demande d'annulation du test A/B reçue.")
        self._is_cancelled = True

    def _execute_chain(self, provider: Any, prompts: list[str], prefix: str) -> str:
        """Exécute la chaîne d'agents en passant le résultat au suivant."""
        current_input = f"TEXTE SOURCE :\n{self.source_text}"
        res = ""
        total = len(prompts)

        for i, prompt in enumerate(prompts):
            if self._is_cancelled:
                return ""

            if total > 1:
                self.progress.emit(f"{prefix} - Étape {i + 1}/{total}...")
            else:
                self.progress.emit(f"{prefix} en cours de génération...")

            logger.debug("%s - Exécution de l'étape %d/%d (prompt: %d car.)", prefix, i + 1, total, len(prompt))
            res = provider.generate(system_prompt=prompt, user_prompt=current_input)
            current_input = res  # L'entrée du prochain agent est le résultat de l'actuel

        return res

    def run(self) -> None:
        """Exécute les deux générations séquentiellement et émet les résultats."""
        logger.info(
            "Démarrage du test A/B (%d étapes pour Sujet A, %d étapes pour Sujet B, %d car. texte source)",
            len(self.prompts_a),
            len(self.prompts_b),
            len(self.source_text),
        )
        t0 = time.perf_counter()
        try:
            if self._is_cancelled:
                logger.info("Test A/B annulé avant exécution.")
                self.cancelled.emit()
                return

            res_a = self._execute_chain(self.provider_a, self.prompts_a, "⏳ Sujet A")
            if self._is_cancelled:
                logger.info("Test A/B annulé après Sujet A.")
                self.cancelled.emit()
                return
            self.result_a.emit(res_a)

            res_b = self._execute_chain(self.provider_b, self.prompts_b, "⏳ Sujet B")
            if self._is_cancelled:
                logger.info("Test A/B annulé après Sujet B.")
                self.cancelled.emit()
                return
            self.result_b.emit(res_b)

            elapsed = time.perf_counter() - t0
            logger.info(
                "Test A/B terminé avec succès en %.2fs (résultat A: %d car., résultat B: %d car.)",
                elapsed,
                len(res_a),
                len(res_b),
            )
            self.finished_signal.emit()

        except Exception as e:
            logger.exception("Erreur critique lors de l'exécution du test A/B : %s", e)
            self.error_signal.emit(str(e))
