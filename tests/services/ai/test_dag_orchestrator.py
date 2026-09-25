import json
import threading
from typing import Any

import pytest

from ankiforge.database.models import PersonaModel, PipelineModel, PipelineRunModel, PipelineStepModel
from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.ai.orchestrator import (
    CARD_SECTION_DOCUMENTATION_RULE,
    PipelineOrchestrator,
    _source_context_metadata,
    _stamp_card_source_metadata,
)
from ankiforge.services.ai.state import PipelineRunState

pytestmark = pytest.mark.integration


class DummyProvider(LLMProvider):
    """Fournisseur LLM de test déterministe."""

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        system_prompt: str,
        user_prompt: str | list[dict[str, Any]],
        response_format: str = "json",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        self.calls.append({"system": system_prompt, "user": user_prompt, "format": response_format, "max_tokens": max_tokens, "temperature": temperature})
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


def test_llm_prompt_empty_input_variable_falls_back_to_source(qtbot: Any) -> None:
    """input_variable absente/vide ne doit plus produire un prompt utilisateur vide (régressions batchfactory)."""
    pipeline = PipelineModel.create(name="Pipeline Input Variable Manquante")
    persona = PersonaModel.create(
        name="Archiviste Test Manquant",
        system_prompt="Archiviste: génère des notes JSON.",
        output_format="json",
    )
    PipelineStepModel.create(
        pipeline=pipeline,
        persona=persona,
        step_order=1,
        step_type="LLM_PROMPT",
        config_data=json.dumps({"input_variable": "generated_cards", "output_variable": "sortie"}),
    )

    provider = DummyProvider({"Archiviste:": '{"notes": [{"Front": "Q1", "Back": "A1"}]}'})

    source_text = "## 2. Principe d'Incertitude d'Heisenberg\nDelta x * Delta p >= hbar / 2."
    initial_state = PipelineRunState(document_id=1, initial_prompt=source_text)
    initial_state.set_variable("text_source", source_text)

    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        initial_state=initial_state,
        ai_provider=provider,
    )
    finished_states: list[Any] = []
    orchestrator.signals.pipeline_finished.connect(lambda st: finished_states.append(st))
    orchestrator.run()

    assert len(finished_states) == 1
    assert provider.calls, "Le provider aurait dû être appelé."
    assert provider.calls[0]["user"] == source_text
    cards = finished_states[0].get_variable("generated_cards", [])
    assert len(cards) == 1
    assert cards[0]["Front"] == "Q1"
    assert cards[0]["Back"] == "A1"


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


def test_orchestrator_rag_retrieval_hybrid_step(tmp_path, monkeypatch):
    """Vérifie l'exécution de l'étape RAG_RETRIEVAL avec le moteur hybride FAISS/BM25."""
    import json

    from ankiforge.database.models import DocumentChunkModel, DocumentModel
    from ankiforge.services.rag.vector_manager import VectorManager

    monkeypatch.setattr("ankiforge.services.rag.vector_manager.get_app_data_dir", lambda: tmp_path)

    # Création d'un document avec fragments
    doc = DocumentModel.create(title="Cours Pharmacologie RRF", content="Texte brut", file_type="md")
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        content="La pénicilline est un antibiotique bêta-lactamine qui inhibe la synthèse de la paroi bactérienne.",
        heading_path="Antibiotiques > Pénicilline",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=2,
        content="L'aspirine (acide acétylsalicylique) est un anti-inflammatoire non stéroïdien (AINS) inhibiteur de COX-1 et COX-2.",
        heading_path="Antalgiques > Aspirine",
    )

    # Indexation
    vm = VectorManager(llm_config=None)
    vm.index_document(doc)

    pipeline = PipelineModel.create(name="Pipeline RAG Hybride")
    step_cfg = {
        "top_k": 1,
        "retrieval_mode": "hybrid",
        "w_dense": 0.6,
        "w_sparse": 0.4,
        "rrf_k": 60,
        "output_variable": "retrieved_chunks",
    }
    PipelineStepModel.create(
        pipeline=pipeline,
        step_order=1,
        step_type="RAG_RETRIEVAL",
        config_data=json.dumps(step_cfg),
    )

    initial_state = PipelineRunState(document_id=doc.id, initial_prompt="Recherche sur la pénicilline et paroi bactérienne")
    provider = DummyProvider()

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
    assert "retrieved_chunks" in final_state.variables
    chunks = final_state.variables["retrieved_chunks"]
    assert len(chunks) == 1
    assert "pénicilline" in chunks[0].lower() or "bactérienne" in chunks[0].lower()

    # Détails RRF
    assert "retrieved_chunks_details" in final_state.variables
    details = final_state.variables["retrieved_chunks_details"]
    assert len(details) == 1
    assert "rrf_score" in details[0]


