import json

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.ai.consultant_engine import ConsultantEngine


class LoopingProvider(LLMProvider):
    """Fournisseur LLM de test qui simule un modèle bouclant 4 fois sur le même outil avec les mêmes arguments."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, system_prompt: str, user_prompt: str | list[dict], response_format: str = "json") -> str:
        self.call_count += 1
        if self.call_count <= 4:
            # Même outil avec exactement les mêmes arguments
            return json.dumps(
                {
                    "tool": "get_deck_stats",
                    "args": {"deck_name": "LoopDeck"},
                }
            )
        return "Réponse finale suite à l'interruption de la boucle."


def test_consultant_engine_cycle_prevention() -> None:
    """Vérifie que ConsultantEngine détecte et coupe les boucles infinies de mêmes appels d'outils."""
    import asyncio

    async def _test() -> None:
        provider = LoopingProvider()
        config = LLMConfigModel(provider="openai", model_id="gpt-4o")
        engine = ConsultantEngine(llm_config=config, ai_provider=provider)

        events = []
        async for ev in engine.chat_stream("Diagnostique le deck LoopDeck"):
            events.append(ev)

        # Récupérer les événements d'observation d'outils
        tool_results = [ev for ev in events if ev.get("type") == "tool_result"]
        assert len(tool_results) >= 3

        # Le 3ème appel consécutif identique doit être court-circuité avec un message d'avertissement de boucle
        third_result = tool_results[2]
        assert "Avertissement boucle" in third_result.get("result", "")

    asyncio.run(_test())
