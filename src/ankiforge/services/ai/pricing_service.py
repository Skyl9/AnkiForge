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


def calculate_job_estimate(
    text_length: int,
    step_count: int,
    chunk_strategy: str,
    use_vision: bool,
    image_count: int,
    prompt_pricing: float,
    completion_pricing: float,
) -> tuple[int, float]:
    """
    Calcule une estimation du nombre de jetons (tokens) et du coût financier pour un job.

    Args:
        text_length (int): Longueur du texte source en caractères.
        step_count (int): Nombre d'étapes (agents) dans le pipeline.
        chunk_strategy (str): Stratégie de découpage choisie.
        use_vision (bool): Si la vision est activée.
        image_count (int): Nombre d'images détectées dans le texte.
        prompt_pricing (float): Coût par million de tokens en entrée (USD).
        completion_pricing (float): Coût par million de tokens en sortie (USD).

    Returns:
        tuple[int, float]: (nombre_total_tokens_estime, cout_estime_usd)
    """
    # Heuristique : 1 token = ~4 caractères
    base_doc_tokens = text_length // 4

    # Majoration Vision
    if use_vision:
        base_doc_tokens += image_count * 300  # +300 tokens par image (moyenne basse)

    # Majoration dynamique selon la méthode de découpage
    if chunk_strategy == "Chevauchement (Overlap)":
        base_doc_tokens = int(base_doc_tokens * 1.15)  # +15% car des phrases sont lues deux fois

    # Le document est relu par CHAQUE agent du pipeline
    steps = max(1, step_count)

    # Tokens d'entrée (Le document + un peu de gras pour les instructions)
    input_tokens = (base_doc_tokens + 500) * steps

    # Tokens de sortie estimés (On estime qu'un résumé/flashcard fait 20% de la taille d'origine)
    output_tokens = int((base_doc_tokens * 0.2) * steps)

    total_tokens = input_tokens + output_tokens

    # Calcul financier
    total_cost = (input_tokens / 1_000_000 * prompt_pricing) + (output_tokens / 1_000_000 * completion_pricing)

    logger.debug(
        "Estimation de coût job IA : %d caractères -> ~%d tokens, coût estimé: $%.5f (étapes: %d, vision: %s)",
        text_length,
        total_tokens,
        total_cost,
        steps,
        use_vision,
    )

    return total_tokens, total_cost