def test_orchestrator_forwards_temperature_and_max_tokens_from_config(qtbot):
    """Vérifie que temperature / max_tokens dans config_data (ou l'état) sont transmis au provider."""
    pipeline = PipelineModel.create(name="Pipeline Température")
    persona = PersonaModel.create(name="Générateur Temp", system_prompt="Générateur JSON.", output_format="json")
    step = PipelineStepModel.create(
        pipeline=pipeline,
        persona=persona,
        step_order=1,
        step_type="LLM_PROMPT",
        config_data=json.dumps({"temperature": 0.85}),
    )
    del step

    provider = DummyProvider()
    initial_state = PipelineRunState(initial_prompt="Créer des cartes")
    initial_state.set_variable("max_tokens", 512)

    orchestrator = PipelineOrchestrator(pipeline_id=pipeline.id, initial_state=initial_state, ai_provider=provider)
    finished_states: list[Any] = []
    orchestrator.signals.pipeline_finished.connect(lambda st: finished_states.append(st))
    orchestrator.run()

    assert len(finished_states) == 1
    assert provider.calls, "Le provider aurait dû être appelé."
    last_call = provider.calls[-1]
    assert last_call["temperature"] == 0.85
    assert last_call["max_tokens"] == 512


def test_orchestrator_uses_state_temperature_when_config_missing():
    """Vérifie le repli sur la variable d'état 'temperature' quand config_data n'en contient pas."""
    pipeline = PipelineModel.create(name="Pipeline État Température")
    persona = PersonaModel.create(name="Agent État", system_prompt="Agent JSON.", output_format="json")
    PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=1, step_type="LLM_PROMPT")

    provider = DummyProvider()
    initial_state = PipelineRunState(initial_prompt="Créer des cartes")
    initial_state.set_variable("temperature", 0.45)

    orchestrator = PipelineOrchestrator(pipeline_id=pipeline.id, initial_state=initial_state, ai_provider=provider)
    finished_states: list[Any] = []
    orchestrator.signals.pipeline_finished.connect(lambda st: finished_states.append(st))
    orchestrator.run()

    assert len(finished_states) == 1
    assert provider.calls
    assert provider.calls[-1]["temperature"] == 0.45


def test_call_provider_generate_falls_back_for_legacy_providers():
    """Vérifie le repli sans temperature pour les providers legacy ne l'acceptant pas."""

    class LegacyProvider(LLMProvider):
        def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
            return '{"cards": [{"Front": "Q", "Back": "A"}]}'

    pipeline = PipelineModel.create(name="Pipeline Legacy Provider")
    persona = PersonaModel.create(name="Agent Legacy", system_prompt="Agent JSON.", output_format="json")
    PipelineStepModel.create(
        pipeline=pipeline,
        persona=persona,
        step_order=1,
        step_type="LLM_PROMPT",
        config_data=json.dumps({"temperature": 0.9, "max_tokens": 1000}),
    )

    provider = LegacyProvider()
    initial_state = PipelineRunState(initial_prompt="Créer des cartes")
    orchestrator = PipelineOrchestrator(pipeline_id=pipeline.id, initial_state=initial_state, ai_provider=provider)
    finished_states: list[Any] = []
    orchestrator.signals.pipeline_finished.connect(lambda st: finished_states.append(st))
    orchestrator.run()

    assert len(finished_states) == 1


