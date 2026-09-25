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
def test_openai_compatible_provider_empty_system_gets_fallback(mock_openai_class):
    """Un prompt système vide ne doit jamais devenir une partie de texte nulle (erreur NIM HTTP 400)."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_choice = MagicMock()
    mock_choice.message.content = "ok"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    provider = OpenAICompatibleProvider("http://fake", "fake-model")
    provider.generate("", "User")

    _, kwargs = mock_client.chat.completions.create.call_args
    messages = kwargs["messages"]
    system_content = messages[0]["content"]
    assert isinstance(system_content, str) and system_content.strip()
    assert messages[1]["content"] == "User"


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_sanitizes_null_text_parts(mock_openai_class):
    """Les parties de texte null sont retirées : aucune partie {'text': None} ne part sur le réseau."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_choice = MagicMock()
    mock_choice.message.content = "ok"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    provider = OpenAICompatibleProvider("http://fake", "fake-model")
    provider.generate(
        "System",
        [
            {"type": "text", "text": None},
            {"type": "text", "text": "Contenu valide"},
            {"type": "image_url", "image_url": {"url": ""}},
        ],
    )

    _, kwargs = mock_client.chat.completions.create.call_args
    user_content = kwargs["messages"][1]["content"]
    assert user_content == [{"type": "text", "text": "Contenu valide"}]
    assert not any(part.get("text") is None for part in user_content)


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_all_invalid_parts_falls_back_to_text(mock_openai_class):
    """Si toutes les parties sont invalides, on envoie un texte vide (jamais une liste vide)."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_choice = MagicMock()
    mock_choice.message.content = "ok"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    provider = OpenAICompatibleProvider("http://fake", "fake-model")
    provider.generate("System", [{"type": "text", "text": None}])

    _, kwargs = mock_client.chat.completions.create.call_args
    assert kwargs["messages"][1]["content"] == ""


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


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_opencode_provider_success(mock_openai_class):
    """Vérifie l'instanciation et la génération avec OpenCodeProvider."""
    from ankiforge.services.ai.flexible_service import OpenCodeProvider

    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_choice = MagicMock()
    mock_choice.message.content = '{"notes": [{"front": "Q", "back": "A"}]}'
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice], usage=MagicMock(prompt_tokens=10, completion_tokens=20))

    provider = OpenCodeProvider(api_key="sk-ONR9yD6SzaNBqJFkOlSlCOgr3t5ECdu42dJtrDyYS5vSKIx6Mi", model_name="deepseek-v4-flash")
    assert provider.provider_name == "opencode"
    mock_openai_class.assert_called_once()
    _, init_kwargs = mock_openai_class.call_args
    assert init_kwargs["base_url"] == "https://opencode.ai/zen/v1"
    assert init_kwargs["api_key"] == "sk-ONR9yD6SzaNBqJFkOlSlCOgr3t5ECdu42dJtrDyYS5vSKIx6Mi"

    res = provider.generate("System", "User")
    assert '{"notes":' in res


