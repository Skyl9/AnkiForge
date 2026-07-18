# src/services/ai/base.py
from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """
    Interface abstraite définissant le contrat pour tous les fournisseurs d'IA.

    Cette classe doit être héritée par chaque service d'IA (OpenAI, Gemini, Ollama, etc.)
    pour garantir une interface cohérente à travers l'application ankiforge_obsidian.
    """

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
        """
        Génère une réponse à partir d'un prompt système et d'un prompt utilisateur.

        Args:
            system_prompt (str): Instructions de base pour l'IA (le "rôle").
            user_prompt (str | list[dict[str, Any]]): Le message de l'utilisateur ou un payload multimodal.
            response_format (str): Le format attendu ("json" ou "text"). Par défaut "json".

        Returns:
            str: La réponse brute générée par l'IA.

        Raises:
            RuntimeError: Si l'appel à l'API échoue.
        """
        pass


class MockProvider(LLMProvider):
    """
    Implémentation de test (Mock) pour simuler une IA sans appel réseau.

    Utilisée pour le développement, les tests unitaires ou comme solution de repli
    en cas de panne des services cloud.
    """

    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
        """
        Simule une réponse JSON ou textuelle immédiate.

        Args:
            system_prompt (str): Instructions ignorées par le mock.
            user_prompt (str | list[dict[str, Any]]): Message ignoré par le mock.
            response_format (str): Définit si le mock renvoie du JSON simulé ou du texte.

        Returns:
            str: Une réponse factice prédéfinie.
        """
        if response_format == "text":
            return "Ceci est une réponse simulée en texte libre."
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
