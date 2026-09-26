"""Tests d'intégration réseau et BDD pour le daemon MCP (MCPServerDaemon)."""

from __future__ import annotations

import asyncio
import json
import socket

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.server.mcpserver import MCPServer

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.services.ai.mcp_daemon import MCPServerDaemon, find_available_port, is_port_in_use
from ankiforge.services.ai.mcp_server import mcp

pytestmark = pytest.mark.integration


def test_find_available_port_skips_occupied_port():
    """Vérifie que find_available_port contourne automatiquement un port déjà occupé."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        occupied_port = s.getsockname()[1]
        s.listen(1)

        assert is_port_in_use(occupied_port, host="127.0.0.1") is True

        next_port = find_available_port(start_port=occupied_port, host="127.0.0.1")
        assert next_port != occupied_port
        assert next_port > occupied_port
        assert is_port_in_use(next_port, host="127.0.0.1") is False


def test_mcp_server_daemon_lifecycle(tmp_path):
    """Vérifie le cycle de vie complet du daemon (démarrage, statut, requêtes HTTP, arrêt, nettoyage)."""
    dummy_mcp = MCPServer("DummyServer")

    @dummy_mcp.tool()
    def ping() -> str:
        return "pong"

    daemon = MCPServerDaemon(
        mcp_server=dummy_mcp,
        host="127.0.0.1",
        base_port=9200,
        data_dir=tmp_path,
    )

    assert daemon.is_running is False
    assert daemon.port is None
    assert daemon.token is None

    started = daemon.start(timeout=5.0)
    assert started is True
    assert daemon.is_running is True
    assert daemon.port is not None and daemon.port >= 9200
    assert daemon.token is not None
    assert daemon.token_file.exists()
    assert daemon.state_file.exists()

    # 1. Requête sans authentification -> 401
    resp_unauth = httpx.get(f"http://127.0.0.1:{daemon.port}/sse", timeout=3.0)
    assert resp_unauth.status_code == 401

    # 2. Requête avec token Bearer -> 200
    headers = {"Authorization": f"Bearer {daemon.token}"}
    with httpx.stream("GET", f"http://127.0.0.1:{daemon.port}/sse", headers=headers, timeout=3.0) as resp_auth:
        assert resp_auth.status_code == 200

    # 3. Arrêt propre et fermeture des sessions
    daemon.stop(timeout=5.0)
    assert daemon.is_running is False
    assert not daemon.token_file.exists()
    assert daemon.state_file.exists()
    state = json.loads(daemon.state_file.read_text(encoding="utf-8"))
    assert state["status"] == "stopped"


def test_mcp_server_daemon_port_collision_fallback(tmp_path):
    """Vérifie que le daemon bascule automatiquement vers un port supérieur en cas de collision."""
    dummy_mcp = MCPServer("CollisionTestServer")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 9300))
        s.listen(1)

        daemon = MCPServerDaemon(
            mcp_server=dummy_mcp,
            host="127.0.0.1",
            base_port=9300,
            data_dir=tmp_path,
        )

        try:
            started = daemon.start(timeout=5.0)
            assert started is True
            assert daemon.is_running is True
            assert daemon.port == 9301
        finally:
            daemon.stop(timeout=5.0)


def test_mcp_server_daemon_uvicorn_bind_collision_retries_without_deadlock(tmp_path, monkeypatch):
    """Vérifie que le daemon ne deadlock pas sur self._lock si Uvicorn échoue au bind et bascule au port suivant."""
    dummy_mcp = MCPServer("CollisionRecoveryServer")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 9350))
        s.listen(1)

        calls = 0
        real_find_available_port = find_available_port

        def _mock_find_available_port(start_port: int = 8765, max_attempts: int = 100, host: str = "127.0.0.1") -> int:
            nonlocal calls
            calls += 1
            if calls == 1:
                return 9350
            return real_find_available_port(start_port=start_port, max_attempts=max_attempts, host=host)

        monkeypatch.setattr("ankiforge.services.ai.mcp_daemon.find_available_port", _mock_find_available_port)

        daemon = MCPServerDaemon(
            mcp_server=dummy_mcp,
            host="127.0.0.1",
            base_port=9350,
            data_dir=tmp_path,
        )

        try:
            started = daemon.start(timeout=5.0)
            assert started is True
            assert daemon.is_running is True
            assert daemon.port == 9351
        finally:
            daemon.stop(timeout=5.0)


def test_mcp_server_daemon_real_tools_over_sse(tmp_path):
    """Vérifie l'exécution des outils MCP réels (audit_deck_wozniak, find_duplicate_cards, apply_patch) via SSE."""
    deck = DeckModel.create(name="Deck MCP Test")
    note_type = NoteTypeModel.create(name="Modèle MCP Test")
    note = NoteModel.create(note_type=note_type)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Front": "Question Originale", "Back": "Réponse Originale"}),
        is_active=True,
    )
    CardModel.create(deck=deck, note=note, card_type_id=1, queue=0, due=0, ord=0)

    daemon = MCPServerDaemon(mcp_server=mcp, base_port=9500, data_dir=tmp_path)
    started = daemon.start(timeout=5.0)
    assert started is True
    assert daemon.is_running is True
    assert daemon.port is not None

    async def _test_session():
        auth_headers = {"Authorization": f"Bearer {daemon.token}"}

        async with (
            sse_client(daemon.sse_url, headers=auth_headers) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()

            # 1. Vérification de l'exposition des outils
            tools_result = await session.list_tools()
            tool_names = [t.name for t in tools_result.tools]
            assert "audit_deck_wozniak" in tool_names
            assert "find_duplicate_cards" in tool_names
            assert "apply_patch" in tool_names

            # 2. Appel outil audit_deck_wozniak
            audit_res = await session.call_tool("audit_deck_wozniak", arguments={"deck_name": "Deck MCP Test"})
            assert audit_res is not None
            assert not audit_res.is_error
            assert any("Deck MCP Test" in str(c) or "cartes" in str(c) for c in audit_res.content)

            # 3. Appel outil find_duplicate_cards
            dup_res = await session.call_tool("find_duplicate_cards", arguments={"deck_name": "Deck MCP Test", "threshold": 0.8})
            assert dup_res is not None
            assert not dup_res.is_error

            # 4. Appel outil apply_patch
            patch_payload = {
                "patch_type": "card",
                "target_id": note.id,
                "patch_data_json": json.dumps({"Front": "Question Patchée via MCP", "Back": "Réponse Patchée"}),
                "explanation": "Correction via agent externe",
            }
            patch_res = await session.call_tool("apply_patch", arguments=patch_payload)
            assert patch_res is not None
            assert not patch_res.is_error
            assert any("Succès" in str(c) or "appliqué" in str(c) for c in patch_res.content)

    try:
        asyncio.run(_test_session())
    finally:
        daemon.stop(timeout=5.0)

    # Vérification que la modification en base de données a été persistée par l'outil MCP
    active_version = NoteVersionModel.get(NoteVersionModel.note == note, NoteVersionModel.is_active == True)  # noqa: E712
    fields = json.loads(active_version.content)
    assert fields["Front"] == "Question Patchée via MCP"
