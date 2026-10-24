"""Tests unitaires pour le suivi du budget tokens & coûts en temps réel du Consultant IA.

Vérifie le calcul des tokens réels et du coût USD (pricing_service), l'émission des signaux de budget,
et l'interruption préventive automatique au seuil de 80%.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.consultant_engine import ConsultantEngine
from ankiforge.services.settings_service import SettingsService

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_llm_config():
    return LLMConfigModel(
        name="GPT-4o Test",
        provider="openai",
        model_name="gpt-4o",
        temperature=0.7,
        max_tokens=4096,
        is_active=True,
    )


def test_consultant_budget_warning_at_80_percent(mock_llm_config):
    """Vérifie l'émission de budget_warning et l'interruption préventive à 80% du quota."""

    async def _run():
        # Configurer un budget bas pour le test (1000 tokens)
        SettingsService.set("ai/consultant_token_budget", 1000)
        SettingsService.set("ai/consultant_cost_budget", 0.05)

        events_collected = []

        mock_provider = MagicMock()
        # Réponse générée suffisante pour consommer > 800 tokens (80% de 1000)
        mock_provider.generate.return_value = (
            "Voici une analyse détaillée de votre collection Anki. Plusieurs cartes présentent des formulations trop longues qui violent la règle d'atomicité de Wozniak. "
        ) * 45

        engine = ConsultantEngine(llm_config=mock_llm_config, ai_provider=mock_provider)

        async for event in engine.chat_stream("Analyse mon deck"):
            events_collected.append(event)

        # Vérifier la présence de budget_update
        budget_updates = [e for e in events_collected if e.get("type") == "budget_update"]
        assert len(budget_updates) > 0
        assert budget_updates[-1]["tokens_used"] >= 800

        # Vérifier l'événement budget_warning (seuil >= 80% atteint)
        warning_events = [e for e in events_collected if e.get("type") == "budget_warning"]
        assert len(warning_events) == 1
        assert warning_events[0]["threshold"] == 0.8
        assert warning_events[0]["tokens_used"] >= 800

        # Vérifier que le message final mentionne l'arrêt préventif
        finish_events = [e for e in events_collected if e.get("type") == "finished"]
        assert len(finish_events) == 1
        assert "80%" in finish_events[0]["text"] or "budget" in finish_events[0]["text"].lower()

    asyncio.run(_run())