def test_source_context_metadata_and_stamp_provenance():
    """_source_context_metadata extrait les clés de provenance, _stamp_card_source_metadata les écrit sur les cartes."""
    from ankiforge.services.ai.state import PipelineRunState as PRS

    state = PRS(document_id=7, initial_prompt="test")
    state.set_variable("source_chunk_id", 12)
    state.set_variable("source_heading_path", "Chapitre 1 > Cellule")
    state.set_variable("source_page_number", 4)

    ctx = _source_context_metadata(state)
    assert ctx["chunk_id"] == 12
    assert ctx["heading_path"] == "Chapitre 1 > Cellule"
    assert ctx["page_number"] == 4

    cards: list[dict[str, Any]] = [{"Front": "Q", "Back": "A"}]
    _stamp_card_source_metadata(cards, ctx, documentation=True)
    assert cards[0]["_source_chunk_id"] == 12
    assert cards[0]["_source_heading_path"] == "Chapitre 1 > Cellule"
    assert cards[0]["_source_page_number"] == 4
    assert cards[0]["_documentation_enabled"] is True

    # Documenté=False propage False, sans écraser si déjà présent
    cards2: list[dict[str, Any]] = [{"Front": "X", "_source_chunk_id": 99}]
    _stamp_card_source_metadata(cards2, ctx, documentation=False)
    assert cards2[0]["_source_chunk_id"] == 99
    assert cards2[0]["_documentation_enabled"] is False


def test_llm_prompt_documentation_rule_prepended(qtbot: Any) -> None:
    """Avec document_id et declasser_sections_dans_tags True (défaut), la règle de section est préfixée dans le prompt système."""
    pipeline = PipelineModel.create(name="Pipeline Documentation ON")
    persona = PersonaModel.create(name="Générateur", system_prompt="Créer des cartes JSON.", output_format="json")
    PipelineStepModel.create(
        pipeline=pipeline,
        persona=persona,
        step_order=1,
        step_type="LLM_PROMPT",
        config_data=json.dumps({}),
    )

    provider = DummyProvider()
    initial_state = PipelineRunState(document_id=42, initial_prompt="Contenu source.")
    initial_state.set_variable("source_chunk_id", 5)
    initial_state.set_variable("source_heading_path", "Chapitre A")
    initial_state.set_variable("source_page_number", 2)

    orchestrator = PipelineOrchestrator(pipeline_id=pipeline.id, initial_state=initial_state, ai_provider=provider)
    finished_states: list[Any] = []
    orchestrator.signals.pipeline_finished.connect(lambda st: finished_states.append(st))
    orchestrator.run()

    assert len(finished_states) == 1
    system_prompt = provider.calls[0]["system"]
    assert CARD_SECTION_DOCUMENTATION_RULE in system_prompt

    cards = finished_states[0].get_variable("generated_cards", [])
    assert len(cards) >= 1
    assert cards[0].get("_source_chunk_id") == 5
    assert cards[0].get("_source_heading_path") == "Chapitre A"
    assert cards[0].get("_documentation_enabled") is True


