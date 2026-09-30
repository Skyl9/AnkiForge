"""Tests unitaires pour le catalogue de modèles LLM et la détection de capacités."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from ankiforge.services.ai.model_catalog import (
    ModelCatalog,
)

pytestmark = pytest.mark.unit


def test_curated_models_not_empty():
    """Vérifie que la liste des modèles sélectionnés contient les références majeures 2025-2026."""
    models = ModelCatalog.get_curated_catalog()
    assert len(models) >= 8

    providers = {m.provider for m in models}
    assert "gemini" in providers
    assert "anthropic" in providers
    assert "openai" in providers
    assert "groq" in providers


def test_get_model_spec():
    """Vérifie la récupération d'un modèle connu et l'inférence pour un modèle custom."""
    # Modèle exact
    spec = ModelCatalog.get_model_spec("gemini", "gemini-3.5-flash-lite")
    assert spec is not None
    assert spec.provider == "gemini"
    assert spec.supports_vision is True
    assert spec.context_window >= 1_000_000

    # Claude 3.7 Sonnet
    claude = ModelCatalog.get_model_spec("anthropic", "claude-3-7-sonnet-20250219")
    assert claude is not None
    assert claude.supports_thinking is True

    # Modèle inconnu / personnalisé : inférence automatique
    unknown = ModelCatalog.get_model_spec("custom", "non-existent")
    assert unknown is not None
    assert unknown.provider == "custom"
    assert unknown.model_id == "non-existent"


def test_recommend_models_for_task():
    """Vérifie le moteur de recommandation par cas d'usage métier AnkiForge."""
    # Flashcards atomiques
    flashcard_models = ModelCatalog.recommend_models_for_task("flashcards")
    assert len(flashcard_models) > 0
    assert any("flashcards" in m.recommended_tasks for m in flashcard_models)

    # Schémas et figures (requiert vision)
    diagram_models = ModelCatalog.recommend_models_for_task("vision")
    assert len(diagram_models) > 0
    assert all(m.supports_vision for m in diagram_models)

    # Wozniak (raisonnement / qualité)
    wozniak_models = ModelCatalog.recommend_models_for_task("audit")
    assert len(wozniak_models) > 0
    assert any(m.supports_thinking or m.quality_tier == "flagship" for m in wozniak_models)


def test_detect_ollama_model_capabilities_multimodal():
    """Vérifie la détection automatique des capacités Ollama pour un modèle multimodal (LLaVA)."""
    fake_show_response = {
        "model_info": {
            "llama.context_length": 8192,
            "clip.projector_type": "mlp",  # Indique la vision
        },
        "template": "{{ .Prompt }}",
    }

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps(fake_show_response).encode()
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        caps = ModelCatalog.detect_ollama_model_capabilities("http://localhost:11434", "llava:7b")

    assert caps.supports_vision is True
    assert caps.supports_thinking is False
    assert caps.context_window == 8192
    assert "vision" in caps.recommended_tasks


def test_detect_ollama_model_capabilities_reasoning():
    """Vérifie la détection d'un modèle de raisonnement CoT (DeepSeek-R1 / QwQ)."""
    fake_show_response = {
        "model_info": {
            "llama.context_length": 32768,
        },
        "template": "{{ if .System }}<think>{{ .System }}</think>{{ end }} {{ .Prompt }}",
    }

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps(fake_show_response).encode()
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        caps = ModelCatalog.detect_ollama_model_capabilities("http://localhost:11434", "deepseek-r1:8b")

    assert caps.supports_thinking is True
    assert caps.supports_vision is False
    assert caps.context_window == 32768
    assert "reasoning" in caps.recommended_tasks


def test_detect_ollama_offline_fallback():
    """Vérifie le comportement gracieux de repli si Ollama est injoignable."""
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        caps = ModelCatalog.detect_ollama_model_capabilities("http://localhost:11434", "llama3.2-vision")

    # Détection par heuristique de nom
    assert caps.supports_vision is True
    assert caps.supports_json is True
    assert caps.context_window == 8192


def test_opencode_and_openrouter_models_in_catalog():
    """Vérifie la présence et la gratuité des modèles OpenCode et OpenRouter Free."""
    # Modèle OpenCode vérifié
    opencode_spec = ModelCatalog.get_model_spec("opencode", "deepseek-v4-flash")
    assert opencode_spec is not None
    assert opencode_spec.provider == "opencode"
    assert opencode_spec.model_id == "deepseek-v4-flash"
    assert opencode_spec.speed_rating == "ultra-fast"

    # Modèle OpenRouter gratuit vérifié
    openrouter_spec = ModelCatalog.get_model_spec("openrouter", "qwen/qwen3.8-27b:free")
    assert openrouter_spec is not None
    assert openrouter_spec.is_free is True
    assert openrouter_spec.prompt_pricing == 0.0
    assert openrouter_spec.completion_pricing == 0.0

    # Inférence automatique pour tout modèle se terminant par :free
    inferred_free = ModelCatalog.get_model_spec("openrouter", "meta-llama/llama-3.3-70b-instruct:free")
    assert inferred_free.is_free is True
    assert inferred_free.prompt_pricing == 0.0


def test_get_declared_capabilities_refuses_approximate_matching():
    """La correspondance exacte refuse l'appariement de `get_model_spec`, qui ignore le fournisseur.

    `get_model_spec("azure-openai", "gpt-4o")` recopie la fiche OpenAI — capacités **et** tarifs —
    alors qu'aucune paire (fournisseur, modèle) de ce nom n'est curatée. C'est acceptable pour
    découvrir un modèle dans une liste déroulante, pas pour écrire une affirmation en base.
    """
    assert ModelCatalog.get_declared_capabilities("openai", "gpt-4o") is not None
    assert ModelCatalog.get_declared_capabilities("openai", "o1") is not None

    assert ModelCatalog.get_model_spec("azure-openai", "gpt-4o").supports_vision is True  # l'approximation
    assert ModelCatalog.get_declared_capabilities("azure-openai", "gpt-4o") is None  # la déclaration


def test_declares_vision_requires_evidence():
    """Un fournisseur hébergé non catalogué reste « texte seul » : une affirmation false coûte une erreur d'API."""
    assert ModelCatalog.declares_vision("openai", "gpt-4o") is True
    assert ModelCatalog.declares_vision("openai", "o1-mini") is False  # texte, malgré le voisin multimodal `o1`
    assert ModelCatalog.declares_vision("openai", "gpt-5-vision-preview") is False  # absent du catalogue
    # Même inférence par nom, mais un fournisseur hors catalogue : la preuve n'existe pas.
    assert ModelCatalog.get_model_spec("azure-openai", "gpt-4o").supports_vision is True
    assert ModelCatalog.declares_vision("azure-openai", "gpt-4o") is False


def test_declares_vision_keeps_named_local_multimodal_models():
    """Hors ligne, le nom est le seul signal pour un VLM local : on ne doit pas le perdre."""
    assert ModelCatalog.is_local_provider("ollama") is True
    assert ModelCatalog.is_local_provider("http://localhost:11434") is True
    assert ModelCatalog.is_local_provider("openai") is False

    assert ModelCatalog.declares_vision("ollama", "qwen2-vl:7b") is True
    assert ModelCatalog.declares_vision("ollama", "bakllava:13b") is True
    assert ModelCatalog.declares_vision("ollama", "llama3.2-vision") is True
    assert ModelCatalog.declares_vision("ollama", "deepseek-r1:8b") is False
