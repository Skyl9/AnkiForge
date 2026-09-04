import logging
import os
from typing import Any, cast

import openai
import requests
from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.base import LLMProvider, MockProvider
from ankiforge.services.ai.gemini_service import GeminiService
from ankiforge.services.ai.utils import get_human_readable_api_error, log_token_usage

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
            logger.exception("Erreur API (%s) : %s", self.model_name, e)
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


class AnthropicProvider(LLMProvider):
    """
    Fournisseur pour les modèles Anthropic (Claude 3.5, Claude 3.7 Sonnet avec Thinking Mode, etc.).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "claude-3-7-sonnet-20250219",
        thinking_budget: int = 0,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "dummy_key")
        self.model_name = model_name
        self.thinking_budget = thinking_budget

    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        # Conversion du prompt utilisateur au format Anthropic (compatible OpenAI multimodal)
        anthropic_content: list[dict[str, Any]] = []
        if isinstance(user_prompt, str):
            anthropic_content = [{"type": "text", "text": user_prompt}]
        else:
            for item in user_prompt:
                if item.get("type") == "text":
                    anthropic_content.append({"type": "text", "text": item.get("text", "")})
                elif item.get("type") == "image_url":
                    url = item.get("image_url", {}).get("url", "")
                    if "base64," in url:
                        parts = url.split("base64,")
                        b64_data = parts[1]
                        mime_type = parts[0].split(";")[0].replace("data:", "") or "image/png"
                    else:
                        b64_data = url
                        mime_type = "image/png"

                    anthropic_content.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": b64_data,
                            },
                        }
                    )

        max_tokens = 4096
        payload: dict[str, Any] = {
            "model": self.model_name,
            "system": system_prompt,
            "messages": [{"role": "user", "content": anthropic_content}],
        }

        # Support du Thinking Mode pour Claude 3.7
        if self.thinking_budget > 0:
            payload["thinking"] = {"type": "enabled", "budget_tokens": self.thinking_budget}
            max_tokens = max(max_tokens, self.thinking_budget + 2048)

        payload["max_tokens"] = max_tokens

        try:
            response = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()

            # Enregistrement des tokens consommés
            if "usage" in data:
                usage = data["usage"]
                log_token_usage("anthropic", self.model_name, usage.get("input_tokens", 0), usage.get("output_tokens", 0))

            # Extraction du bloc de réponse textuelle (en ignorant les blocs de réflexion "thinking")
            content_blocks = data.get("content", [])
            for block in content_blocks:
                if block.get("type") == "text":
                    return str(block.get("text", ""))

            if content_blocks and "text" in content_blocks[0]:
                return str(content_blocks[0]["text"])

            return ""
        except requests.RequestException as e:
            logger.exception("Erreur API Anthropic (%s) : %s", self.model_name, e)
            raise RuntimeError(f"Erreur API Anthropic ({self.model_name}) : {e}") from e


class AIManager:
    """
    Orchestrateur central gérant le chargement et la configuration de l'IA active.
    Récupère les paramètres depuis la base de données SQLite.
    """

    def __init__(self) -> None:
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
    def create_provider(
        provider_name: str,
        model_id: str,
        api_key: str | None = None,
        thinking_budget: int = 0,
    ) -> LLMProvider:
        """
        Instancie un fournisseur d'IA à partir de données brutes (Thread-safe).
        """
        p_name = provider_name.lower()
        key = api_key or ""
        if not key:
            try:
                from ankiforge.services.settings_service import SettingsService

                key = str(SettingsService.get(f"keys/{p_name}", ""))
            except Exception:
                pass  # nosec B110

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
        elif p_name == "anthropic":
            return AnthropicProvider(api_key=key, model_name=model_id, thinking_budget=thinking_budget)
        return MockProvider()

    def reload_provider(self) -> None:
        """
        Recharge l'IA active depuis la base de données.
        """
        try:
            from ankiforge.database.models import LLMConfigModel

            config = LLMConfigModel.select().first()
            if config:
                self.provider = self.create_provider_from_config(config)
                logger.info("Fournisseur d'IA rechargé : %s (%s)", config.provider, config.model_id)
            else:
                self.provider = MockProvider()
                logger.warning("Aucune configuration d'IA trouvée, utilisation du MockProvider.")
        except Exception as e:
            self.provider = MockProvider()
            logger.error("Erreur lors du rechargement de l'IA, utilisation du MockProvider: %s", e)
