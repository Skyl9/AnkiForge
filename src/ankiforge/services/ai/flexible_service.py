import logging
import os
from typing import cast, Any

import openai
import requests
from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.base import LLMProvider, MockProvider
from ankiforge.services.ai.gemini_service import GeminiService
from ankiforge.services.ai.utils import log_token_usage
from ankiforge.utils.paths import get_app_data_dir

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
        except (openai.APIError, openai.APIConnectionError) as e:
            logger.exception(f"Erreur API ({self.model_name}) :")
            raise RuntimeError(f"Erreur API ({self.model_name}) : {str(e)}") from e


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

    S'occupe de la lecture des paramètres utilisateurs (.env) et de l'instanciation
    dynamique du fournisseur d'IA approprié.
    """

    def __init__(self):
        """
        Initialise le gestionnaire et charge le fournisseur configuré par défaut.
        """
        self.env_path = get_app_data_dir() / ".env"  # Créer le fichier .env s'il n'existe pas
        if not self.env_path.exists():
            self.env_path.write_text("AI_PROVIDER=Ollama\nAI_MODEL=llama3\n", encoding="utf-8")

        load_dotenv(str(self.env_path))
        self.provider: LLMProvider = MockProvider()  # Fallback de sécurité
        self.reload_provider()

    @staticmethod
    def create_provider_from_config(config: LLMConfigModel) -> LLMProvider:
        """
        Crée un fournisseur d'IA à partir d'un objet de configuration en base de données.

        Args:
            config (LLMConfigModel): Configuration stockée en BDD.

        Returns:
            LLMProvider: Instance prête à l'emploi du service d'IA.
        """
        p_name = config.provider.lower()
        if p_name == "ollama":
            return OllamaProvider(model_name=config.model_id)
        elif p_name == "gemini":
            return GeminiService(model_name=config.model_id)
        elif p_name == "groq":
            return GroqProvider(model_name=config.model_id)
        elif p_name == "openai":
            return OpenAICompatibleProvider(
                base_url="https://api.openai.com/v1",
                model_name=config.model_id,
                api_key=os.environ.get("OPENAI_API_KEY", ""),
            )
        return MockProvider()

    def reload_provider(self):
        """
        Recharge l'IA active en fonction des variables d'environnement actuelles.
        """
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
