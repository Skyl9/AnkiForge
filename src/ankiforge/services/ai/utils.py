import json
import re


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
            # 2. FALLBACK ULTIME : L'IA a oublié les backticks mais a mis du texte autour.
            # On cherche le plus grand bloc compris entre { } ou [ ]
            fallback_match = re.search(r"(\{.*\}|\[.*\])", response_text, re.DOTALL)
            if fallback_match:
                cleaned_text = fallback_match.group(1).strip()
            else:
                # Si vraiment on ne trouve rien, on tente le tout pour le tout
                cleaned_text = response_text.strip()
        cleaned_text = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', cleaned_text)
        return json.loads(cleaned_text)

    except json.JSONDecodeError as e:
        raise ValueError(f"L'IA a généré un format invalide. Impossible de lire le JSON.\nDétail: {e}")
