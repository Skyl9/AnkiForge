"""Tests unitaires et d'intégration de la voie d'exécution déléguée MCP des pipelines DAG.

Couvre les 4 tickets précédents :
- contrat trigger_pipeline_run (prompt persona par étape + empreinte SHA-256)
- distinction des modes d'exécution dans PipelineOrchestrator (local vs délégué)
- staging des résultats dans le Garde-Fou MCP sans écriture BDD directe
- gestion du timeout et de l'annulation d'étape déléguée

Tous les appels à l'agent externe MCP sont mockés de manière déterministe (zéro appel réseau).
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import pytest
from PySide6.QtCore import QThreadPool

from ankiforge.database.models import (
    DeckModel,
    NoteModel,
    NoteTypeModel,
    PersonaModel,
    PipelineModel,
    PipelineRunModel,
    PipelineStepModel,
    StagedPatchModel,
)
from ankiforge.services.ai.mcp_tool_registry import MCPToolRegistry
from ankiforge.services.ai.orchestrator import PipelineOrchestrator
from ankiforge.services.ai.persona_override import _digest, resolve_system_prompt


def _build_delegated_pipeline(uid: str) -> dict[str, Any]:
    """Construit un pipeline avec une étape LLM_PROMPT assortie d'une persona."""
    deck = DeckModel.create(name=f"Sciences::Physique_{uid}")
    note_type = NoteTypeModel.create(
        name=f"Basique_{uid}",
        fields_schema=json.dumps([{"name": "Front"}, {"name": "Back"}]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{Front}}<hr>{{Back}}"}]),
    )
    persona = PersonaModel.create(
        name=f"Architecte_{uid}",
        system_prompt="Tu es un expert qui génère des flashcards au format JSON.",
        persona_type="pipeline",
    )
    pipeline = PipelineModel.create(name=f"Pipeline Delegue_{uid}", description="Pipeline en mode délégué MCP.")
    PipelineStepModel.create(
        pipeline=pipeline,
        persona=persona,
        step_order=1,
        step_type="LLM_PROMPT",
        config_data=json.dumps({"input_variable": "text_source", "output_format": "json"}),
    )
    return {"deck": deck, "note_type": note_type, "persona": persona, "pipeline": pipeline, "uid": uid}


@pytest.mark.unit
def test_resolve_system_prompt_et_empreinte_sha256_pour_delegation() -> None:
    """Le prompt résolu pour une étape déléguée et son empreinte SHA-256 sont déterministes et détectent le drift."""
    uid = uuid.uuid4().hex[:6]
    persona = PersonaModel.create(
        name=f"P_Digest_{uid}",
        system_prompt="Génère des cartes JSON strictes.",
        persona_type="pipeline",
    )
    prompt = resolve_system_prompt({}, persona)
    assert prompt == "Génère des cartes JSON strictes."

    digest_a = _digest(prompt)
    digest_b = _digest(prompt)
    assert digest_a == digest_b
    assert len(digest_a) == 64  # SHA-256 hex

    # Même texte reformaté (espaces) -> même empreinte (pas de faux drift)
    assert _digest("Génère des cartes JSON strictes.  \n") == digest_a

    # Autre texte -> empreinte différente (drift réel détecté)
    assert _digest("Autre consigne.") != digest_a


@pytest.mark.unit
def test_orchestrateur_mode_delegue_stocke_resultat_en_staging_sans_ecriture_bdd() -> None:
    """En mode délégué, l'orchestrateur appelle le fournisseur externe et stocke le résultat dans un StagedPatchModel sans créer de note en base."""
    env = _build_delegated_pipeline("orch_direct")
    pipeline = env["pipeline"]
    step = PipelineStepModel.get((PipelineStepModel.pipeline == pipeline) & (PipelineStepModel.step_order == 1))

    contenu_agent = '{"Front": "Capitale de la France ?", "Back": "Paris"}'

    def fournisseur_externe(request: dict[str, Any]) -> dict[str, Any]:
        assert request["step_order"] == 1
        assert request["persona_prompt"] == "Tu es un expert qui génère des flashcards au format JSON."
        assert request["persona_prompt_digest"]
        assert request["persona_name"] == f"Architecte_{env['uid']}"
        assert "input_context" in request
        return {"content": contenu_agent, "status": "completed"}

    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        execution_mode="mcp_delegated",
        timeout_per_step_seconds=5,
        delegate_content_provider=fournisseur_externe,
    )
    orchestrator.state.set_variable("last_output", "contexte source")
    orchestrator._execute_delegated_ia_step(step)

    # Résultat stocké dans l'état, pas de note créée directement en base
    assert orchestrator.state.get_variable("result_step_1") == contenu_agent
    assert orchestrator.state.get_variable("delegated_pending") is None
    assert NoteModel.select().count() == 0

    # Un patch de staging a été créé pour l'étape déléguée
    patches = list(StagedPatchModel.select().where(StagedPatchModel.patch_type == "pipeline_step_delegated"))
    assert len(patches) == 1
    patch = patches[0]
    assert patch.status == "pending"
    payload = json.loads(patch.diff_payload)
    assert payload["type"] == "pipeline_step_delegated"
    assert payload["persona_prompt"] == "Tu es un expert qui génère des flashcards au format JSON."
    assert payload["persona_prompt_digest"] == _digest("Tu es un expert qui génère des flashcards au format JSON.")
    assert payload["persona_name"] == f"Architecte_{env['uid']}"
    assert payload["generated_content"] == contenu_agent
    assert payload["run_id"] == orchestrator.run_id
    assert patch.bundle is not None
    assert patch.bundle.status == "building"  # scellé seulement à la fin du run


