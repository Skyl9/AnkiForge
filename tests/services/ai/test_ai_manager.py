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


def test_ai_manager_applies_generation_timeout_from_settings(mock_db):
    """Le délai de génération configurable est appliqué aux clients réseau des providers."""
    from ankiforge.services.ai.flexible_service import _resolve_generation_timeout_seconds
    from ankiforge.services.settings_service import SettingsService

    assert _resolve_generation_timeout_seconds() == 60000.0

    SettingsService.set("ai/generation_timeout_seconds", 42, category="ai")
    assert _resolve_generation_timeout_seconds() == 42.0

    provider = AIManager.create_provider("openai", "gpt-4o", api_key="sk-test-key")
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.client.timeout == 42.0

    ollama = AIManager.create_provider("ollama", "llama3")
    assert isinstance(ollama, OllamaProvider)
    assert ollama.client.timeout == 42.0


def test_ai_manager_replaces_invalid_generation_timeout_with_default(mock_db):
    """Un réglage invalide ou non positif retombe sur le délai par défaut."""
    from ankiforge.services.ai.flexible_service import _resolve_generation_timeout_seconds
    from ankiforge.services.settings_service import SettingsService

    SettingsService.set("ai/generation_timeout_seconds", -5, category="ai")
    assert _resolve_generation_timeout_seconds() == 60000.0

    SettingsService.set("ai/generation_timeout_seconds", "pas-un-nombre", category="ai")
    assert _resolve_generation_timeout_seconds() == 60000.0


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


def test_ai_manager_create_opencode_with_key(mock_db):
    """Vérifie que l'AIManager instancie OpenCodeProvider avec la clé fournie."""
    from ankiforge.services.ai.flexible_service import OpenCodeProvider

    config = LLMConfigModel.create(
        display_name="OpenCode Test",
        provider="opencode",
        model_id="deepseek-v4-flash",
        api_key="sk-ONR9yD6SzaNBqJFkOlSlCOgr3t5ECdu42dJtrDyYS5vSKIx6Mi",
        context_limit=128000,
    )
    provider = AIManager.create_provider_from_config(config)
    assert isinstance(provider, OpenCodeProvider)
    assert provider.model_name == "deepseek-v4-flash"
    assert provider.client.api_key == "sk-ONR9yD6SzaNBqJFkOlSlCOgr3t5ECdu42dJtrDyYS5vSKIx6Mi"


def test_ai_manager_create_openrouter_with_key(mock_db):
    """Vérifie que l'AIManager instancie OpenRouterProvider avec la clé fournie."""
    from ankiforge.services.ai.flexible_service import OpenRouterProvider

    config = LLMConfigModel.create(
        display_name="OpenRouter Test",
        provider="openrouter",
        model_id="qwen/qwen3.8-27b:free",
        api_key="sk-or-v1-testkey",
        context_limit=128000,
    )
    provider = AIManager.create_provider_from_config(config)
    assert isinstance(provider, OpenRouterProvider)
    assert provider.model_name == "qwen/qwen3.8-27b:free"
    assert provider.client.api_key == "sk-or-v1-testkey"


def test_ai_manager_opencode_missing_key_fallback(mock_db, monkeypatch):
    """Vérifie le repli sur MockProvider si la clé OpenCode est absente."""
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    config = LLMConfigModel.create(
        display_name="OpenCode No Key",
        provider="opencode",
        model_id="deepseek-v4-flash",
        api_key="",
        context_limit=128000,
    )
    provider = AIManager.create_provider_from_config(config)
    assert isinstance(provider, MockProvider)
