import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, cast

import openai
import requests
from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.base import LLMProvider, LLMResult, MockProvider
from ankiforge.services.ai.retry import is_retryable_status, with_retry
from ankiforge.services.ai.utils import get_human_readable_api_error, log_token_usage

logger = logging.getLogger(__name__)

_DEFAULT_OLLAMA_URL = "http://localhost:11434"
# Délai (en secondes) au-delà duquel une génération IA stagnante est abandonnée en échec d'étape.
# Détail : 60000 s (16,6 h) gelait la génération quasi indéfiniment quand un fournisseur restait muet
# (modèles gratuits lents/afflués) — symptôme « UI bloquée, j'ai quitté ». Toujours borné par
# _MIN/_MAX_GENERATION_TIMEOUT_SECONDS, jamais désactivable.
_DEFAULT_TIMEOUT_SECONDS = 600.0
_MIN_GENERATION_TIMEOUT_SECONDS = 30.0
_MAX_GENERATION_TIMEOUT_SECONDS = 3600.0
_DEFAULT_MAX_RETRIES = 2

# En-têtes recommandés par OpenRouter pour le tracking du trafic (référence à l'application).
_OPENROUTER_DEFAULT_HEADERS: dict[str, str] = {
    "HTTP-Referer": "https://github.com/Skyl9/AnkiForge",
    "X-Title": "AnkiForge",
}


class TruncatedOutputError(RuntimeError):
    """Réponse du modèle coupée au plafond de tokens (``finish_reason='length'``) avec contenu non vide.

    Contrairement à la réponse vide, la sortie est partiellement exploitable mais inachevée :
    le JSON est généralement tronqué en pleine chaîne, rendant la sortie inutilisable telle quelle.
    """


class ContentFilteredError(RuntimeError):
    """Réponse tronquée par le filtre de sécurité du fournisseur (``finish_reason='content_filter'``)."""


# Garde-fou : on ne laisse JAMAIS une tentative de rattrapage de troncature exploser le budget de sortie.
_MAX_TRUNCATION_RETRY_TOKENS = 1_048_576


@dataclass(frozen=True)
class _OpenRouterModelInfo:
    """Capacités réelles d'un modèle OpenRouter issues de l'endpoint /models."""

    supports_response_format: bool
    supports_structured_outputs: bool
    max_output_tokens: int | None
    context_length: int | None


_OPENROUTER_META_TTL_SECONDS = 6 * 3600
_openrouter_meta_cache: dict[str, tuple[_OpenRouterModelInfo, float]] = {}
_openrouter_meta_lock = threading.Lock()

_REASONING_MAX_COMPLETION_FAMILIES: tuple[str, ...] = (
    "o1",
    "o1-mini",
    "o1-preview",
    "o3",
    "o3-mini",
    "o4",
    "o4-mini",
    "gpt-5",
    "gpt-5-mini",
)


def _uses_reasoning_params(model_name: str) -> bool:
    """Détecte les familles OpenAI (o1/o3/o4/gpt-5) qui exigent ``max_completion_tokens``.

    Contrairement à un simple ``in``, la frontière alphanumérique évite les faux positifs
    sur des IDs OpenRouter dont le slug contient ``o1``/``o3`` sans être un modèle de raisonnement.
    """
    low = model_name.lower()
    return any(re.search(rf"(^|[^a-z0-9]){re.escape(family)}([^a-z0-9]|$)", low) for family in _REASONING_MAX_COMPLETION_FAMILIES)


