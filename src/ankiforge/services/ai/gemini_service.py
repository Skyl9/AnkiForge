import base64
import logging
from typing import Any

from google import genai
from google.genai import types

from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.ai.retry import RETRYABLE_STATUS_CODES, with_retry
from ankiforge.services.ai.utils import get_human_readable_api_error, log_token_usage
from ankiforge.utils.ssl_certificates import setup_ssl_certificates

logger = logging.getLogger(__name__)


def _is_retryable_gemini_error(exc: BaseException) -> bool:
    """Détecte les erreurs Gemini transitoires (quota/surcharge/timeout réseau)."""
    if isinstance(exc, ConnectionError | TimeoutError):
        return True
    if not isinstance(exc, genai.errors.APIError):
        return False
    code = getattr(exc, "code", None)
    if isinstance(code, int) and code in RETRYABLE_STATUS_CODES:
        return True
    text = str(exc).lower()
    return any(token in text for token in ("429", "500", "502", "503", "504", "timeout", "unavailable", "overloaded"))


class GeminiService(LLMProvider):
    """
    Service d'intégration pour l'API Google Gemini.

    Gère l'authentification et la communication avec les modèles Gemini via le SDK officiel
    de Google. Supporte les fonctionnalités multimodales (vision).
    """

    def __init__(self, api_key: str, model_name: str = "gemini-3.5-flash-lite", max_tokens: int = 65536, timeout: float = 60000.0):
        """
        Initialise le client Gemini.

        Args:
            api_key (str): Clé API Google AI Studio.
            model_name (str): Nom du modèle Gemini à utiliser.
            max_tokens (int): Nombre maximal de tokens de sortie.
            timeout (float): Délai maximal (secondes) par requête réseau.

        Raises:
            ValueError: Si aucune clé API n'est disponible.
        """
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.timeout = timeout

        if not self.api_key:
            raise ValueError("Clé API Gemini manquante. Veuillez la configurer dans les paramètres.")

        # Garantir un environnement de certificats SSL valide avant d'instancier genai.Client
        setup_ssl_certificates()

        # Connexion directe à l'API Google AI Studio (timeout converti en millisecondes pour le SDK)
        http_options: types.HttpOptionsDict = {}
        if timeout > 0:
            http_options["timeout"] = int(timeout * 1000)
        self.client = genai.Client(api_key=self.api_key, http_options=http_options)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str | list[dict[str, Any]],
        response_format: str = "json",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        Génère une réponse textuelle ou JSON structurée via Gemini.

        Args:
            system_prompt (str): Instructions système (system_instruction).
            user_prompt (str | list[dict[str, Any]]): Prompt utilisateur ou contenu multimodal.
            response_format (str): Format de réponse ("json" ou "text").
            max_tokens (int | None): Plafond optionnel de tokens à générer.
            temperature (float | None): Température de créativité (défaut 0.2).

        Returns:
            str: Le contenu textuel de la réponse générée.

        Raises:
            RuntimeError: En cas d'erreur lors de l'appel à l'API Gemini.
        """
        effective_max = max_tokens or self.max_tokens
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature if temperature is not None else 0.2,
            max_output_tokens=effective_max,
        )

        if response_format == "json":
            config.response_mime_type = "application/json"

        try:
            # --- ADAPTATION POUR LA VISION ---
            contents_to_send: list[Any] = []

            if isinstance(user_prompt, str):
                contents_to_send = [user_prompt]
            else:
                # C'est un payload multimodal (OpenAI style), on le traduit pour Gemini
                for item in user_prompt:
                    if item["type"] == "text":
                        contents_to_send.append(item["text"])
                    elif item["type"] == "image_url":
                        # Gemini SDK attend un objet Part pour les images
                        b64_data = item["image_url"]["url"].split("base64,")[1]
                        mime_type = item["image_url"]["url"].split(";")[0].split(":")[1]

                        contents_to_send.append(
                            types.Part.from_bytes(
                                data=base64.b64decode(b64_data),
                                mime_type=mime_type,
                            )
                        )
            # ---------------------------------

            # On envoie la liste transformée
            response = with_retry(
                lambda: self.client.models.generate_content(model=self.model_name, contents=contents_to_send, config=config),
                max_attempts=3,
                should_retry=_is_retryable_gemini_error,
                description=f"Gemini {self.model_name}",
            )

            if hasattr(response, "usage_metadata") and response.usage_metadata:
                p_tokens = response.usage_metadata.prompt_token_count or 0
                c_tokens = response.usage_metadata.candidates_token_count or 0
                log_token_usage("gemini", self.model_name, p_tokens, c_tokens)

            return response.text or ""
        except genai.errors.APIError as e:
            logger.exception("Erreur API Gemini brute (%s) : %s", self.model_name, e)
            human_msg = get_human_readable_api_error(e)
            raise RuntimeError(f"Erreur API Gemini ({self.model_name}) : {human_msg}") from e
