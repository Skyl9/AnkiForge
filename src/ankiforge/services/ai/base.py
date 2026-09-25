import inspect
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResult:
    """Résultat structuré d'un appel LLM incluant le contenu cible et le raisonnement (CoT)."""

    content: str
    thought: str | None = None
    raw_response: Any = None


class LLMProvider:
    """
    Classe de base définissant le contrat pour tous les fournisseurs d'IA.

    Permet à chaque implémentation de fournir soit ``generate_response`` (avec support
    de la chaîne de pensée / CoT), soit ``generate`` (texte brut rétrocompatible).
    """

    def generate_response(
        self,
        system_prompt: str,
        user_prompt: str | list[dict[str, Any]],
        response_format: str = "json",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResult:
        """
        Génère une réponse complète incluant la chaîne de pensée (thought/CoT) si disponible.
        """
        if type(self).generate is LLMProvider.generate:
            raise NotImplementedError(f"{type(self).__name__} doit implémenter soit generate_response soit generate")

        kwargs: dict[str, Any] = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response_format": response_format,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            kwargs["temperature"] = temperature
        try:
            sig = inspect.signature(self.generate)
            params = sig.parameters
            has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
            if not has_var_kw:
                kwargs = {k: v for k, v in kwargs.items() if k in params}
        except (ValueError, TypeError):
            pass

        content = self.generate(**kwargs)
        return LLMResult(content=content)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str | list[dict[str, Any]],
        response_format: str = "json",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        Génère une réponse textuelle brute (délègue par défaut vers generate_response).

        Args:
            system_prompt (str): Instructions de base pour l'IA (le "rôle").
            user_prompt (str | list[dict[str, Any]]): Le message de l'utilisateur ou un payload multimodal.
            response_format (str): Le format attendu ("json" ou "text"). Par défaut "json".
            max_tokens (int | None): Plafond maximal de tokens à générer (optionnel).
            temperature (float | None): Température de créativité (optionnel, fournisseur défaut sinon).

        Returns:
            str: La réponse brute générée par l'IA.

        Raises:
            RuntimeError: Si l'appel à l'API échoue.
        """
        return self.generate_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
            max_tokens=max_tokens,
            temperature=temperature,
        ).content


class MockProvider(LLMProvider):
    """
    Implémentation de test (Mock) pour simuler une IA sans appel réseau.

    Utilisée pour le développement, les tests unitaires ou comme solution de repli
    en cas de panne des services cloud.
    """

    def generate(
        self,
        system_prompt: str,
        user_prompt: str | list[dict[str, Any]],
        response_format: str = "json",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        Simule une réponse JSON ou textuelle immédiate.

        Args:
            system_prompt (str): Instructions ignorées par le mock.
            user_prompt (str | list[dict[str, Any]]): Message ignoré par le mock.
            response_format (str): Définit si le mock renvoie du JSON simulé ou du texte.
            max_tokens (int | None): Limite de tokens (ignorée par le mock).
            temperature (float | None): Température (ignorée par le mock).

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
