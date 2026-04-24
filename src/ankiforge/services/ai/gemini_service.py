import base64
import logging

from google import genai
from google.genai import types
from typing import Any

from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.ai.utils import log_token_usage, get_human_readable_api_error

logger = logging.getLogger(__name__)


class GeminiService(LLMProvider):
    """
    Service d'intégration pour l'API Google Gemini.

    Gère l'authentification et la communication avec les modèles Gemini via le SDK officiel
    de Google. Supporte les fonctionnalités multimodales (vision).
    """

    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash"):
        """
        Initialise le client Gemini.

        Args:
            api_key (str): Clé API Google AI Studio.
            model_name (str): Nom du modèle Gemini à utiliser.

        Raises:
            ValueError: Si aucune clé API n'est disponible.
        """
        self.api_key = api_key
        self.model_name = model_name

        if not self.api_key:
            raise ValueError("Clé API Gemini manquante. Veuillez la configurer dans les paramètres.")

        # Connexion directe à l'API Google AI Studio
        self.client = genai.Client(api_key=self.api_key)

    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
        """
        Génère une réponse textuelle ou JSON structurée via Gemini.

        Args:
            system_prompt (str): Instructions système (system_instruction).
            user_prompt (str | list[dict[str, Any]]): Prompt utilisateur ou contenu multimodal.
            response_format (str): Format de réponse ("json" ou "text").

        Returns:
            str: Le contenu textuel de la réponse générée.

        Raises:
            RuntimeError: En cas d'erreur lors de l'appel à l'API Gemini.
        """

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.2,
        )

        if response_format == "json":
            config.response_mime_type = "application/json"

        try:
            # --- ADAPTATION POUR LA VISION ---
            contents_to_send = []

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
            response = self.client.models.generate_content(model=self.model_name, contents=contents_to_send, config=config)

            if hasattr(response, "usage_metadata") and response.usage_metadata:
                p_tokens = response.usage_metadata.prompt_token_count or 0
                c_tokens = response.usage_metadata.candidates_token_count or 0
                log_token_usage("gemini", self.model_name, p_tokens, c_tokens)

            return response.text or ""
        except genai.errors.APIError as e:
            logger.exception(f"Erreur API Gemini brute ({self.model_name}) :")
            human_msg = get_human_readable_api_error(e)
            raise RuntimeError(f"Erreur API Gemini ({self.model_name}) : {human_msg}") from e
