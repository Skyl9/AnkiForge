"""Tests unitaires et d'intégration pour les outils MCP d'accès aux albums et de gestion des pipelines DAG."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from ankiforge.database.models import (
    DocumentModel,
    DocumentPageModel,
    FolderModel,
    MediaModel,
    PersonaModel,
    PipelineModel,
    PipelineRunModel,
    PipelineStepModel,
)
from ankiforge.services.ai.mcp_server import mcp
from ankiforge.services.ai.mcp_tool_registry import (
    DEFAULT_CONSULTANT_TOOLS,
    MCPToolRegistry,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def album_dataset():
    uid = uuid.uuid4().hex[:6]
    folder = FolderModel.create(name=f"Dossier Anatomie {uid}")

    # Album 1 avec dossier et 3 planches
    album1 = DocumentModel.create(
        title=f"Planches Anatomiques {uid}",
        file_type="album",
        total_pages=3,
        folder=folder,
    )
    media1 = MediaModel.create(
        filename=f"planche_1_{uid}.png",
        original_name="p1.png",
        checksum=f"chk1_{uid}",
        mime_type="image/png",
    )
    media2 = MediaModel.create(
        filename=f"planche_2_{uid}.png",
        original_name="p2.png",
        checksum=f"chk2_{uid}",
        mime_type="image/png",
    )
    media3 = MediaModel.create(
        filename=f"planche_3_{uid}.png",
        original_name="p3.png",
        checksum=f"chk3_{uid}",
        mime_type="image/png",
    )

    p1 = DocumentPageModel.create(
        document=album1,
        media=media1,
        page_number=1,
        rotation=0,
        status="ready",
        ocr_text="Titre : Le Crâne Humain. Os frontal et pariétal.",
        crop_data=json.dumps([10, 20, 200, 300]),
    )
    p2 = DocumentPageModel.create(
        document=album1,
        media=media2,
        page_number=2,
        rotation=90,
        status="stale",
        ocr_text="",
        crop_data=None,
    )
    p3 = DocumentPageModel.create(
        document=album1,
        media=media3,
        page_number=3,
        rotation=0,
        status="pending",
        ocr_text="Détail mandibule et arcade dentaire.",
        crop_data=None,
    )

    # Album 2 sans dossier et sans planches
    album2 = DocumentModel.create(
        title=f"Croquis Botaniques {uid}",
        file_type="album",
        total_pages=0,
        folder=None,
    )

    # Document normal (non album)
    doc_pdf = DocumentModel.create(
        title=f"Cours Magistral {uid}",
        file_type="pdf",
        total_pages=10,
    )

    return {
        "folder": folder,
        "album1": album1,
        "album2": album2,
        "doc_pdf": doc_pdf,
        "pages": [p1, p2, p3],
    }


@pytest.fixture
def dag_dataset():
    uid = uuid.uuid4().hex[:6]
    persona = PersonaModel.create(
        name=f"Extracteur {uid}",
        persona_type="pipeline",
        system_prompt="Extrais les points clés.",
    )

    pipeline = PipelineModel.create(
        name=f"Pipeline Génération {uid}",
        description="Pipeline complet de génération de cartes.",
    )

    s1 = PipelineStepModel.create(
        pipeline=pipeline,
        step_order=1,
        step_type="LLM_PROMPT",
        persona=persona,
        failure_behavior="stop",
        config_data=json.dumps({"token_budget": 1000}),
    )
    s2 = PipelineStepModel.create(
        pipeline=pipeline,
        step_order=2,
        step_type="PYTHON_TOOL",
        failure_behavior="continue",
        config_data=json.dumps({"script_name": "clean_html"}),
    )

    # Enregistrer un run
    state_payload = {
        "total_tokens": 450,
        "completed_steps": [1],
        "step_execution_counts": {"1": 1},
        "step_tokens": {"1": 450},
        "errors": [],
        "variables": {"generated_cards": [{"front": "Q", "back": "A"}]},
    }
    run = PipelineRunModel.create(
        pipeline=pipeline,
        status="completed",
        current_step_order=2,
        state_data=json.dumps(state_payload),
    )

    return {
        "pipeline": pipeline,
        "persona": persona,
        "steps": [s1, s2],
        "run": run,
    }


# =====================================================================
# TESTS OUTILS ALBUMS
# =====================================================================


def test_list_albums(album_dataset):
    """Vérifie le listage des albums, la pagination et le filtrage par dossier."""
    # Listage sans filtre
    res = MCPToolRegistry.list_albums(limit=10, offset=0)
    assert album_dataset["album1"].title in res
    assert album_dataset["album2"].title in res
    assert album_dataset["doc_pdf"].title not in res
    assert "Planches Anatomiques" in res

    # Filtrage par dossier
    res_folder = MCPToolRegistry.list_albums(folder_name=album_dataset["folder"].name)
    assert album_dataset["album1"].title in res_folder
    assert album_dataset["album2"].title not in res_folder

    # Données JSON valides
    # Le résultat contient une section JSON
    json_start = res.find("[")
    json_end = res.rfind("]") + 1
    albums_data = json.loads(res[json_start:json_end])
    assert any(a["id"] == album_dataset["album1"].id for a in albums_data)
    a1 = next(a for a in albums_data if a["id"] == album_dataset["album1"].id)
    assert a1["total_pages"] == 3
    assert a1["folder"] == album_dataset["folder"].name
    assert a1["plates_count"] == 3
    assert a1["status_counts"].get("ready") == 1
    assert a1["status_counts"].get("stale") == 1


def test_get_album_plates_by_id(album_dataset):
    """Vérifie la consultation des planches d'un album par identifiant."""
    res = MCPToolRegistry.get_album_plates(album_id=album_dataset["album1"].id, limit=2)
    assert f"Album #{album_dataset['album1'].id}" in res
    assert "planche_1_" in res
    assert "Le Crâne Humain" in res

    # JSON vérifié
    json_start = res.find("[")
    json_end = res.rfind("]") + 1
    plates_data = json.loads(res[json_start:json_end])
    assert len(plates_data) == 2
    assert plates_data[0]["page_number"] == 1
    assert plates_data[0]["rotation"] == 0
    assert plates_data[0]["crop_box"] == [10, 20, 200, 300]
    assert plates_data[0]["has_ocr"] is True


