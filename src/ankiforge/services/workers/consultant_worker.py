import json
import logging
from typing import Any

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class ConsultantWorker(QThread):
    """Thread qui envoie le contexte massif à l'IA pour obtenir des conseils."""

    progress = Signal(str)
    finished_signal = Signal(str)
    error_signal = Signal(str)

    def __init__(self, ai_provider: Any, context_data: dict[str, Any], instruction: str):
        super().__init__()
        self.ai_provider = ai_provider
        self.context_data = context_data
        self.instruction = instruction

    def run(self):
        try:
            self.progress.emit("Extraction et structuration du contexte...")

            system_prompt = (
                "Tu es un expert en mémorisation, pédagogie et création de flashcards Anki.\n"
                "Ton rôle est d'analyser les documents et les paquets de cartes fournis en contexte.\n"
                "Réponds aux questions de l'utilisateur pour l'aider à améliorer son apprentissage.\n"
                "RÈGLES :\n"
                "1. Réponds en Markdown avec une structure claire.\n"
                "2. Si l'utilisateur demande un audit (/audit), cherche les incohérences ou les cartes trop complexes.\n"
                "3. Sois direct, pédagogique et critique si nécessaire."
            )

            user_payload = {"contexte_fourni": self.context_data, "requete_utilisateur": self.instruction}

            user_prompt = json.dumps(user_payload, ensure_ascii=False, indent=2)

            # On récupère le nom du modèle de manière sécurisée pour l'affichage
            model_name = getattr(self.ai_provider, "model_name", "l'IA")
            self.progress.emit(f"Envoi des données au modèle {model_name}...")

            # Appel API
            raw_response = self.ai_provider.generate(system_prompt=system_prompt, user_prompt=user_prompt, response_format="text")

            self.progress.emit("Réponse reçue, formatage en cours...")
            self.finished_signal.emit(raw_response)

        except Exception as e:
            logger.exception("Erreur dans le ChatConsultantThread :")
            self.error_signal.emit(str(e))
