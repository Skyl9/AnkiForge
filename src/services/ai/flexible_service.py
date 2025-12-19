# src/services/ai/flexible_service.py
import os
from openai import OpenAI
from src.services.ai.base import LLMProvider

class OpenAICompatibleProvider(LLMProvider):
    """
    Implémentation générique pour toutes les API compatibles avec le standard OpenAI
    (Ollama, Groq, OpenRouter, LMStudio, etc.)
    """
    def __init__(self, base_url: str, model_name: str, api_key: str = "dummy_key"):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model_name = model_name

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        response_format = {"type": "json_object"}
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format=response_format,
                temperature=0.2
            )
            return response.choices[0].message.content
        except Exception as e:
            raise RuntimeError(f"Erreur API ({self.model_name}) : {str(e)}")


# =====================================================================
# IMPLÉMENTATIONS SPÉCIFIQUES (Celles que tu utiliseras dans main.py)
# =====================================================================

class OllamaProvider(OpenAICompatibleProvider):
    """Fournisseur d'IA locale 100% gratuit via Ollama."""
    def __init__(self, model_name: str = "llama3"):
        super().__init__(
            base_url="http://localhost:11434/v1",
            model_name=model_name,
            api_key="ollama" # Pas de clé requise en local
        )


class GroqProvider(OpenAICompatibleProvider):
    """Fournisseur Cloud ultra-rapide."""
    def __init__(self, api_key: str = None):
        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise ValueError("Clé API GROQ_API_KEY manquante.")
        super().__init__(
            base_url="https://api.groq.com/openai/v1",
            model_name="llama3-8b-8192",
            api_key=key
        )


class OpenRouterProvider(OpenAICompatibleProvider):
    """Fournisseur Cloud agnostique (Accès à Gemini Flash gratuitement)."""
    def __init__(self, api_key: str = None):
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("Clé API OPENROUTER_API_KEY manquante.")
        super().__init__(
            base_url="https://openrouter.ai/api/v1",
            model_name="google/gemini-2.5-flash:free",
            api_key=key
        )