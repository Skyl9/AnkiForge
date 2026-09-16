import logging
from typing import Any

logger = logging.getLogger(__name__)


def estimate_run_cost(
    prompt_tokens: int,
    completion_tokens: int,
    config: Any | None = None,
) -> tuple[int, float]:
    """
    Estime le coût réel (USD) d'un run A/B à partir d'une configuration LLM.

    Args:
        prompt_tokens (int): Nombre de tokens d'entrée consommés.
        completion_tokens (int): Nombre de tokens de sortie consommés.
        config: Objet LLMConfigModel (ou None pour un coût local/mock à 0).

    Returns:
        tuple[int, float]: (tokens_total, cout_estime_usd)
    """
    total_tokens = max(0, int(prompt_tokens)) + max(0, int(completion_tokens))
    if config is None:
        return total_tokens, 0.0

    provider = str(getattr(config, "provider", ""))
    is_free = bool(getattr(config, "is_free", False)) or provider == "ollama"
    if is_free:
        return total_tokens, 0.0

    prompt_pricing = float(getattr(config, "prompt_pricing", 0.0) or 0.0)
    completion_pricing = float(getattr(config, "completion_pricing", 0.0) or 0.0)
    if prompt_pricing == 0.0 and completion_pricing == 0.0:
        return total_tokens, 0.0

    total_cost = (max(0, int(prompt_tokens)) / 1_000_000 * prompt_pricing) + (max(0, int(completion_tokens)) / 1_000_000 * completion_pricing)
    logger.debug(
        "Coût estimé run A/B : %d tokens entrée / %d sortie -> $%.5f (fournisseur: %s)",
        prompt_tokens,
        completion_tokens,
        total_cost,
        provider,
    )
    return total_tokens, total_cost
