import logging
import os
from typing import Any, cast

import openai
import requests
from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.base import LLMProvider, MockProvider
from ankiforge.services.ai.retry import is_retryable_status, with_retry
from ankiforge.services.ai.utils import get_human_readable_api_error, log_token_usage

logger = logging.getLogger(__name__)

_DEFAULT_OLLAMA_URL = "http://localhost:11434"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_DEFAULT_MAX_RETRIES = 2


def _ollama_base_url() -> str:
    """Retourne l'URL locale d'Ollama configurée (validée anti-SSRF, repli sur localhost)."""
    from ankiforge.services.ai.model_catalog import _is_loopback_url

    url = _DEFAULT_OLLAMA_URL
    try:
        from ankiforge.services.settings_service import SettingsService

        configured = str(SettingsService.get("ollama/url", _DEFAULT_OLLAMA_URL) or _DEFAULT_OLLAMA_URL).rstrip("/")
        if configured and _is_loopback_url(configured):
            url = configured
        elif configured:
            logger.warning("URL Ollama non locale refusée (anti-SSRF) : %s. Repli sur %s.", configured, _DEFAULT_OLLAMA_URL)
    except Exception as e:
        logger.debug("Lecture du réglage ollama/url impossible, repli sur %s : %s", _DEFAULT_OLLAMA_URL, e)
    return url


