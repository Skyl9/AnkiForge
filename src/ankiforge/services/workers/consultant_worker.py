import asyncio
import json
import logging
from typing import Any

from PySide6.QtCore import QThread, Signal

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.consultant_engine import ConsultantEngine

logger = logging.getLogger(__name__)


class ConsultantWorker(QThread):
    """
    Expert IA interactif pour l'analyse de collection.
    Utilise ConsultantEngine pour le Tool Calling (MCP) en arrière-plan.
    """

    progress = Signal(str)
    finished_signal = Signal(str)
    error_signal = Signal(str)

    def __init__(self, llm_config: LLMConfigModel, persona: Any, context_data: dict[str, Any], instruction: str):
        """
        Initialise le consultant IA.

        Args:
            llm_config (LLMConfigModel): La configuration de l'IA sélectionnée.
            persona (Any): L'agent IA (PersonaModel) sélectionné.
            context_data (dict[str, Any]): Synthèse des données Anki (notes, doublons).
            instruction (str): La question ou commande de l'utilisateur.
        """
        super().__init__()
        self.llm_config = llm_config
        self.persona = persona
        self.context_data = context_data
        self.instruction = instruction

    def run(self):
        """Prépare le payload contextuel et lance le moteur ReAct via asyncio."""
        try:
            self.progress.emit("Initialisation du moteur IA et connexion aux outils...")

            # Construire un prompt augmenté avec le contexte si besoin
            if self.context_data and (self.context_data.get("documents") or self.context_data.get("paquets")):
                context_str = json.dumps(self.context_data, ensure_ascii=False, indent=2)
                full_prompt = f"Contexte actuel :\n```json\n{context_str}\n```\n\nRequête de l'utilisateur :\n{self.instruction}"
            else:
                full_prompt = self.instruction

            model_name = getattr(self.llm_config, "model_id", "l'IA")
            self.progress.emit(f"Exécution de la requête via {model_name}...")

            async def _run_engine():
                engine = ConsultantEngine(self.llm_config, persona=self.persona)
                final_response = []
                async for chunk in engine.chat_stream(full_prompt):
                    if isinstance(chunk, str):
                        # On pourrait émettre en direct si on le souhaitait, mais ici on concatène
                        # ou on émet des messages intermédiaires.
                        if chunk.startswith("🔄") or chunk.startswith("✅") or chunk.startswith("❌"):
                            self.progress.emit(chunk.strip())
                        else:
                            final_response.append(chunk)
                return "".join(final_response)

            final_text = asyncio.run(_run_engine())

            self.progress.emit("Réponse finalisée.")
            self.finished_signal.emit(final_text)

        except Exception as e:
            logger.exception("Erreur dans le ConsultantWorker :")
            self.error_signal.emit(str(e))
