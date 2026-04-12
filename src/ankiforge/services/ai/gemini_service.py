import base64
import logging
import os

from google import genai
from google.genai import types
from mypy.types import Any

from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.ai.utils import log_token_usage

logger = logging.getLogger(__name__)


class GeminiService(LLMProvider):
    def __init__(self, api_key: str | None = None, model_name: str = "gemini-2.0-flash"):
        """
        Initialise le client Gemini avec la clé API Studio.
        """
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model_name = model_name

        if not self.api_key:
            raise ValueError("Clé API Gemini manquante. Veuillez définir GEMINI_API_KEY dans le .env")

        # Connexion directe à l'API Google AI Studio
        self.client = genai.Client(api_key=self.api_key)

    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]]) -> str:
        """
        Génère une réponse JSON structurée.
        """
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",  # Force le JSON valide
            temperature=0.2,
        )

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
        except Exception as e:
            logger.exception(f"Erreur Gemini ({self.model_name}) :")
            raise RuntimeError(f"Erreur Gemini ({self.model_name}) : {str(e)}") from e
