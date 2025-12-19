import os
from google import genai
from google.genai import types


class GeminiService:
    def __init__(self, api_key: str = None):
        # 1. Récupération de la clé API
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")

        if not self.api_key:
            raise ValueError("Clé API Gemini manquante. Veuillez définir GEMINI_API_KEY.")

        # 2. Initialisation du nouveau client officiel
        self.client = genai.Client(api_key=self.api_key)

        # On utilise le dernier modèle Flash
        self.model_name = 'gemini-2.5-flash'

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Envoie le texte à Gemini en forçant une réponse au format JSON avec le nouveau SDK."""

        # 3. La configuration (JSON forcé + Instructions système) se fait maintenant via GenerateContentConfig
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=0.2  # Température basse pour garantir le respect strict du JSON
        )

        # 4. On génère la réponse via le client
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=user_prompt,
            config=config
        )

        return response.text