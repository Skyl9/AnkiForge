"""
Repository for Persona Models, Persona Folders, Persona Versions, LLM Configs, and Prompts.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ankiforge.database.models import (
    LLMConfigModel,
    PersonaFolderModel,
    PersonaModel,
    PersonaVersionModel,
    PromptModel,
)
from ankiforge.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class PersonaRepository(BaseRepository):
    """Data access repository for AI Personas, folders, LLM engine configurations, and prompts."""

    def get_all_folders(self) -> list[PersonaFolderModel]:
        """Retrieve all persona folders."""
        return list(PersonaFolderModel.select().order_by(PersonaFolderModel.name.asc()))

    def get_folder_by_id(self, folder_id: int) -> PersonaFolderModel | None:
        """Retrieve a persona folder by ID."""
        try:
            return PersonaFolderModel.get_or_none(PersonaFolderModel.id == folder_id)
        except Exception as e:
            logger.error("Failed to get persona folder %s: %s", folder_id, e)
            return None

    def create_folder(self, name: str, parent: PersonaFolderModel | None = None) -> PersonaFolderModel:
        """Create a new persona folder."""
        with self.atomic():
            return PersonaFolderModel.create(name=name, parent=parent)

    def delete_folder(self, folder_id: int) -> bool:
        """Delete a persona folder and cascade."""
        folder = self.get_folder_by_id(folder_id)
        if not folder:
            return False

        with self.atomic():
            folder.delete_instance(recursive=True)
            return True

    def get_all_personas(
        self,
        folder_id: int | None = None,
        persona_type: str | None = None,
    ) -> list[PersonaModel]:
        """Retrieve all personas optionally filtered by folder or type."""
        query = PersonaModel.select().order_by(PersonaModel.name.asc())
        if folder_id is not None:
            query = query.where(PersonaModel.folder == folder_id)
        if persona_type is not None:
            query = query.where(PersonaModel.persona_type == persona_type)
        return list(query)

    def get_persona_by_id(self, persona_id: int) -> PersonaModel | None:
        """Retrieve a persona by ID."""
        try:
            return PersonaModel.get_or_none(PersonaModel.id == persona_id)
        except Exception as e:
            logger.error("Failed to get persona %s: %s", persona_id, e)
            return None

    def get_persona_by_name(self, name: str) -> PersonaModel | None:
        """Retrieve a persona by its unique name."""
        try:
            return PersonaModel.get_or_none(PersonaModel.name == name)
        except Exception as e:
            logger.error("Failed to get persona by name '%s': %s", name, e)
            return None

    def create_persona(
        self,
        name: str,
        system_prompt: str,
        description: str | None = None,
        output_format: str = "json",
        persona_type: str = "pipeline",
        folder: PersonaFolderModel | None = None,
        allowed_tools: list[str] | None = None,
        llm_config: LLMConfigModel | None = None,
    ) -> PersonaModel:
        """Create a new persona and its initial version snapshot."""
        tools_str = json.dumps(allowed_tools or [])
        with self.atomic():
            persona = PersonaModel.create(
                name=name,
                system_prompt=system_prompt,
                description=description,
                output_format=output_format,
                persona_type=persona_type,
                folder=folder,
                allowed_tools=tools_str,
                llm_config=llm_config,
            )
            PersonaVersionModel.create(
                persona=persona,
                version_number=1,
                system_prompt=system_prompt,
                description=description,
                output_format=output_format,
                persona_type=persona_type,
                allowed_tools=tools_str,
                llm_config=llm_config,
                commit_message="Initial persona version",
                is_active=True,
            )
            return persona

    def update_persona(self, persona_id: int, **kwargs: Any) -> PersonaModel | None:
        """Update fields of an existing persona."""
        persona = self.get_persona_by_id(persona_id)
        if not persona:
            return None

        with self.atomic():
            for key, val in kwargs.items():
                if hasattr(persona, key):
                    if key == "allowed_tools" and isinstance(val, list):
                        setattr(persona, key, json.dumps(val))
                    else:
                        setattr(persona, key, val)
            persona.save()
            return persona

    def delete_persona(self, persona_id: int) -> bool:
        """Delete a persona and cascade to its versions."""
        persona = self.get_persona_by_id(persona_id)
        if not persona:
            return False

        with self.atomic():
            persona.delete_instance(recursive=True)
            return True

    def get_all_llm_configs(self) -> list[LLMConfigModel]:
        """Retrieve all LLM engine configurations."""
        return list(LLMConfigModel.select().order_by(LLMConfigModel.display_name.asc()))

    def get_llm_config_by_id(self, config_id: int) -> LLMConfigModel | None:
        """Retrieve an LLM configuration by ID."""
        try:
            return LLMConfigModel.get_or_none(LLMConfigModel.id == config_id)
        except Exception as e:
            logger.error("Failed to get LLM config %s: %s", config_id, e)
            return None

    def get_llm_config_by_display_name(self, name: str) -> LLMConfigModel | None:
        """Retrieve an LLM configuration by display name."""
        try:
            return LLMConfigModel.get_or_none(LLMConfigModel.display_name == name)
        except Exception as e:
            logger.error("Failed to get LLM config by name '%s': %s", name, e)
            return None

    def create_llm_config(
        self,
        display_name: str,
        provider: str,
        model_id: str,
        context_limit: int = 8192,
        temperature: float = 0.7,
        api_key: str | None = None,
        prompt_pricing: float = 0.0,
        completion_pricing: float = 0.0,
        is_free: bool = False,
    ) -> LLMConfigModel:
        """Create a new LLM configuration."""
        with self.atomic():
            return LLMConfigModel.create(
                display_name=display_name,
                provider=provider,
                model_id=model_id,
                context_limit=context_limit,
                temperature=temperature,
                api_key=api_key,
                prompt_pricing=prompt_pricing,
                completion_pricing=completion_pricing,
                is_free=is_free,
            )

    def update_llm_config(self, config_id: int, **kwargs: Any) -> LLMConfigModel | None:
        """Update an existing LLM configuration."""
        config = self.get_llm_config_by_id(config_id)
        if not config:
            return None

        with self.atomic():
            for key, val in kwargs.items():
                if hasattr(config, key):
                    setattr(config, key, val)
            config.save()
            return config

    def delete_llm_config(self, config_id: int) -> bool:
        """Delete an LLM configuration."""
        config = self.get_llm_config_by_id(config_id)
        if not config:
            return False

        with self.atomic():
            config.delete_instance()
            return True

    def get_all_prompts(self) -> list[PromptModel]:
        """Retrieve all prompt templates."""
        return list(PromptModel.select().order_by(PromptModel.name.asc()))

    def get_prompt_by_name(self, name: str) -> PromptModel | None:
        """Retrieve a prompt template by name."""
        try:
            return PromptModel.get_or_none(PromptModel.name == name)
        except Exception as e:
            logger.error("Failed to get prompt by name '%s': %s", name, e)
            return None
