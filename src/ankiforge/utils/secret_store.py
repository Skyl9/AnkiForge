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

logger = logging.getLogger(__name__)

try:
    import keyring
    from keyring.errors import KeyringError

    _HAS_KEYRING = True
except Exception:  # pragma: no cover - dépendance/runtime manquant
    keyring = None  # type: ignore[assignment]
    KeyringError = Exception  # type: ignore[assignment,misc]
    _HAS_KEYRING = False

SERVICE_NAME = "AnkiForge"


def _account(namespace: str, key: str) -> str:
    """Nom de compte composé pour éviter toute collision entre catégories."""
    return f"{namespace}:{key}"


def store_secret(namespace: str, key: str, value: str) -> bool:
    """Enregistre un secret dans le trousseau. Retourne True en cas de succès."""
    if not _HAS_KEYRING or not keyring or value is None:
        return False
    try:
        keyring.set_password(SERVICE_NAME, _account(namespace, key), value)
        return True
    except Exception as e:
        logger.debug("keyring.set_password indisponible (%s), repli stockage historique", e)
        return False


def load_secret(namespace: str, key: str) -> str | None:
    """Récupère un secret depuis le trousseau (None si absent ou indisponible)."""
    if not _HAS_KEYRING or not keyring:
        return None
    try:
        return keyring.get_password(SERVICE_NAME, _account(namespace, key))
    except Exception as e:
        logger.debug("keyring.get_password indisponible (%s)", e)
        return None


def delete_secret(namespace: str, key: str) -> None:
    """Supprime un secret du trousseau (best-effort)."""
    if not _HAS_KEYRING or not keyring:
        return
    try:
        keyring.delete_password(SERVICE_NAME, _account(namespace, key))
    except KeyringError:
        pass  # secret absent du trousseau : rien à supprimer
    except Exception as e:  # pragma: no cover - backend exotique
        logger.debug("keyring.delete_password indisponible (%s)", e)


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
    key = load_secret("llm", f"{provider}:{model_id}")
    if not key:
        key = load_secret("llm", f"{provider}:{provider}")
    return key or None


def delete_llm_key(model_id: str, provider: str) -> None:
    delete_secret("llm", f"{provider}:{model_id}")
