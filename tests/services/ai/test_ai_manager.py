from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.flexible_service import AIManager, MockProvider, OllamaProvider, OpenAICompatibleProvider


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


def test_ai_manager_passes_max_tokens_from_config(mock_db):
    """Vérifie que l'AIManager transmet le max_tokens configuré en base."""
    config = LLMConfigModel.create(
        display_name="Claude Max",
        provider="anthropic",
        model_id="claude-3-7-sonnet-20250219",
        api_key="sk-ant-test",
        context_limit=200000,
        max_tokens=64000,
        sort_order=5,
    )
    provider = AIManager.create_provider_from_config(config)
    assert getattr(provider, "max_tokens", None) == 64000


def test_ai_manager_reload_provider_selects_top_model_by_sort_order(mock_db):
    """Vérifie que l'AIManager sélectionne le modèle ayant le plus petit sort_order (en tête de liste)."""
    from ankiforge.services.settings_service import SettingsService

    SettingsService.set("ai/default_model_id", "", category="ai")
    LLMConfigModel.create(
        display_name="GPT-4o Low Priority",
        provider="openai",
        model_id="gpt-4o",
        api_key="sk-test",
        sort_order=50,
    )
    LLMConfigModel.create(
        display_name="Gemini Top Priority",
        provider="gemini",
        model_id="gemini-3.5-flash-lite",
        api_key="fake-gemini",
        sort_order=0,
    )
    manager = AIManager()
    manager.reload_provider()
    # Le provider rechargé doit être celui avec sort_order=0
    assert getattr(manager.provider, "model_name", None) == "gemini-3.5-flash-lite"