@pytest.mark.unit
def test_orchestrateur_mode_delegue_timeout_etape() -> None:
    """En cas de timeout de l'agent externe, l'étape déléguée est marquée en échec."""
    env = _build_delegated_pipeline("timeout")
    pipeline = env["pipeline"]
    step = PipelineStepModel.get((PipelineStepModel.pipeline == pipeline) & (PipelineStepModel.step_order == 1))

    def fournisseur_silencieux(request: dict[str, Any]) -> dict[str, Any] | None:
        # L'agent externe ne répond jamais : simule un timeout
        return None

    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        execution_mode="mcp_delegated",
        timeout_per_step_seconds=1,
        delegate_content_provider=fournisseur_silencieux,
    )
    with pytest.raises(TimeoutError):
        orchestrator._execute_delegated_ia_step(step)

    errors = orchestrator.state.errors
    assert any("timeout" in e.lower() for e in errors), errors


@pytest.mark.unit
def test_orchestrateur_mode_local_n_appelle_pas_le_fournisseur_externe() -> None:
    """En mode local, le fournisseur de contenu délégué n'est jamais sollicité (comportement inchangé)."""
    env = _build_delegated_pipeline("local")
    pipeline = env["pipeline"]
    step = PipelineStepModel.get((PipelineStepModel.pipeline == pipeline) & (PipelineStepModel.step_order == 1))

    appels: list[dict[str, Any]] = []

    def fournisseur_externe(request: dict[str, Any]) -> dict[str, Any]:
        appels.append(request)
        return {"content": "X", "status": "completed"}

    orchestrator = PipelineOrchestrator(
        pipeline_id=pipeline.id,
        execution_mode="local",
        delegate_content_provider=fournisseur_externe,
    )
    # En mode local, l'étape IA est exécutée par _execute_llm_prompt, pas par le délégué.
    orchestrator._execute_llm_prompt(step)
    assert appels == []
    assert orchestrator.execution_mode == "local"


@pytest.mark.integration
def test_trigger_pipeline_run_delegue_contrat_prompt_par_etape() -> None:
    """Contrat MCP : déclenchement délégué, remise du contenu par provide_pipeline_step_content aboutit à un patch de staging sans écriture BDD directe."""
    env = _build_delegated_pipeline("mcp_contrat")
    pipeline = env["pipeline"]
    deck = env["deck"]

    raw = MCPToolRegistry.trigger_pipeline_run(
        pipeline_id=pipeline.id,
        deck_name=deck.name,
        execution_mode="mcp_delegated",
        timeout_per_step_seconds=5,
    )
    res = json.loads(raw)
    assert res["status"] == "started"
    assert res["execution_mode"] == "mcp_delegated"
    assert res["timeout_per_step_seconds"] == 5
    run_id = res["run_id"]

    # L'orchestrateur démarre de façon asynchrone et bloque sur l'attente du contenu
    # de l'étape 1. On réessaye la remise jusqu'à ce que l'étape soit en attente.
    delivered = False
    for _ in range(100):
        raw2 = MCPToolRegistry.provide_pipeline_step_content(
            run_id=run_id,
            step_order=1,
            generated_content='{"Front": "Q", "Back": "R"}',
            status="completed",
        )
        res2 = json.loads(raw2)
        if res2.get("status") == "delivered":
            delivered = True
            break
        time.sleep(0.05)
    assert delivered, f"L'étape 1 n'a jamais été en attente (dernière réponse : {res2})"
    assert res2["status"] == "delivered"
    assert res2["step_order"] == 1

    finished = QThreadPool.globalInstance().waitForDone(10000)
    assert finished, "L'orchestrateur délégué ne s'est pas terminé dans le délai."

    run = PipelineRunModel.get_by_id(run_id)
    assert run.status == "staged"

    # Le résultat est dans un patch de staging en attente (Garde-Fou MCP), pas en note directe
    patches = list(StagedPatchModel.select().where((StagedPatchModel.patch_type == "pipeline_step_delegated") & (StagedPatchModel.status == "pending")))
    assert len(patches) >= 1
    payload = json.loads(patches[0].diff_payload)
    assert payload["persona_prompt"]
    assert payload["persona_prompt_digest"]
    assert payload["generated_content"] == '{"Front": "Q", "Back": "R"}'
    assert NoteModel.select().count() == 0


