# src/services/ai/utils.py
import json
import re


def parse_ai_json_response(response_text: str):
    """
    Nettoie et convertit la réponse de l'IA en objet Python (dict ou list).
    Gère les cas où l'IA met des ```json autour.
    """
    try:
        # 1. Nettoyage des balises Markdown code block
        cleaned_text = re.sub(r"```json\s*", "", response_text)
        cleaned_text = re.sub(r"```\s*$", "", cleaned_text)
        cleaned_text = cleaned_text.strip()

        # 2. Parsing
        return json.loads(cleaned_text)
    except json.JSONDecodeError:
        # Fallback : on retourne une structure d'erreur pour l'afficher dans l'UI
        print(f"Erreur de parsing JSON. Texte reçu : {response_text}")
        return []