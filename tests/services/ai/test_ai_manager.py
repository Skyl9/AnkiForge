from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.flexible_service import AIManager, OllamaProvider, MockProvider, OpenAICompatibleProvider


def test_ai_manager_create_provider_from_config(mock_db):
    """Vérifie que l'AIManager crée le bon provider à partir d'une config en BDD."""
    config = LLMConfigModel.create(display_name="Ollama Test", provider="ollama", model_id="llama3", api_key="custom_key", context_limit=4096)

    provider = AIManager.create_provider_from_config(config)
    assert isinstance(provider, OllamaProvider)
    assert provider.model_name == "llama3"


def test_ai_manager_create_openai_with_key(mock_db):
    """Vérifie que l'AIManager injecte bien la clé API pour OpenAI."""
    config = LLMConfigModel.create(display_name="OpenAI Test", provider="openai", model_id="gpt-4o", api_key="sk-test-key", context_limit=128000)

    provider = AIManager.create_provider_from_config(config)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.client.api_key == "sk-test-key"


def test_ai_manager_invalid_provider_fallback(mock_db):
    """Vérifie le repli sur MockProvider pour un fournisseur inconnu."""
    config = LLMConfigModel.create(display_name="Inconnu", provider="magic_ai", model_id="v1", api_key="", context_limit=1000)

    provider = AIManager.create_provider_from_config(config)
    assert isinstance(provider, MockProvider)
