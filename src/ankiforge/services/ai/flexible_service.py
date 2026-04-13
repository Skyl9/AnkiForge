# src/services/ai/flexible_service.py
import logging
import os
from typing import cast, Any

import requests
from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

from ankiforge.services.ai.base import LLMProvider, MockProvider
from ankiforge.services.ai.gemini_service import GeminiService
from ankiforge.services.ai.utils import log_token_usage
from ankiforge.utils.paths import get_app_data_dir

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    """
    Implémentation générique pour toutes les API compatibles avec le standard OpenAI
    (Ollama, Groq, OpenRouter, LMStudio, etc.)
    """

    def __init__(self, base_url: str, model_name: str, api_key: str | None = "dummy_key"):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model_name = model_name

    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
        messages = [
            ChatCompletionSystemMessageParam(role="system", content=system_prompt),
            ChatCompletionUserMessageParam(role="user", content=user_prompt),
        ]
        try:
            kwargs = {
                "model": self.model_name,
                "messages": messages,
                "temperature": 0.2,
            }

            # 👇 C'est ici que l'on connecte votre interface au backend !
            if response_format == "json":
                kwargs["response_format"] = {"type": "json_object"}

            response = cast(
                ChatCompletion,
                self.client.chat.completions.create(**kwargs),
            )
            if hasattr(response, "usage") and response.usage:
                p_tokens = response.usage.prompt_tokens or 0
                c_tokens = response.usage.completion_tokens or 0

                # Petite astuce pour retrouver le nom du provider
                provider_name = "openai"
                if "groq" in str(self.client.base_url):
                    provider_name = "groq"
                elif "localhost" in str(self.client.base_url):
                    provider_name = "ollama"

                log_token_usage(provider_name, self.model_name, p_tokens, c_tokens)

            content = response.choices[0].message.content or ""
            return content
        except Exception as e:
            logger.exception(f"Erreur API ({self.model_name}) :")
            raise RuntimeError(f"Erreur API ({self.model_name}) : {str(e)}") from e


class OllamaProvider(OpenAICompatibleProvider):
    """Fournisseur d'IA locale 100% gratuit via Ollama."""

    def __init__(self, model_name: str = "llama3"):
        super().__init__(base_url="http://localhost:11434/v1", model_name=model_name, api_key="ollama")

    @staticmethod
    def get_available_models() -> list[str]:
        """Récupère dynamiquement la liste des modèles locaux installés sur Ollama."""
        try:
            # Appel à l'API locale d'Ollama (timeout court pour ne pas bloquer l'UI si Ollama est éteint)
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            if response.status_code == 200:
                data = response.json()
                return [model.get("name") for model in data.get("models", [])]
            return []
        except requests.RequestException:
            return []


class GroqProvider(OpenAICompatibleProvider):
    """Fournisseur Cloud ultra-rapide."""

    def __init__(self, api_key: str | None = None, model_name: str = "llama3-8b-8192"):
        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise ValueError("Clé API GROQ_API_KEY manquante.")
        super().__init__(base_url="https://api.groq.com/openai/v1", model_name=model_name, api_key=key)


class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str | None = None, model_name: str = "google/gemini-2.5-flash:free"):
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("Clé API OPENROUTER_API_KEY manquante.")
        super().__init__(base_url="https://openrouter.ai/api/v1", model_name=model_name, api_key=key)


class AIManager:
    """Gestionnaire dynamique qui charge la bonne IA selon le fichier .env."""

    def __init__(self):
        self.env_path = get_app_data_dir() / ".env"  # Créer le fichier .env s'il n'existe pas
        if not self.env_path.exists():
            self.env_path.write_text("AI_PROVIDER=Ollama\nAI_MODEL=llama3\n", encoding="utf-8")

        load_dotenv(str(self.env_path))
        self.provider: LLMProvider = MockProvider()  # Fallback de sécurité
        self.reload_provider()

    def reload_provider(self):
        """Recharge l'IA en fonction des paramètres actuels du .env."""
        load_dotenv(str(self.env_path), override=True)  # Force le rafraichissement

        provider_name = os.getenv("AI_PROVIDER", "Ollama")
        model_name = os.getenv("AI_MODEL", "qwen2.5:7b")

        try:
            if provider_name == "Ollama":
                self.provider = OllamaProvider(model_name=model_name)
            elif provider_name == "Gemini":
                self.provider = GeminiService(model_name=model_name)
            elif provider_name == "Groq":
                self.provider = GroqProvider(api_key=os.getenv("GROQ_API_KEY", ""), model_name=model_name)
            else:
                self.provider = MockProvider()
            logger.info(f"✅ IA connectée : {provider_name} ({model_name})")
        except Exception:
            logger.exception("⚠️ Erreur IA, passage en mode Mock :")
            self.provider = MockProvider()
