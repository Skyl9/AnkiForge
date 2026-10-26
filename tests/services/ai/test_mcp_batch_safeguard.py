"""Tests unitaires et d'intégration pour le garde-fou volumétrique des lots MCP (ADR 0048).

Vérifie l'ordre d'évaluation :
1. PAYLOAD_TOO_LARGE (avant tout parsing)
2. INVALID_JSON (avec position d'erreur et aucun fragment de contenu)
3. TOO_MANY_NOTES (plafond dur de 100 cartes)
ainsi que l'absence d'état partiel (Two-Phase Commit) et l'absence de contenu de carte dans les logs.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from ankiforge.database.models import (
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    StagedBundleModel,
    StagedPatchModel,
)
from ankiforge.services.ai.mcp_batch_safeguard import (
    MAX_BATCH_CHARS,
    MAX_BATCH_NOTES,
    MCPBatchSafeguard,
)
from ankiforge.services.ai.mcp_daemon import MCPServerDaemon
from ankiforge.services.ai.mcp_server import mcp
from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry


def _extract_text(tool_result: Any) -> str:
    """Helper unifié d'extraction textuelle depuis le CallToolResult FastMCP."""
    if hasattr(tool_result, "content") and tool_result.content:
        return str(tool_result.content[0].text)
    return str(tool_result)


@pytest.fixture
def batch_safeguard_setup(mock_db: Any) -> dict[str, Any]:
    """Prépare un jeu de données minimal pour tester les outils de lot."""
    deck = DeckModel.create(name="Sciences::Physique")
    schema_fields = json.dumps(["Recto", "Verso"])
    note_type = NoteTypeModel.create(name="Standard Test Model", fields_schema=schema_fields)

    notes = []
    for i in range(1, 15):
        n = NoteModel.create(deck=deck, note_type=note_type, tags=f"tag_{i}")
        NoteVersionModel.create(
            note=n,
            version_number=1,
            is_active=True,
            content=json.dumps({"Recto": f"Question {i}", "Verso": f"Reponse {i}"}),
        )
        notes.append(n)

    return {"deck": deck, "note_type": note_type, "notes": notes}


# =====================================================================
# 1. Tests unitaires du garde-fou partagé MCPBatchSafeguard
# =====================================================================


def test_batch_safeguard_payload_too_large_evaluated_before_parsing() -> None:
    """Vérifie que PAYLOAD_TOO_LARGE est évalué avant tout parsing JSON, même sur un payload invalide."""
    large_payload = "A" * (MAX_BATCH_CHARS + 50)
    parsed, err_json = MCPBatchSafeguard.validate_batch_payload("test_tool", large_payload)

    assert parsed is None
    assert err_json is not None
    err = json.loads(err_json)
    assert err["status"] == "error"
    assert err["error_code"] == "PAYLOAD_TOO_LARGE"
    assert err["tool"] == "test_tool"
    assert err["received_chars"] == MAX_BATCH_CHARS + 50
    assert err["max_chars"] == MAX_BATCH_CHARS
    assert err["received_notes"] is None
    assert err["max_notes"] == MAX_BATCH_NOTES
    assert err["no_state_written"] is True
    assert "suggestion" in err


def test_batch_safeguard_invalid_json_reports_error_position() -> None:
    """Vérifie qu'un JSON mal formé sous la borne de caractères renvoie INVALID_JSON avec sa position."""
    truncated_json = '[{"fields": {"Recto": "Question incomplète"'
    parsed, err_json = MCPBatchSafeguard.validate_batch_payload("test_tool", truncated_json)

    assert parsed is None
    assert err_json is not None
    err = json.loads(err_json)
    assert err["status"] == "error"
    assert err["error_code"] == "INVALID_JSON"
    assert err["tool"] == "test_tool"
    assert err["received_chars"] == len(truncated_json)
    assert err["error_position"] is not None
    assert err["error_position"] > 0
    assert err["received_notes"] is None
    assert err["no_state_written"] is True