def test_opencode_provider_missing_key(monkeypatch):
    """Vérifie que OpenCodeProvider lève une ValueError si la clé API est absente."""
    from ankiforge.services.ai.flexible_service import OpenCodeProvider

    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENCODE_API_KEY manquante"):
        OpenCodeProvider(api_key=None)


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openrouter_provider_success(mock_openai_class):
    """Vérifie l'instanciation et l'URL de base pour OpenRouterProvider."""
    from ankiforge.services.ai.flexible_service import OpenRouterProvider

    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    provider = OpenRouterProvider(api_key="sk-or-v1-test", model_name="qwen/qwen3.8-27b:free")
    assert provider.provider_name == "openrouter"
    _, init_kwargs = mock_openai_class.call_args
    assert init_kwargs["base_url"] == "https://openrouter.ai/api/v1"
    assert init_kwargs["api_key"] == "sk-or-v1-test"


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_opencode_provider_custom_base_url(mock_openai_class):
    """Vérifie que OpenCodeProvider respecte un base_url custom passé en argument et via SettingsService."""
    from ankiforge.services.ai.flexible_service import OpenCodeProvider
    from ankiforge.services.settings_service import SettingsService

    # 1. base_url explicite
    OpenCodeProvider(api_key="sk-test", base_url="http://custom-opencode:8080/v1")
    _, init_kwargs = mock_openai_class.call_args
    assert init_kwargs["base_url"] == "http://custom-opencode:8080/v1"

    # 2. base_url depuis SettingsService
    with patch.object(SettingsService, "get", return_value="https://my-zen-proxy.internal/v1"):
        OpenCodeProvider(api_key="sk-test")
        _, init_kwargs = mock_openai_class.call_args
        assert init_kwargs["base_url"] == "https://my-zen-proxy.internal/v1"


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openrouter_provider_custom_base_url(mock_openai_class):
    """Vérifie que OpenRouterProvider respecte un base_url custom passé en argument et via SettingsService."""
    from ankiforge.services.ai.flexible_service import OpenRouterProvider
    from ankiforge.services.settings_service import SettingsService

    # 1. base_url explicite
    OpenRouterProvider(api_key="sk-or-test", base_url="http://custom-openrouter:9090/v1")
    _, init_kwargs = mock_openai_class.call_args
    assert init_kwargs["base_url"] == "http://custom-openrouter:9090/v1"

    # 2. base_url depuis SettingsService
    with patch.object(SettingsService, "get", return_value="https://my-openrouter-proxy.internal/v1"):
        OpenRouterProvider(api_key="sk-or-test")
        _, init_kwargs = mock_openai_class.call_args
        assert init_kwargs["base_url"] == "https://my-openrouter-proxy.internal/v1"


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_openrouter_gateway_error(mock_openai_class):
    """Vérifie l'extraction du message d'erreur d'une passerelle (ex. OpenRouter 200 OK avec choices=None)."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    # Simule le cas précis de log.txt où choices est None et error est dans model_extra
    mock_response = MagicMock(spec=["choices", "model_extra", "usage"])
    mock_response.choices = None
    mock_response.model_extra = {"error": {"message": "Upstream provider timed out", "code": 504}}
    mock_response.usage = None
    mock_client.chat.completions.create.return_value = mock_response

    provider = OpenAICompatibleProvider("https://openrouter.ai/api/v1", "nvidia/nemotron-test")
    with pytest.raises(RuntimeError) as exc_info:
        provider.generate("System", "User")

    err_msg = str(exc_info.value)
    assert "Erreur du fournisseur IA (nvidia/nemotron-test)" in err_msg
    assert "code 504" in err_msg
    assert "Upstream provider timed out" in err_msg
    assert "Timeout / Erreur 504" in err_msg


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_empty_choices(mock_openai_class):
    """Vérifie la détection d'une réponse vide sans choices."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.choices = []
    mock_response.model_extra = {}
    mock_response.usage = None
    mock_client.chat.completions.create.return_value = mock_response

    provider = OpenAICompatibleProvider("https://openrouter.ai/api/v1", "test-model")
    with pytest.raises(RuntimeError) as exc_info:
        provider.generate("System", "User")

    assert "sans choix généré" in str(exc_info.value)


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_model_refusal(mock_openai_class):
    """Vérifie la remontée explicite en cas de refus du modèle (refusal)."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    mock_choice = MagicMock()
    mock_choice.message.refusal = "Demande incompatible avec la politique de sécurité."
    mock_choice.message.content = ""
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice], usage=None)

    provider = OpenAICompatibleProvider("https://fake", "test-model")
    with pytest.raises(RuntimeError) as exc_info:
        provider.generate("System", "User")

    assert "a refusé de générer une réponse" in str(exc_info.value)
    assert "Demande incompatible" in str(exc_info.value)


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_finish_reason_length(mock_openai_class):
    """Vérifie l'alerte explicite si le modèle s'est arrêté par manque de tokens sans contenu."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    mock_choice = MagicMock()
    mock_choice.message.refusal = None
    mock_choice.message.content = ""
    mock_choice.finish_reason = "length"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice], usage=None)

    provider = OpenAICompatibleProvider("https://fake", "test-model")
    with pytest.raises(RuntimeError) as exc_info:
        provider.generate("System", "User")

    assert "dépassement du quota de tokens" in str(exc_info.value)


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_truncation_nonempty_retries_with_more_tokens(mock_openai_class):
    """Une réponse non vide tronquée (finish_reason='length') déclenche UN retry avec un budget élargi.

    Corrige le cas réel d'AnkiForge : le modèle OpenAI-compatible remplissait exactement son
    max_tokens, finish_reason='length' avec du contenu partiel (JSON coupé en pleine chaîne).
    """
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    def side_effect(**kwargs):
        choice = MagicMock()
        choice.message.refusal = None
        if kwargs["max_tokens"] == 16384:
            choice.message.content = '{"notes": [{"Front": "Q1", "Back": "A'
            choice.finish_reason = "length"
        else:
            choice.message.content = '{"notes": [{"Front": "Q1", "Back": "A1"}]}'
            choice.finish_reason = "stop"
        return MagicMock(choices=[choice], usage=None)

    mock_client.chat.completions.create.side_effect = side_effect

    provider = OpenAICompatibleProvider("https://fake", "test-model")
    res = provider.generate("System", "User")

    assert '"Back": "A1"' in res
    assert mock_client.chat.completions.create.call_count == 2
    max_tokens_used = [c.kwargs["max_tokens"] for c in mock_client.chat.completions.create.call_args_list]
    assert max_tokens_used == [16384, 32768]


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_truncation_retries_once_then_raises(mock_openai_class):
    """Si le retry avec budget élargi est lui aussi tronqué, on ne boucle pas : TruncatedOutputError."""
    from ankiforge.services.ai.flexible_service import TruncatedOutputError

    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    mock_choice = MagicMock()
    mock_choice.message.refusal = None
    mock_choice.message.content = '{"notes": [{"Front": "Q1", "Back": "A'
    mock_choice.finish_reason = "length"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice], usage=None)

    provider = OpenAICompatibleProvider("https://fake", "test-model")
    with pytest.raises(TruncatedOutputError) as exc_info:
        provider.generate("System", "User")

    assert "épuisé son budget" in str(exc_info.value)
    assert mock_client.chat.completions.create.call_count == 2


