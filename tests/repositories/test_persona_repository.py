"""
Unit tests for PersonaRepository.
"""

from __future__ import annotations

from ankiforge.repositories.persona_repository import PersonaRepository


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