def test_batch_safeguard_too_many_notes_reports_counts() -> None:
    """Vérifie qu'une liste valide de plus de 100 notes est rejetée avec TOO_MANY_NOTES."""
    many_notes = [{"fields": {"Recto": f"Q{i}"}} for i in range(101)]
    valid_json = json.dumps(many_notes)
    parsed, err_json = MCPBatchSafeguard.validate_batch_payload("test_tool", valid_json)

    assert parsed is None
    assert err_json is not None
    err = json.loads(err_json)
    assert err["status"] == "error"
    assert err["error_code"] == "TOO_MANY_NOTES"
    assert err["tool"] == "test_tool"
    assert err["received_notes"] == 101
    assert err["max_notes"] == MAX_BATCH_NOTES
    assert err["received_chars"] == len(valid_json)
    assert err["no_state_written"] is True


def test_batch_safeguard_nominal_accepts_valid_payload() -> None:
    """Vérifie qu'un lot respectant les deux seuils est accepté sans erreur."""
    good_notes = [{"fields": {"Recto": f"Q{i}"}} for i in range(5)]
    valid_json = json.dumps(good_notes)
    parsed, err_json = MCPBatchSafeguard.validate_batch_payload("test_tool", valid_json)

    assert err_json is None
    assert parsed is not None
    assert len(parsed) == 5


# =====================================================================
# 2. Tests d'intégration sur create_notes_batch (Les 3 refus + nominal)
# =====================================================================


def test_create_notes_batch_payload_too_large(batch_safeguard_setup: dict[str, Any]) -> None:
    """Test 1: create_notes_batch avec payload > 32 000 car → PAYLOAD_TOO_LARGE, aucun patch créé."""
    initial_patches_count = StagedPatchModel.select().count()
    payload_huge = "[" + '{"fields": {"Recto": "Trop long"}},' * 1500 + '{"fields": {"Recto": "Fin"}}]'
    assert len(payload_huge) > MAX_BATCH_CHARS

    async def _run() -> None:
        res_raw = await mcp.call_tool(
            "create_notes_batch",
            {
                "notes_json": payload_huge,
                "default_deck": "Sciences::Physique",
                "default_note_type": "Standard Test Model",
            },
        )
        data = json.loads(_extract_text(res_raw))
        assert data["status"] == "error"
        assert data["error_code"] == "PAYLOAD_TOO_LARGE"
        assert data["tool"] == "create_notes_batch"
        assert data["received_chars"] == len(payload_huge)
        assert data["max_chars"] == MAX_BATCH_CHARS
        assert data["received_notes"] is None
        assert data["no_state_written"] is True

    asyncio.run(_run())
    assert StagedPatchModel.select().count() == initial_patches_count


def test_create_notes_batch_invalid_json(batch_safeguard_setup: dict[str, Any]) -> None:
    """Test 2: create_notes_batch avec JSON tronqué → INVALID_JSON, aucun patch créé."""
    initial_patches_count = StagedPatchModel.select().count()
    truncated_json = '[{"deck": "Sciences::Physique", "fields": {"Recto": "Question cou'

    async def _run() -> None:
        res_raw = await mcp.call_tool(
            "create_notes_batch",
            {
                "notes_json": truncated_json,
                "default_deck": "Sciences::Physique",
                "default_note_type": "Standard Test Model",
            },
        )
        data = json.loads(_extract_text(res_raw))
        assert data["status"] == "error"
        assert data["error_code"] == "INVALID_JSON"
        assert data["tool"] == "create_notes_batch"
        assert data["received_chars"] == len(truncated_json)
        assert data["error_position"] is not None
        assert data["error_position"] > 0
        assert data["received_notes"] is None
        assert data["no_state_written"] is True

    asyncio.run(_run())
    assert StagedPatchModel.select().count() == initial_patches_count


