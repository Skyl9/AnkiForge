"""
Unit tests for PersonaRepository.
"""

from __future__ import annotations

import pytest

from ankiforge.repositories.persona_repository import PersonaRepository

pytestmark = pytest.mark.integration


def test_persona_repository_crud() -> None:
    repo = PersonaRepository()

    # LLM Config
    llm = repo.create_llm_config(
        display_name="GPT-4o",
        provider="openai",
        model_id="gpt-4o",
        context_limit=128000,
    )
    assert repo.get_llm_config_by_id(llm.id) is not None
    assert repo.get_llm_config_by_display_name("GPT-4o") is not None
    assert len(repo.get_all_llm_configs()) == 1

    # Folder
    folder = repo.create_folder("Science Personas")
    assert repo.get_folder_by_id(folder.id) is not None
    assert len(repo.get_all_folders()) == 1

    # Persona
    persona = repo.create_persona(
        name="Physics Professor",
        system_prompt="You are an expert in classical mechanics.",
        description="Generates physics cards",
        folder=folder,
        llm_config=llm,
        allowed_tools=["query_peewee"],
    )
    assert persona is not None
    assert repo.get_persona_by_id(persona.id) is not None
    assert repo.get_persona_by_name("Physics Professor") is not None
    assert len(repo.get_all_personas(folder_id=folder.id)) == 1

    # Update persona
    updated = repo.update_persona(persona.id, description="Updated description")
    assert updated is not None
    assert updated.description == "Updated description"

    # Delete persona
    deleted = repo.delete_persona(persona.id)
    assert deleted is True
    assert repo.get_persona_by_id(persona.id) is None


def test_create_llm_config_backfills_capabilities_from_the_catalog() -> None:
    """Sans valeur imposée, la ligne hérite du catalogue : un moteur multimodal ne doit pas
    rester « texte seul » sous le seul effet du défaut SQLite `supports_vision = False`."""
    repo = PersonaRepository()

    vision = repo.create_llm_config(display_name="Backfill Vision", provider="openai", model_id="gpt-4o")
    assert vision.supports_vision is True

    text_only = repo.create_llm_config(display_name="Backfill Texte", provider="openai", model_id="o1-mini")
    assert text_only.supports_vision is False


def test_create_llm_config_honours_an_explicit_capability() -> None:
    """Une capacité imposée (Ollama détecté avec un projecteur CLIP) prime sur le catalogue."""
    repo = PersonaRepository()

    engine = repo.create_llm_config(
        display_name="Qwen2-VL local",
        provider="ollama",
        model_id="qwen2-vl:7b",
        supports_vision=True,
    )
    assert engine.supports_vision is True
