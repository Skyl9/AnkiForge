import json
from ankiforge.database.models import AgentModel, NoteTypeModel, PipelineModel, PipelineStepModel
from ankiforge.services.ai.base import MockProvider
from ankiforge.services.workers.creation_worker import CreationWorker, CreationTaskPayload


def test_creation_worker_success(mock_db):
    """Vérifie que le worker exécute le pipeline et émet le signal 'finished' avec les notes."""

    # 1. PRÉPARATION DE LA BASE DE DONNÉES
    nt = NoteTypeModel.create(name="Test", fields_schema=json.dumps(["Front", "Back"]), templates="[]", css_style="")
    pipe = PipelineModel.create(name="Test Pipe")
    agent = AgentModel.create(name="Test Agent", system_prompt="Prompt test", output_format="json")
    PipelineStepModel.create(pipeline=pipe, agent=agent, step_order=1)

    # 2. PRÉPARATION DU PAYLOAD (MAIN THREAD STYLE)
    payload = CreationTaskPayload(
        text_source="Texte de cours",
        note_type_id=nt.id,
        note_type_fields_schema=nt.fields_schema,
        pipeline_id=pipe.id,
        pipeline_name=pipe.name,
        pipeline_steps=[{"name": agent.name, "system_prompt": agent.system_prompt, "output_format": agent.output_format}],
        use_vision=False,
    )

    # 3. PRÉPARATION DU WORKER
    provider = MockProvider()
    worker = CreationWorker(ai_provider=provider, payload=payload)

    # On prépare des "boîtes" pour capturer les signaux émis par le worker
    emitted_notes = []
    emitted_errors = []
    worker.finished.connect(lambda notes: emitted_notes.append(notes))
    worker.error.connect(lambda err: emitted_errors.append(err))

    # 4. ACTION (Appel direct et synchrone !)
    worker.run()

    # 5. VÉRIFICATIONS
    assert len(emitted_errors) == 0, f"Une erreur inattendue a été émise : {emitted_errors}"
    assert len(emitted_notes) == 1, "Le signal 'finished' n'a pas été émis correctement."

    # On vérifie le contenu de la note générée
    notes_list = emitted_notes[0]
    assert len(notes_list) == 1
    assert "Front" in notes_list[0]
    assert "Question simulée" in notes_list[0]["Front"]


def test_creation_worker_empty_pipeline(mock_db):
    """Vérifie que le worker lève une erreur si le pipeline est vide."""
    nt = NoteTypeModel.create(name="Test", fields_schema=json.dumps([]), templates="[]", css_style="")
    pipe_vide = PipelineModel.create(name="Pipe Vide")

    payload = CreationTaskPayload(
        text_source="Texte", note_type_id=nt.id, note_type_fields_schema=nt.fields_schema, pipeline_id=pipe_vide.id, pipeline_name=pipe_vide.name, pipeline_steps=[], use_vision=False
    )

    worker = CreationWorker(MockProvider(), payload=payload)

    emitted_errors = []
    worker.error.connect(lambda err: emitted_errors.append(err))

    worker.run()

    assert len(emitted_errors) == 1
    assert "ne contient aucun agent" in emitted_errors[0]