@patch("ankiforge.services.ai.flexible_service._openrouter_max_output_tokens", return_value=8192)
@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_truncation_at_cap_raises_no_retry(mock_openai_class, mock_cap):
    """Route OpenRouter ``:free`` déjà au plafond réel : pas de retry, erreur immédiate (évite un 2e appel ~4 min)."""
    from ankiforge.services.ai.flexible_service import TruncatedOutputError

    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    mock_choice = MagicMock()
    mock_choice.message.refusal = None
    mock_choice.message.content = '{"notes": [{"Front": "Q1", "Back": "A'
    mock_choice.finish_reason = "length"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice], usage=None)

    provider = OpenAICompatibleProvider("https://openrouter.ai/api/v1", "qwen/qwen3.8-27b:free", max_tokens=8192)
    with pytest.raises(TruncatedOutputError) as exc_info:
        provider.generate("System", "User")

    assert "épuisé son budget" in str(exc_info.value)
    assert mock_client.chat.completions.create.call_count == 1


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_content_filter_nonempty_raises(mock_openai_class):
    """Un finish_reason='content_filter' avec contenu non vide est remonté explicitement."""
    from ankiforge.services.ai.flexible_service import ContentFilteredError

    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    mock_choice = MagicMock()
    mock_choice.message.refusal = None
    mock_choice.message.content = "Contenu partiellement filtré"
    mock_choice.finish_reason = "content_filter"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice], usage=None)

    provider = OpenAICompatibleProvider("https://fake", "test-model")
    with pytest.raises(ContentFilteredError) as exc_info:
        provider.generate("System", "User")

    assert "filtre de sécurité" in str(exc_info.value)
    assert mock_client.chat.completions.create.call_count == 1


