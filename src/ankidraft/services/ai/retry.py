"""Politique de retry unifiée (backoff exponentiel) pour les appels réseau aux fournisseurs LLM.

Centralise la résilience aux erreurs transitoires (timeouts, connexions coupées,
quotas/surcharges 429 et erreurs serveur 5xx) afin que chaque fournisseur
(Anthropic, Gemini, ...) partage le même comportement.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

# Codes HTTP considérés comme transitoires (retryables).
RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


def is_retryable_status(code: int | None) -> bool:
    """Indique si un code de statut HTTP justifie une nouvelle tentative."""
    return code is not None and code in RETRYABLE_STATUS_CODES


def with_retry[T](
    operation: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 8.0,
    should_retry: Callable[[BaseException], bool] | None = None,
    description: str = "appel LLM",
) -> T:
    """Exécute une opération avec backoff exponentiel sur les erreurs transitoires.

    Args:
        operation: Callable sans argument déclenchant l'appel réseau.
        max_attempts: Nombre total de tentatives (>= 1).
        base_delay: Délai initial en secondes avant la première nouvelle tentative.
        max_delay: Plafond du délai exponentiel.
        should_retry: Prédicat décidant si l'exception mérite un retry (défaut: toutes).
        description: Libellé utilisé dans les logs de WARNING.

    Returns:
        Le résultat de ``operation`` dès la première réussite.

    Raises:
        L'exception d'origine si toutes les tentatives échouent ou si ``should_retry`` la rejette.
    """
    last_exc: BaseException | None = None
    attempts = max(1, max_attempts)
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            last_exc = exc
            retryable = should_retry(exc) if should_retry is not None else True
            if not retryable or attempt >= attempts:
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            logger.warning(
                "Échec transitoire (%s, tentative %d/%d) : %s. Nouvelle tentative dans %.1fs.",
                description,
                attempt,
                attempts,
                exc,
                delay,
            )
            time.sleep(delay)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"Échec de l'opération '{description}' sans exception capturée.")


async def with_retry_async[T](
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 8.0,
    should_retry: Callable[[BaseException], bool] | None = None,
    description: str = "appel LLM",
) -> T:
    """Équivalent async de ``with_retry`` : backoff exponentiel non bloquant (asyncio.sleep).

    À privilégier dans les boucles ReAct/streaming (``_chat_stream_impl``) pour ne
    jamais geler l'event loop pendant l'attente de retry.
    """
    last_exc: BaseException | None = None
    attempts = max(1, max_attempts)
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except Exception as exc:
            last_exc = exc
            retryable = should_retry(exc) if should_retry is not None else True
            if not retryable or attempt >= attempts:
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            logger.warning(
                "Échec transitoire (%s, tentative %d/%d) : %s. Nouvelle tentative dans %.1fs.",
                description,
                attempt,
                attempts,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"Échec de l'opération '{description}' sans exception capturée.")