def test_llm_prompt_documentation_off_suppresses_rule_and_metadata(qtbot: Any) -> None:
    """Avec declasser_sections_dans_tags False, la règle de section n'est pas injectée et documentation_enabled=False."""
    pipeline = PipelineModel.create(name="Pipeline Documentation OFF")
    persona = PersonaModel.create(name="Générateur", system_prompt="Créer des cartes.", output_format="json")
    PipelineStepModel.create(
        pipeline=pipeline,
        persona=persona,
        step_order=1,
        step_type="LLM_PROMPT",
        config_data=json.dumps({"declasser_sections_dans_tags": False}),
    )

    provider = DummyProvider()
    initial_state = PipelineRunState(document_id=42, initial_prompt="Contenu.")
    initial_state.set_variable("source_chunk_id", 7)

    orchestrator = PipelineOrchestrator(pipeline_id=pipeline.id, initial_state=initial_state, ai_provider=provider)
    finished_states: list[Any] = []
    orchestrator.signals.pipeline_finished.connect(lambda st: finished_states.append(st))
    orchestrator.run()

    assert len(finished_states) == 1
    system_prompt = provider.calls[0]["system"]
    assert CARD_SECTION_DOCUMENTATION_RULE not in system_prompt

    cards = finished_states[0].get_variable("generated_cards", [])
    assert cards[0].get("_documentation_enabled") is False


def test_llm_prompt_no_document_id_skips_documentation_rule(qtbot: Any) -> None:
    """Sans document_id, même avec declasser_sections_dans_tags True, la règle de documentation n'est pas préfixée."""
    pipeline = PipelineModel.create(name="Pipeline No Doc")
    persona = PersonaModel.create(name="Générateur", system_prompt="Créer des cartes.", output_format="json")
    PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=1, step_type="LLM_PROMPT")

    provider = DummyProvider()
    initial_state = PipelineRunState(document_id=None, initial_prompt="Contenu orphelin.")

    orchestrator = PipelineOrchestrator(pipeline_id=pipeline.id, initial_state=initial_state, ai_provider=provider)
    finished_states: list[Any] = []
    orchestrator.signals.pipeline_finished.connect(lambda st: finished_states.append(st))
    orchestrator.run()

    system_prompt = provider.calls[0]["system"]
    assert CARD_SECTION_DOCUMENTATION_RULE not in system_prompt
    cards = finished_states[0].get_variable("generated_cards", [])
    assert cards[0].get("_documentation_enabled") is True


def test_orchestrator_dag_failure_branching_goto():
    """Vérifie le saut vers on_failure_step lorsque failure_behavior='goto_failure_step'."""
    pipeline = PipelineModel.create(name="Pipeline Failure Goto")
    persona = PersonaModel.create(name="Agent", system_prompt="Prompt", output_format="text")

    step1 = PipelineStepModel.create(
        pipeline=pipeline,
        persona=persona,
        step_order=1,
        step_type="PYTHON_TOOL",
        failure_behavior="goto_failure_step",
        config_data=json.dumps({"tool_name": "clean_html_latex"}),
    )
    PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=2, step_type="LLM_PROMPT")
    step3_handler = PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=3, step_type="LLM_PROMPT")

    step1.on_failure_step = step3_handler
    step1.save()

    def failing_tool(state: PipelineRunState) -> None:
        raise ValueError("Erreur intentionnelle étape 1")

    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        tool_registry={"clean_html_latex": failing_tool},
        ai_provider=DummyProvider(),
    )

    started_steps: list[int] = []
    orchestrator.signals.step_started.connect(lambda order, desc: started_steps.append(order))

    finished_states: list[Any] = []
    orchestrator.signals.pipeline_finished.connect(lambda st: finished_states.append(st))

    orchestrator.run()

    # L'étape 2 a été sautée, l'étape 3 de récupération a été exécutée
    assert started_steps == [1, 3]
    assert len(finished_states) == 1
    assert len(finished_states[0].errors) >= 1


