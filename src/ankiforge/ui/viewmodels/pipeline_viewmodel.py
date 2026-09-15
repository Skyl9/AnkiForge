"""
ViewModel for DAG Pipeline Editor and Execution Management.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import QObject, Signal

from ankiforge.database.models import (
    LLMConfigModel,
    PersonaModel,
    PipelineModel,
    PipelineStepModel,
    PythonToolModel,
)
from ankiforge.repositories.persona_repository import PersonaRepository
from ankiforge.repositories.pipeline_repository import PipelineRepository
from ankiforge.ui.viewmodels.base import BaseViewModel
from ankiforge.utils.event_bus import (
    AppEventBus,
    PipelineCreatedEvent,
    PipelineDeletedEvent,
    PipelineRunFinishedEvent,
    PipelineRunStartedEvent,
    PipelineUpdatedEvent,
)

logger = logging.getLogger(__name__)


class PipelineViewModel(BaseViewModel):
    """Encapsulates state and business logic for DAG pipeline configuration and execution."""

    pipelines_loaded = Signal(list)
    pipeline_selected = Signal(object)
    steps_updated = Signal(list)
    step_selected = Signal(int, object)
    execution_started = Signal(str)
    execution_step_changed = Signal(int, str)
    execution_log_appended = Signal(str)
    execution_completed = Signal(bool, str, int)

    def __init__(
        self,
        pipeline_repo: PipelineRepository | None = None,
        persona_repo: PersonaRepository | None = None,
        bus: AppEventBus | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(bus=bus, parent=parent)
        self._pipeline_repo = pipeline_repo or PipelineRepository()
        self._persona_repo = persona_repo or PersonaRepository()

        self._pipelines: list[PipelineModel] = []
        self._current_pipeline: PipelineModel | None = None
        self._steps: list[PipelineStepModel] = []
        self._selected_step_index: int = 0
        self._personas: list[PersonaModel] = []
        self._llm_configs: list[LLMConfigModel] = []
        self._python_tools: list[PythonToolModel] = []

    @property
    def pipelines(self) -> list[PipelineModel]:
        return self._pipelines

    @property
    def current_pipeline(self) -> PipelineModel | None:
        return self._current_pipeline

    @property
    def steps(self) -> list[PipelineStepModel]:
        return self._steps

    @property
    def selected_step_index(self) -> int:
        return self._selected_step_index

    @property
    def personas(self) -> list[PersonaModel]:
        return self._personas

    @property
    def llm_configs(self) -> list[LLMConfigModel]:
        return self._llm_configs

    @property
    def python_tools(self) -> list[PythonToolModel]:
        return self._python_tools

    def load_data(self) -> None:
        """Load pipelines, personas, tools and llm configs from repositories."""
        try:
            self._personas = self._persona_repo.get_all_personas()
            self._llm_configs = self._persona_repo.get_all_llm_configs()
            self._python_tools = self._pipeline_repo.get_all_python_tools()
            self._pipelines = self._pipeline_repo.get_all_pipelines()

            self.pipelines_loaded.emit(self._pipelines)

            if self._pipelines and (self._current_pipeline is None or self._current_pipeline not in self._pipelines):
                self.select_pipeline(self._pipelines[0].id)
            elif not self._pipelines:
                self._current_pipeline = None
                self._steps = []
                self.pipeline_selected.emit(None)
                self.steps_updated.emit([])
        except Exception as e:
            self.set_error(f"Failed to load pipeline data: {e}")

    def select_pipeline(self, pipeline_id: int) -> None:
        """Select a pipeline by its ID and load its steps."""
        pipeline = self._pipeline_repo.get_pipeline_by_id(pipeline_id)
        if not pipeline:
            return

        self._current_pipeline = pipeline
        self._steps = self._pipeline_repo.get_steps_for_pipeline(pipeline_id)
        self._selected_step_index = 0

        self.pipeline_selected.emit(pipeline)
        self.steps_updated.emit(self._steps)

        if self._steps:
            self.step_selected.emit(0, self._steps[0])
        else:
            self.step_selected.emit(-1, None)

    def create_pipeline(self, name: str, description: str = "") -> PipelineModel:
        """Create a new pipeline and select it."""
        pipeline = self._pipeline_repo.create_pipeline(name=name, description=description)
        self._pipelines = self._pipeline_repo.get_all_pipelines()
        self.publish_event(PipelineCreatedEvent(pipeline_id=pipeline.id, pipeline_name=pipeline.name))
        self.pipelines_loaded.emit(self._pipelines)
        self.select_pipeline(pipeline.id)
        return pipeline

    def duplicate_pipeline(self, pipeline_id: int, new_name: str) -> PipelineModel | None:
        """Duplicate an existing pipeline."""
        new_pipeline = self._pipeline_repo.duplicate_pipeline(pipeline_id, new_name)
        if new_pipeline:
            self._pipelines = self._pipeline_repo.get_all_pipelines()
            self.publish_event(PipelineCreatedEvent(pipeline_id=new_pipeline.id, pipeline_name=new_pipeline.name))
            self.pipelines_loaded.emit(self._pipelines)
            self.select_pipeline(new_pipeline.id)
        return new_pipeline

    def delete_pipeline(self, pipeline_id: int) -> bool:
        """Delete a pipeline."""
        success = self._pipeline_repo.delete_pipeline(pipeline_id)
        if success:
            self.publish_event(PipelineDeletedEvent(pipeline_id=pipeline_id))
            self.load_data()
        return success

    def select_step(self, index: int) -> None:
        """Select a step by its index in the current pipeline."""
        if 0 <= index < len(self._steps):
            self._selected_step_index = index
            self.step_selected.emit(index, self._steps[index])

    def add_step(
        self,
        step_type: str,
        persona_id: int | None = None,
        config: dict[str, Any] | None = None,
    ) -> PipelineStepModel | None:
        """Add a step to the current pipeline."""
        if not self._current_pipeline:
            return None

        persona = self._persona_repo.get_persona_by_id(persona_id) if persona_id else None
        next_order = len(self._steps) + 1
        step = self._pipeline_repo.create_step(
            pipeline=self._current_pipeline,
            step_order=next_order,
            step_type=step_type,
            persona=persona,
            config_data=config or {},
        )
        self._steps = self._pipeline_repo.get_steps_for_pipeline(self._current_pipeline.id)
        self.steps_updated.emit(self._steps)
        self.select_step(len(self._steps) - 1)
        self.publish_event(PipelineUpdatedEvent(pipeline_id=self._current_pipeline.id, pipeline_name=self._current_pipeline.name))
        return step

    def update_step(self, step_id: int, **kwargs: Any) -> PipelineStepModel | None:
        """Update properties of a step."""
        updated = self._pipeline_repo.update_step(step_id, **kwargs)
        if updated and self._current_pipeline:
            self._steps = self._pipeline_repo.get_steps_for_pipeline(self._current_pipeline.id)
            self.steps_updated.emit(self._steps)
            if 0 <= self._selected_step_index < len(self._steps):
                self.step_selected.emit(self._selected_step_index, self._steps[self._selected_step_index])
            self.publish_event(PipelineUpdatedEvent(pipeline_id=self._current_pipeline.id, pipeline_name=self._current_pipeline.name))
        return updated

    def delete_step(self, step_id: int) -> bool:
        """Delete a step from the current pipeline."""
        if not self._current_pipeline:
            return False

        success = self._pipeline_repo.delete_step(step_id)
        if success:
            self._steps = self._pipeline_repo.get_steps_for_pipeline(self._current_pipeline.id)
            self.steps_updated.emit(self._steps)
            new_idx = max(0, min(self._selected_step_index, len(self._steps) - 1))
            if self._steps:
                self.select_step(new_idx)
            else:
                self.step_selected.emit(-1, None)
            self.publish_event(PipelineUpdatedEvent(pipeline_id=self._current_pipeline.id, pipeline_name=self._current_pipeline.name))
        return success

    def reorder_steps(self, step_ids: list[int]) -> None:
        """Reorder steps for the current pipeline."""
        if not self._current_pipeline:
            return

        self._pipeline_repo.reorder_steps(self._current_pipeline.id, step_ids)
        self._steps = self._pipeline_repo.get_steps_for_pipeline(self._current_pipeline.id)
        self.steps_updated.emit(self._steps)
        self.publish_event(PipelineUpdatedEvent(pipeline_id=self._current_pipeline.id, pipeline_name=self._current_pipeline.name))

    def duplicate_step(self, step_id: int) -> PipelineStepModel | None:
        """Duplicate a step in the current pipeline."""
        if not self._current_pipeline:
            return None

        step_to_dup = next((s for s in self._steps if s.id == step_id), None)
        if not step_to_dup:
            return None

        config_data = step_to_dup.config_data or "{}"
        try:
            config = json.loads(config_data) if isinstance(config_data, str) else config_data
        except Exception:
            config = {}

        persona_id = step_to_dup.persona.id if step_to_dup.persona else None
        return self.add_step(
            step_type=step_to_dup.step_type,
            persona_id=persona_id,
            config=config,
        )

    def log_execution(self, log_line: str) -> None:
        """Append an execution log line."""
        self.execution_log_appended.emit(log_line)

    def notify_run_started(self, run_id: str = "") -> None:
        """Notify execution start."""
        if self._current_pipeline:
            self.publish_event(
                PipelineRunStartedEvent(
                    pipeline_id=self._current_pipeline.id,
                    pipeline_name=self._current_pipeline.name,
                    run_id=run_id,
                )
            )
            self.execution_started.emit(self._current_pipeline.name)

    def notify_run_finished(self, success: bool, error: str = "", cards_count: int = 0) -> None:
        """Notify execution finish."""
        if self._current_pipeline:
            self.publish_event(
                PipelineRunFinishedEvent(
                    pipeline_id=self._current_pipeline.id,
                    pipeline_name=self._current_pipeline.name,
                    success=success,
                    error=error,
                    generated_cards_count=cards_count,
                )
            )
            self.execution_completed.emit(success, error, cards_count)
