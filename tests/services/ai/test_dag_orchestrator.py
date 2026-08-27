import threading
from typing import Any

from ankiforge.database.models import PersonaModel, PipelineModel, PipelineStepModel
from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.ai.orchestrator import PipelineOrchestrator
from ankiforge.services.ai.state import PipelineRunState


class DummyProvider(LLMProvider):
    """Fournisseur LLM de test déterministe."""

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.calls: list[dict[str, Any]] = []

    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
        self.calls.append({"system": system_prompt, "user": user_prompt, "format": response_format})
        for key, resp in self.responses.items():
            if key in system_prompt or key in str(user_prompt):
                return resp
        if response_format == "json":
            return '{"cards": [{"Front": "Question test", "Back": "Réponse test"}]}'
        return "Résultat textuel de test."


def test_pipeline_run_state_basic_and_serialization():
    """Vérifie le fonctionnement de PipelineRunState et sa sérialisation."""
    state = PipelineRunState(document_id=42, initial_prompt="Créer des cartes")
    state.set_variable("topic", "Biologie")
    state.add_retrieved_chunks(["Chunk 1 : Cellule", "Chunk 2 : Mitochondrie"])
    state.add_error("Erreur mineure")
    state.log_step_execution(1, "LLM_PROMPT", "SUCCESS", 0.42, "OK")

    assert state.get_variable("topic") == "Biologie"
    assert state.get_variable("inexistant", "default") == "default"
    assert len(state.retrieved_chunks) == 2
    assert len(state.errors) == 1
    assert len(state.execution_history) == 1

    # Sérialisation
    data = state.to_dict()
    assert data["document_id"] == 42
    assert data["variables"]["topic"] == "Biologie"

    # Désérialisation
    restored = PipelineRunState.from_dict(data)
    assert restored.document_id == 42
    assert restored.get_variable("topic") == "Biologie"
    assert len(restored.retrieved_chunks) == 2
    assert len(restored.execution_history) == 1


def test_orchestrator_linear_pipeline(qtbot):
    """Vérifie l'exécution séquentielle d'un pipeline linéaire avec LLM_PROMPT."""
    pipeline = PipelineModel.create(name="Pipeline Test Linéaire")
    persona1 = PersonaModel.create(name="Extracteur", system_prompt="Tu es un extracteur pour {{ topic }}.", output_format="text")
    persona2 = PersonaModel.create(name="Générateur", system_prompt="Tu es un générateur de cartes JSON.", output_format="json")

    PipelineStepModel.create(pipeline=pipeline, persona=persona1, step_order=1, step_type="LLM_PROMPT")
    PipelineStepModel.create(pipeline=pipeline, persona=persona2, step_order=2, step_type="LLM_PROMPT")

    provider = DummyProvider(
        {
            "extracteur": "Notions extraites : Mitose, Méiose.",
            "générateur": '{"cards": [{"Front": "Qu\'est-ce que la mitose ?", "Back": "Division cellulaire"}]}',
        }
    )

    initial_state = PipelineRunState()
    initial_state.set_variable("topic", "Génétique")

    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        initial_state=initial_state,
        ai_provider=provider,
    )

    started_steps = []
    completed_steps = []
    finished_states = []

    orchestrator.signals.step_started.connect(lambda order, desc: started_steps.append(order))
    orchestrator.signals.step_completed.connect(lambda order, st: completed_steps.append(order))
    orchestrator.signals.pipeline_finished.connect(lambda st: finished_states.append(st))

    orchestrator.run()

    assert started_steps == [1, 2]
    assert completed_steps == [1, 2]
    assert len(finished_states) == 1
    final_state = finished_states[0]

    assert "generated_cards" in final_state.variables
    assert len(final_state.variables["generated_cards"]) == 1
    assert final_state.variables["generated_cards"][0]["Front"] == "Qu'est-ce que la mitose ?"
    assert len(final_state.execution_history) == 2


