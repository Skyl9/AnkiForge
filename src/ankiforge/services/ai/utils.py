import json
import re
from jinja2 import Template

from ankiforge.database.models import TokenUsageModel, LLMConfigModel


def log_token_usage(provider: str, model_id: str, prompt_tokens: int, completion_tokens: int) -> None:
    """
    Enregistre la consommation de jetons (tokens) en base de données et calcule le coût estimé.

    Args:
        provider (str): Nom du fournisseur d'IA (ex: 'openai', 'gemini').
        model_id (str): Identifiant du modèle utilisé.
        prompt_tokens (int): Nombre de jetons envoyés en entrée.
        completion_tokens (int): Nombre de jetons générés en sortie.
    """
    cost = 0.0

    # On cherche la config du modèle pour obtenir les tarifs dynamiques
    config = LLMConfigModel.get_or_none(LLMConfigModel.model_id == model_id)
    if config:
        cost = (prompt_tokens / 1_000_000 * config.prompt_pricing) + (completion_tokens / 1_000_000 * config.completion_pricing)

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
