"""
Worker asynchrone pour le Consultant IA AnkiForge.
Orchestre l'exécution en arrière-plan du moteur ReAct avec streaming temps réel et interruption.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

from PySide6.QtCore import QThread, Signal

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.consultant_engine import ConsultantEngine

logger = logging.getLogger(__name__)


class ConsultantWorker(QThread):
    """
    Expert IA interactif pour l'analyse de collection et le diagnostic.
    Utilise ConsultantEngine pour la boucle ReAct avec streaming fluide et support de l'interruption (Stop).
    """

    thought_emitted = Signal(int, str, bool)  # step, content, is_running
    tool_started_signal = Signal(str, str)  # tool_name, args_str
    tool_finished_signal = Signal(str, str, str, bool)  # tool_name, args_str, result_str, is_error
    tool_call_emitted = Signal(str, str, str, bool)  # compatibilité historique
    text_delta_signal = Signal(str)  # token / chunk streaming
    progress = Signal(str)
    finished_signal = Signal(str)
    next_steps_signal = Signal(list)
    cancelled_signal = Signal()
    error_signal = Signal(str)

    def __init__(
        self,
        llm_config: LLMConfigModel | None = None,
        persona: Any = None,
        context_data: dict[str, Any] | None = None,
        instruction: str = "",
        ai_provider: Any = None,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__()
        self.llm_config = llm_config
        self.persona = persona
        self.context_data = context_data or {}
        self.instruction = instruction
        self.ai_provider = ai_provider
        self.conversation_history = conversation_history or []
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        """Déclenche l'interruption immédiate de l'exécution ReAct."""
        logger.info("Interruption demandée par l'utilisateur pour le ConsultantWorker.")
        self._cancel_event.set()

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def run(self) -> None:
        """Prépare le payload contextuel et lance le moteur ReAct via asyncio avec streaming."""
        import time

        t0 = time.perf_counter()
        try:
            self.progress.emit("Initialisation de l'assistant...")

            # Construction du prompt augmenté
            if self.context_data and (self.context_data.get("documents") or self.context_data.get("paquets")):
                context_str = json.dumps(self.context_data, ensure_ascii=False, indent=2)
                full_prompt = f"Contexte actuel des documents et paquets attachés :\n```json\n{context_str}\n```\n\nRequête de l'utilisateur :\n{self.instruction}"
            else:
                full_prompt = self.instruction

            active_config = self.llm_config or LLMConfigModel.select().first()
            if not active_config and self.ai_provider is None:
                active_config = LLMConfigModel(provider="openai", model_id="gpt-4o")

            model_name = getattr(active_config, "display_name", getattr(active_config, "model_id", "l'IA")) if active_config else "l'IA"
            logger.info("Démarrage de session ConsultantWorker (modèle: %s, %d messages historiques)", model_name, len(self.conversation_history))
            self.progress.emit(f"Connexion via {model_name}...")

            async def _run_engine() -> tuple[str, list[str], bool]:
                engine = ConsultantEngine(llm_config=active_config, persona=self.persona, ai_provider=self.ai_provider)
                final_text = ""
                next_steps_list: list[str] = []
                curr_tool_name = ""
                curr_tool_args: dict[str, Any] = {}
                was_cancelled = False

                async for event in engine.chat_stream(
                    user_query=full_prompt,
                    history=self.conversation_history,
                    cancel_event=self._cancel_event,
                ):
                    if self._cancel_event.is_set():
                        was_cancelled = True
                        break

                    ev_type = event.get("type")

                    if ev_type == "thought":
                        step = event.get("step", 1)
                        content = event.get("content", "")
                        is_run = bool(event.get("is_running", False))
                        self.thought_emitted.emit(step, content, is_run)
                        self.progress.emit(f"🤔 {content}")

                    elif ev_type == "tool_start":
                        curr_tool_name = event.get("tool", "unknown")
                        curr_tool_args = event.get("args", {})
                        args_str = json.dumps(curr_tool_args, ensure_ascii=False)
                        self.tool_started_signal.emit(curr_tool_name, args_str)
                        self.progress.emit(f"🔧 Exécution de `{curr_tool_name}`...")

                    elif ev_type == "tool_result":
                        t_name = event.get("tool", curr_tool_name)
                        result = str(event.get("result", ""))
                        is_err = bool(event.get("is_error", False))
                        args_str = json.dumps(curr_tool_args, ensure_ascii=False)
                        self.tool_finished_signal.emit(t_name, args_str, result, is_err)
                        self.tool_call_emitted.emit(t_name, args_str, result, is_err)
                        self.progress.emit(f"✅ Résultat de `{t_name}`.")

                    elif ev_type == "text_delta":
                        delta = event.get("delta", "")
                        self.text_delta_signal.emit(delta)

                    elif ev_type == "text":
                        final_text = event.get("content", "")

                    elif ev_type == "finished":
                        if not final_text:
                            final_text = event.get("content", "")
                        next_steps_list = event.get("next_steps", [])

                    elif ev_type == "cancelled":
                        was_cancelled = True
                        break

                return final_text, next_steps_list, was_cancelled

            final_output, next_steps, was_cancelled = asyncio.run(_run_engine())
            elapsed = time.perf_counter() - t0

            if was_cancelled or self._cancel_event.is_set():
                logger.info("Session ConsultantWorker interrompue après %.2fs", elapsed)
                self.progress.emit("Session interrompue.")
                self.cancelled_signal.emit()
            else:
                logger.info("Session ConsultantWorker terminée avec succès en %.2fs (%d caractères)", elapsed, len(final_output))
                self.progress.emit("Réponse finalisée.")
                if next_steps:
                    self.next_steps_signal.emit(next_steps)
                self.finished_signal.emit(final_output)

        except Exception as e:
            logger.exception("Erreur dans le ConsultantWorker : %s", e)
            self.error_signal.emit(str(e))