def test_orchestrator_map_reduce():
    """Vérifie le fonctionnement de l'étape MAP_REDUCE en parallèle."""
    pipeline = PipelineModel.create(name="Pipeline MapReduce")
    persona = PersonaModel.create(name="Linter", system_prompt="Linter pour: {{ item }}", output_format="json")
    PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=1, step_type="MAP_REDUCE")

    provider = DummyProvider()
    initial_state = PipelineRunState()
    initial_state.set_variable("map_items", ["Item A", "Item B", "Item C"])

    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        initial_state=initial_state,
        ai_provider=provider,
    )

    finished_states = []
    orchestrator.signals.pipeline_finished.connect(lambda st: finished_states.append(st))

    orchestrator.run()

    assert len(finished_states) == 1
    final_state = finished_states[0]
    assert "map_reduce_results" in final_state.variables
    assert len(final_state.variables["map_reduce_results"]) == 3
    assert len(final_state.variables["generated_cards"]) == 3


def test_orchestrator_human_validation_pause_and_resume():
    """Vérifie la mise en pause pour validation humaine et sa reprise."""
    pipeline = PipelineModel.create(name="Pipeline Validation Humaine")
    PipelineStepModel.create(pipeline=pipeline, step_order=1, step_type="HUMAN_VALIDATION")
    persona2 = PersonaModel.create(name="Finaliseur", system_prompt="Finalisation", output_format="text")
    PipelineStepModel.create(pipeline=pipeline, persona=persona2, step_order=2, step_type="LLM_PROMPT")

    provider = DummyProvider()
    initial_state = PipelineRunState()

    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        initial_state=initial_state,
        ai_provider=provider,
    )

    paused_states = []
    finished_states = []

    def on_human_validation(st):
        paused_states.append(st)

        # On simule la validation utilisateur après 50ms
        def do_resume():
            st.set_variable("validated_by_user", True)
            orchestrator.resume(st)

        threading.Timer(0.05, do_resume).start()

    orchestrator.signals.human_validation_required.connect(on_human_validation)
    orchestrator.signals.pipeline_finished.connect(lambda st: finished_states.append(st))

    orchestrator.run()

    assert len(paused_states) == 1
    assert len(finished_states) == 1
    assert finished_states[0].get_variable("validated_by_user") is True


def test_orchestrator_dag_branching_success_and_failure():
    """Vérifie le branchement conditionnel (on_success_step et on_failure_step)."""
    pipeline = PipelineModel.create(name="Pipeline Branching")
    persona = PersonaModel.create(name="Step Persona", system_prompt="Test", output_format="text")

    step1 = PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=1, step_type="LLM_PROMPT")
    PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=2, step_type="LLM_PROMPT")
    step3_target = PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=3, step_type="LLM_PROMPT")

    # Étape 1 saute directement à l'étape 3 en succès
    step1.on_success_step = step3_target
    step1.save()

    provider = DummyProvider()
    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        ai_provider=provider,
    )

    started_steps = []
    orchestrator.signals.step_started.connect(lambda order, desc: started_steps.append(order))

    orchestrator.run()

    # L'étape 2 doit avoir été sautée !
    assert started_steps == [1, 3]


def test_orchestrator_python_tool():
    """Vérifie l'exécution d'outils Python enregistrés."""
    pipeline = PipelineModel.create(name="Pipeline Python Tool")
    persona = PersonaModel.create(name="custom_filter_tool", system_prompt="", output_format="text")
    PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=1, step_type="PYTHON_TOOL")

    def my_custom_tool(state: PipelineRunState) -> dict:
        return {"tool_executed": True, "count": 42}

    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        tool_registry={"custom_filter_tool": my_custom_tool},
    )

    finished_states = []
    orchestrator.signals.pipeline_finished.connect(lambda st: finished_states.append(st))

    orchestrator.run()

    assert len(finished_states) == 1
    assert finished_states[0].get_variable("result_tool_1") == {"tool_executed": True, "count": 42}


def test_orchestrator_cancellation():
    """Vérifie l'annulation propre en cours d'exécution."""
    pipeline = PipelineModel.create(name="Pipeline Annulation")
    PipelineStepModel.create(pipeline=pipeline, step_order=1, step_type="HUMAN_VALIDATION")

    orchestrator = PipelineOrchestrator(pipeline_id=pipeline.id)

    cancelled_signals = []
    orchestrator.signals.cancelled.connect(lambda: cancelled_signals.append(True))

    def cancel_after_start(st):
        orchestrator.cancel()

    orchestrator.signals.human_validation_required.connect(cancel_after_start)
    orchestrator.run()

    assert len(cancelled_signals) == 1