def test_orchestrator_dag_failure_branching_continue():
    """Vérifie que l'exécution continue séquentiellement si failure_behavior='continue'."""
    pipeline = PipelineModel.create(name="Pipeline Failure Continue")
    persona = PersonaModel.create(name="Agent", system_prompt="Prompt", output_format="text")

    PipelineStepModel.create(
        pipeline=pipeline,
        persona=persona,
        step_order=1,
        step_type="PYTHON_TOOL",
        failure_behavior="continue",
        config_data=json.dumps({"tool_name": "clean_html_latex"}),
    )
    PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=2, step_type="LLM_PROMPT")

    def failing_tool(state: PipelineRunState) -> None:
        raise ValueError("Erreur continue étape 1")

    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        tool_registry={"clean_html_latex": failing_tool},
        ai_provider=DummyProvider(),
    )

    started_steps: list[int] = []
    orchestrator.signals.step_started.connect(lambda order, desc: started_steps.append(order))

    finished_states: list[Any] = []
    orchestrator.signals.pipeline_finished.connect(lambda st: finished_states.append(st))

    orchestrator.run()

    assert started_steps == [1, 2]
    assert len(finished_states) == 1
    assert len(finished_states[0].errors) >= 1


def test_orchestrator_dag_failure_branching_stop():
    """Vérifie l'arrêt immédiat du pipeline si failure_behavior='stop'."""
    pipeline = PipelineModel.create(name="Pipeline Failure Stop")
    persona = PersonaModel.create(name="Agent", system_prompt="Prompt", output_format="text")

    PipelineStepModel.create(
        pipeline=pipeline,
        persona=persona,
        step_order=1,
        step_type="PYTHON_TOOL",
        failure_behavior="stop",
        config_data=json.dumps({"tool_name": "clean_html_latex"}),
    )
    PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=2, step_type="LLM_PROMPT")

    def failing_tool(state: PipelineRunState) -> None:
        raise ValueError("Erreur fatale étape 1")

    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        tool_registry={"clean_html_latex": failing_tool},
        ai_provider=DummyProvider(),
    )

    started_steps: list[int] = []
    errors: list[str] = []
    orchestrator.signals.step_started.connect(lambda order, desc: started_steps.append(order))
    orchestrator.signals.error_occurred.connect(lambda msg: errors.append(msg))

    orchestrator.run()

    assert started_steps == [1]
    assert len(errors) == 1
    assert "Erreur fatale étape 1" in errors[0]


def test_orchestrator_cycle_detection_and_per_step_limit():
    """Vérifie la détection de cycle et l'arrêt via max_step_executions."""
    pipeline = PipelineModel.create(name="Pipeline Cycle Test")
    persona = PersonaModel.create(name="Agent Cycle", system_prompt="Prompt", output_format="text")

    step1 = PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=1, step_type="LLM_PROMPT")
    step2 = PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=2, step_type="LLM_PROMPT")

    # Boucle infinie : step1 -> step2 -> step1
    step1.on_success_step = step2
    step1.save()
    step2.on_success_step = step1
    step2.save()

    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        ai_provider=DummyProvider(),
        max_executions_per_step=3,
    )

    errors: list[str] = []
    orchestrator.signals.error_occurred.connect(lambda msg: errors.append(msg))

    orchestrator.run()

    assert len(errors) == 1
    assert "Limite d'exécutions par étape dépassée" in errors[0]
    assert orchestrator.state.get_step_execution_count(1) == 4  # Déclenche l'erreur au 4ème tour (> 3)


def test_orchestrator_step_token_budget_exceeded():
    """Vérifie l'échec explicite en cas de dépassement de budget de tokens par étape."""
    pipeline = PipelineModel.create(name="Pipeline Budget Step")
    persona = PersonaModel.create(name="Agent Verbeux", system_prompt="Court", output_format="text")
    PipelineStepModel.create(
        pipeline=pipeline,
        persona=persona,
        step_order=1,
        step_type="LLM_PROMPT",
        config_data=json.dumps({"max_tokens_budget": 5}),
    )

    # Réponse longue qui va générer plus de 5 tokens
    provider = DummyProvider({"Court": "Une très longue réponse de test générant plus de 5 tokens sans aucun doute."})

    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        ai_provider=provider,
    )

    errors: list[str] = []
    orchestrator.signals.error_occurred.connect(lambda msg: errors.append(msg))

    orchestrator.run()

    assert len(errors) == 1
    assert "Budget de tokens dépassé pour l'étape 1" in errors[0]