class OpenAICompatibleProvider(LLMProvider):
    """
    Service générique pour les APIs compatibles avec le standard OpenAI.

    Gère les appels vers Ollama, Groq, OpenRouter ou toute autre plateforme
    exposant un endpoint compatible ChatCompletion.
    """

    def __init__(
        self,
        base_url: str,
        model_name: str,
        api_key: str | None = "dummy_key",
        max_tokens: int = 16384,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = _DEFAULT_MAX_RETRIES,
    ):
        """
        Initialise le client OpenAI avec l'URL de base et le modèle cible.

        Args:
            base_url (str): URL de l'endpoint API.
            model_name (str): Nom du modèle à invoquer (ex: 'llama3').
            api_key (str | None): Clé API nécessaire. Par défaut "dummy_key".
            max_tokens (int): Nombre maximal de tokens de réponse.
            timeout (float): Délai maximal (secondes) par requête réseau.
            max_retries (int): Nombre de tentatives automatiques du SDK OpenAI.
        """
        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=max_retries)
        self.model_name = model_name
        self.max_tokens = max_tokens

    @property
    def provider_name(self) -> str:
        """Déduit le nom du fournisseur à partir de l'URL de base du client."""
        base = str(getattr(self.client, "base_url", "") or "")
        if "groq" in base:
            return "groq"
        if "openrouter" in base:
            return "openrouter"
        if "anthropic" in base:
            return "anthropic"
        if "localhost" in base or "127.0.0.1" in base:
            return "ollama"
        return "openai"

    def generate(
        self,
        system_prompt: str,
        user_prompt: str | list[dict[str, Any]],
        response_format: str = "json",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        Envoie une requête de génération à l'API.

        Args:
            system_prompt (str): Instructions système définissant le comportement de l'IA.
            user_prompt (str | list[dict[str, Any]]): Contenu de l'utilisateur (texte ou multimodal).
            response_format (str): Format de réponse attendu ("json" ou "text").
            max_tokens (int | None): Plafond optionnel de tokens à générer.
            temperature (float | None): Température de créativité (défaut 0.2).

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
            effective_max = max_tokens or self.max_tokens
            kwargs: dict[str, Any] = {
                "model": self.model_name,
                "messages": messages,
                "temperature": temperature if temperature is not None else 0.2,
            }

            if any(k in self.model_name.lower() for k in ("o1", "o3", "gpt-5")):
                kwargs["max_completion_tokens"] = effective_max
            else:
                kwargs["max_tokens"] = effective_max

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

                log_token_usage(self.provider_name, self.model_name, p_tokens, c_tokens)

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

    def __init__(self, model_name: str = "llama3", max_tokens: int = 16384):
        """
        Initialise le service Ollama sur l'URL locale configurée (repli localhost).

        Args:
            model_name (str): Nom du modèle local à utiliser.
            max_tokens (int): Nombre maximal de tokens de réponse.
        """
        super().__init__(base_url=f"{_ollama_base_url()}/v1", model_name=model_name, api_key="ollama", max_tokens=max_tokens)

    @staticmethod
    def get_available_models() -> list[str]:
        """
        Récupère dynamiquement la liste des modèles installés localement.

        Returns:
            list[str]: Liste des noms des modèles disponibles sur Ollama.
        """
        try:
            # Appel à l'API locale d'Ollama (timeout court pour ne pas bloquer l'UI si Ollama est éteint)
            response = requests.get(f"{_ollama_base_url()}/api/tags", timeout=2)
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

    def __init__(self, api_key: str | None = None, model_name: str = "llama3-8b-8192", max_tokens: int = 16384):
        """
        Initialise le client Groq.

        Args:
            api_key (str | None): Clé API Groq. Cherchée dans l'environnement par défaut.
            model_name (str): Modèle à utiliser sur Groq.
            max_tokens (int): Nombre maximal de tokens de réponse.

        Raises:
            ValueError: Si aucune clé API n'est fournie ou trouvée.
        """
        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise ValueError("Clé API GROQ_API_KEY manquante.")
        super().__init__(base_url="https://api.groq.com/openai/v1", model_name=model_name, api_key=key, max_tokens=max_tokens)


class OpenRouterProvider(OpenAICompatibleProvider):
    """
    Fournisseur d'accès multi-IA via la plateforme OpenRouter.
    """

    def __init__(self, api_key: str | None = None, model_name: str = "google/gemini-2.5-flash:free", max_tokens: int = 16384):
        """
        Initialise le client OpenRouter.

        Args:
            api_key (str | None): Clé API OpenRouter.
            model_name (str): Modèle cible disponible sur OpenRouter.
            max_tokens (int): Nombre maximal de tokens de réponse.

        Raises:
            ValueError: Si la clé API est absente.
        """
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("Clé API OPENROUTER_API_KEY manquante.")
        super().__init__(base_url="https://openrouter.ai/api/v1", model_name=model_name, api_key=key, max_tokens=max_tokens)


class AnthropicProvider(LLMProvider):
    """
    Fournisseur pour les modèles Anthropic (Claude 3.5, Claude 3.7 Sonnet avec Thinking Mode, etc.).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "claude-3-7-sonnet-20250219",
        thinking_budget: int = 0,
        max_tokens: int = 16384,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "dummy_key")
        self.model_name = model_name
        self.thinking_budget = thinking_budget
        self.max_tokens = max_tokens

    def generate(
        self,
        system_prompt: str,
        user_prompt: str | list[dict[str, Any]],
        response_format: str = "json",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
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

        effective_max = max_tokens or self.max_tokens
        payload: dict[str, Any] = {
            "model": self.model_name,
            "system": system_prompt,
            "messages": [{"role": "user", "content": anthropic_content}],
            "temperature": temperature if temperature is not None else 0.2,
        }

        # Support du Thinking Mode pour Claude 3.7
        if self.thinking_budget > 0:
            payload["thinking"] = {"type": "enabled", "budget_tokens": self.thinking_budget}
            effective_max = max(effective_max, self.thinking_budget + 4096)

        payload["max_tokens"] = effective_max

        def _post_message() -> requests.Response:
            resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=_DEFAULT_TIMEOUT_SECONDS)
            if is_retryable_status(resp.status_code):
                raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
            resp.raise_for_status()
            return resp

        def _should_retry(exc: BaseException) -> bool:
            if isinstance(exc, requests.Timeout | requests.ConnectionError):
                return True
            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                return is_retryable_status(exc.response.status_code)
            return False

        try:
            response = with_retry(
                _post_message,
                max_attempts=3,
                should_retry=_should_retry,
                description=f"Anthropic {self.model_name}",
            )
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
        self.current_config: LLMConfigModel | None = None
        self.current_model: str = ""
        self.reload_provider()

    @staticmethod
    def create_provider_from_config(config: LLMConfigModel) -> LLMProvider:
        """
        Crée un fournisseur d'IA à partir d'un objet de configuration en base de données.
        Injecte l'api_key et max_tokens. La clé est chargée depuis le trousseau OS
        (keyring) en priorité, puis depuis la BDD (stockage historique).
        """
        from ankiforge.utils.secret_store import load_llm_key

        key = str(config.api_key) if config.api_key else None
        if not key:
            key = load_llm_key(str(config.model_id), str(config.provider))
        return AIManager.create_provider(
            provider_name=str(config.provider),
            model_id=str(config.model_id),
            api_key=key,
            max_tokens=int(getattr(config, "max_tokens", 16384) or 16384),
        )

    @staticmethod
    def create_provider(
        provider_name: str,
        model_id: str,
        api_key: str | None = None,
        thinking_budget: int = 0,
        max_tokens: int = 16384,
    ) -> LLMProvider:
        """
        Instancie un fournisseur d'IA à partir de données brutes (Thread-safe).
        """
        p_name = provider_name.lower()
        key = api_key or ""
        if not key:
            try:
                from ankiforge.utils.secret_store import load_llm_key

                key = load_llm_key(model_id, p_name) or ""
            except Exception:
                pass

        if not key:
            try:
                from ankiforge.services.settings_service import SettingsService

                key = str(SettingsService.get(f"keys/{p_name}", ""))
            except Exception:
                pass

        try:
            if p_name == "ollama":
                return OllamaProvider(model_name=model_id, max_tokens=max_tokens)
            elif p_name == "gemini":
                if not key:
                    logger.warning("Clé API Gemini absente pour le modèle %s, repli sur MockProvider.", model_id)
                    return MockProvider()
                from ankiforge.services.ai.gemini_service import GeminiService

                return GeminiService(api_key=key, model_name=model_id, max_tokens=max_tokens)
            elif p_name == "groq":
                if not key and not os.environ.get("GROQ_API_KEY"):
                    logger.warning("Clé API Groq absente pour le modèle %s, repli sur MockProvider.", model_id)
                    return MockProvider()
                return GroqProvider(api_key=key, model_name=model_id, max_tokens=max_tokens)
            elif p_name == "openai":
                if not key and not os.environ.get("OPENAI_API_KEY"):
                    logger.warning("Clé API OpenAI absente pour le modèle %s, repli sur MockProvider.", model_id)
                    return MockProvider()
                return OpenAICompatibleProvider(
                    base_url="https://api.openai.com/v1",
                    model_name=model_id,
                    api_key=key,
                    max_tokens=max_tokens,
                )
            elif p_name == "anthropic":
                return AnthropicProvider(api_key=key, model_name=model_id, thinking_budget=thinking_budget, max_tokens=max_tokens)
        except Exception as err:
            logger.warning("Échec de création du provider %s (%s) : %s. Utilisation de MockProvider.", p_name, model_id, err)
            return MockProvider()

        return MockProvider()

    def reload_provider(self) -> None:
        """
        Recharge l'IA active depuis la base de données (sélectionne le modèle par défaut ou le premier par sort_order).
        """
        try:
            from ankiforge.database.models import LLMConfigModel
            from ankiforge.services.settings_service import SettingsService

            default_id = SettingsService.get("ai/default_model_id")
            config = None
            if default_id:
                try:
                    config = LLMConfigModel.get_or_none(LLMConfigModel.id == int(default_id))
                except (ValueError, TypeError):
                    config = LLMConfigModel.get_or_none(LLMConfigModel.model_id == str(default_id))

            if not config:
                config = LLMConfigModel.select().order_by(LLMConfigModel.sort_order.asc(), LLMConfigModel.id.asc()).first()

            if config:
                self.current_config = config
                self.current_model = str(config.model_id)
                self.provider = self.create_provider_from_config(config)
                logger.info("Fournisseur d'IA rechargé : %s (%s, max_tokens=%d)", config.provider, config.model_id, getattr(config, "max_tokens", 16384))
            else:
                self.current_config = None
                self.current_model = ""
                self.provider = MockProvider()
                logger.warning("Aucune configuration d'IA trouvée, utilisation du MockProvider.")
        except Exception as e:
            self.current_config = None
            self.current_model = ""
            self.provider = MockProvider()
            logger.error("Erreur lors du rechargement de l'IA, utilisation du MockProvider: %s", e)