def test_create_notes_batch_too_many_notes(batch_safeguard_setup: dict[str, Any]) -> None:
    """Test 3: create_notes_batch avec 101 notes → TOO_MANY_NOTES, aucun patch créé."""
    initial_patches_count = StagedPatchModel.select().count()
    many_notes = [{"fields": {"Recto": f"Q{i}", "Verso": f"R{i}"}} for i in range(101)]

    async def _run() -> None:
        res_raw = await mcp.call_tool(
            "create_notes_batch",
            {
                "notes_json": json.dumps(many_notes),
                "default_deck": "Sciences::Physique",
                "default_note_type": "Standard Test Model",
            },
        )
        data = json.loads(_extract_text(res_raw))
        assert data["status"] == "error"
        assert data["error_code"] == "TOO_MANY_NOTES"
        assert data["tool"] == "create_notes_batch"
        assert data["received_notes"] == 101
        assert data["max_notes"] == MAX_BATCH_NOTES
        assert data["no_state_written"] is True

    asyncio.run(_run())
    assert StagedPatchModel.select().count() == initial_patches_count


# =====================================================================
# 3. Tests d'intégration sur propose_cards_batch_refactor (Les 3 refus)
# =====================================================================


def test_propose_cards_batch_refactor_payload_too_large(batch_safeguard_setup: dict[str, Any]) -> None:
    """Test 4a: propose_cards_batch_refactor avec payload > 32 000 car → PAYLOAD_TOO_LARGE."""
    initial_bundles_count = StagedBundleModel.select().count()
    payload_huge = "[" + '{"note_id": 1, "fields": {"Recto": "Trop long"}},' * 1500 + '{"note_id": 1}]'

    async def _run() -> None:
        res_raw = await mcp.call_tool(
            "propose_cards_batch_refactor",
            {
                "refactors_json": payload_huge,
            },
        )
        data = json.loads(_extract_text(res_raw))
        assert data["status"] == "error"
        assert data["error_code"] == "PAYLOAD_TOO_LARGE"
        assert data["tool"] == "propose_cards_batch_refactor"
        assert data["received_chars"] == len(payload_huge)
        assert data["max_chars"] == MAX_BATCH_CHARS
        assert data["received_notes"] is None
        assert data["no_state_written"] is True

    asyncio.run(_run())
    assert StagedBundleModel.select().count() == initial_bundles_count


def test_propose_cards_batch_refactor_invalid_json(batch_safeguard_setup: dict[str, Any]) -> None:
    """Test 4b: propose_cards_batch_refactor avec JSON tronqué → INVALID_JSON."""
    initial_bundles_count = StagedBundleModel.select().count()
    truncated_json = '[{"note_id": 1, "fields": {"Recto": "Valeur tronq'

    async def _run() -> None:
        res_raw = await mcp.call_tool(
            "propose_cards_batch_refactor",
            {
                "refactors_json": truncated_json,
            },
        )
        data = json.loads(_extract_text(res_raw))
        assert data["status"] == "error"
        assert data["error_code"] == "INVALID_JSON"
        assert data["tool"] == "propose_cards_batch_refactor"
        assert data["received_chars"] == len(truncated_json)
        assert data["error_position"] is not None
        assert data["error_position"] > 0
        assert data["received_notes"] is None
        assert data["no_state_written"] is True

    asyncio.run(_run())
    assert StagedBundleModel.select().count() == initial_bundles_count


def test_propose_cards_batch_refactor_too_many_notes(batch_safeguard_setup: dict[str, Any]) -> None:
    """Test 4c: propose_cards_batch_refactor avec 101 cartes → TOO_MANY_NOTES."""
    initial_bundles_count = StagedBundleModel.select().count()
    fake_refactors = [{"note_id": i, "fields": {"Recto": f"Q{i}"}} for i in range(101)]

    async def _run() -> None:
        res_raw = await mcp.call_tool(
            "propose_cards_batch_refactor",
            {
                "refactors_json": json.dumps(fake_refactors),
            },
        )
        data = json.loads(_extract_text(res_raw))
        assert data["status"] == "error"
        assert data["error_code"] == "TOO_MANY_NOTES"
        assert data["tool"] == "propose_cards_batch_refactor"
        assert data["received_notes"] == 101
        assert data["max_notes"] == MAX_BATCH_NOTES
        assert data["no_state_written"] is True

    asyncio.run(_run())
    assert StagedBundleModel.select().count() == initial_bundles_count