def test_orchestrator_global_token_budget_exceeded():
    """Vérifie l'arrêt immédiat lorsque le budget global de tokens est dépassé."""
    pipeline = PipelineModel.create(name="Pipeline Budget Global")
    persona = PersonaModel.create(name="Agent", system_prompt="Prompt", output_format="text")
    PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=1, step_type="LLM_PROMPT")
    PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=2, step_type="LLM_PROMPT")

    provider = DummyProvider()
    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        ai_provider=provider,
        max_total_tokens=5,  # Budget très restreint
    )

    errors: list[str] = []
    orchestrator.signals.error_occurred.connect(lambda msg: errors.append(msg))

    orchestrator.run()

    assert len(errors) == 1
    assert "Budget global de tokens dépassé" in errors[0]


def test_orchestrator_state_persistence_to_db():
    """Vérifie la création et mise à jour de PipelineRunModel en base de données."""
    pipeline = PipelineModel.create(name="Pipeline Persistance DB")
    persona = PersonaModel.create(name="Agent JSON", system_prompt="Prompt", output_format="json")
    PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=1, step_type="LLM_PROMPT")

    provider = DummyProvider()
    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        ai_provider=provider,
        persist_state=True,
    )

    finished_states: list[Any] = []
    orchestrator.signals.pipeline_finished.connect(lambda st: finished_states.append(st))

    orchestrator.run()

    assert len(finished_states) == 1
    assert orchestrator.run_id is not None

    run_db = PipelineRunModel.get_by_id(orchestrator.run_id)
    assert run_db.status == "completed"
    assert run_db.pipeline.id == pipeline.id
    saved_state = json.loads(run_db.state_data)
    assert "generated_cards" in saved_state["variables"]
    assert "step_execution_counts" in saved_state


def test_orchestrator_resume_from_persisted_run():
    """Vérifie la reprise d'un run interrompu via PipelineOrchestrator.resume_run."""
    pipeline = PipelineModel.create(name="Pipeline Reprise Run")
    persona = PersonaModel.create(name="Agent Reprise", system_prompt="Prompt", output_format="text")
    PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=1, step_type="LLM_PROMPT")
    PipelineStepModel.create(pipeline=pipeline, persona=persona, step_order=2, step_type="LLM_PROMPT")

    # Création d'un run en pause ou interrompu à l'étape 2
    initial_st = PipelineRunState(initial_prompt="Prompt initial")
    initial_st.set_variable("restored_key", "restored_value")

    run_db = PipelineRunModel.create(
        pipeline=pipeline,
        status="paused",
        current_step_order=2,
        state_data=json.dumps(initial_st.to_dict()),
    )

    provider = DummyProvider()
    orchestrator = PipelineOrchestrator.resume_run(
        run_id=run_db.id,
        ai_provider=provider,
    )

    started_steps: list[int] = []
    orchestrator.signals.step_started.connect(lambda order, desc: started_steps.append(order))

    finished_states: list[Any] = []
    orchestrator.signals.pipeline_finished.connect(lambda st: finished_states.append(st))

    orchestrator.run()

    # Reprise directement à l'étape 2
    assert started_steps == [2]
    assert len(finished_states) == 1
    assert finished_states[0].get_variable("restored_key") == "restored_value"

    run_refreshed = PipelineRunModel.get_by_id(run_db.id)
    assert run_refreshed.status == "completed"


