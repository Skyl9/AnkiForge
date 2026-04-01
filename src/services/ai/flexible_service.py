# src/services/ai/flexible_service.py
import os

from dotenv import load_dotenv
from openai import OpenAI
from src.services.ai.base import LLMProvider, MockProvider
from src.services.ai.gemini_service import GeminiService


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

    @staticmethod
    def get_available_models() -> list[str]:
        """Récupère dynamiquement la liste des modèles locaux installés sur Ollama."""
        import requests
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


class AIManager:
    """Gestionnaire dynamique qui charge la bonne IA selon le fichier .env."""

    def __init__(self):
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.env_path = os.path.join(BASE_DIR, ".env")
        # Créer le fichier .env s'il n'existe pas
        if not os.path.exists(self.env_path):
            with open(self.env_path, 'w') as f:
                f.write("AI_PROVIDER=Ollama\nAI_MODEL=mistral-nemo\n")

        load_dotenv(self.env_path)
        self.provider = MockProvider()  # Fallback de sécurité
        self.reload_provider()

    def reload_provider(self):
        """Recharge l'IA en fonction des paramètres actuels du .env."""
        load_dotenv(self.env_path, override=True)  # Force le rafraichissement

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
            print(f"✅ IA connectée : {provider_name} ({model_name})")
        except Exception as e:
            print(f"⚠️ Erreur IA, passage en mode Mock : {e}")
            self.provider = MockProvider()