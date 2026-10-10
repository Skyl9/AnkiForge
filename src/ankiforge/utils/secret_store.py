"""Stockage sécurisé des secrets applicatifs via le trousseau de l'OS (keyring).

Les clés API sont de vrais secrets : les conserver en clair dans la base SQLite ou
dans les ``.env`` les rend récupérables par tout processus ayant accès au profil
utilisateur. Avec ``keyring``, elles sont confiées au trousseau natif de la
plateforme (Keychain macOS, Credential Manager Windows, Secret Service Linux).

Comportement dégradé : si aucun backend de trousseau n'est disponible (CI
headless, machine sans service *secrets*), les fonctions rendent un échec
``False``/``None`` silencieux — les appelants retombent alors sur leur stockage
historique (colonne ``api_key`` de la BDD), sans jamais faire planter l'app.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

keyring: Any
try:
    import keyring

    _HAS_KEYRING = True
except Exception:  # pragma: no cover - dépendance/runtime manquant
    keyring = None
    _HAS_KEYRING = False

SERVICE_NAME = "AnkiForge"

# Cache mémoire de session pour éviter toute réinterrogation répétée du trousseau OS
_SECRET_CACHE: dict[tuple[str, str], str | None] = {}


def _account(namespace: str, key: str) -> str:
    """Nom de compte composé pour éviter toute collision entre catégories."""
    return f"{namespace}:{key}"


def clear_secret_cache() -> None:
    """Vide le cache mémoire des secrets (utile lors des tests ou réinitialisations de profil)."""
    _SECRET_CACHE.clear()


def store_secret(namespace: str, key: str, value: str) -> bool:
    """Enregistre un secret dans le trousseau. Retourne True en cas de succès."""
    if not _HAS_KEYRING or not keyring or value is None:
        return False
    account = _account(namespace, key)
    logger.info("Enregistrement du secret dans le trousseau OS (%s, compte='%s')...", SERVICE_NAME, account)
    try:
        keyring.set_password(SERVICE_NAME, account, value)
        _SECRET_CACHE[(namespace, key)] = value
        return True
    except Exception as e:
        logger.debug("keyring.set_password indisponible (%s), repli stockage historique", e)
        return False


def load_secret(namespace: str, key: str) -> str | None:
    """Récupère un secret depuis le trousseau (None si absent ou indisponible)."""
    cache_key = (namespace, key)
    if cache_key in _SECRET_CACHE:
        return _SECRET_CACHE[cache_key]

    if not _HAS_KEYRING or not keyring:
        return None

    account = _account(namespace, key)
    logger.debug("Lecture du secret dans le trousseau OS (%s, compte='%s')...", SERVICE_NAME, account)
    try:
        val = keyring.get_password(SERVICE_NAME, account)
        _SECRET_CACHE[cache_key] = val
        return val
    except Exception as e:
        logger.debug("keyring.get_password indisponible pour '%s' (%s)", account, e)
        _SECRET_CACHE[cache_key] = None
        return None


def delete_secret(namespace: str, key: str) -> bool:
    """Supprime un secret du trousseau et du cache mémoire."""
    cache_key = (namespace, key)
    _SECRET_CACHE.pop(cache_key, None)
    if not _HAS_KEYRING or not keyring:
        return False
    account = _account(namespace, key)
    logger.info("Suppression du secret dans le trousseau OS (%s, compte='%s')...", SERVICE_NAME, account)
    try:
        keyring.delete_password(SERVICE_NAME, account)
        return True
    except Exception as e:
        logger.debug("keyring.delete_password indisponible (%s)", e)
        return False


# ----------------------------------------------------------------------------
# Raccourcis dédiés aux clés LLM (namespaces "llm")
# ----------------------------------------------------------------------------


def store_llm_key(model_id: str, provider: str, value: str) -> bool:
    """Stocke la clé API LLM d'un modèle (identifiable par provider + model_id)."""
    if not value:
        return False
    return store_secret("llm", f"{provider}:{model_id}", value)


def load_llm_key(model_id: str, provider: str) -> str | None:
    """Récupère la clé API LLM d'un modèle ; tente aussi la clé provider-level
    stockée par les anciennes sauvegardes de paramètres (trousseau de l'onglet)."""
    # 1. Vérifie si une variable d'environnement de session est déjà définie
    env_keys = [f"{provider.upper()}_API_KEY"]
    if provider.lower() == "gemini":
        env_keys.append("GOOGLE_API_KEY")

    for env_k in env_keys:
        val = os.environ.get(env_k)
        if val and val.strip():
            return val.strip()

    # 2. Recherche spécifique au modèle dans le trousseau
    key = load_secret("llm", f"{provider}:{model_id}")
    # 3. Repli sur la clé générique au niveau du fournisseur
    if not key:
        key = load_secret("llm", f"{provider}:{provider}")
    return key or None
