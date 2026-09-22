import pytest

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.pricing_service import estimate_run_cost

pytestmark = pytest.mark.integration


def test_estimate_run_cost_local_provider_free():
    """Un fournisseur local Ollama (ou gratuit) ne génère aucun coût."""
    cfg = LLMConfigModel.create(provider="ollama", model_id="llama3", display_name="Llama 3 Local", is_free=True)
    total, cost = estimate_run_cost(100, 50, cfg)
    assert total == 150
    assert cost == 0.0


def test_estimate_run_cost_tokens_aggregated():
    total, cost = estimate_run_cost(1000, 500, None)
    assert total == 1500
    assert cost == 0.0


def test_estimate_run_cost_real_pricing():
    """Le coût réel est calculé via les prix du fournisseur (par million de tokens)."""
    cfg = LLMConfigModel.create(provider="openai", model_id="gpt-4o", display_name="GPT-4o", prompt_pricing=5.0, completion_pricing=15.0)
    total, cost = estimate_run_cost(1_000_000, 1_000_000, cfg)
    assert total == 2_000_000
    assert cost == 20.0  # 5$ + 15$


def test_estimate_run_cost_negative_inputs_clamped():
    total, cost = estimate_run_cost(-10, -20, None)
    assert total == 0
    assert cost == 0.0