@pytest.mark.integration
def test_timeout_etape_delegue_run_echec() -> None:
    """Un timeout d'étape déléguée fait échouer le run (pas de blocage indéfini)."""
    env = _build_delegated_pipeline("mcp_timeout")
    pipeline = env["pipeline"]
    deck = env["deck"]

    MCPToolRegistry.trigger_pipeline_run(
        pipeline_id=pipeline.id,
        deck_name=deck.name,
        execution_mode="mcp_delegated",
        timeout_per_step_seconds=1,
    )
    # Aucun appel de provide_pipeline_step_content : timeout après 1 seconde.

    finished = QThreadPool.globalInstance().waitForDone(10000)
    assert finished

    runs = list(PipelineRunModel.select().where(PipelineRunModel.pipeline == pipeline))
    assert runs, "Un run doit avoir été créé."
    # Le run bascule en échec dès que l'étape déléguée expire.
    assert any(run.status in ("failed", "cancelled") for run in runs), [r.status for r in runs]


@pytest.mark.integration
def test_annulation_pipeline_run_delegue() -> None:
    """L'outil abort_pipeline_run interrompt une exécution déléguée bloquée sur une étape."""
    env = _build_delegated_pipeline("mcp_abort")
    pipeline = env["pipeline"]
    deck = env["deck"]

    MCPToolRegistry.trigger_pipeline_run(
        pipeline_id=pipeline.id,
        deck_name=deck.name,
        execution_mode="mcp_delegated",
        timeout_per_step_seconds=60,
    )
    time.sleep(0.3)  # Laisse à l'orchestrateur le temps de bloquer sur l'attente du contenu.

    raw_abort = MCPToolRegistry.abort_pipeline_run(run_id=PipelineRunModel.select().order_by(PipelineRunModel.id.desc()).limit(1).get().id, reason="Test annulation")
    res_abort = json.loads(raw_abort)
    assert res_abort["status"] == "aborted"

    finished = QThreadPool.globalInstance().waitForDone(10000)
    assert finished

    run = PipelineRunModel.select().order_by(PipelineRunModel.id.desc()).limit(1).get()
    assert run.status in ("cancelled", "failed"), run.status


@pytest.mark.unit
def test_staged_patch_pipeline_delegue_visible_dans_garde_fou() -> None:
    """Un patch de staging issu d'un pipeline délégué est présent en base (affichable par le Garde-Fou MCP)."""
    env = _build_delegated_pipeline("garde_fou")
    pipeline = env["pipeline"]

    from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

    bundle_id = StagedPatchRegistry_begin_bundle_for_test(pipeline)
    StagedPatchRegistry_create_patch_for_test(bundle_id, pipeline)
    StagedPatchRegistry.commit_bundle(bundle_id)

    patches = list(StagedPatchModel.select().where((StagedPatchModel.patch_type == "pipeline_step_delegated") & (StagedPatchModel.status == "pending")))
    assert len(patches) == 1
    assert patches[0].bundle is not None
    assert patches[0].bundle.status == "pending"


# ---------------------------------------------------------------------------
# Helpers locaux pour le test de visibilité Garde-Fou (évite d'importer le widget UI ici)
# ---------------------------------------------------------------------------


def StagedPatchRegistry_begin_bundle_for_test(pipeline: PipelineModel) -> str:
    from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

    return StagedPatchRegistry.begin_bundle(
        title=f"Pipeline délégué #{pipeline.id}",
        explanation="Test visibilité Garde-Fou.",
    )


def StagedPatchRegistry_create_patch_for_test(bundle_id: str, pipeline: PipelineModel) -> None:
    from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

    StagedPatchRegistry.create_patch(
        patch_type="pipeline_step_delegated",
        diff_payload={
            "type": "pipeline_step_delegated",
            "pipeline_id": pipeline.id,
            "step_order": 1,
            "step_type": "LLM_PROMPT",
            "persona_prompt": "Prompt de test.",
            "persona_prompt_digest": _digest("Prompt de test."),
            "persona_name": "Testeur",
            "generated_content": '{"Front": "Q", "Back": "R"}',
            "title": "Étape déléguée 1 [LLM_PROMPT]",
        },
        bundle_id=bundle_id,
    )
