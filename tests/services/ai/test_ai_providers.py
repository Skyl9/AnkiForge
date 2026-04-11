from unittest.mock import patch, MagicMock

from ankiforge.services.ai.base import MockProvider
from ankiforge.services.ai.flexible_service import OpenAICompatibleProvider, OllamaProvider
from ankiforge.services.ai.gemini_service import GeminiService


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
    """Vérifie l'intégration du SDK Google Gemini."""
    mock_client_instance = MagicMock()
    mock_genai_client.return_value = mock_client_instance

    mock_response = MagicMock()
    mock_response.text = '{"gemini": "ok"}'
    mock_client_instance.models.generate_content.return_value = mock_response

    provider = GeminiService(api_key="fake_key")
    res = provider.generate("System", "User")

    assert res == '{"gemini": "ok"}'
