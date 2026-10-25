"""Tests d'intégration et de non-régression pour le déclenchement asynchrone MCP de pipelines DAG et finalisation Staged."""

from __future__ import annotations

import asyncio
import json
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
    StagedBundleModel,
)
from ankiforge.services.ai.mcp_server import mcp
from ankiforge.services.ai.mcp_tool_registry import MCPToolRegistry
from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

pytestmark = pytest.mark.integration


@pytest.fixture
def pipeline_env(mock_db: Any) -> dict[str, Any]:
    """Prépare un environnement complet avec Deck, NoteType et Pipelines de test."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Sciences::Physique_{uid}")
    note_type = NoteTypeModel.create(
        name=f"Basique_{uid}",
        fields_schema=json.dumps([{"name": "Front"}, {"name": "Back"}]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{Front}}<hr>{{Back}}"}]),
    )

    # 1. Pipeline de nettoyage Python (Nettoyeur HTML/LaTeX)
    clean_pipeline = PipelineModel.create(
        name=f"Pipeline Finition Clean_{uid}",
        description="Nettoie HTML et harmonise LaTeX",
    )
    PipelineStepModel.create(
        pipeline=clean_pipeline,
        step_order=1,
        step_type="PYTHON_TOOL",
        config_data=json.dumps({"tool_name": "clean_html_latex"}),
    )

    return {
        "deck": deck,
        "note_type": note_type,
        "clean_pipeline": clean_pipeline,
        "uid": uid,
    }


def test_trigger_pipeline_run_anti_hallucination_deck_not_found(pipeline_env: dict[str, Any]) -> None:
    """Vérifie le rejet explicite si le deck cible n'existe pas en base."""
    raw_res = MCPToolRegistry.trigger_pipeline_run(
        pipeline_id=pipeline_env["clean_pipeline"].id,
        deck_name="Inexistant::Paquet_Fantome",
        cards_json=json.dumps([{"Front": "Q1", "Back": "R1"}]),
    )
    res = json.loads(raw_res)
    assert res["status"] == "error"
    assert "Inexistant::Paquet_Fantome" in res["message"]


def test_trigger_pipeline_run_pipeline_not_found(pipeline_env: dict[str, Any]) -> None:
    """Vérifie le rejet explicite si le pipeline_id est introuvable."""
    raw_res = MCPToolRegistry.trigger_pipeline_run(
        pipeline_id=999999,
        deck_name=pipeline_env["deck"].name,
        cards_json=json.dumps([{"Front": "Q1", "Back": "R1"}]),
    )
    res = json.loads(raw_res)
    assert res["status"] == "error"
    assert "999999" in res["message"]


def test_trigger_pipeline_run_invalid_cards_json(pipeline_env: dict[str, Any]) -> None:
    """Vérifie le rejet si cards_json n'est pas un JSON valide ou est vide."""
    # JSON invalide
    raw_res1 = MCPToolRegistry.trigger_pipeline_run(
        pipeline_id=pipeline_env["clean_pipeline"].id,
        deck_name=pipeline_env["deck"].name,
        cards_json="{malformed json",
    )
    res1 = json.loads(raw_res1)
    assert res1["status"] == "error"

    # Liste vide
    raw_res2 = MCPToolRegistry.trigger_pipeline_run(
        pipeline_id=pipeline_env["clean_pipeline"].id,
        deck_name=pipeline_env["deck"].name,
        cards_json="[]",
    )
    res2 = json.loads(raw_res2)
    assert res2["status"] == "error"


def test_trigger_pipeline_run_execution_and_staged_finalization(pipeline_env: dict[str, Any]) -> None:
    """Vérifie le cycle complet : déclenchement asynchrone, traitement DAG et conversion en StagedBundle."""
    deck = pipeline_env["deck"]
    note_type = pipeline_env["note_type"]
    pipeline = pipeline_env["clean_pipeline"]

    cards_to_process = [
        {
            "Front": "Quelle est la valeur de $$x^2$$ ? <script>alert(1)</script>",
            "Back": "La valeur est $x \\cdot x$.",
            "tags": ["maths", "algebre"],
        },
        {
            "Front": "Définition de <p>l'énergie cinétique</p> :",
            "Back": "$$E_c = \\frac{1}{2}mv^2$$",
            "tags": ["physique"],
        },
    ]

    # Déclenchement
    raw_trigger = MCPToolRegistry.trigger_pipeline_run(
        pipeline_id=pipeline.id,
        deck_name=deck.name,
        cards_json=json.dumps(cards_to_process),
        note_type_name=note_type.name,
    )
    trigger_res = json.loads(raw_trigger)
    assert trigger_res["status"] == "started"
    assert trigger_res["cards_count"] == 2
    run_id = trigger_res["run_id"]
    assert run_id > 0

    # Attente impérative de l'achèvement de l'exécution dans le pool de threads Qt
    pool = QThreadPool.globalInstance()
    finished = pool.waitForDone(10000)
    assert finished, "Le worker du pipeline ne s'est pas terminé dans le délai imparti."

    # Vérification de l'état du run en base
    run = PipelineRunModel.get_by_id(run_id)
    assert run.status == "staged"

    # Vérification de l'enrichissement de get_pipeline_run
    raw_status = MCPToolRegistry.get_pipeline_run(run_id=run_id)
    assert "STAGED" in raw_status
    json_start = raw_status.find("{", raw_status.find("Run DAG"))
    json_end = raw_status.rfind("}") + 1
    run_details = json.loads(raw_status[json_start:json_end])
    assert run_details["status"] == "staged"
    bundle_id = run_details.get("bundle_id")
    assert bundle_id is not None
    assert bundle_id.startswith("bundle_")

    # Vérification de l'intégrité du StagedBundle
    bundle = StagedBundleModel.get_or_none(StagedBundleModel.bundle_id == bundle_id)
    assert bundle is not None
    assert bundle.status == "pending"
    assert bundle.total_steps >= 1

    patches = list(bundle.patches)
    assert len(patches) == 1
    patch = patches[0]
    assert patch.patch_type == "batch_note_create"
    diff = json.loads(patch.diff_payload)
    assert diff["count"] == 2

    # Vérifier que le nettoyage LaTeX et HTML a bien été opéré par l'étape PYTHON_TOOL
    cleaned_cards = diff["notes"]
    c1 = cleaned_cards[0]
    assert "\\\\[x^2\\\\]" in c1["fields"]["Front"] or "\\[x^2\\]" in c1["fields"]["Front"]
    assert "<script>" not in c1["fields"]["Front"]
    assert "\\\\(x \\\\cdot x\\\\)" in c1["fields"]["Back"] or "\\(x \\cdot x\\)" in c1["fields"]["Back"]

    # Application du bundle dans la collection physique (Two-Phase Commit)
    apply_res = StagedPatchRegistry.apply_bundle_all(bundle_id)
    assert apply_res["status"] == "applied"
    assert apply_res["applied_steps_count"] == 1

    # Les notes doivent maintenant exister en base
    created_notes = list(NoteModel.select())
    assert len(created_notes) == 2
    for n in created_notes:
        card = n.cards.first()
        assert card is not None
        assert card.deck.id == deck.id
        assert n.note_type.id == note_type.id


