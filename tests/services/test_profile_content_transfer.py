from pathlib import Path

from peewee import SqliteDatabase

from ankiforge.database.models import (
    LLMConfigModel,
    PersonaFolderModel,
    PersonaModel,
    PersonaVersionModel,
    PipelineModel,
    PipelineStepModel,
)
from ankiforge.services.profile_content_transfer import ProfileContentTransfer


def test_import_persona_from_another_profile(mock_db, tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    source_dir = profiles_dir / "source"
    source_dir.mkdir(parents=True)
    source_db = SqliteDatabase(str(source_dir / "ankiforge.db"))
    models = [LLMConfigModel, PersonaFolderModel, PersonaModel, PersonaVersionModel, PipelineModel, PipelineStepModel]
    with source_db.bind_ctx(models, bind_refs=False, bind_backrefs=False):
        source_db.connect()
        source_db.create_tables(models)
        with source_db.atomic():
            folder = PersonaFolderModel.create(name="Formation")
            llm = LLMConfigModel.create(
                display_name="Source Engine",
                provider="ollama",
                model_id="llama3",
                api_key="must-not-be-copied",
            )
            persona = PersonaModel.create(
                name="Agent Source",
                description="Agent transféré",
                system_prompt="Crée des cartes.",
                output_format="json",
                persona_type="pipeline",
                folder=folder,
                allowed_tools='["query_peewee"]',
                llm_config=llm,
            )
            PersonaVersionModel.create(
                persona=persona,
                system_prompt=persona.system_prompt,
                description=persona.description,
                output_format=persona.output_format,
                persona_type=persona.persona_type,
                allowed_tools=persona.allowed_tools,
                llm_config=llm,
            )
    source_db.close()

    imported = ProfileContentTransfer.import_persona("source", "Agent Source", profiles_dir)

    assert imported.name == "Agent Source"
    assert imported.folder.name == "Formation"
    assert imported.llm_config.display_name == "Source Engine"
    assert imported.llm_config.api_key is None


def test_import_pipeline_imports_missing_personas_and_preserves_links(mock_db, tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    source_dir = profiles_dir / "source"
    source_dir.mkdir(parents=True)
    source_db = SqliteDatabase(str(source_dir / "ankiforge.db"))
    models = [LLMConfigModel, PersonaFolderModel, PersonaModel, PersonaVersionModel, PipelineModel, PipelineStepModel]
    with source_db.bind_ctx(models, bind_refs=False, bind_backrefs=False):
        source_db.connect()
        source_db.create_tables(models)
        with source_db.atomic():
            persona = PersonaModel.create(name="Pipeline Agent", system_prompt="Génère.")
            pipeline = PipelineModel.create(name="Pipeline Source", description="DAG transféré")
            first = PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=1, config_data='{"input_variable":"text_source"}')
            second = PipelineStepModel.create(pipeline=pipeline, step_order=2, step_type="HUMAN_VALIDATION")
            first.on_success_step = second
            first.save()
    source_db.close()

    imported = ProfileContentTransfer.import_pipeline("source", "Pipeline Source", profiles_dir)

    assert imported.name == "Pipeline Source"
    steps = list(PipelineStepModel.select().where(PipelineStepModel.pipeline == imported).order_by(PipelineStepModel.step_order))
    assert [step.persona.name if step.persona else None for step in steps] == ["Pipeline Agent", None]
    assert steps[0].on_success_step.id == steps[1].id
