"""Tests unitaires pour le module de stockage sécurisé des secrets (secret_store).

Valide le comportement du trousseau OS (keyring), la mise en cache mémoire de session,
la priorité accordée aux variables d'environnement, et la résilience en cas d'indisponibilité.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

import ankiforge.utils.secret_store as ss


@pytest.fixture(autouse=True)
def clean_cache_and_env():
    """Nettoie le cache et les variables d'environnement de test avant et après chaque test."""
    ss.clear_secret_cache()
    # Supprimer temporairement les clés d'API de test
    keys_to_clean = ["OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"]
    saved = {k: os.environ.get(k) for k in keys_to_clean}
    for k in keys_to_clean:
        os.environ.pop(k, None)

    yield

    ss.clear_secret_cache()
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)


def test_store_and_load_secret_with_cache():
    """Vérifie l'enregistrement et la lecture d'un secret avec utilisation du cache mémoire."""
    mock_keyring = MagicMock()
    mock_keyring.get_password.return_value = "secret_val_123"

    with patch.object(ss, "keyring", mock_keyring), patch.object(ss, "_HAS_KEYRING", True):
        # 1. Enregistrement
        ok = ss.store_secret("llm", "openai:test", "secret_val_123")
        assert ok is True
        mock_keyring.set_password.assert_called_once_with(ss.SERVICE_NAME, "llm:openai:test", "secret_val_123")

        # 2. Première lecture : doit provenir du cache (car renseigné par store_secret)
        val = ss.load_secret("llm", "openai:test")
        assert val == "secret_val_123"
        # get_password n'a pas été appelé car le cache contenait déjà la valeur
        mock_keyring.get_password.assert_not_called()


def test_load_secret_queries_keyring_and_caches():
    """Vérifie que load_secret interroge le trousseau une seule fois puis met en cache."""
    mock_keyring = MagicMock()
    mock_keyring.get_password.return_value = "my_token"

    with patch.object(ss, "keyring", mock_keyring), patch.object(ss, "_HAS_KEYRING", True):
        # 1. Première lecture -> appel keyring
        val1 = ss.load_secret("tokens", "auth")
        assert val1 == "my_token"
        assert mock_keyring.get_password.call_count == 1

        # 2. Deuxième lecture -> servi par le cache sans second appel keyring
        val2 = ss.load_secret("tokens", "auth")
        assert val2 == "my_token"
        assert mock_keyring.get_password.call_count == 1


def test_clear_secret_cache():
    """Vérifie que clear_secret_cache force une nouvelle interrogation du trousseau."""
    mock_keyring = MagicMock()
    mock_keyring.get_password.return_value = "val"

    with patch.object(ss, "keyring", mock_keyring), patch.object(ss, "_HAS_KEYRING", True):
        ss.load_secret("ns", "k")
        assert mock_keyring.get_password.call_count == 1

        ss.clear_secret_cache()

        ss.load_secret("ns", "k")
        assert mock_keyring.get_password.call_count == 2


def test_delete_secret():
    """Vérifie la suppression d'un secret du trousseau et l'éviction du cache."""
    mock_keyring = MagicMock()

    with patch.object(ss, "keyring", mock_keyring), patch.object(ss, "_HAS_KEYRING", True):
        ss.store_secret("ns", "k", "test_val")
        assert ("ns", "k") in ss._SECRET_CACHE

        ok = ss.delete_secret("ns", "k")
        assert ok is True
        assert ("ns", "k") not in ss._SECRET_CACHE
        mock_keyring.delete_password.assert_called_once_with(ss.SERVICE_NAME, "ns:k")


def test_load_llm_key_prefers_session_environment_variable():
    """Vérifie que load_llm_key retourne immédiatement la variable d'environnement sans toucher au trousseau."""
    os.environ["OPENAI_API_KEY"] = "sk-from-env"

    mock_keyring = MagicMock()
    with patch.object(ss, "keyring", mock_keyring), patch.object(ss, "_HAS_KEYRING", True):
        key = ss.load_llm_key("gpt-4o", "openai")
        assert key == "sk-from-env"
        # Aucune interrogation du trousseau OS
        mock_keyring.get_password.assert_not_called()


def test_load_llm_key_gemini_recognizes_google_api_key():
    """Vérifie que Gemini reconnaît aussi GOOGLE_API_KEY sans interroger le trousseau."""
    os.environ["GOOGLE_API_KEY"] = "AIza-from-env"

    mock_keyring = MagicMock()
    with patch.object(ss, "keyring", mock_keyring), patch.object(ss, "_HAS_KEYRING", True):
        key = ss.load_llm_key("gemini-3.5-flash-lite", "gemini")
        assert key == "AIza-from-env"
        mock_keyring.get_password.assert_not_called()


def test_load_llm_key_falls_back_to_provider_level():
    """Vérifie le repli sur la clé globale provider si la clé spécifique au modèle est absente."""
    mock_keyring = MagicMock()

    def _mock_get_password(service: str, account: str):
        if account == "llm:anthropic:anthropic":
            return "sk-ant-provider-wide"
        return None

    mock_keyring.get_password.side_effect = _mock_get_password

    with patch.object(ss, "keyring", mock_keyring), patch.object(ss, "_HAS_KEYRING", True):
        key = ss.load_llm_key("claude-3-7-sonnet", "anthropic")
        assert key == "sk-ant-provider-wide"


def test_secret_store_graceful_degradation_on_exception():
    """Vérifie que les exceptions du trousseau retournent None/False sans planter."""
    mock_keyring = MagicMock()
    mock_keyring.get_password.side_effect = RuntimeError("Keyring locked or unavailable")
    mock_keyring.set_password.side_effect = RuntimeError("Permission denied")
    mock_keyring.delete_password.side_effect = RuntimeError("Permission denied")

    with patch.object(ss, "keyring", mock_keyring), patch.object(ss, "_HAS_KEYRING", True):
        assert ss.load_secret("ns", "k") is None
        assert ss.store_secret("ns", "k", "v") is False
        assert ss.delete_secret("ns", "k") is False


def test_secret_store_without_keyring_dependency():
    """Vérifie le comportement silencieux si keyring n'est pas disponible."""
    with patch.object(ss, "_HAS_KEYRING", False), patch.object(ss, "keyring", None):
        assert ss.store_secret("ns", "k", "val") is False
        assert ss.load_secret("ns", "k") is None
        assert ss.delete_secret("ns", "k") is False