def test_trigger_pipeline_run_with_document_and_variables(pipeline_env: dict[str, Any]) -> None:
    """Vérifie le déclenchement avec document_id et variables_json personnalisées."""
    from ankiforge.database.models import DocumentModel

    deck = pipeline_env["deck"]
    pipeline = pipeline_env["clean_pipeline"]
    doc = DocumentModel.create(title="Cours d'électromagnétisme", content="Texte cours")

    # Document inexistant -> rejet
    res_err = json.loads(
        MCPToolRegistry.trigger_pipeline_run(
            pipeline_id=pipeline.id,
            deck_name=deck.name,
            cards_json=json.dumps([{"Front": "Q", "Back": "R"}]),
            document_id=88888,
        )
    )
    assert res_err["status"] == "error"
    assert "88888" in res_err["message"]

    # Document valide + variables
    res_ok = json.loads(
        MCPToolRegistry.trigger_pipeline_run(
            pipeline_id=pipeline.id,
            deck_name=deck.name,
            cards_json=json.dumps([{"Front": "Champ E : $$E = -\\nabla V$$", "Back": "Formule"}]),
            document_id=doc.id,
            variables_json=json.dumps({"temperature": 0.2, "custom_tag": "maxwell"}),
        )
    )
    assert res_ok["status"] == "started"
    QThreadPool.globalInstance().waitForDone(10000)

    run = PipelineRunModel.get_by_id(res_ok["run_id"])
    assert run.status == "staged"


def test_trigger_pipeline_run_default_note_type_resolution(pipeline_env: dict[str, Any]) -> None:
    """Vérifie que note_type_name omis est automatiquement résolu vers le modèle par défaut."""
    deck = pipeline_env["deck"]
    pipeline = pipeline_env["clean_pipeline"]

    res_raw = MCPToolRegistry.trigger_pipeline_run(
        pipeline_id=pipeline.id,
        deck_name=deck.name,
        cards_json=json.dumps([{"Front": "Question auto", "Back": "Réponse auto"}]),
        note_type_name="",  # Omis
    )
    res = json.loads(res_raw)
    assert res["status"] == "started"
    QThreadPool.globalInstance().waitForDone(10000)

    run = PipelineRunModel.get_by_id(res["run_id"])
    assert run.status == "staged"


def test_trigger_pipeline_run_with_llm_step(pipeline_env: dict[str, Any]) -> None:
    """Vérifie l'exécution d'un pipeline avec étape LLM_PROMPT déterministe (MockProvider)."""
    uid = pipeline_env["uid"]
    deck = pipeline_env["deck"]
    note_type = pipeline_env["note_type"]

    persona = PersonaModel.create(
        name=f"Linter Persona_{uid}",
        system_prompt="Linter de cartes",
        persona_type="pipeline",
    )
    llm_pipeline = PipelineModel.create(
        name=f"Pipeline LLM_{uid}",
        description="Pipeline avec étape LLM",
    )
    PipelineStepModel.create(
        pipeline=llm_pipeline,
        persona=persona,
        step_order=1,
        step_type="LLM_PROMPT",
        config_data=json.dumps({"input_variable": "generated_cards"}),
    )

    cards = [{"Front": "Concept initial", "Back": "Définition initiale"}]
    res_raw = MCPToolRegistry.trigger_pipeline_run(
        pipeline_id=llm_pipeline.id,
        deck_name=deck.name,
        cards_json=json.dumps(cards),
        note_type_name=note_type.name,
    )
    res = json.loads(res_raw)
    assert res["status"] == "started"

    finished = QThreadPool.globalInstance().waitForDone(10000)
    assert finished

    run = PipelineRunModel.get_by_id(res["run_id"])
    assert run.status == "staged"


def test_fastmcp_trigger_pipeline_run_exposed() -> None:
    """Vérifie que FastMCP expose bien l'outil trigger_pipeline_run avec sa signature canonique."""

    async def _check() -> list[str]:
        tools = await mcp.list_tools()
        return [t.name for t in tools]

    tool_names = asyncio.run(_check())
    assert "trigger_pipeline_run" in tool_names
