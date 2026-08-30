"""
Unit tests for PipelineRepository.
"""

from __future__ import annotations

from ankiforge.database.models import PersonaModel
from ankiforge.repositories.pipeline_repository import PipelineRepository


def test_pipeline_repository_crud() -> None:
    repo = PipelineRepository()

    # Pipelines
    pipeline = repo.create_pipeline(name="Default Generator", description="Standard DAG pipeline")
    assert repo.get_pipeline_by_id(pipeline.id) is not None
    assert repo.get_pipeline_by_name("Default Generator") is not None
    assert len(repo.get_all_pipelines()) == 1

    # Persona for step
    persona = PersonaModel.create(name="Creator", system_prompt="You create flashcards.")

    # Steps
    step1 = repo.create_step(pipeline, step_order=1, step_type="LLM_PROMPT", persona=persona)
    step2 = repo.create_step(pipeline, step_order=2, step_type="HUMAN_VALIDATION")

    steps = repo.get_steps_for_pipeline(pipeline.id)
    assert len(steps) == 2
    assert steps[0].step_type == "LLM_PROMPT"
    assert steps[1].step_type == "HUMAN_VALIDATION"

    # Reorder steps
    repo.reorder_steps(pipeline.id, [step2.id, step1.id])
    steps_reordered = repo.get_steps_for_pipeline(pipeline.id)
    assert steps_reordered[0].id == step2.id
    assert steps_reordered[1].id == step1.id

    # Duplicate pipeline
    duplicated = repo.duplicate_pipeline(pipeline.id, "Default Generator (Copy)")
    assert duplicated is not None
    dup_steps = repo.get_steps_for_pipeline(duplicated.id)
    assert len(dup_steps) == 2

    # Python tools
    tool = repo.create_python_tool(
        name="cleaner",
        display_name="HTML Cleaner",
        code="def run(state): return state",
        description="Cleans HTML",
    )
    assert repo.get_python_tool_by_id(tool.id) is not None
    assert repo.get_python_tool_by_name("cleaner") is not None
    assert len(repo.get_all_python_tools()) == 1

    # Delete pipeline
    deleted = repo.delete_pipeline(pipeline.id)
    assert deleted is True
    assert repo.get_pipeline_by_id(pipeline.id) is None