def _openrouter_model_meta(base_url: str, model_name: str) -> _OpenRouterModelInfo | None:
    """Capacités réelles d'un modèle OpenRouter (GET /models), cache 6 h, best-effort.

    Le paramètre ``response_format`` est supporté par *certains* modèles/endpoints seulement :
    l'envoyer à un modèle qui ne le gère pas provoque des erreurs 400/404 ou un JSON non garanti.
    Le plafond réel de sortie est aussi bien plus bas que le ``max_tokens`` configuré pour les
    routes ``:free``.

    Returns:
        Infos de capacité, ou None si indisponible (réseau, JSON inattendu, environnement de test).
    """
    # Jamais de requête réseau pendant les tests (ANKIFORGE_ENV=testing, défini par conftest).
    if os.environ.get("ANKIFORGE_ENV") == "testing":
        return None
    key = f"{base_url.rstrip('/')}|{model_name.lower()}"
    now = time.monotonic()
    with _openrouter_meta_lock:
        cached = _openrouter_meta_cache.get(key)
        if cached and now - cached[1] < _OPENROUTER_META_TTL_SECONDS:
            return cached[0]
    try:
        resp = requests.get(f"{base_url.rstrip('/')}/models", timeout=2.0, headers=_OPENROUTER_DEFAULT_HEADERS)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return None
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return None
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("id") or "").lower() != model_name.lower():
            continue
        supported = entry.get("supported_parameters")
        s_params = {str(s).lower() for s in supported} if isinstance(supported, list) else set()
        max_out = entry.get("max_completion_tokens") or entry.get("max_tokens")
        if max_out is None:
            top = entry.get("top_provider")
            if isinstance(top, dict):
                max_out = top.get("max_completion_tokens") or top.get("max_tokens")
        info = _OpenRouterModelInfo(
            supports_response_format="response_format" in s_params,
            supports_structured_outputs="structured_outputs" in s_params,
            max_output_tokens=int(max_out) if isinstance(max_out, int) else None,
            context_length=int(entry["context_length"]) if isinstance(entry.get("context_length"), int) else None,
        )
        with _openrouter_meta_lock:
            _openrouter_meta_cache[key] = (info, now)
        return info
    return None


def _supports_response_format(provider_name: str, model_name: str, base_url: str) -> bool:
    """Décide si le mode ``json_object`` doit être envoyé (paramètre non universel).

    - Providers OpenAI-compatibles classiques : oui par défaut.
    - OpenRouter : via l'endpoint /models quand disponible, sinon repli sur le catalogue.
    """
    if provider_name != "openrouter":
        return True
    meta = _openrouter_model_meta(base_url, model_name)
    if meta is not None:
        return meta.supports_response_format or meta.supports_structured_outputs
    try:
        from ankiforge.services.ai.model_catalog import ModelCatalog

        return bool(ModelCatalog.get_model_spec("openrouter", model_name).supports_json)
    except Exception:
        return True


def _openrouter_max_output_tokens(base_url: str, model_name: str) -> int | None:
    """Plafond de sortie réel d'un modèle OpenRouter (None si inconnu)."""
    meta = _openrouter_model_meta(base_url, model_name)
    return meta.max_output_tokens if meta is not None else None


def _extract_reasoning_from_message(message: Any) -> str:
    """Extrait le contenu de raisonnement d'un message (OpenAI ``reasoning``, DeepSeek ``reasoning_content``…)."""
    for attr in ("reasoning", "reasoning_content", "thinking"):
        val = getattr(message, attr, None)
        if isinstance(val, str) and val.strip():
            return val
        if val and not hasattr(val, "_mock_return_value") and not str(type(val)).endswith("MagicMock'>"):
            text_val = str(val).strip()
            if text_val:
                return text_val
    extra = getattr(message, "model_extra", None)
    if isinstance(extra, dict):
        for key in ("reasoning", "reasoning_content", "thinking"):
            val = extra.get(key)
            if isinstance(val, str) and val.strip():
                return val
            if val and not hasattr(val, "_mock_return_value") and not str(type(val)).endswith("MagicMock'>"):
                text_val = str(val).strip()
                if text_val:
                    return text_val
    return ""


