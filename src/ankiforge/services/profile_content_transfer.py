"""Import de personas et de pipelines entre profils AnkiForge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from peewee import SqliteDatabase

from ankiforge.database.models import (
    LLMConfigModel,
    PersonaFolderModel,
    PersonaModel,
    PersonaVersionModel,
    PipelineModel,
    PipelineStepModel,
)
from ankiforge.services.profile_manager import ProfileManager


class ProfileContentTransfer:
    """Transfère du contenu entre bases de profils sans changer la base active."""

    _source_models = [
        LLMConfigModel,
        PersonaFolderModel,
        PersonaModel,
        PersonaVersionModel,
        PipelineModel,
        PipelineStepModel,
    ]

    @staticmethod
    def list_personas(profile_name: str, profiles_dir: Path | None = None) -> list[str]:
        with ProfileContentTransfer._source_database(profile_name, profiles_dir) as source_db, source_db.bind_ctx(ProfileContentTransfer._source_models):
            return [str(p.name) for p in PersonaModel.select().order_by(PersonaModel.name.asc())]

    @staticmethod
    def list_pipelines(profile_name: str, profiles_dir: Path | None = None) -> list[str]:
        with ProfileContentTransfer._source_database(profile_name, profiles_dir) as source_db, source_db.bind_ctx(ProfileContentTransfer._source_models):
            return [str(p.name) for p in PipelineModel.select().order_by(PipelineModel.name.asc())]

    @staticmethod
    def import_persona(
        profile_name: str,
        persona_name: str,
        profiles_dir: Path | None = None,
    ) -> PersonaModel:
        with ProfileContentTransfer._source_database(profile_name, profiles_dir) as source_db, source_db.bind_ctx(ProfileContentTransfer._source_models):
            source = PersonaModel.get_or_none(PersonaModel.name == persona_name)
            if source is None:
                raise ValueError(f"Agent introuvable dans le profil '{profile_name}' : {persona_name}")
            payload = ProfileContentTransfer._persona_payload(source)

        return ProfileContentTransfer._create_persona(payload, force_copy=True)

    @staticmethod
    def import_pipeline(
        profile_name: str,
        pipeline_name: str,
        profiles_dir: Path | None = None,
    ) -> PipelineModel:
        with ProfileContentTransfer._source_database(profile_name, profiles_dir) as source_db, source_db.bind_ctx(ProfileContentTransfer._source_models):
            source = PipelineModel.get_or_none(PipelineModel.name == pipeline_name)
            if source is None:
                raise ValueError(f"Pipeline introuvable dans le profil '{profile_name}' : {pipeline_name}")
            payload = ProfileContentTransfer._pipeline_payload(source)

        personas: dict[str, PersonaModel] = {}
        for persona_payload in payload["personas"]:
            persona_name = str(persona_payload["name"])
            existing = PersonaModel.get_or_none(PersonaModel.name == persona_name)
            personas[persona_name] = existing or ProfileContentTransfer._create_persona(persona_payload, force_copy=False)

        name = ProfileContentTransfer._available_name(str(payload["name"]), PipelineModel)
        with PipelineModel._meta.database.atomic():
            pipeline = PipelineModel.create(name=name, description=payload["description"])
            created_steps: dict[int, PipelineStepModel] = {}
            for index, step in enumerate(payload["steps"], start=1):
                created_steps[index] = PipelineStepModel.create(
                    pipeline=pipeline,
                    persona=personas.get(step["persona_name"]) if step["persona_name"] else None,
                    step_order=index,
                    step_type=step["step_type"],
                    failure_behavior=step["failure_behavior"],
                    config_data=json.dumps(step["config"]),
                )
            for index, step in enumerate(payload["steps"], start=1):
                updates: dict[str, PipelineStepModel] = {}
                success_order = step["on_success_order"]
                failure_order = step["on_failure_order"]
                if isinstance(success_order, int) and success_order in created_steps:
                    updates["on_success_step"] = created_steps[success_order]
                if isinstance(failure_order, int) and failure_order in created_steps:
                    updates["on_failure_step"] = created_steps[failure_order]
                if updates:
                    PipelineStepModel.update(updates).where(PipelineStepModel.id == created_steps[index].id).execute()
        return pipeline

    @staticmethod
    def _source_database(profile_name: str, profiles_dir: Path | None) -> SqliteDatabase:
        manager = ProfileManager()
        if profiles_dir is not None:
            manager.profiles_dir = profiles_dir
        db_path = manager.get_db_path(profile_name)
        if not db_path.is_file():
            raise FileNotFoundError(f"Base du profil introuvable : {profile_name}")
        return SqliteDatabase(str(db_path), timeout=30, pragmas={"foreign_keys": 1})

    @staticmethod
    def _persona_payload(persona: PersonaModel) -> dict[str, Any]:
        folder_chain: list[dict[str, Any]] = []
        folder = persona.folder
        while folder is not None:
            folder_chain.append({"name": str(folder.name), "parent_index": len(folder_chain) - 1})
            folder = folder.parent
        folder_chain.reverse()

        llm = persona.llm_config
        versions = [
            {
                "version_number": int(version.version_number),
                "system_prompt": str(version.system_prompt),
                "description": version.description,
                "output_format": str(version.output_format),
                "persona_type": str(version.persona_type),
                "allowed_tools": str(version.allowed_tools),
                "commit_message": str(version.commit_message),
                "is_active": bool(version.is_active),
            }
            for version in PersonaVersionModel.select().where(PersonaVersionModel.persona == persona).order_by(PersonaVersionModel.version_number.asc())
        ]
        return {
            "name": str(persona.name),
            "description": persona.description,
            "system_prompt": str(persona.system_prompt),
            "output_format": str(persona.output_format),
            "persona_type": str(persona.persona_type),
            "allowed_tools": str(persona.allowed_tools),
            "folder_chain": folder_chain,
            "llm": (
                {
                    "display_name": str(llm.display_name),
                    "provider": str(llm.provider),
                    "model_id": str(llm.model_id),
                    "context_limit": int(llm.context_limit),
                    "temperature": float(llm.temperature),
                    "prompt_pricing": float(llm.prompt_pricing),
                    "completion_pricing": float(llm.completion_pricing),
                    "is_free": bool(llm.is_free),
                }
                if llm is not None
                else None
            ),
            "versions": versions,
        }

    @staticmethod
    def _pipeline_payload(pipeline: PipelineModel) -> dict[str, Any]:
        steps = list(PipelineStepModel.select().where(PipelineStepModel.pipeline == pipeline).order_by(PipelineStepModel.step_order.asc()))
        persona_payloads: dict[str, dict[str, Any]] = {}
        step_payloads: list[dict[str, Any]] = []
        for step in steps:
            persona_name = str(step.persona.name) if step.persona else None
            if step.persona is not None and persona_name is not None and persona_name not in persona_payloads:
                persona_payloads[persona_name] = ProfileContentTransfer._persona_payload(step.persona)
            try:
                config = json.loads(step.config_data or "{}")
            except (TypeError, json.JSONDecodeError):
                config = {}
            step_payloads.append(
                {
                    "persona_name": persona_name,
                    "step_type": str(step.step_type),
                    "failure_behavior": str(step.failure_behavior),
                    "config": config,
                    "on_success_order": int(step.on_success_step.step_order) if step.on_success_step else None,
                    "on_failure_order": int(step.on_failure_step.step_order) if step.on_failure_step else None,
                }
            )
        return {
            "name": str(pipeline.name),
            "description": pipeline.description,
            "steps": step_payloads,
            "personas": list(persona_payloads.values()),
        }

    @staticmethod
    def _create_persona(payload: dict[str, Any], force_copy: bool) -> PersonaModel:
        database = PersonaModel._meta.database
        with database.atomic():
            name = ProfileContentTransfer._available_name(str(payload["name"]), PersonaModel) if force_copy else str(payload["name"])
            folder = None
            for folder_data in payload["folder_chain"]:
                query = PersonaFolderModel.select().where((PersonaFolderModel.name == folder_data["name"]) & (PersonaFolderModel.parent == folder))
                folder = query.get_or_none() or PersonaFolderModel.create(name=folder_data["name"], parent=folder)

            llm = None
            llm_data = payload["llm"]
            if llm_data:
                llm = LLMConfigModel.get_or_none(LLMConfigModel.display_name == llm_data["display_name"])
                if llm is None:
                    llm = LLMConfigModel.create(api_key=None, **llm_data)

            persona = PersonaModel.create(
                name=name,
                description=payload["description"],
                system_prompt=payload["system_prompt"],
                output_format=payload["output_format"],
                persona_type=payload["persona_type"],
                folder=folder,
                allowed_tools=payload["allowed_tools"],
                llm_config=llm,
            )
            versions = payload["versions"] or [
                {
                    "version_number": 1,
                    "system_prompt": payload["system_prompt"],
                    "description": payload["description"],
                    "output_format": payload["output_format"],
                    "persona_type": payload["persona_type"],
                    "allowed_tools": payload["allowed_tools"],
                    "commit_message": "Import depuis un autre profil",
                    "is_active": True,
                }
            ]
            for version in versions:
                PersonaVersionModel.create(persona=persona, **version, llm_config=llm)
        return persona

    @staticmethod
    def _available_name(base_name: str, model: Any) -> str:
        name = base_name
        counter = 1
        while model.get_or_none(model.name == name) is not None:
            name = f"{base_name} (Importé {counter})"
            counter += 1
        return name