@patch("ankiforge.services.settings_service.SettingsService.get")
def test_resolve_generation_timeout_bounded_default(mock_settings_get):
    """Le timeout de génération par défaut doit être borné (pas un gel de ~16 h quand l'IA stagne).

    Régression : _DEFAULT_TIMEOUT_SECONDS valait 60000 s (16,6 h) — un fournisseur lent/afflué
    (qwen:free, Gemini afflué, NVIDIA 503) figeait la génération quasi indéfiniment, obligeant à
    quitter l'application (symptôme « UI bloquée, j'ai quitté »).
    """
    from ankiforge.services.ai.flexible_service import (
        _DEFAULT_TIMEOUT_SECONDS,
        _MAX_GENERATION_TIMEOUT_SECONDS,
        _MIN_GENERATION_TIMEOUT_SECONDS,
        _resolve_generation_timeout_seconds,
    )

    mock_settings_get.return_value = None
    resolved = _resolve_generation_timeout_seconds()

    assert _MIN_GENERATION_TIMEOUT_SECONDS <= resolved <= _MAX_GENERATION_TIMEOUT_SECONDS
    assert resolved == _DEFAULT_TIMEOUT_SECONDS
    assert resolved < 60 * 20  # plafonné bien en dessous d'une veille de 20 min


@patch("ankiforge.services.settings_service.SettingsService.get")
def test_resolve_generation_timeout_clamps_absurd_values(mock_settings_get):
    """Des valeurs aberrantes du réglage (0, négatif, des millions) sont bornées, jamais désactivables."""
    from ankiforge.services.ai.flexible_service import (
        _DEFAULT_TIMEOUT_SECONDS,
        _MAX_GENERATION_TIMEOUT_SECONDS,
        _MIN_GENERATION_TIMEOUT_SECONDS,
        _resolve_generation_timeout_seconds,
    )

    mock_settings_get.return_value = 10**9
    assert _resolve_generation_timeout_seconds() == _MAX_GENERATION_TIMEOUT_SECONDS

    mock_settings_get.return_value = 0.001
    assert _resolve_generation_timeout_seconds() == _MIN_GENERATION_TIMEOUT_SECONDS

    mock_settings_get.return_value = -5.0
    assert _resolve_generation_timeout_seconds() == _DEFAULT_TIMEOUT_SECONDS

    mock_settings_get.return_value = "pas un nombre"
    assert _resolve_generation_timeout_seconds() == _DEFAULT_TIMEOUT_SECONDS


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_wraps_internal_typeerror(mock_openai_class):
    """Vérifie qu'un TypeError inattendu interne ne fuit JAMAIS sous forme de TypeError brut."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.side_effect = TypeError("Internal unexpected type error")

    provider = OpenAICompatibleProvider("https://fake", "test-model")
    with pytest.raises(RuntimeError) as exc_info:
        provider.generate("System", "User")

    assert "Erreur inattendue" in str(exc_info.value)
    assert not isinstance(exc_info.value, TypeError)


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_empty_content_stop_raises(mock_openai_class):
    """Une réponse vide avec finish_reason='stop' ne doit plus être renvoyée silencieusement."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_choice = MagicMock()
    mock_choice.message.refusal = None
    mock_choice.message.content = ""
    mock_choice.finish_reason = "stop"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice], usage=None)

    provider = OpenAICompatibleProvider("https://fake", "test-model")
    with pytest.raises(RuntimeError) as exc_info:
        provider.generate("System", "User")

    assert "réponse vide" in str(exc_info.value)
    assert "stop" in str(exc_info.value)


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_empty_content_null(mock_openai_class):
    """Une réponse avec message.content = None ne doit pas être renvoyée comme chaîne vide."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_choice = MagicMock()
    mock_choice.message.refusal = None
    mock_choice.message.content = None
    mock_choice.finish_reason = "stop"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice], usage=None)

    provider = OpenAICompatibleProvider("https://fake", "test-model")
    with pytest.raises(RuntimeError) as exc_info:
        provider.generate("System", "User")

    assert "réponse vide" in str(exc_info.value)


@patch("ankiforge.services.ai.flexible_service._extract_reasoning_tokens", return_value=(512, 512))
@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_reasoning_budget_consumed(mock_openai_class, mock_reasoning):
    """Cas OpenRouter documenté : le modèle reasoning a consommé tout le budget en raisonnement."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_choice = MagicMock()
    mock_choice.message.refusal = None
    mock_choice.message.content = ""
    mock_choice.finish_reason = "length"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice], usage=None)

    provider = OpenAICompatibleProvider("https://openrouter.ai/api/v1", "qwen/qwen3.8-27b:free")
    with pytest.raises(RuntimeError) as exc_info:
        provider.generate("System", "User")

    assert "raisonnement" in str(exc_info.value)
    assert "max_tokens" in str(exc_info.value)


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_reasoning_budget_untouched_keeps_finish_reason_error(mock_openai_class):
    """Sans tokens de raisonnement, un finish_reason 'length' conserve son message dédié."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_choice = MagicMock()
    mock_choice.message.refusal = None
    mock_choice.message.content = ""
    mock_choice.finish_reason = "length"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice], usage=None)

    provider = OpenAICompatibleProvider("https://fake", "test-model")
    with pytest.raises(RuntimeError) as exc_info:
        provider.generate("System", "User")

    assert "dépassement du quota de tokens" in str(exc_info.value)


@patch("ankiforge.services.ai.flexible_service._openrouter_max_output_tokens", return_value=4096)
@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_openrouter_clamps_max_tokens(mock_openai_class, mock_cap):
    """Le max_tokens demandé est borné au plafond réel de sortie du modèle OpenRouter."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_choice = MagicMock()
    mock_choice.message.refusal = None
    mock_choice.message.content = '{"reponse": "ok"}'
    mock_choice.finish_reason = "stop"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice], usage=None)

    provider = OpenAICompatibleProvider("https://openrouter.ai/api/v1", "qwen/qwen3.8-27b:free")
    provider.generate("System", "User")

    mock_cap.assert_called_once()
    _, kwargs = mock_client.chat.completions.create.call_args
    assert kwargs["max_tokens"] == 4096