def _extract_reasoning_tokens(response: Any) -> tuple[int | None, int | None]:
    """Retourne (reasoning_tokens, completion_tokens) si le fournisseur les fournit."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None, None
    raw_completion = getattr(usage, "completion_tokens", 0)
    completion_tokens = int(raw_completion) if isinstance(raw_completion, int) else 0
    details = getattr(usage, "completion_tokens_details", None)
    reasoning_tokens = None
    if details is not None:
        raw = getattr(details, "reasoning_tokens", None)
        if isinstance(raw, int):
            reasoning_tokens = raw
    return (reasoning_tokens or None), (completion_tokens or None)


_THINK_TAG_REGEX = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)


def extract_thought_tags(content: str, initial_thought: str | None = None) -> tuple[str, str | None]:
    """Extrait le texte contenu dans les balises <think>...</think> et nettoie le contenu textuel.

    Si un initial_thought est fourni (issu des champs d'API 'reasoning', 'reasoning_content' ou 'thinking'),
    il est combiné avec les pensées détectées dans les balises. Le texte rendu est débarrassé de toute
    balise <think> pour préserver le parsing JSON.
    """
    if not content:
        return content, initial_thought

    matches = _THINK_TAG_REGEX.findall(content)
    if not matches:
        return content, initial_thought

    extracted_thoughts: list[str] = [m.strip() for m in matches if m.strip()]
    cleaned_content = _THINK_TAG_REGEX.sub("", content).strip()

    combined_thought: str | None = initial_thought
    if extracted_thoughts:
        text_thought = "\n\n".join(extracted_thoughts)
        combined_thought = f"{combined_thought}\n\n{text_thought}" if combined_thought else text_thought

    return cleaned_content, combined_thought


_FALLBACK_SYSTEM_PROMPT = "Vous êtes un assistant IA utile, concis et précis. Répondez en français sauf indication contraire."


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


def _resolve_generation_timeout_seconds() -> float:
    """Résout le délai maximal de génération (secondes) depuis les réglages utilisateur.

    Returns:
        Délai en secondes (toujours > 0 ; repli sur la valeur par défaut si le
        réglage est absent, invalide ou non positif).
    """
    try:
        from ankiforge.services.settings_service import SettingsService

        raw = SettingsService.get("ai/generation_timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
        timeout = float(raw)
    except (TypeError, ValueError):
        timeout = _DEFAULT_TIMEOUT_SECONDS
    if timeout <= 0:
        timeout = _DEFAULT_TIMEOUT_SECONDS
    return min(max(timeout, _MIN_GENERATION_TIMEOUT_SECONDS), _MAX_GENERATION_TIMEOUT_SECONDS)


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
        *,
        provider_name_override: str | None = None,
        default_headers: dict[str, str] | None = None,
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
            provider_name_override (str | None): Nom du fournisseur explicite (indépendant de l'URL).
            default_headers (dict[str, str] | None): En-têtes HTTP globaux du client (ex: HTTP-Referer OpenRouter).
        """
        self.base_url = base_url
        self.provider_name_override = provider_name_override
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
        )
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.is_ollama = "localhost" in base_url or "127.0.0.1" in base_url

    @property
    def provider_name(self) -> str:
        """Nom du fournisseur : explicite si fourni, sinon déduit de l'URL de base."""
        if self.provider_name_override:
            return self.provider_name_override
        base = self.base_url or str(getattr(self.client, "base_url", "") or "")
        if "groq" in base:
            return "groq"
        if "openrouter" in base:
            return "openrouter"
        if "opencode" in base:
            return "opencode"
        if "anthropic" in base:
            return "anthropic"
        if "localhost" in base or "127.0.0.1" in base:
            return "ollama"
        return "openai"

    def max_tokens_kwargs(self, effective_max: int) -> dict[str, int]:
        """Paramètre de plafond adapté au modèle (``max_completion_tokens`` vs ``max_tokens``).

        Les familles OpenAI o1/o3/o4/gpt-5 rejettent ``max_tokens`` au profit de
        ``max_completion_tokens`` ; les autres modèles attendent ``max_tokens``.
        """
        if _uses_reasoning_params(self.model_name):
            return {"max_completion_tokens": effective_max}
        return {"max_tokens": effective_max}

    def clamp_max_tokens(self, effective_max: int) -> int:
        """Borne le plafond de sortie au maximum réel du modèle (ex. routes OpenRouter ``:free``).

        Un ``max_tokens`` supérieur au plafond de sortie de la route renvoie un HTTP 400
        amont (ex: « does not support max tokens > N ») sans jamais produire de contenu.
        """
        if self.provider_name != "openrouter":
            return effective_max
        cap = _openrouter_max_output_tokens(self.base_url, self.model_name)
        if cap and cap > 0:
            return min(effective_max, cap)
        return effective_max

    def _truncation_retry_budget(self, effective_max: int) -> int | None:
        """Budget de sortie à tenter lors d'une troncature, ou ``None`` si aucun sur-dimensionnement possible.

        - OpenRouter : on monte au plafond réel de la route lorsque le plafond est connu ; si le
          budget actuel en est déjà à la limite (cas des modèles ``:free``), on ne réessaie pas car
          un second appel serait tronqué de façon identique.
        - Autres fournisseurs : on double le budget (borne de sécurité anti-DoS), pour une seule tentative.
        """
        if self.provider_name == "openrouter":
            cap = _openrouter_max_output_tokens(self.base_url, self.model_name)
            target = int(cap) if (cap and cap > 0) else effective_max * 2
        else:
            target = effective_max * 2
        target = min(int(target), _MAX_TRUNCATION_RETRY_TOKENS)
        if target <= effective_max:
            return None
        return target

    @staticmethod
    def _ensure_system_prompt(system_prompt: str | None) -> str:
        """Garantit un prompt système non vide.

        Certaines passerelles (OpenRouter/NVIDIA NIM…) convertissent chaque message en
        « content parts » et rejettent les parties de texte non typées : un contenu système
        vide devient alors une partie ``{"type": "text", "text": null}`` (HTTP 400).
        """
        text = str(system_prompt or "").strip()
        return text if text else _FALLBACK_SYSTEM_PROMPT

    @staticmethod
    def _sanitize_user_prompt(user_prompt: str | list[dict[str, Any]]) -> str | list[dict[str, Any]]:
        """Normalise le contenu utilisateur pour ne jamais expédier de partie de texte nulle.

        - ``str`` : transmis tel quel (format le plus compatible).
        - ``list`` : chaque partie texte doit porter un ``"text"`` de type ``str`` ; les parties
          sans texte ou images invalides sont retirées du flux.
        """
        if isinstance(user_prompt, str):
            return user_prompt
        if not isinstance(user_prompt, list):
            return str(user_prompt or "")
        parts: list[dict[str, Any]] = []
        for item in user_prompt or []:
            if not isinstance(item, dict):
                continue
            part_type = str(item.get("type") or "text")
            if part_type == "text":
                text = item.get("text")
                if text is None:
                    continue
                parts.append({"type": "text", "text": str(text)})
            elif part_type == "image_url":
                url_val = item.get("image_url")
                url = str(url_val.get("url") or "") if isinstance(url_val, dict) else ""
                if url:
                    parts.append({"type": "image_url", "image_url": {"url": url}})
        return parts if parts else ""

    def generate_response(
        self,
        system_prompt: str,
        user_prompt: str | list[dict[str, Any]],
        response_format: str = "json",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResult:
        """
        Envoie une requête de génération à l'API et retourne un LLMResult structuré.

        Args:
            system_prompt (str): Instructions système définissant le comportement de l'IA.
            user_prompt (str | list[dict[str, Any]]): Contenu de l'utilisateur (texte ou multimodal).
            response_format (str): Format de réponse attendu ("json" ou "text").
            max_tokens (int | None): Plafond optionnel de tokens à générer.
            temperature (float | None): Température de créativité (défaut 0.2).

        Returns:
            LLMResult: Résultat structuré incluant contenu textuel purifié et raisonnement extrait.

        Raises:
            RuntimeError: En cas d'échec de la communication avec l'API.
        """
        messages = [
            ChatCompletionSystemMessageParam(role="system", content=self._ensure_system_prompt(system_prompt)),
            ChatCompletionUserMessageParam(role="user", content=cast(Any, self._sanitize_user_prompt(user_prompt))),
        ]
        try:
            effective_max = self.clamp_max_tokens(max_tokens or self.max_tokens)
            kwargs: dict[str, Any] = {
                "model": self.model_name,
                "messages": messages,
                "temperature": temperature if temperature is not None else 0.2,
            }

            kwargs.update(self.max_tokens_kwargs(effective_max))

            # 👇 C'est ici que l'on connecte votre interface au backend !
            # Le mode json_object n'est pas supporté par tous les modèles/passeries :
            # ne l'envoyer que lorsque la passerelle le garantit.
            if response_format == "json" and not self.is_ollama and _supports_response_format(self.provider_name, self.model_name, self.base_url):
                kwargs["response_format"] = {"type": "json_object"}

            def _run_once() -> LLMResult:
                """Exécute un appel de complétion et en retourne le contenu final (ou lève)."""
                response = cast(
                    ChatCompletion,
                    self.client.chat.completions.create(**kwargs),
                )
                if hasattr(response, "usage") and response.usage:
                    p_tokens = response.usage.prompt_tokens or 0
                    c_tokens = response.usage.completion_tokens or 0

                    log_token_usage(self.provider_name, self.model_name, p_tokens, c_tokens)

                choices = getattr(response, "choices", None)
                if not choices:
                    # Vérification d'un éventuel payload d'erreur retourné sous HTTP 200 (ex: passerelle OpenRouter / NVIDIA)
                    err_obj = None
                    if hasattr(response, "model_extra") and isinstance(response.model_extra, dict):
                        err_obj = response.model_extra.get("error")
                    if not err_obj:
                        raw_err = getattr(response, "error", None)
                        if isinstance(raw_err, dict | str):
                            err_obj = raw_err

                    if err_obj:
                        if isinstance(err_obj, dict):
                            err_msg = str(err_obj.get("message") or err_obj)
                            err_code = err_obj.get("code")
                        else:
                            err_msg = str(err_obj)
                            err_code = None
                        code_str = f" [code {err_code}]" if err_code else ""
                        human_msg = get_human_readable_api_error(Exception(f"{err_msg}{code_str}"))
                        logger.error("Erreur renvoyée par le fournisseur IA (%s)%s : %s", self.model_name, code_str, err_msg)
                        raise RuntimeError(f"Erreur du fournisseur IA ({self.model_name}){code_str} : {err_msg} — {human_msg}")

                    logger.warning("Le fournisseur IA (%s) a renvoyé une réponse sans choix de complétion (choices=%s).", self.model_name, choices)
                    human_msg = get_human_readable_api_error(Exception("sans choix généré"))
                    raise RuntimeError(f"Le fournisseur IA ({self.model_name}) a renvoyé une réponse sans choix généré (choices vide ou nul) — {human_msg}")

                choice = choices[0]
                message = getattr(choice, "message", None)
                if not message:
                    logger.warning("Le choix de complétion du fournisseur IA (%s) ne contient aucun message.", self.model_name)
                    raise RuntimeError(f"Le fournisseur IA ({self.model_name}) a renvoyé un choix de complétion sans message.")

                refusal = getattr(message, "refusal", None)
                if isinstance(refusal, str) and refusal.strip():
                    logger.warning("Le modèle IA (%s) a refusé la requête : %s", self.model_name, refusal)
                    raise RuntimeError(f"Le modèle IA ({self.model_name}) a refusé de générer une réponse : {refusal}")

                content = getattr(message, "content", None) or ""
                finish_reason = getattr(choice, "finish_reason", None)
                reason_str = str(finish_reason or "").strip()

                if not str(content).strip():
                    reasoning_tokens, completion_tokens = _extract_reasoning_tokens(response)
                    # Cas documenté OpenRouter : un modèle reasoning a consommé tout son budget de
                    # sortie en raisonnement (200 OK, content vide). Un retry n'aide pas.
                    if reasoning_tokens and completion_tokens and reasoning_tokens >= completion_tokens * 0.9:
                        logger.warning(
                            "Le modèle IA (%s) a consommé son budget de sortie en raisonnement (reasoning=%s, completion=%s).",
                            self.model_name,
                            reasoning_tokens,
                            completion_tokens,
                        )
                        raise RuntimeError(
                            f"Le modèle IA ({self.model_name}) a consommé tout son budget de tokens en raisonnement "
                            f"(finish_reason='{reason_str}', reasoning_tokens={reasoning_tokens}, completion_tokens={completion_tokens}). "
                            "Augmentez max_tokens, désactivez le mode 'thinking' du modèle ou choisissez un modèle adapté à la génération de contenu."
                        )
                    if isinstance(finish_reason, str) and finish_reason in ("length", "content_filter"):
                        reason_msg = "dépassement du quota de tokens (length)" if finish_reason == "length" else "filtrage de sécurité (content_filter)"
                        raise RuntimeError(f"Le modèle IA ({self.model_name}) s'est arrêté prématurément ({reason_msg}) sans contenu textuel généré.")

                    human_msg = get_human_readable_api_error(Exception("réponse vide"))
                    logger.warning(
                        "Le modèle IA (%s) a renvoyé une réponse vide (finish_reason='%s').",
                        self.model_name,
                        reason_str,
                    )
                    raise RuntimeError(
                        f"Le modèle IA ({self.model_name}) a renvoyé une réponse vide (finish_reason='{reason_str}'). Réessayez, augmentez max_tokens ou choisissez un autre modèle — {human_msg}"
                    )

                # NOUVEAU : troncature avec contenu non vide. Le modèle a épuisé son budget de sortie
                # alors qu'il restait des tokens à produire : la réponse est généralement coupée en
                # pleine chaîne JSON et inexploitable sans un nouveau passage avec un budget élargi.
                if reason_str == "length" or reason_str == "content_filter":
                    logger.warning(
                        "Le modèle IA (%s) a été tronqué (finish_reason='%s') avec contenu non vide : la sortie est partielle.",
                        self.model_name,
                        reason_str,
                    )
                    if reason_str == "content_filter":
                        raise ContentFilteredError(
                            f"Le modèle IA ({self.model_name}) a été interrompu par le filtre de sécurité (finish_reason='content_filter'). "
                            "La réponse contient du contenu filtré : reformulez la requête ou assouplissez les filtres du modèle."
                        )
                    raise TruncatedOutputError(
                        f"Le modèle IA ({self.model_name}) a épuisé son budget de tokens de sortie (finish_reason='length') : "
                        "la réponse a été tronquée avant sa fin. Réduisez le contenu source, augmentez max_tokens "
                        "ou choisissez un modèle avec une sortie plus large."
                    )

                raw_reasoning = _extract_reasoning_from_message(message) or None
                cleaned_content, thought = extract_thought_tags(str(content), initial_thought=raw_reasoning)
                return LLMResult(content=cleaned_content, thought=thought, raw_response=response)

            # Une seule tentative de rattrapage : on élargit le budget de sortie puis on renvoie.
            # Si le plafond réel de la route est déjà atteint (ex. modèles OpenRouter ``:free``),
            # _truncation_retry_budget renvoie None et l'erreur remonte immédiatement.
            attempts = 0
            while True:
                attempts += 1
                try:
                    return _run_once()
                except TruncatedOutputError:
                    if attempts >= 2:
                        raise
                    retry_max = self._truncation_retry_budget(effective_max)
                    if retry_max is None or retry_max <= effective_max:
                        raise
                    effective_max = retry_max
                    kwargs.update(self.max_tokens_kwargs(effective_max))
                    logger.warning(
                        "Réponse tronquée du modèle IA (%s), nouvelle tentative avec un budget de sortie élargi (%d tokens).",
                        self.model_name,
                        effective_max,
                    )
        except (openai.APIError, openai.APIConnectionError) as e:
            logger.exception("Erreur API (%s) : %s", self.model_name, e)
            human_msg = get_human_readable_api_error(e)
            raise RuntimeError(f"Erreur API ({self.model_name}) : {human_msg}") from e
        except RuntimeError:
            raise
        except Exception as e:
            logger.exception("Erreur inattendue lors de la génération IA (%s) : %s", self.model_name, e)
            raise RuntimeError(f"Erreur inattendue lors de la génération IA ({self.model_name}) : {e}") from e

    def generate(
        self,
        system_prompt: str,
        user_prompt: str | list[dict[str, Any]],
        response_format: str = "json",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Envoie une requête de génération et retourne la chaîne textuelle brute épurée."""
        return self.generate_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
            max_tokens=max_tokens,
            temperature=temperature,
        ).content


class OllamaProvider(OpenAICompatibleProvider):
    """
    Fournisseur d'IA locale 100% gratuit utilisant Ollama.
    """

    def __init__(self, model_name: str = "llama3", max_tokens: int = 16384, timeout: float = _DEFAULT_TIMEOUT_SECONDS):
        """
        Initialise le service Ollama sur l'URL locale configurée (repli localhost).

        Args:
            model_name (str): Nom du modèle local à utiliser.
            max_tokens (int): Nombre maximal de tokens de réponse.
            timeout (float): Délai maximal (secondes) par requête réseau.
        """
        super().__init__(
            base_url=f"{_ollama_base_url()}/v1",
            model_name=model_name,
            api_key="ollama",
            max_tokens=max_tokens,
            timeout=timeout,
            provider_name_override="ollama",
        )

    @property
    def provider_name(self) -> str:
        return "ollama"

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

    def __init__(self, api_key: str | None = None, model_name: str = "llama3-8b-8192", max_tokens: int = 16384, timeout: float = _DEFAULT_TIMEOUT_SECONDS):
        """
        Initialise le client Groq.

        Args:
            api_key (str | None): Clé API Groq. Cherchée dans l'environnement par défaut.
            model_name (str): Modèle à utiliser sur Groq.
            max_tokens (int): Nombre maximal de tokens de réponse.
            timeout (float): Délai maximal (secondes) par requête réseau.

        Raises:
            ValueError: Si aucune clé API n'est fournie ou trouvée.
        """
        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise ValueError("Clé API GROQ_API_KEY manquante.")
        super().__init__(
            base_url="https://api.groq.com/openai/v1",
            model_name=model_name,
            api_key=key,
            max_tokens=max_tokens,
            timeout=timeout,
            provider_name_override="groq",
        )

    @property
    def provider_name(self) -> str:
        return "groq"


class OpenRouterProvider(OpenAICompatibleProvider):
    """
    Fournisseur d'accès multi-IA via la plateforme OpenRouter.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "qwen/qwen3.8-27b:free",
        base_url: str | None = None,
        max_tokens: int = 16384,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ):
        """
        Initialise le client OpenRouter.

        Args:
            api_key (str | None): Clé API OpenRouter.
            model_name (str): Modèle cible disponible sur OpenRouter.
            base_url (str | None): URL de la passerelle (défaut : openrouter/base_url ou https://openrouter.ai/api/v1).
            max_tokens (int): Nombre maximal de tokens de réponse.
            timeout (float): Délai maximal (secondes) par requête réseau.

        Raises:
            ValueError: Si la clé API est absente.
        """
        resolved_url = base_url
        if not resolved_url:
            try:
                from ankiforge.services.settings_service import SettingsService

                resolved_url = str(SettingsService.get("openrouter/base_url", "https://openrouter.ai/api/v1") or "https://openrouter.ai/api/v1").rstrip("/")
            except Exception:
                resolved_url = "https://openrouter.ai/api/v1"

        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("Clé API OPENROUTER_API_KEY manquante.")
        super().__init__(
            base_url=resolved_url,
            model_name=model_name,
            api_key=key,
            max_tokens=max_tokens,
            timeout=timeout,
            provider_name_override="openrouter",
            default_headers=_OPENROUTER_DEFAULT_HEADERS,
        )

    @property
    def provider_name(self) -> str:
        return "openrouter"


class OpenCodeProvider(OpenAICompatibleProvider):
    """
    Fournisseur d'accès aux modèles d'IA via la passerelle OpenCode (OpenCode Zen / passerelle locale).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "deepseek-v4-flash",
        base_url: str | None = None,
        max_tokens: int = 16384,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ):
        """
        Initialise le client OpenCode.

        Args:
            api_key (str | None): Clé API OpenCode (ou variable OPENCODE_API_KEY).
            model_name (str): Modèle cible (ex: 'deepseek-v4-flash', 'gemini-3.5-flash-lite').
            base_url (str | None): URL de la passerelle (défaut : opencode/base_url ou https://opencode.ai/zen/v1).
            max_tokens (int): Plafond maximal de tokens.
            timeout (float): Délai maximal par requête réseau.

        Raises:
            ValueError: Si la clé API est absente.
        """
        resolved_url = base_url
        if not resolved_url:
            try:
                from ankiforge.services.settings_service import SettingsService

                resolved_url = str(SettingsService.get("opencode/base_url", "https://opencode.ai/zen/v1") or "https://opencode.ai/zen/v1").rstrip("/")
            except Exception:
                resolved_url = "https://opencode.ai/zen/v1"

        key = api_key or os.environ.get("OPENCODE_API_KEY")
        if not key:
            raise ValueError("Clé API OPENCODE_API_KEY manquante.")
        super().__init__(
            base_url=resolved_url,
            model_name=model_name,
            api_key=key,
            max_tokens=max_tokens,
            timeout=timeout,
            provider_name_override="opencode",
        )

    @property
    def provider_name(self) -> str:
        return "opencode"


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
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model_name = model_name
        self.thinking_budget = thinking_budget
        self.max_tokens = max_tokens
        self.timeout = timeout

    def generate_response(
        self,
        system_prompt: str,
        user_prompt: str | list[dict[str, Any]],
        response_format: str = "json",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResult:
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
                    anthropic_content.append({"type": "text", "text": str(item.get("text") or "")})
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
            resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=self.timeout)
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

            # Extraction des blocs textuels et des blocs de réflexion "thinking"
            content_blocks = data.get("content", [])
            raw_thought_parts: list[str] = []
            text_parts: list[str] = []
            for block in content_blocks:
                b_type = block.get("type")
                if b_type == "thinking":
                    th = block.get("thinking")
                    if th:
                        raw_thought_parts.append(str(th))
                elif b_type == "text":
                    text_parts.append(str(block.get("text", "")))

            raw_thought = "\n\n".join(raw_thought_parts) if raw_thought_parts else None
            raw_content = "\n".join(text_parts) if text_parts else (str(content_blocks[0].get("text", "")) if (content_blocks and "text" in content_blocks[0]) else "")

            cleaned_content, thought = extract_thought_tags(raw_content, initial_thought=raw_thought)
            return LLMResult(content=cleaned_content, thought=thought, raw_response=data)
        except requests.RequestException as e:
            logger.exception("Erreur API Anthropic (%s) : %s", self.model_name, e)
            raise RuntimeError(f"Erreur API Anthropic ({self.model_name}) : {e}") from e

    def generate(
        self,
        system_prompt: str,
        user_prompt: str | list[dict[str, Any]],
        response_format: str = "json",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Génère une réponse textuelle en déléguant à generate_response."""
        return self.generate_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
            max_tokens=max_tokens,
            temperature=temperature,
        ).content


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
            except Exception as err:
                logger.debug("Échec du chargement de la clé via secret_store : %s", err)

        if not key:
            try:
                from ankiforge.services.settings_service import SettingsService

                key = str(SettingsService.get(f"keys/{p_name}", ""))
            except Exception as err:
                logger.debug("Échec du chargement de la clé via SettingsService : %s", err)

        timeout = _resolve_generation_timeout_seconds()
        try:
            if p_name == "ollama":
                return OllamaProvider(model_name=model_id, max_tokens=max_tokens, timeout=timeout)
            elif p_name == "gemini":
                if not key:
                    logger.warning("Clé API Gemini absente pour le modèle %s, repli sur MockProvider.", model_id)
                    return MockProvider()
                from ankiforge.services.ai.gemini_service import GeminiService

                return GeminiService(api_key=key, model_name=model_id, max_tokens=max_tokens, timeout=timeout)
            elif p_name == "groq":
                if not key and not os.environ.get("GROQ_API_KEY"):
                    logger.warning("Clé API Groq absente pour le modèle %s, repli sur MockProvider.", model_id)
                    return MockProvider()
                return GroqProvider(api_key=key, model_name=model_id, max_tokens=max_tokens, timeout=timeout)
            elif p_name == "openai":
                if not key and not os.environ.get("OPENAI_API_KEY"):
                    logger.warning("Clé API OpenAI absente pour le modèle %s, repli sur MockProvider.", model_id)
                    return MockProvider()
                return OpenAICompatibleProvider(
                    base_url="https://api.openai.com/v1",
                    model_name=model_id,
                    api_key=key,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    provider_name_override="openai",
                )
            elif p_name == "openrouter":
                if not key and not os.environ.get("OPENROUTER_API_KEY"):
                    logger.warning("Clé API OpenRouter absente pour le modèle %s, repli sur MockProvider.", model_id)
                    return MockProvider()
                return OpenRouterProvider(api_key=key, model_name=model_id, max_tokens=max_tokens, timeout=timeout)
            elif p_name == "opencode":
                if not key and not os.environ.get("OPENCODE_API_KEY"):
                    logger.warning("Clé API OpenCode absente pour le modèle %s, repli sur MockProvider.", model_id)
                    return MockProvider()
                return OpenCodeProvider(api_key=key, model_name=model_id, max_tokens=max_tokens, timeout=timeout)
            elif p_name == "anthropic":
                if not key and not os.environ.get("ANTHROPIC_API_KEY"):
                    logger.warning("Clé API Anthropic absente pour le modèle %s, repli sur MockProvider.", model_id)
                    return MockProvider()
                return AnthropicProvider(api_key=key, model_name=model_id, thinking_budget=thinking_budget, max_tokens=max_tokens, timeout=timeout)
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
