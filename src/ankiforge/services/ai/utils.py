import json
import re
from jinja2 import Template

from ankiforge.database.models import TokenUsageModel

PRICING_1M_USD = {
    "gpt-4o": (5.0, 15.0),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-3-5-sonnet-20240620": (3.0, 15.0),
    "gemini-1.5-pro": (3.5, 10.5),
    "gemini-2.5-flash": (0.075, 0.30),
    "gemini-2.0-flash": (0.10, 0.40),
}


def log_token_usage(provider: str, model_id: str, prompt_tokens: int, completion_tokens: int) -> None:
    """Enregistre la consommation en base de données et estime le coût."""
    cost = 0.0

    # On cherche le prix du modèle (ou 0.0 s'il est local/gratuit comme Ollama/Groq)
    rates = PRICING_1M_USD.get(model_id, (0.0, 0.0))
    if rates != (0.0, 0.0):
        cost = (prompt_tokens / 1_000_000 * rates[0]) + (completion_tokens / 1_000_000 * rates[1])

    TokenUsageModel.create(
        provider=provider,
        model_id=model_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        estimated_cost_usd=cost,
    )


def parse_ai_json_response(response_text: str):
    """
    Nettoie et convertit la réponse de l'IA en objet Python (dict ou list).
    Extrait intelligemment le bloc JSON même s'il y a du texte autour.
    """
    try:
        backticks = "`" * 3
        # 1. On cherche d'abord proprement un bloc de code markdown
        pattern = backticks + r"(?:json)?\s*(.*?)" + backticks
        match = re.search(pattern, response_text, re.DOTALL)

        if match:
            cleaned_text = match.group(1).strip()
        else:
            # 2. FALLBACK ULTIME : L'IA a oublié les backticks
            fallback_match = re.search(r"(\{.*}|\[.*])", response_text, re.DOTALL)
            if fallback_match:
                cleaned_text = fallback_match.group(1).strip()
            else:
                cleaned_text = response_text.strip()

        # 👇 3. LE BOUCLIER ANTI-CRASH (Version Définitive & Infaillible) 👇
        def escape_latex(m):
            char = m.group(1)
            # Si le backslash protège un caractère JSON valide (ex: \n, \", \\)
            if char in '"\\/bfnrtu':
                return "\\" + char
            # Sinon, c'est du LaTeX rebelle (ex: \(, \[), on double le backslash !
            else:
                return "\\\\" + char

        # On intercepte chaque backslash suivi d'un caractère et on le filtre
        cleaned_text = re.sub(r"\\(.)", escape_latex, cleaned_text)

        return json.loads(cleaned_text)

    except json.JSONDecodeError as e:
        raise ValueError(f"L'IA a généré un format invalide. Impossible de lire le JSON.\nDétail: {e}") from e


def format_system_prompt(system_prompt_template: str, fields_schema_json: str | None) -> str:
    """
    Remplit dynamiquement un prompt système Jinja2 avec les champs Anki cibles.

    Args:
        system_prompt_template (str): Le prompt système brut contenant les variables Jinja2.
        fields_schema_json (str | None): Le schéma JSON des champs du modèle de note.

    Returns:
        str: Le prompt système final prêt à être envoyé à l'IA.
    """
    fields = json.loads(fields_schema_json) if fields_schema_json else ["Front", "Back"]
    fields_str = '", "'.join(fields)

    first_field = fields[0] if len(fields) > 0 else "Field1"
    second_field = fields[1] if len(fields) > 1 else "Field2"

    jinja_template = Template(system_prompt_template)
    return jinja_template.render(
        fields_str=fields_str,
        first_field=first_field,
        second_field=second_field,
    )