@patch("ankiforge.services.ai.flexible_service._supports_response_format", return_value=False)
@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_json_mode_skipped_when_unsupported(mock_openai_class, mock_support):
    """Le mode json_object n'est pas expédié quand la passerelle ne le garantit pas."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_choice = MagicMock()
    mock_choice.message.refusal = None
    mock_choice.message.content = '{"reponse": "ok"}'
    mock_choice.finish_reason = "stop"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice], usage=None)

    provider = OpenAICompatibleProvider("https://openrouter.ai/api/v1", "some/model")
    provider.generate("System", "User")

    _, kwargs = mock_client.chat.completions.create.call_args
    assert "response_format" not in kwargs


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_o1_via_openrouter_uses_max_completion_tokens(mock_openai_class):
    """Une famille o1 via OpenRouter doit utiliser max_completion_tokens, même avec un slug complet."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_choice = MagicMock()
    mock_choice.message.refusal = None
    mock_choice.message.content = '{"reponse": "ok"}'
    mock_choice.finish_reason = "stop"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice], usage=None)

    provider = OpenAICompatibleProvider("https://openrouter.ai/api/v1", "openai/o1", max_tokens=32000)
    provider.generate("System", "User")

    _, kwargs = mock_client.chat.completions.create.call_args
    assert kwargs["max_completion_tokens"] == 32000
    assert "max_tokens" not in kwargs


def test_mock_provider_generate_response():
    """MockProvider.generate_response doit retourner un LLMResult structuré."""
    from ankiforge.services.ai.base import LLMResult, MockProvider

    provider = MockProvider()
    result = provider.generate_response("system", "user")
    assert isinstance(result, LLMResult)
    assert '"notes":' in result.content
    assert result.thought is None
    # generate() standard continue de retourner str
    assert provider.generate("system", "user") == result.content


def test_extract_thought_tags_cleans_content_and_extracts_reasoning():
    """extract_thought_tags retire les balises <think> et isole le texte de réflexion."""
    from ankiforge.services.ai.flexible_service import extract_thought_tags

    raw = '<think>\nAnalyser les faits du document\nFormuler une carte cloze\n</think>\n{"notes": [{"front": "Q", "back": "A"}]}'
    clean, thought = extract_thought_tags(raw)
    assert clean == '{"notes": [{"front": "Q", "back": "A"}]}'
    assert thought == "Analyser les faits du document\nFormuler une carte cloze"

    # Cas sans balise think
    clean2, thought2 = extract_thought_tags('{"notes": []}')
    assert clean2 == '{"notes": []}'
    assert thought2 is None

    # Cas avec thought initial fourni et pas de balise dans le texte
    clean3, thought3 = extract_thought_tags('{"notes": []}', initial_thought="Pensees API")
    assert clean3 == '{"notes": []}'
    assert thought3 == "Pensees API"


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_extracts_reasoning_content(mock_openai_class):
    """OpenAICompatibleProvider extrait le raisonnement natif (reasoning/reasoning_content)."""
    from ankiforge.services.ai.base import LLMResult
    from ankiforge.services.ai.flexible_service import OpenAICompatibleProvider

    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_choice = MagicMock()
    mock_choice.message.refusal = None
    mock_choice.message.content = '{"notes": []}'
    mock_choice.message.reasoning_content = "Réflexion DeepSeek détaillée"
    mock_choice.finish_reason = "stop"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice], usage=None)

    provider = OpenAICompatibleProvider("http://fake", "deepseek-r1")
    result = provider.generate_response("System", "User")

    assert isinstance(result, LLMResult)
    assert result.content == '{"notes": []}'
    assert result.thought == "Réflexion DeepSeek détaillée"


