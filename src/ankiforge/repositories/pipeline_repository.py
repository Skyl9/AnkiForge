"""
Repository for DAG Pipelines, Pipeline Steps, and Python Tools.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ankiforge.database.models import (
    PersonaModel,
    PipelineModel,
    PipelineStepModel,
    PythonToolModel,
)
from ankiforge.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class PipelineRepository(BaseRepository):
    """Data access repository for DAG pipelines and deterministic Python tools."""

    def get_all_pipelines(self) -> list[PipelineModel]:
        """Retrieve all pipelines ordered alphabetically."""
        return list(PipelineModel.select().order_by(PipelineModel.name.asc()))

    def get_pipeline_by_id(self, pipeline_id: int) -> PipelineModel | None:
        """Retrieve a pipeline by its ID."""
        try:
            return PipelineModel.get_or_none(PipelineModel.id == pipeline_id)
        except Exception as e:
            logger.error("Failed to get pipeline %s: %s", pipeline_id, e)
            return None

    def get_pipeline_by_name(self, name: str) -> PipelineModel | None:
        """Retrieve a pipeline by its name."""
        try:
            return PipelineModel.get_or_none(PipelineModel.name == name)
        except Exception as e:
            logger.error("Failed to get pipeline by name '%s': %s", name, e)
            return None

    def create_pipeline(self, name: str, description: str = "") -> PipelineModel:
        """Create a new empty pipeline."""
        with self.atomic():
            return PipelineModel.create(name=name, description=description)

    def update_pipeline(self, pipeline_id: int, **kwargs: Any) -> PipelineModel | None:
        """Update fields of an existing pipeline."""
        pipeline = self.get_pipeline_by_id(pipeline_id)
        if not pipeline:
            return None

        with self.atomic():
            for key, val in kwargs.items():
                if hasattr(pipeline, key):
                    setattr(pipeline, key, val)
            pipeline.save()
            return pipeline

    def delete_pipeline(self, pipeline_id: int) -> bool:
        """Delete a pipeline and cascade delete all its steps."""
        pipeline = self.get_pipeline_by_id(pipeline_id)
        if not pipeline:
            return False

        with self.atomic():
            pipeline.delete_instance(recursive=True)
            return True

    def duplicate_pipeline(self, pipeline_id: int, new_name: str) -> PipelineModel | None:
        """Duplicate an existing pipeline with all its steps and transitions."""
        src_pipeline = self.get_pipeline_by_id(pipeline_id)
        if not src_pipeline:
            return None

        with self.atomic():
            new_pipeline = PipelineModel.create(
                name=new_name,
                description=src_pipeline.description,
            )
            old_steps = self.get_steps_for_pipeline(pipeline_id)
            id_mapping: dict[int, PipelineStepModel] = {}
            for step in old_steps:
                new_step = PipelineStepModel.create(
                    pipeline=new_pipeline,
                    persona=step.persona,
                    step_order=step.step_order,
                    step_type=step.step_type,
                    failure_behavior=step.failure_behavior,
                    config_data=step.config_data,
                )
                id_mapping[step.id] = new_step

            # Wire successor links
            for step in old_steps:
                new_step = id_mapping[step.id]
                needs_save = False
                if step.on_success_step and step.on_success_step.id in id_mapping:
                    new_step.on_success_step = id_mapping[step.on_success_step.id]
                    needs_save = True
                if step.on_failure_step and step.on_failure_step.id in id_mapping:
                    new_step.on_failure_step = id_mapping[step.on_failure_step.id]
                    needs_save = True
                if needs_save:
                    new_step.save()

            return new_pipeline

    def get_steps_for_pipeline(self, pipeline_id: int) -> list[PipelineStepModel]:
        """Retrieve steps for a pipeline ordered by step_order."""
        return list(PipelineStepModel.select().where(PipelineStepModel.pipeline == pipeline_id).order_by(PipelineStepModel.step_order.asc()))

    def create_step(
        self,
        pipeline: PipelineModel,
        step_order: int,
        step_type: str = "LLM_PROMPT",
        persona: PersonaModel | None = None,
        failure_behavior: str = "stop",
        config_data: str | dict[str, Any] = "{}",
    ) -> PipelineStepModel:
        """Create and append a new step to a pipeline."""
        config_str = json.dumps(config_data) if isinstance(config_data, dict) else config_data
        with self.atomic():
            return PipelineStepModel.create(
                pipeline=pipeline,
                persona=persona,
                step_order=step_order,
                step_type=step_type,
                failure_behavior=failure_behavior,
                config_data=config_str,
            )

    def update_step(self, step_id: int, **kwargs: Any) -> PipelineStepModel | None:
        """Update properties of a pipeline step."""
        try:
            step = PipelineStepModel.get_or_none(PipelineStepModel.id == step_id)
        except Exception:
            return None

        if not step:
            return None

        with self.atomic():
            for key, val in kwargs.items():
                if hasattr(step, key):
                    if key == "config_data" and isinstance(val, dict):
                        setattr(step, key, json.dumps(val))
                    else:
                        setattr(step, key, val)
            step.save()
            return step

    def delete_step(self, step_id: int) -> bool:
        """Delete a step and re-index following steps."""
        try:
            step = PipelineStepModel.get_or_none(PipelineStepModel.id == step_id)
        except Exception:
            return False

        if not step:
            return False

        pipeline_ref = step.pipeline
        pipeline_id = int(pipeline_ref.id) if isinstance(pipeline_ref, PipelineModel) else int(pipeline_ref)
        with self.atomic():
            step.delete_instance()
            remaining_steps = self.get_steps_for_pipeline(pipeline_id)
            for idx, st in enumerate(remaining_steps, start=1):
                if st.step_order != idx:
                    st.step_order = idx
                    st.save()
            return True

    def reorder_steps(self, pipeline_id: int, step_ids_order: list[int]) -> None:
        """Reorder steps according to a list of step IDs."""
        with self.atomic():
            # Step 1: assign temporary negative orders to prevent UNIQUE constraint conflict
            for idx, step_id in enumerate(step_ids_order, start=1):
                PipelineStepModel.update(step_order=-idx).where((PipelineStepModel.id == step_id) & (PipelineStepModel.pipeline == pipeline_id)).execute()
            # Step 2: assign positive target orders
            for new_order, step_id in enumerate(step_ids_order, start=1):
                PipelineStepModel.update(step_order=new_order).where((PipelineStepModel.id == step_id) & (PipelineStepModel.pipeline == pipeline_id)).execute()

    def get_all_python_tools(self) -> list[PythonToolModel]:
        """Retrieve all python tools."""
        return list(PythonToolModel.select().order_by(PythonToolModel.display_name.asc()))

    def get_python_tool_by_id(self, tool_id: int) -> PythonToolModel | None:
        """Retrieve a python tool by ID."""
        try:
            return PythonToolModel.get_or_none(PythonToolModel.id == tool_id)
        except Exception as e:
            logger.error("Failed to get python tool %s: %s", tool_id, e)
            return None

    def get_python_tool_by_name(self, name: str) -> PythonToolModel | None:
        """Retrieve a python tool by unique name identifier."""
        try:
            return PythonToolModel.get_or_none(PythonToolModel.name == name)
        except Exception as e:
            logger.error("Failed to get python tool by name '%s': %s", name, e)
            return None

    def create_python_tool(
        self,
        name: str,
        display_name: str,
        code: str,
        description: str | None = None,
        is_builtin: bool = False,
    ) -> PythonToolModel:
        """Create a new Python tool definition."""
        with self.atomic():
            return PythonToolModel.create(
                name=name,
                display_name=display_name,
                description=description,
                code=code,
                is_builtin=is_builtin,
            )

    def update_python_tool(self, tool_id: int, **kwargs: Any) -> PythonToolModel | None:
        """Update an existing Python tool."""
        tool = self.get_python_tool_by_id(tool_id)
        if not tool:
            return None

        with self.atomic():
            for key, val in kwargs.items():
                if hasattr(tool, key):
                    setattr(tool, key, val)
            tool.save()
            return tool

    def delete_python_tool(self, tool_id: int) -> bool:
        """Delete a Python tool."""
        tool = self.get_python_tool_by_id(tool_id)
        if not tool:
            return False

        with self.atomic():
            tool.delete_instance()
            return True
