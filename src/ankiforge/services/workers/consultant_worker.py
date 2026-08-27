"""
Worker asynchrone pour le Consultant IA AnkiForge.
Orchestre l'exécution en arrière-plan du moteur ReAct et transmet les signaux à l'UI PySide6.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from PySide6.QtCore import QThread, Signal

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.consultant_engine import ConsultantEngine

logger = logging.getLogger(__name__)


class ConsultantWorker(QThread):
    """
    Expert IA interactif pour l'analyse de collection et le diagnostic.
    Utilise ConsultantEngine pour la boucle ReAct (Thought ➔ Action ➔ Observation) en arrière-plan.
    """

    thought_emitted = Signal(int, str)
    tool_call_emitted = Signal(str, str, str, bool)  # tool_name, args_json, result_str, is_error
    progress = Signal(str)
    finished_signal = Signal(str)
    error_signal = Signal(str)

    def __init__(
        self,
        llm_config: Optional[LLMConfigModel] = None,
        persona: Any = None,
        context_data: Optional[Dict[str, Any]] = None,
        instruction: str = "",
        ai_provider: Any = None,
    ) -> None:
        super().__init__()
        self.llm_config = llm_config
        self.persona = persona
        self.context_data = context_data or {}
        self.instruction = instruction
        self.ai_provider = ai_provider

    def run(self) -> None:
        """Prépare le payload contextuel et lance le moteur ReAct via asyncio."""
        import time

        t0 = time.perf_counter()
        try:
            self.progress.emit("Initialisation du moteur IA et connexion aux outils MCP...")

            # Construire un prompt augmenté avec le contexte si disponible
            if self.context_data and (self.context_data.get("documents") or self.context_data.get("paquets")):
                context_str = json.dumps(self.context_data, ensure_ascii=False, indent=2)
                full_prompt = f"Contexte actuel des documents et paquets attachés :\n```json\n{context_str}\n```\n\nRequête de l'utilisateur :\n{self.instruction}"
            else:
                full_prompt = self.instruction

            active_config = self.llm_config or LLMConfigModel.select().first()
            if not active_config and self.ai_provider is None:
                active_config = LLMConfigModel(provider="openai", model_id="gpt-4o")

            model_name = getattr(active_config, "display_name", getattr(active_config, "model_id", "l'IA")) if active_config else "l'IA"
            logger.info("Démarrage de la session ConsultantWorker (modèle: %s, requête: %s...)", model_name, self.instruction[:60])
            self.progress.emit(f"Exécution ReAct MCP via {model_name}...")

            async def _run_engine() -> str:
                engine = ConsultantEngine(llm_config=active_config, persona=self.persona, ai_provider=self.ai_provider)
                final_text = ""
                curr_tool_name = ""
                curr_tool_args: Dict[str, Any] = {}

                async for event in engine.chat_stream(full_prompt):
                    ev_type = event.get("type")

                    if ev_type == "thought":
                        step = event.get("step", 1)
                        content = event.get("content", "")
                        self.thought_emitted.emit(step, content)
                        self.progress.emit(f"🤔 Étape {step} : Réflexion ReAct...")

                    elif ev_type == "tool_start":
                        curr_tool_name = event.get("tool", "unknown")
                        curr_tool_args = event.get("args", {})
                        self.progress.emit(f"🔧 Exécution de l'outil MCP `{curr_tool_name}`...")

                    elif ev_type == "tool_result":
                        t_name = event.get("tool", curr_tool_name)
                        result = str(event.get("result", ""))
                        is_err = bool(event.get("is_error", False))
                        args_str = json.dumps(curr_tool_args, ensure_ascii=False)
                        self.tool_call_emitted.emit(t_name, args_str, result, is_err)
                        self.progress.emit(f"✅ Résultat MCP reçu de `{t_name}`.")

                    elif ev_type == "text":
                        final_text += event.get("content", "")

                    elif ev_type == "finished":
                        if not final_text:
                            final_text = event.get("content", "")

                return final_text

            final_output = asyncio.run(_run_engine())
            elapsed = time.perf_counter() - t0
            logger.info("Session ConsultantWorker terminée avec succès en %.2fs (%d caractères générés)", elapsed, len(final_output))
            self.progress.emit("Réponse finalisée.")
            self.finished_signal.emit(final_output)

        except Exception as e:
            logger.exception("Erreur dans le ConsultantWorker : %s", e)
            self.error_signal.emit(str(e))
