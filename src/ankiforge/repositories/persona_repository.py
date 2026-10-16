"""Dépôt des modèles de persona, des dossiers de persona, des versions de persona, des configurations LLM et des prompts."""

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
from ankiforge.services.ai.model_catalog import ModelCatalog

logger = logging.getLogger(__name__)


class PersonaRepository(BaseRepository):
    """Dépôt d'accès aux données des personas IA, des dossiers, des configurations de moteur LLM et des prompts."""

    def get_all_folders(self) -> list[PersonaFolderModel]:
        """Retourne tous les dossiers de persona."""
        return list(PersonaFolderModel.select().order_by(PersonaFolderModel.name.asc()))

    def get_folder_by_id(self, folder_id: int) -> PersonaFolderModel | None:
        """Retourne un dossier de persona par son ID."""
        try:
            return PersonaFolderModel.get_or_none(PersonaFolderModel.id == folder_id)
        except Exception as e:
            logger.error("Failed to get persona folder %s: %s", folder_id, e)
            return None

    def create_folder(self, name: str, parent: PersonaFolderModel | None = None) -> PersonaFolderModel:
        """Crée un nouveau dossier de persona."""
        with self.atomic():
            return PersonaFolderModel.create(name=name, parent=parent)

    def delete_folder(self, folder_id: int) -> bool:
        """Supprime un dossier de persona et propage en cascade."""
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
        """Retourne toutes les personas, éventuellement filtrées par dossier ou par type."""
        query = PersonaModel.select().order_by(PersonaModel.name.asc())
        if folder_id is not None:
            query = query.where(PersonaModel.folder == folder_id)
        if persona_type is not None:
            query = query.where(PersonaModel.persona_type == persona_type)
        return list(query)

    def get_persona_by_id(self, persona_id: int) -> PersonaModel | None:
        """Retourne une persona par son ID."""
        try:
            return PersonaModel.get_or_none(PersonaModel.id == persona_id)
        except Exception as e:
            logger.error("Failed to get persona %s: %s", persona_id, e)
            return None

    def get_persona_by_name(self, name: str) -> PersonaModel | None:
        """Retourne une persona par son nom unique."""
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
        """Crée une nouvelle persona et son instantané de version initial."""
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
        """Met à jour les champs d'une persona existante."""
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
        """Supprime une persona et propage en cascade à ses versions."""
        persona = self.get_persona_by_id(persona_id)
        if not persona:
            return False

        with self.atomic():
            persona.delete_instance(recursive=True)
            return True

    def get_all_llm_configs(self) -> list[LLMConfigModel]:
        """Retourne toutes les configurations de moteur LLM."""
        return list(LLMConfigModel.select().order_by(LLMConfigModel.sort_order.asc(), LLMConfigModel.display_name.asc()))

    def get_llm_config_by_id(self, config_id: int) -> LLMConfigModel | None:
        """Retourne une configuration LLM par son ID."""
        try:
            return LLMConfigModel.get_or_none(LLMConfigModel.id == config_id)
        except Exception as e:
            logger.error("Failed to get LLM config %s: %s", config_id, e)
            return None

    def get_llm_config_by_display_name(self, name: str) -> LLMConfigModel | None:
        """Retourne une configuration LLM par son nom d'affichage."""
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
        context_limit: int = 128000,
        max_tokens: int = 16384,
        sort_order: int = 100,
        temperature: float = 0.7,
        api_key: str | None = None,
        prompt_pricing: float = 0.0,
        completion_pricing: float = 0.0,
        is_free: bool = False,
        supports_vision: bool | None = None,
    ) -> LLMConfigModel:
        """Crée une nouvelle configuration LLM.

        Les capacités (Vision, Thinking, JSON…) sont déduites du catalogue au moment de la création,
        sauf valeur imposée — un moteur local détecté avec un projecteur CLIP, que le catalogue hors
        ligne ignore, doit pouvoir déclarer sa Vision. Le catalogue est donc l'**écrivain** de ces
        colonnes : la lecture n'y revient jamais (voir `vision_capability.resolve_vision_support`).

        Seul un modèle dont la Vision est *prouvée* est enregistré comme tel : voir
        `ModelCatalog.declares_vision`, seule politique d'écriture. Un modèle hébergé absent du
        catalogue reste « texte seul » — un remède existe (ajouter sa fiche à `CURATED_MODELS`), mais
        il est hors de portée de l'utilisateur, d'où le choix de l'honnêteté sur l'optimisme.
        """
        spec = ModelCatalog.get_declared_capabilities(provider, model_id)
        vision = supports_vision if supports_vision is not None else ModelCatalog.declares_vision(provider, model_id)

        fields: dict[str, Any] = {"supports_vision": vision}
        if spec is not None:
            fields |= {
                "supports_thinking": spec.supports_thinking,
                "supports_json": spec.supports_json,
                "speed_rating": spec.speed_rating,
                "quality_tier": spec.quality_tier,
                "recommended_tasks": json.dumps(spec.recommended_tasks),
                "description": spec.description,
            }

        with self.atomic():
            return LLMConfigModel.create(
                display_name=display_name,
                provider=provider,
                model_id=model_id,
                context_limit=context_limit,
                max_tokens=max_tokens,
                sort_order=sort_order,
                temperature=temperature,
                api_key=api_key,
                prompt_pricing=prompt_pricing,
                completion_pricing=completion_pricing,
                is_free=is_free,
                **fields,
            )

    def update_llm_config(self, config_id: int, **kwargs: Any) -> LLMConfigModel | None:
        """Met à jour une configuration LLM existante."""
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
        """Supprime une configuration LLM."""
        config = self.get_llm_config_by_id(config_id)
        if not config:
            return False

        with self.atomic():
            config.delete_instance()
            return True

    def get_all_prompts(self) -> list[PromptModel]:
        """Retourne tous les modèles de prompt."""
        return list(PromptModel.select().order_by(PromptModel.name.asc()))

    def get_prompt_by_name(self, name: str) -> PromptModel | None:
        """Retourne un modèle de prompt par son nom."""
        try:
            return PromptModel.get_or_none(PromptModel.name == name)
        except Exception as e:
            logger.error("Failed to get prompt by name '%s': %s", name, e)
            return None
