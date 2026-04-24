import logging
import os
from typing import cast, Any

import openai
import requests
from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.base import LLMProvider, MockProvider
from ankiforge.services.ai.gemini_service import GeminiService
from ankiforge.services.ai.utils import log_token_usage, get_human_readable_api_error

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    """
    Service générique pour les APIs compatibles avec le standard OpenAI.

    Gère les appels vers Ollama, Groq, OpenRouter ou toute autre plateforme
    exposant un endpoint compatible ChatCompletion.
    """

    def __init__(self, base_url: str, model_name: str, api_key: str | None = "dummy_key"):
        """
        Initialise le client OpenAI avec l'URL de base et le modèle cible.

        Args:
            base_url (str): URL de l'endpoint API.
            model_name (str): Nom du modèle à invoquer (ex: 'llama3').
            api_key (str | None): Clé API nécessaire. Par défaut "dummy_key".
        """
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model_name = model_name

    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
        """
        Envoie une requête de génération à l'API.

        Args:
            system_prompt (str): Instructions système définissant le comportement de l'IA.
            user_prompt (str | list[dict[str, Any]]): Contenu de l'utilisateur (texte ou multimodal).
            response_format (str): Format de réponse attendu ("json" ou "text").

        Returns:
            str: Le texte généré par l'IA.

        Raises:
            RuntimeError: En cas d'échec de la communication avec l'API.
        """
        messages = [
            ChatCompletionSystemMessageParam(role="system", content=system_prompt),
            ChatCompletionUserMessageParam(role="user", content=cast(Any, user_prompt)),
        ]
        try:
            kwargs: dict[str, Any] = {
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
        except (openai.APIError, openai.APIConnectionError) as e:
            logger.exception(f"Erreur API ({self.model_name}) :")
            human_msg = get_human_readable_api_error(e)
            raise RuntimeError(f"Erreur API ({self.model_name}) : {human_msg}") from e


class OllamaProvider(OpenAICompatibleProvider):
    """
    Fournisseur d'IA locale 100% gratuit utilisant Ollama.
    """

    def __init__(self, model_name: str = "llama3"):
        """
        Initialise le service Ollama sur l'URL locale par défaut.

        Args:
            model_name (str): Nom du modèle local à utiliser.
        """
        super().__init__(base_url="http://localhost:11434/v1", model_name=model_name, api_key="ollama")

    @staticmethod
    def get_available_models() -> list[str]:
        """
        Récupère dynamiquement la liste des modèles installés localement.

        Returns:
            list[str]: Liste des noms des modèles disponibles sur Ollama.
        """
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
    """
    Fournisseur Cloud haute performance utilisant l'infrastructure Groq.
    """

    def __init__(self, api_key: str | None = None, model_name: str = "llama3-8b-8192"):
        """
        Initialise le client Groq.

        Args:
            api_key (str | None): Clé API Groq. Cherchée dans l'environnement par défaut.
            model_name (str): Modèle à utiliser sur Groq.

        Raises:
            ValueError: Si aucune clé API n'est fournie ou trouvée.
        """
        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise ValueError("Clé API GROQ_API_KEY manquante.")
        super().__init__(base_url="https://api.groq.com/openai/v1", model_name=model_name, api_key=key)


class OpenRouterProvider(OpenAICompatibleProvider):
    """
    Fournisseur d'accès multi-IA via la plateforme OpenRouter.
    """

    def __init__(self, api_key: str | None = None, model_name: str = "google/gemini-2.5-flash:free"):
        """
        Initialise le client OpenRouter.

        Args:
            api_key (str | None): Clé API OpenRouter.
            model_name (str): Modèle cible disponible sur OpenRouter.

        Raises:
            ValueError: Si la clé API est absente.
        """
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("Clé API OPENROUTER_API_KEY manquante.")
        super().__init__(base_url="https://openrouter.ai/api/v1", model_name=model_name, api_key=key)


class AIManager:
    """
    Orchestrateur central gérant le chargement et la configuration de l'IA active.
    Récupère les paramètres depuis la base de données SQLite.
    """

    def __init__(self):
        """
        Initialise le gestionnaire.
        """
        self.provider: LLMProvider = MockProvider()  # Fallback de sécurité
        self.reload_provider()

    @staticmethod
    def create_provider_from_config(config: LLMConfigModel) -> LLMProvider:
        """
        Crée un fournisseur d'IA à partir d'un objet de configuration en base de données.
        Injecte l'api_key stockée en BDD.
        """
        return AIManager.create_provider(provider_name=str(config.provider), model_id=str(config.model_id), api_key=str(config.api_key) if config.api_key else None)

    @staticmethod
    def create_provider(provider_name: str, model_id: str, api_key: str | None = None) -> LLMProvider:
        """
        Instancie un fournisseur d'IA à partir de données brutes (Thread-safe).
        """
        p_name = provider_name.lower()
        key = api_key or ""

        if p_name == "ollama":
            return OllamaProvider(model_name=model_id)
        elif p_name == "gemini":
            return GeminiService(api_key=key, model_name=model_id)
        elif p_name == "groq":
            return GroqProvider(api_key=key, model_name=model_id)
        elif p_name == "openai":
            return OpenAICompatibleProvider(
                base_url="https://api.openai.com/v1",
                model_name=model_id,
                api_key=key,
            )
        return MockProvider()

    def reload_provider(self):
        """
        Recharge l'IA active. (Logique simplifiée : elle sera pilotée par les vues via create_provider_from_config)
        """
        logger.info("Gestionnaire d'IA prêt.")