def test_call_provider_generate_filters_signature_and_does_not_retry_internal_typeerror(mock_db):
    """Vérifie que _call_provider_generate filtre les kwargs selon la signature et ne masque pas les TypeError internes."""

    class CustomProviderWithoutTemperature(LLMProvider):
        def __init__(self) -> None:
            self.call_count = 0

        def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
            self.call_count += 1
            return '{"ok": true}'

    pipeline = PipelineModel.create(name="SigTest", description="desc")
    orch = PipelineOrchestrator(pipeline_id=pipeline.id, ai_provider=DummyProvider())

    # 1. Fournisseur sans paramètre temperature ni max_tokens dans la signature
    custom_prov = CustomProviderWithoutTemperature()
    res = orch._call_provider_generate(
        custom_prov,
        system_prompt="sys",
        user_prompt="usr",
        temperature=0.7,
        max_tokens=2048,
    )
    assert res == '{"ok": true}'
    assert custom_prov.call_count == 1

    # 2. Fournisseur qui lève un TypeError interne (ex: NoneType subscriptable)
    class BuggyInternalProvider(LLMProvider):
        def __init__(self) -> None:
            self.call_count = 0

        def generate(
            self,
            system_prompt: str,
            user_prompt: str | list[dict[str, Any]],
            response_format: str = "json",
            max_tokens: int | None = None,
            temperature: float | None = None,
        ) -> str:
            self.call_count += 1
            # Erreur interne dans le corps de generate()
            raise TypeError("'NoneType' object is not subscriptable")

    buggy_prov = BuggyInternalProvider()
    with pytest.raises(TypeError, match="'NoneType' object is not subscriptable"):
        orch._call_provider_generate(
            buggy_prov,
            system_prompt="sys",
            user_prompt="usr",
            temperature=0.7,
            max_tokens=2048,
        )

    # Doit avoir été appelé EXACTEMENT une fois, SANS retry aveugle !
    assert buggy_prov.call_count == 1


def test_pipeline_run_state_logs_thought_and_retrieval():
    """PipelineRunState enregistre le champ thought dans execution_history et le sérialise."""
    state = PipelineRunState(document_id=10, initial_prompt="Générer")
    thought_text = "Étape 1 : Analyse des faits scientifiques majeurs."
    state.log_step_execution(
        step_order=1,
        step_type="LLM_PROMPT",
        status="SUCCESS",
        duration_sec=1.25,
        details="OK",
        tokens_used=150,
        thought=thought_text,
    )

    assert len(state.execution_history) == 1
    hist = state.execution_history[0]
    assert hist["thought"] == thought_text
    assert state.get_step_thought(1) == thought_text
    assert state.get_step_thought(999) is None

    # Test sérialisation & désérialisation
    serialized = state.to_dict()
    assert serialized["execution_history"][0]["thought"] == thought_text

    restored = PipelineRunState.from_dict(serialized)
    assert restored.get_step_thought(1) == thought_text


def test_orchestrator_captures_thought_in_state_and_history():
    """L'orchestrateur extrait le thought de LLMResult, le stocke dans state et execution_history."""
    from ankiforge.services.ai.base import LLMResult

    class ThinkingProvider(LLMProvider):
        def generate_response(
            self,
            system_prompt: str,
            user_prompt: str | list[dict[str, Any]],
            response_format: str = "json",
            max_tokens: int | None = None,
            temperature: float | None = None,
        ) -> LLMResult:
            return LLMResult(
                content='{"cards": [{"Front": "Quelle est la capitale ?", "Back": "Paris"}]}',
                thought="Raisonnement sur la capitale de la France.",
            )

        def generate(self, *args: Any, **kwargs: Any) -> str:
            return self.generate_response(*args, **kwargs).content

    pipeline = PipelineModel.create(name="ThoughtPipeline", description="Test thought trace")
    PipelineStepModel.create(
        pipeline=pipeline,
        step_order=1,
        step_type="LLM_PROMPT",
        config_data=json.dumps({"output_format": "json"}),
    )

    orch = PipelineOrchestrator(pipeline_id=pipeline.id, ai_provider=ThinkingProvider())
    orch.run()

    # Vérifications dans l'état final
    assert orch.state.get_step_thought(1) == "Raisonnement sur la capitale de la France."
    assert orch.state.get_variable("thought_step_1") == "Raisonnement sur la capitale de la France."
    assert orch.state.get_variable("last_thought") == "Raisonnement sur la capitale de la France."

    # Les cartes doivent être correctement extraites
    cards = orch.state.get_variable("generated_cards")
    assert cards is not None
    assert len(cards) == 1
    assert cards[0]["Front"] == "Quelle est la capitale ?"


