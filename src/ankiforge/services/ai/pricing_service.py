# src/ankiforge/services/ai/pricing_service.py

PRICING_1M_USD = {
    "gpt-4o": (5.0, 15.0),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-3-5-sonnet-20240620": (3.0, 15.0),
    "gemini-1.5-pro": (3.5, 10.5),
    "gemini-2.5-flash": (0.075, 0.30),
    "gemini-2.0-flash": (0.10, 0.40),
}


def calculate_job_estimate(
    text_length: int,
    step_count: int,
    chunk_strategy: str,
    use_vision: bool,
    image_count: int,
    model_id: str,
) -> tuple[int, float]:
    """
    Calcule une estimation du nombre de jetons (tokens) et du coût financier pour un job.

    Args:
        text_length (int): Longueur du texte source en caractères.
        step_count (int): Nombre d'étapes (agents) dans le pipeline.
        chunk_strategy (str): Stratégie de découpage choisie.
        use_vision (bool): Si la vision est activée.
        image_count (int): Nombre d'images détectées dans le texte.
        model_id (str): Identifiant du modèle LLM.

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
    rates = PRICING_1M_USD.get(model_id, (0.0, 0.0))
    total_cost = (input_tokens / 1_000_000 * rates[0]) + (output_tokens / 1_000_000 * rates[1])

    return total_tokens, total_cost
