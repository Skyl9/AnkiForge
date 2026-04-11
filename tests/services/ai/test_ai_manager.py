import os
from unittest.mock import patch

import pytest

from ankiforge.services.ai.base import MockProvider
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.ai.flexible_service import OllamaProvider


@pytest.fixture
def clean_env():
    """Nettoie les variables d'environnement pour chaque test."""
    with patch.dict(os.environ, clear=True):
        yield


@patch("ankiforge.services.ai.flexible_service.get_app_data_dir")
def test_ai_manager_init_creates_env(mock_get_dir, tmp_path, clean_env):
    """Vérifie la création automatique du .env au premier lancement."""
    mock_get_dir.return_value = tmp_path

    manager = AIManager()

    env_file = tmp_path / ".env"
    assert env_file.exists()
    assert "AI_PROVIDER=Ollama" in env_file.read_text()
    assert isinstance(manager.provider, OllamaProvider)


@patch("ankiforge.services.ai.flexible_service.get_app_data_dir")
def test_ai_manager_fallback(mock_get_dir, tmp_path, clean_env):
    """Vérifie le repli sur MockProvider en cas d'erreur de configuration."""
    mock_get_dir.return_value = tmp_path

    # On force un provider inexistant
    env_file = tmp_path / ".env"
    env_file.write_text("AI_PROVIDER=Inconnu\n", encoding="utf-8")

    manager = AIManager()
    assert isinstance(manager.provider, MockProvider)