def test_orchestrator_handles_think_tags_in_raw_content():
    """L'orchestrateur sépare les balises <think> et ne corrompt pas le parsing JSON des cartes."""
    from ankiforge.services.ai.base import LLMResult

    class ThinkTagProvider(LLMProvider):
        def generate_response(
            self,
            system_prompt: str,
            user_prompt: str | list[dict[str, Any]],
            response_format: str = "json",
            max_tokens: int | None = None,
            temperature: float | None = None,
        ) -> LLMResult:
            # Même si le fournisseur renvoie le format avec balises dans content
            raw = '<think>Pensees en direct du modele local</think>{"cards": [{"Front": "QTag", "Back": "ATag"}]}'
            from ankiforge.services.ai.flexible_service import extract_thought_tags

            c, th = extract_thought_tags(raw)
            return LLMResult(content=c, thought=th)

        def generate(self, *args: Any, **kwargs: Any) -> str:
            return self.generate_response(*args, **kwargs).content

    pipeline = PipelineModel.create(name="ThinkTagPipeline", description="Test think tag handling")
    PipelineStepModel.create(
        pipeline=pipeline,
        step_order=1,
        step_type="LLM_PROMPT",
        config_data=json.dumps({"output_format": "json"}),
    )

    orch = PipelineOrchestrator(pipeline_id=pipeline.id, ai_provider=ThinkTagProvider())
    orch.run()

    assert orch.state.get_step_thought(1) == "Pensees en direct du modele local"
    cards = orch.state.get_variable("generated_cards")
    assert cards is not None
    assert len(cards) == 1
    assert cards[0]["Front"] == "QTag"


def test_orchestrator_map_reduce_captures_thoughts():
    """L'orchestrateur agrège les chaînes de pensée de chaque élément en MAP_REDUCE."""
    from ankiforge.services.ai.base import LLMResult

    class MapReduceThinkingProvider(LLMProvider):
        def generate_response(
            self,
            system_prompt: str,
            user_prompt: str | list[dict[str, Any]],
            response_format: str = "json",
            max_tokens: int | None = None,
            temperature: float | None = None,
        ) -> LLMResult:
            prompt_str = str(user_prompt)
            thought = f"Réflexion sur l'élément : {prompt_str[:15]}"
            cards = [{"Front": f"Front for {prompt_str[:10]}", "Back": "Back"}]
            return LLMResult(content=json.dumps({"cards": cards}), thought=thought)

    pipeline = PipelineModel.create(name="MRThoughtPipeline", description="Test MR thought trace")
    PipelineStepModel.create(
        pipeline=pipeline,
        step_order=1,
        step_type="MAP_REDUCE",
        config_data=json.dumps(
            {
                "items_variable": "input_items",
                "output_format": "json",
            }
        ),
    )

    orch = PipelineOrchestrator(pipeline_id=pipeline.id, ai_provider=MapReduceThinkingProvider())
    orch.state.set_variable("input_items", ["chunk 1 text", "chunk 2 text"])
    orch.run()

    step1_thought = orch.state.get_step_thought(1)
    assert step1_thought is not None
    assert "[Élément 1/2]" in step1_thought
    assert "[Élément 2/2]" in step1_thought
    assert "Réflexion sur l'élément" in step1_thought
    assert orch.state.get_variable("last_thought") == step1_thought

    generated_cards = orch.state.get_variable("generated_cards")
    assert generated_cards is not None
    assert len(generated_cards) == 2
