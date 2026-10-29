"""Tests unitaires et d'intégration pour les outils MCP d'accès aux albums et de gestion des pipelines DAG."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

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


def _extract_text(res: Any) -> str:
    """Helper canonique d'extraction de texte FastMCP conformément aux règles d'ingénierie."""
    return str(res.content[0].text) if hasattr(res, "content") and res.content else str(res)


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
# TESTS OUTILS OCR ALBUM (AGENT EXTERNE)
# =====================================================================


def test_get_album_ocr_context_reject_without_vision(album_dataset):
    """Vérifie le garde-fou Vision : confirm_vision faux rejette l'appel."""
    res = MCPToolRegistry.get_album_ocr_context(
        document_id=album_dataset["album1"].id,
        confirm_vision=False,
    )
    data = json.loads(res)
    assert data["status"] == "error"
    assert "Vision" in data["message"]
    assert "confirm_vision" in data["message"]


def test_get_album_ocr_context_not_album_rejected(album_dataset):
    """Vérifie qu'un document non album est rejeté."""
    res = MCPToolRegistry.get_album_ocr_context(
        document_id=album_dataset["doc_pdf"].id,
        confirm_vision=True,
    )
    data = json.loads(res)
    assert data["status"] == "error"
    assert "album" in data["message"].lower()


def test_get_album_ocr_context_success(album_dataset):
    """Vérifie l'exposition du contexte OCR par planche avec confirm_vision vrai."""
    album = album_dataset["album1"]
    res = MCPToolRegistry.get_album_ocr_context(
        document_id=album.id,
        confirm_vision=True,
    )
    data = json.loads(res)
    assert data["status"] == "success"
    assert data["document_id"] == album.id
    assert data["title"] == album.title
    assert data["total_plates"] == 3

    plates = data["plates"]
    assert len(plates) == 3
    # Tri par numéro de page
    assert [p["page_number"] for p in plates] == [1, 2, 3]

    p1 = plates[0]
    assert p1["page_id"] == album_dataset["pages"][0].id
    assert p1["rotation"] == 0
    assert p1["status"] == "ready"
    assert p1["has_ocr"] is True
    assert p1["besoin_transcription"] is False
    assert p1["ocr_text"] == "Titre : Le Crâne Humain. Os frontal et pariétal."

    p2 = plates[1]
    assert p2["page_id"] == album_dataset["pages"][1].id
    assert p2["rotation"] == 90
    assert p2["status"] == "stale"
    assert p2["has_ocr"] is False
    assert p2["besoin_transcription"] is True
    assert p2["ocr_text"] == ""

    # Média lié présent
    assert p1["media_filename"] is not None
    assert str(p1["media_filename"]).endswith(".png")


def test_get_album_ocr_context_page_ids_filter(album_dataset):
    """Vérifie le filtrage ciblé par page_ids."""
    p1 = album_dataset["pages"][0]
    p3 = album_dataset["pages"][2]
    res = MCPToolRegistry.get_album_ocr_context(
        document_id=album_dataset["album1"].id,
        page_ids=[p1.id, p3.id],
        confirm_vision=True,
    )
    data = json.loads(res)
    assert data["status"] == "success"
    assert data["total_plates"] == 2
    assert [p["page_number"] for p in data["plates"]] == [1, 3]


def test_set_album_page_ocr_success(album_dataset):
    """Vérifie l'enregistrement du texte transcrit et la mutation tracée."""
    page = album_dataset["pages"][1]  # ocr_text vide initialement
    corrected = "Transcription VLM de la planche 2 : os maxillaire."

    res = MCPToolRegistry.set_album_page_ocr(
        page_id=page.id,
        corrected_text=corrected,
        agent_external=True,
    )
    data = json.loads(res)
    assert data["status"] == "success"
    assert data["page_id"] == page.id
    assert data["page_number"] == page.page_number
    assert data["document_id"] == page.document_id
    assert data["ocr_text_length"] == len(corrected)
    assert data["agent_external"] is True

    # Vérification en base (rechargement via get_by_id, jamais refresh_from_db)
    reloaded = DocumentPageModel.get_by_id(page.id)
    assert reloaded.ocr_text == corrected


def test_set_album_page_ocr_unknown_page():
    """Vérifie le rejet d'une planche inexistante."""
    res = MCPToolRegistry.set_album_page_ocr(page_id=999999, corrected_text="Texte")
    data = json.loads(res)
    assert data["status"] == "error"
    assert "introuvable" in data["message"].lower()


def test_set_album_page_ocr_agent_external_flag_false(album_dataset):
    """Vérifie le drapeau agent_external par défaut à False."""
    page = album_dataset["pages"][0]
    res = MCPToolRegistry.set_album_page_ocr(page_id=page.id, corrected_text="Texte par défaut")
    data = json.loads(res)
    assert data["status"] == "success"
    assert data["agent_external"] is False


# =====================================================================
# TESTS INVOCATION DIRECTE FASTMCP (OUTILS OCR ALBUM)
# =====================================================================


def test_fastmcp_album_ocr_tools_registered_and_invocable(album_dataset):
    """Vérifie que les 2 nouveaux outils OCR album sont déclarés et invocables via FastMCP."""
    album = album_dataset["album1"]
    page = album_dataset["pages"][1]

    async def _run() -> None:
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}
        assert "get_album_ocr_context" in tool_names
        assert "set_album_page_ocr" in tool_names

        # Rejet sans confirm_vision
        rej_res = await mcp.call_tool(
            "get_album_ocr_context",
            arguments={"document_id": album.id, "confirm_vision": False},
        )
        rej_data = json.loads(_extract_text(rej_res))
        assert rej_data["status"] == "error"

        # Succès avec confirm_vision
        ctx_res = await mcp.call_tool(
            "get_album_ocr_context",
            arguments={"document_id": album.id, "confirm_vision": True},
        )
        ctx_data = json.loads(_extract_text(ctx_res))
        assert ctx_data["status"] == "success"
        assert ctx_data["total_plates"] == 3

        # Écriture OCR par agent externe
        set_res = await mcp.call_tool(
            "set_album_page_ocr",
            arguments={
                "page_id": page.id,
                "corrected_text": "Texte via FastMCP agent externe",
                "agent_external": True,
            },
        )
        set_data = json.loads(_extract_text(set_res))
        assert set_data["status"] == "success"
        assert set_data["agent_external"] is True

    asyncio.run(_run())


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
    """Vérifie que les 6 outils albums/DAG/OCR sont bien déclarés dans DEFAULT_CONSULTANT_TOOLS."""
    names = [t["function"]["name"] for t in DEFAULT_CONSULTANT_TOOLS]
    assert "list_albums" in names
    assert "get_album_plates" in names
    assert "get_album_ocr_context" in names
    assert "set_album_page_ocr" in names
    assert "list_pipelines" in names
    assert "get_pipeline_run" in names


def test_fastmcp_tools_exposed():
    """Vérifie que le serveur FastMCP expose les 6 outils albums/DAG/OCR."""

    async def _check():
        tools = await mcp.list_tools()
        return [t.name for t in tools]

    tool_names = asyncio.run(_check())
    assert "list_albums" in tool_names
    assert "get_album_plates" in tool_names
    assert "get_album_ocr_context" in tool_names
    assert "set_album_page_ocr" in tool_names
    assert "list_pipelines" in tool_names
    assert "get_pipeline_run" in tool_names
