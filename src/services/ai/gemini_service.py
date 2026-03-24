import os
from google import genai
from google.genai import types
from src.services.ai.base import LLMProvider  # <-- AJOUT

class GeminiService(LLMProvider):  # <-- HÉRITAGE AJOUTÉ
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")

        if not self.api_key:
            raise ValueError("Clé API Gemini manquante. Veuillez définir GEMINI_API_KEY.")

        self.client = genai.Client(api_key=self.api_key)
        self.model_name = 'gemini-2.5-flash'

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=0.2
        )

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=user_prompt,
            config=config
        )

        return response.text