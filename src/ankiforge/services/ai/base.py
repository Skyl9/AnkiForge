# src/services/ai/base.py
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """
    Classe abstraite définissant le contrat que tous les fournisseurs d'IA
    (OpenAI, Groq, Ollama, Gemini...) doivent respecter.
    """

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """
        Doit retourner une chaîne de caractères (idéalement formatée en JSON).
        """
        pass


# --- Implémentation Mock (pour tester sans payer l'API ou sans connexion) ---
class MockProvider(LLMProvider):
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Simule une réponse JSON parfaite pour ne pas faire planter l'interface."""
        return """
        {
            "notes": [
                {
                    "Front": "Question simulée par le MockProvider ?",
                    "Back": "Réponse simulée car l'IA n'est pas connectée."
                }
            ]
        }
        """