import pytest

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.flexible_service import AIManager, MockProvider, OllamaProvider, OpenAICompatibleProvider

pytestmark = pytest.mark.integration


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
    from ankiforge.services.ai.flexible_service import _DEFAULT_TIMEOUT_SECONDS, _resolve_generation_timeout_seconds
    from ankiforge.services.settings_service import SettingsService

    assert _resolve_generation_timeout_seconds() == _DEFAULT_TIMEOUT_SECONDS

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
    from ankiforge.services.ai.flexible_service import _DEFAULT_TIMEOUT_SECONDS, _resolve_generation_timeout_seconds
    from ankiforge.services.settings_service import SettingsService

    SettingsService.set("ai/generation_timeout_seconds", -5, category="ai")
    assert _resolve_generation_timeout_seconds() == _DEFAULT_TIMEOUT_SECONDS

    SettingsService.set("ai/generation_timeout_seconds", "pas-un-nombre", category="ai")
    assert _resolve_generation_timeout_seconds() == _DEFAULT_TIMEOUT_SECONDS


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


def test_ai_manager_init_is_lazy_and_does_not_call_keyring(mock_db):
    """Vérifie que l'instanciation de l'AIManager ne sollicite aucunement le trousseau OS."""
    from unittest.mock import patch

    import ankiforge.utils.secret_store as ss

    LLMConfigModel.create(
        display_name="Gemini Default",
        provider="gemini",
        model_id="gemini-3.5-flash-lite",
        api_key="",
        sort_order=1,
    )

    with patch.object(ss, "load_secret") as mock_load_secret:
        manager = AIManager()
        # Au démarrage, le trousseau ne doit PAS être sollicité
        mock_load_secret.assert_not_called()
        assert manager._provider is None
        assert manager.current_model == "gemini-3.5-flash-lite"


def test_ai_manager_lazy_provider_resolution_on_first_access(mock_db):
    """Vérifie que le provider est créé à la première lecture de manager.provider et mis en cache."""
    LLMConfigModel.create(
        display_name="Ollama Local",
        provider="ollama",
        model_id="llama3",
        sort_order=1,
    )
    manager = AIManager()
    assert manager._provider is None

    # Première sollicitation
    p1 = manager.provider
    assert p1 is not None
    assert getattr(p1, "model_name", None) == "llama3"

    # Deuxième sollicitation : même instance retournée
    p2 = manager.provider
    assert p1 is p2


def test_ai_manager_reload_provider_resets_lazy_cache(mock_db):
    """Vérifie que reload_provider réinitialise le cache pour différer la recréation."""
    LLMConfigModel.create(
        display_name="Ollama A",
        provider="ollama",
        model_id="model-a",
        sort_order=1,
    )
    manager = AIManager()
    p1 = manager.provider
    assert getattr(p1, "model_name", None) == "model-a"

    # Changement du modèle prioritaire
    LLMConfigModel.create(
        display_name="Ollama B",
        provider="ollama",
        model_id="model-b",
        sort_order=0,
    )
    manager.reload_provider()
    assert manager._provider is None
    assert manager.current_model == "model-b"

    # Sollicitation ultérieure
    p2 = manager.provider
    assert getattr(p2, "model_name", None) == "model-b"


def test_ai_manager_passes_temperature_and_supports_json_from_config(mock_db):
    """Vérifie que l'AIManager transmet la température et le support JSON configurés en base."""
    config = LLMConfigModel.create(
        display_name="OpenAI Configuré",
        provider="openai",
        model_id="gpt-4o",
        api_key="sk-test-key",
        context_limit=128000,
        temperature=0.85,
        supports_json=False,
    )
    provider = AIManager.create_provider_from_config(config)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert getattr(provider, "default_temperature", None) == 0.85
    assert getattr(provider, "supports_json", None) is False


def test_create_provider_sans_cle_leve_en_production(mock_db, monkeypatch):
    """Hors environnement de test, create_provider sans clé valide lève une exception explicite (jamais de MockProvider silencieux)."""
    import ankiforge.services.settings_service as ss
    import ankiforge.utils.environment as env
    from ankiforge.services.ai.flexible_service import AIManager

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(env, "get_current_environment", lambda: env.AppEnvironment.PRODUCTION)
    monkeypatch.setattr(ss.SettingsService, "get", lambda key, default=None, category=None: "")

    with pytest.raises(RuntimeError, match="Aucun fournisseur IA disponible"):
        AIManager.create_provider("openai", "gpt-4o", api_key="")


def test_create_provider_fournisseur_inconnu_leve_en_production(mock_db, monkeypatch):
    """Un fournisseur inconnu lève en production plutôt que de retourner MockProvider silencieusement."""
    import ankiforge.services.settings_service as ss
    import ankiforge.utils.environment as env
    from ankiforge.services.ai.flexible_service import AIManager

    monkeypatch.setattr(env, "get_current_environment", lambda: env.AppEnvironment.PRODUCTION)
    monkeypatch.setattr(ss.SettingsService, "get", lambda key, default=None, category=None: "")

    with pytest.raises(ValueError, match="Fournisseur IA inconnu ou non configuré"):
        AIManager.create_provider("magic_ai", "v1", api_key="")


def test_create_provider_retombe_mock_uniquement_en_testing(mock_db, monkeypatch):
    """create_provider sans clé retourne MockProvider uniquement en environnement de test."""
    import ankiforge.services.settings_service as ss
    import ankiforge.utils.environment as env
    from ankiforge.services.ai.base import MockProvider
    from ankiforge.services.ai.flexible_service import AIManager

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(env, "get_current_environment", lambda: env.AppEnvironment.TESTING)
    monkeypatch.setattr(ss.SettingsService, "get", lambda key, default=None, category=None: "")

    provider = AIManager.create_provider("openai", "gpt-4o", api_key="")
    assert isinstance(provider, MockProvider)


def test_create_provider_mock_explicite_toujours_autorise(mock_db, monkeypatch):
    """Le fournisseur explicite 'mock' retourne MockProvider même en dehors de l'environnement de test."""
    import ankiforge.services.settings_service as ss
    import ankiforge.utils.environment as env
    from ankiforge.services.ai.base import MockProvider
    from ankiforge.services.ai.flexible_service import AIManager

    monkeypatch.setattr(env, "get_current_environment", lambda: env.AppEnvironment.PRODUCTION)
    monkeypatch.setattr(ss.SettingsService, "get", lambda key, default=None, category=None: "")

    provider = AIManager.create_provider("mock", "mock-model", api_key="")
    assert isinstance(provider, MockProvider)