@patch("ankiforge.services.ai.flexible_service.OpenAI")
def test_openai_compatible_provider_extracts_and_strips_think_tags(mock_openai_class):
    """OpenAICompatibleProvider extrait et nettoie <think>...</think> du flux de contenu."""
    from ankiforge.services.ai.base import LLMResult
    from ankiforge.services.ai.flexible_service import OpenAICompatibleProvider

    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_choice = MagicMock()
    mock_choice.message.refusal = None
    mock_choice.message.content = '<think>Raisonnement Ollama</think>{"notes": [{"f": 1}]}'
    mock_choice.message.reasoning = None
    mock_choice.message.reasoning_content = None
    mock_choice.message.model_extra = {}
    mock_choice.finish_reason = "stop"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice], usage=None)

    provider = OpenAICompatibleProvider("http://localhost:11434/v1", "deepseek-r1:8b")
    result = provider.generate_response("System", "User")

    assert isinstance(result, LLMResult)
    assert result.content == '{"notes": [{"f": 1}]}'
    assert result.thought == "Raisonnement Ollama"
    # generate() doit aussi retourner le contenu nettoyé
    assert provider.generate("System", "User") == '{"notes": [{"f": 1}]}'


@patch("ankiforge.services.ai.flexible_service.requests.post")
def test_anthropic_provider_extracts_thinking_blocks(mock_post):
    """AnthropicProvider extrait les blocs 'thinking' et conserve le texte pur."""
    from ankiforge.services.ai.base import LLMResult
    from ankiforge.services.ai.flexible_service import AnthropicProvider

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "content": [
            {"type": "thinking", "thinking": "Claude thinking step by step"},
            {"type": "text", "text": '{"result": "ok"}'},
        ],
        "usage": {"input_tokens": 100, "output_tokens": 200},
    }
    mock_post.return_value = mock_response

    provider = AnthropicProvider(api_key="fake_key", model_name="claude-3-7-sonnet-20250219", thinking_budget=2048)
    result = provider.generate_response("System", "User")

    assert isinstance(result, LLMResult)
    assert result.content == '{"result": "ok"}'
    assert result.thought == "Claude thinking step by step"
    assert provider.generate("System", "User") == '{"result": "ok"}'


def test_gemini_service_extracts_thought_parts():
    """GeminiService extrait les parts de pensée (thought=True) et le contenu final."""
    from ankiforge.services.ai.base import LLMResult
    from ankiforge.services.ai.gemini_service import GeminiService

    provider = GeminiService(api_key="fake_gemini_key", model_name="gemini-2.0-flash-thinking-exp")
    mock_candidate = MagicMock()
    thought_part = MagicMock()
    thought_part.thought = True
    thought_part.text = "Pensée Gemini 2.0 Thinking"
    text_part = MagicMock()
    text_part.thought = False
    text_part.text = '{"cards": []}'
    mock_candidate.content.parts = [thought_part, text_part]

    mock_resp = MagicMock()
    mock_resp.candidates = [mock_candidate]
    mock_resp.text = '{"cards": []}'
    mock_resp.usage_metadata = MagicMock(prompt_token_count=50, candidates_token_count=150)

    with patch.object(provider.client.models, "generate_content", return_value=mock_resp):
        result = provider.generate_response("System", "User")
        assert isinstance(result, LLMResult)
        assert result.content == '{"cards": []}'
        assert result.thought == "Pensée Gemini 2.0 Thinking"
        assert provider.generate("System", "User") == '{"cards": []}'