# =====================================================================
# 4. Non-régression, Journalisation des métadonnées pures & multi sous-lots
# =====================================================================


def test_nominal_batch_logs_only_metadata_without_payload_content(
    batch_safeguard_setup: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test 5: Staging nominal et vérification stricte qu'aucun contenu de carte n'apparaît dans les logs de l'outil."""
    caplog.set_level(logging.DEBUG)
    sentinel_word = "SUPER_SECRET_SENTINEL_PHYSICS_XYZ"

    good_notes = [
        {"fields": {"Recto": f"Question {sentinel_word}", "Verso": "Reponse claire"}},
    ]

    async def _run() -> None:
        res_raw = await mcp.call_tool(
            "create_notes_batch",
            {
                "notes_json": json.dumps(good_notes),
                "default_deck": "Sciences::Physique",
                "default_note_type": "Standard Test Model",
            },
        )
        data = json.loads(_extract_text(res_raw))
        assert data["status"] == "staged"

    asyncio.run(_run())

    # Vérification stricte : aucun contenu métier n'apparaît dans les journaux applicatifs MCP / IA
    ai_records = [r for r in caplog.records if r.name.startswith("ankiforge.services.ai")]
    for rec in ai_records:
        assert sentinel_word not in rec.getMessage()

    # Mais le log de métadonnées du garde-fou est bien émis
    ai_messages = [r.getMessage() for r in ai_records]
    assert any("Garde-fou lot MCP [create_notes_batch]" in msg for msg in ai_messages)


def test_two_sub_batches_in_single_bundle_creates_twelve_steps(
    batch_safeguard_setup: dict[str, Any],
) -> None:
    """Test 6: Deux sous-lots de 6 notes sur un même bundle ouvert produisent 12 étapes dans ce bundle."""
    notes = batch_safeguard_setup["notes"]
    assert len(notes) >= 12

    # Ouverture explicite d'un bundle
    bundle_id = StagedPatchRegistry.begin_bundle(
        title="Campagne fragmentation ADR 0048",
        explanation="Refactorisation en 2 sous-lots de 6 cartes",
    )

    sub_batch_1 = [{"note_id": n.id, "fields": {"Recto": f"Q Mod 1-{n.id}"}} for n in notes[:6]]
    sub_batch_2 = [{"note_id": n.id, "fields": {"Recto": f"Q Mod 2-{n.id}"}} for n in notes[6:12]]

    async def _run() -> None:
        res1_raw = await mcp.call_tool(
            "propose_cards_batch_refactor",
            {"refactors_json": json.dumps(sub_batch_1)},
        )
        d1 = json.loads(_extract_text(res1_raw))
        assert d1["status"] == "staged"
        assert d1["bundle_id"] == bundle_id
        assert d1["total_staged"] == 6

        res2_raw = await mcp.call_tool(
            "propose_cards_batch_refactor",
            {"refactors_json": json.dumps(sub_batch_2)},
        )
        d2 = json.loads(_extract_text(res2_raw))
        assert d2["status"] == "staged"
        assert d2["bundle_id"] == bundle_id
        assert d2["total_staged"] == 6

    asyncio.run(_run())

    # Vérification que le bundle contient bien les 12 étapes cumulées
    bundle = StagedBundleModel.get(StagedBundleModel.bundle_id == bundle_id)
    assert bundle is not None
    assert bundle.total_steps == 12

    patches = StagedPatchModel.select().where(StagedPatchModel.bundle == bundle)
    assert patches.count() == 12

    # Nettoyage
    StagedPatchRegistry.abort_bundle(bundle_id)


def test_streamable_http_batch_safeguard_recette(
    batch_safeguard_setup: dict[str, Any],
    tmp_path: Path,
) -> None:
    """Recette réelle Streamable HTTP (ADR 0048 §3.E).

    Vérifie via le transport réseau Streamable HTTP réel (/mcp) :
    - Scénario 1 : Refus propre d'un lot tronqué (INVALID_JSON) sans aucun patch créé.
    - Scénario 2 : Deux sous-lots de 6 notes sur un même bundle ouvert -> 12 étapes créées.
    - Scénario 3 : Non-régression sur un lot nominal sans bundle -> auto-scellé.
    """
    notes = batch_safeguard_setup["notes"]
    daemon = MCPServerDaemon(mcp_server=mcp, base_port=9700, data_dir=tmp_path)
    assert daemon.start(timeout=5.0) is True
    assert daemon.is_running is True
    assert daemon.port is not None
    assert daemon.url is not None

    async def _test_flow() -> None:
        auth_headers = {"Authorization": f"Bearer {daemon.token}"}
        async with (
            httpx.AsyncClient(headers=auth_headers) as http_client,
            streamable_http_client(daemon.url, http_client=http_client) as (read_stream, write_stream),  # type: ignore[arg-type]
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()

            # Scénario 1 : Lot tronqué de ~40 notes (argument incomplet interrompu en plein vol)
            initial_patches = StagedPatchModel.select().count()
            truncated_payload = '[{"note_id": 1, "fields": {"Recto": "Question dense ...'
            res_trunc = await session.call_tool(
                "propose_cards_batch_refactor",
                arguments={"refactors_json": truncated_payload},
            )
            data_trunc = json.loads(_extract_text(res_trunc))
            assert data_trunc["status"] == "error"
            assert data_trunc["error_code"] == "INVALID_JSON"
            assert data_trunc["no_state_written"] is True
            assert StagedPatchModel.select().count() == initial_patches

            # Scénario 2 : Deux sous-lots de 6 notes sur un même bundle ouvert
            bundle_id = StagedPatchRegistry.begin_bundle(
                title="Recette Streamable HTTP",
                explanation="2 sous-lots fragmentés",
            )
            sub1 = [{"note_id": n.id, "fields": {"Recto": f"HTTP Mod 1-{n.id}"}} for n in notes[:6]]
            sub2 = [{"note_id": n.id, "fields": {"Recto": f"HTTP Mod 2-{n.id}"}} for n in notes[6:12]]

            res_sub1 = await session.call_tool(
                "propose_cards_batch_refactor",
                arguments={"refactors_json": json.dumps(sub1)},
            )
            d_sub1 = json.loads(_extract_text(res_sub1))
            assert d_sub1["status"] == "staged"
            assert d_sub1["bundle_id"] == bundle_id
            assert d_sub1["total_staged"] == 6

            res_sub2 = await session.call_tool(
                "propose_cards_batch_refactor",
                arguments={"refactors_json": json.dumps(sub2)},
            )
            d_sub2 = json.loads(_extract_text(res_sub2))
            assert d_sub2["status"] == "staged"
            assert d_sub2["bundle_id"] == bundle_id
            assert d_sub2["total_staged"] == 6

            bundle = StagedBundleModel.get(StagedBundleModel.bundle_id == bundle_id)
            assert bundle.total_steps == 12
            StagedPatchRegistry.abort_bundle(bundle_id)

            # Scénario 3 : Non-régression sans bundle préalable -> auto-scellé
            nominal_lot = [{"note_id": notes[0].id, "fields": {"Recto": "HTTP Unitaire"}}]
            res_nom = await session.call_tool(
                "propose_cards_batch_refactor",
                arguments={"refactors_json": json.dumps(nominal_lot)},
            )
            d_nom = json.loads(_extract_text(res_nom))
            assert d_nom["status"] == "staged"
            auto_bundle_id = d_nom["bundle_id"]
            auto_bundle = StagedBundleModel.get(StagedBundleModel.bundle_id == auto_bundle_id)
            assert auto_bundle.status == "pending"  # Scellé automatiquement car auto-bundle

    try:
        asyncio.run(_test_flow())
    finally:
        daemon.stop(timeout=5.0)