def test_get_album_plates_by_title_and_options(album_dataset):
    """Vérifie la recherche par titre et l'exclusion optionnelle du texte OCR."""
    res = MCPToolRegistry.get_album_plates(
        album_title=album_dataset["album1"].title,
        include_ocr_text=False,
    )
    assert "planche_1_" in res

    json_start = res.find("[")
    json_end = res.rfind("]") + 1
    plates_data = json.loads(res[json_start:json_end])
    assert len(plates_data) == 3
    assert "ocr_text" not in plates_data[0]
    assert plates_data[0]["has_ocr"] is True


def test_get_album_plates_not_found():
    """Vérifie la gestion d'erreur lorsqu'un album n'existe pas."""
    res = MCPToolRegistry.get_album_plates(album_id=999999)
    assert "Erreur" in res
    assert "999999" in res


# =====================================================================
# TESTS OUTILS DAG PIPELINES
# =====================================================================


def test_list_pipelines(dag_dataset):
    """Vérifie le listage des pipelines DAG et leurs étapes."""
    res = MCPToolRegistry.list_pipelines(limit=10)
    assert dag_dataset["pipeline"].name in res
    assert "LLM_PROMPT" in res
    assert "PYTHON_TOOL" in res

    json_start = res.find("[")
    json_end = res.rfind("]") + 1
    pipes_data = json.loads(res[json_start:json_end])
    target = next(p for p in pipes_data if p["id"] == dag_dataset["pipeline"].id)
    assert target["name"] == dag_dataset["pipeline"].name
    assert target["steps_count"] == 2
    assert target["steps"][0]["step_type"] == "LLM_PROMPT"
    assert target["steps"][0]["persona_name"] == dag_dataset["persona"].name
    assert target["latest_run"] is not None
    assert target["latest_run"]["status"] == "completed"


def test_get_pipeline_run(dag_dataset):
    """Vérifie la consultation détaillée d'un run par run_id et par pipeline_id."""
    # Par run_id
    res_run = MCPToolRegistry.get_pipeline_run(run_id=dag_dataset["run"].id)
    assert f"Run DAG #{dag_dataset['run'].id}" in res_run
    assert "COMPLETED" in res_run

    json_start = res_run.find("{", res_run.find("Run DAG"))
    json_end = res_run.rfind("}") + 1
    run_info = json.loads(res_run[json_start:json_end])
    assert run_info["run_id"] == dag_dataset["run"].id
    assert run_info["pipeline_id"] == dag_dataset["pipeline"].id
    assert run_info["status"] == "completed"
    assert run_info["state_summary"]["total_tokens"] == 450
    assert run_info["state_summary"]["completed_steps"] == [1]

    # Par pipeline_id
    res_pipe = MCPToolRegistry.get_pipeline_run(pipeline_id=dag_dataset["pipeline"].id)
    assert f"Run DAG #{dag_dataset['run'].id}" in res_pipe


def test_get_pipeline_run_not_found():
    """Vérifie l'erreur si le run n'existe pas."""
    res = MCPToolRegistry.get_pipeline_run(run_id=999999)
    assert "Erreur" in res
    assert "999999" in res


# =====================================================================
# TESTS DISPATCH CONSULTANT ET SCHÉMAS
# =====================================================================


def test_mcp_tool_registry_albums_and_dag_dispatch(album_dataset, dag_dataset):
    """Vérifie que MCPToolRegistry dispatche directement les outils albums et DAG."""

    obs1 = MCPToolRegistry.list_albums(limit=5)
    assert album_dataset["album1"].title in obs1

    obs2 = MCPToolRegistry.get_album_plates(album_id=album_dataset["album1"].id)
    assert "planche_1_" in obs2

    obs3 = MCPToolRegistry.list_pipelines(limit=5)
    assert dag_dataset["pipeline"].name in obs3

    obs4 = MCPToolRegistry.get_pipeline_run(run_id=dag_dataset["run"].id)
    assert f"Run DAG #{dag_dataset['run'].id}" in obs4


def test_default_consultant_tools_schemas():
    """Vérifie que les 4 outils sont bien déclarés dans DEFAULT_CONSULTANT_TOOLS."""
    names = [t["function"]["name"] for t in DEFAULT_CONSULTANT_TOOLS]
    assert "list_albums" in names
    assert "get_album_plates" in names
    assert "list_pipelines" in names
    assert "get_pipeline_run" in names


def test_fastmcp_tools_exposed():
    """Vérifie que le serveur FastMCP expose les 4 outils."""

    async def _check():
        tools = await mcp.list_tools()
        return [t.name for t in tools]

    tool_names = asyncio.run(_check())
    assert "list_albums" in tool_names
    assert "get_album_plates" in tool_names
    assert "list_pipelines" in tool_names
    assert "get_pipeline_run" in tool_names
