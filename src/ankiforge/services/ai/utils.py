import json
import re

def parse_ai_json_response(response_text: str):
    """
    Nettoie et convertit la réponse de l'IA en objet Python (dict ou list).
    Extrait intelligemment le bloc JSON même s'il y a du texte autour.
    """
    try:
        # On génère les 3 backticks dynamiquement en Python pour ne pas
        # faire planter les parseurs Markdown des interfaces web !
        backticks = "`" * 3
        pattern = backticks + r"(?:json)?(.*?)" + backticks

        match = re.search(pattern, response_text, re.DOTALL)

        if match:
            # S'il y a un bloc de code détecté, on ne garde que son contenu
            cleaned_text = match.group(1).strip()
        else:
            # Sinon, on suppose que l'IA a renvoyé du JSON brut
            cleaned_text = response_text.strip()

        return json.loads(cleaned_text)

    except json.JSONDecodeError:
        print(f"Erreur de parsing JSON. Texte reçu : {response_text}")
        return []