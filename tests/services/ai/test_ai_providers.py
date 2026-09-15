from unittest.mock import MagicMock, patch

import pytest

from ankiforge.services.ai.base import MockProvider
from ankiforge.services.ai.flexible_service import OllamaProvider, OpenAICompatibleProvider
from ankiforge.services.ai.gemini_service import GeminiService

pytestmark = pytest.mark.unit


def test_mock_provider():
    """Vérifie que le fournisseur de secours renvoie toujours son JSON de test."""
    provider = MockProvider()
    res = provider.generate("system", "user")
    assert '"notes":' in res


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_success(mock_openai_class):
    """Vérifie la construction de la requête pour les API type OpenAI."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    mock_choice = MagicMock()
    mock_choice.message.content = '{"reponse": "ok"}'
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    provider = OpenAICompatibleProvider("http://fake", "fake-model")
    res = provider.generate("System", "User")

    assert res == '{"reponse": "ok"}'
    mock_client.chat.completions.create.assert_called_once()
    _, kwargs = mock_client.chat.completions.create.call_args
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["max_tokens"] == 16384


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_o1_max_completion_tokens(mock_openai_class):
    """Vérifie que les modèles type o1/o3 utilisent max_completion_tokens."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_choice = MagicMock()
    mock_choice.message.content = '{"reponse": "ok"}'
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    provider = OpenAICompatibleProvider("http://fake", "o1-mini", max_tokens=32000)
    provider.generate("System", "User")

    _, kwargs = mock_client.chat.completions.create.call_args
    assert kwargs["max_completion_tokens"] == 32000
    assert "max_tokens" not in kwargs


@patch("ankiforge.services.ai.flexible_service.requests.get")
def test_ollama_get_available_models(mock_get):
    """Teste la récupération des modèles Ollama locaux."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"models": [{"name": "llama3"}]}
    mock_get.return_value = mock_response

    models = OllamaProvider.get_available_models()
    assert "llama3" in models


@patch("ankiforge.services.ai.gemini_service.genai.Client")
def test_gemini_service_success(mock_genai_client):
    """Vérifie l'intégration du SDK Google Gemini et la présence de max_output_tokens."""
    mock_client_instance = MagicMock()
    mock_genai_client.return_value = mock_client_instance

    mock_response = MagicMock()
    mock_response.text = '{"gemini": "ok"}'
    mock_client_instance.models.generate_content.return_value = mock_response

    provider = GeminiService(api_key="fake_key", max_tokens=65536)
    res = provider.generate("System", "User")

    assert res == '{"gemini": "ok"}'
    mock_client_instance.models.generate_content.assert_called_once()
    _, call_kwargs = mock_client_instance.models.generate_content.call_args
    assert call_kwargs["config"].max_output_tokens == 65536


@patch("ankiforge.services.ai.flexible_service.requests.post")
def test_anthropic_provider_custom_max_tokens(mock_post):
    """Vérifie qu'Anthropic utilise le max_tokens configuré et non plus 4096 en dur."""
    from ankiforge.services.ai.flexible_service import AnthropicProvider

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "content": [{"type": "text", "text": '{"result": "ok"}'}],
        "usage": {"input_tokens": 100, "output_tokens": 200},
    }
    mock_post.return_value = mock_response

    provider = AnthropicProvider(api_key="fake_key", model_name="claude-3-7-sonnet-20250219", max_tokens=64000)
    res = provider.generate("System", "User")
    assert res == '{"result": "ok"}'

    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["max_tokens"] == 64000
