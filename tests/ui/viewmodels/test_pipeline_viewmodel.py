"""
Unit tests for PipelineViewModel.
"""

from __future__ import annotations

from ankiforge.repositories.persona_repository import PersonaRepository
from ankiforge.repositories.pipeline_repository import PipelineRepository
from ankiforge.ui.viewmodels.pipeline_viewmodel import PipelineViewModel
from ankiforge.utils.event_bus import AppEventBus


def test_pipeline_viewmodel_lifecycle() -> None:
    bus = AppEventBus()
    pipeline_repo = PipelineRepository()
    persona_repo = PersonaRepository()

    vm = PipelineViewModel(pipeline_repo=pipeline_repo, persona_repo=persona_repo, bus=bus)

    # Signals tracking
    loaded_pipelines: list = []
    selected_pipelines: list = []
    updated_steps: list = []

    vm.pipelines_loaded.connect(lambda p: loaded_pipelines.append(p))
    vm.pipeline_selected.connect(lambda p: selected_pipelines.append(p))
    vm.steps_updated.connect(lambda s: updated_steps.append(s))

    # Initial load (empty)
    vm.load_data()
    assert len(loaded_pipelines) == 1
    assert vm.current_pipeline is None

    # Create pipeline
    pipe = vm.create_pipeline(name="DAG Test", description="Test DAG")
    assert pipe is not None
    assert vm.current_pipeline is not None
    assert vm.current_pipeline.name == "DAG Test"

    # Add persona and steps
    persona = persona_repo.create_persona(name="Agent 1", system_prompt="Test prompt")
    step1 = vm.add_step(step_type="LLM_PROMPT", persona_id=persona.id, config={"key": "val"})
    assert step1 is not None
    assert len(vm.steps) == 1

    step2 = vm.add_step(step_type="HUMAN_VALIDATION")
    assert step2 is not None
    assert len(vm.steps) == 2

    # Step selection
    vm.select_step(0)
    assert vm.selected_step_index == 0

    # Duplicate step
    dup_step = vm.duplicate_step(step1.id)
    assert dup_step is not None
    assert len(vm.steps) == 3

    # Delete step
    vm.delete_step(dup_step.id)
    assert len(vm.steps) == 2

    # Duplicate pipeline
    dup_pipe = vm.duplicate_pipeline(pipe.id, "DAG Test (Copy)")
    assert dup_pipe is not None
    assert len(vm.pipelines) == 2

    # Delete pipeline
    vm.delete_pipeline(pipe.id)
    assert len(vm.pipelines) == 1

    vm.dispose()