def test_orchestrator_notes_json_format():
    """Vérifie que l'orchestrateur extrait correctement les cartes au format 'notes' (utilisé par Archiviste et Linter)."""
    pipeline = PipelineModel.create(name="Pipeline Notes Test")
    persona1 = PersonaModel.create(
        name="Archiviste Pédagogue Test",
        system_prompt="Archiviste: Génère des notes avec {{ first_field }} et {{ second_field }}. Clés: {{ fields_str }}",
        output_format="json",
    )
    PipelineStepModel.create(pipeline=pipeline, persona=persona1, step_order=1, step_type="LLM_PROMPT")

    provider = DummyProvider(
        {
            "Archiviste": '{"notes": [{"Front": "Concept Q", "Back": "Explication A"}]}',
        }
    )

    initial_state = PipelineRunState()
    initial_state.set_variable("fields", ["Front", "Back"])

    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        initial_state=initial_state,
        ai_provider=provider,
    )

    finished_states = []
    orchestrator.signals.pipeline_finished.connect(lambda st: finished_states.append(st))

    orchestrator.run()

    assert len(finished_states) == 1
    final_state = finished_states[0]
    assert "generated_cards" in final_state.variables
    cards = final_state.variables["generated_cards"]
    assert len(cards) == 1
    assert cards[0]["Front"] == "Concept Q"
    assert cards[0]["Back"] == "Explication A"
    # Vérifier que le rendu Jinja contenait bien les champs
    assert "Front" in provider.calls[0]["system"]
    assert "Back" in provider.calls[0]["system"]


def test_orchestrator_multi_model_jinja_and_parsing():
    """Vérifie le rendu de {{ available_card_models }} et l'extraction multi-modèles."""
    from ankiforge.database.models import NoteTypeModel

    nt_basic = NoteTypeModel.create(
        name="Basique Test",
        description="Questions directes et définitions.",
        fields_schema='["Front", "Back"]',
    )
    nt_cloze = NoteTypeModel.create(
        name="Cloze Test",
        description="Phrases à trous.",
        fields_schema='["Texte", "Remarques extra"]',
    )

    pipeline = PipelineModel.create(name="Pipeline Multi-Modèles")
    persona = PersonaModel.create(
        name="Extracteur Multi",
        system_prompt="Contexte modèles :\n{{ available_card_models }}",
        output_format="json",
    )
    PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=1, step_type="LLM_PROMPT")

    provider = DummyProvider(
        {
            "Contexte modèles": (
                '{"notes": [  {"model": "Basique Test", "fields": {"Front": "Q1", "Back": "A1"}},  {"model": "Cloze Test", "fields": {"Texte": "{{c1::T1}}", "Remarques extra": "R1"}}]}'
            )
        }
    )

    initial_state = PipelineRunState()
    initial_state.set_variable("selected_models", [nt_basic, nt_cloze])

    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        initial_state=initial_state,
        ai_provider=provider,
    )

    finished_states = []
    orchestrator.signals.pipeline_finished.connect(lambda st: finished_states.append(st))
    orchestrator.run()

    assert len(finished_states) == 1
    final_state = finished_states[0]
    cards = final_state.variables["generated_cards"]
    assert len(cards) == 2
    assert cards[0]["model"] == "Basique Test"
    assert cards[0]["Front"] == "Q1"
    assert cards[1]["model"] == "Cloze Test"
    assert cards[1]["Texte"] == "{{c1::T1}}"

    # Vérifier que le catalogue a bien été injecté dans le prompt système reçu par le LLM
    system_prompt = provider.calls[0]["system"]
    assert "MODÈLES DE CARTES AUTORISÉS" in system_prompt
    assert 'Modèle : "Basique Test"' in system_prompt
    assert "Questions directes et définitions." in system_prompt
    assert 'Modèle : "Cloze Test"' in system_prompt
