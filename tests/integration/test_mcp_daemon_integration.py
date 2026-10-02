"""Tests d'intégration réseau et BDD pour le daemon MCP (MCPServerDaemon)."""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import threading
import time
from contextlib import contextmanager

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.mcpserver import MCPServer

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.services.ai.mcp_daemon import MCPServerDaemon, find_available_port, is_port_in_use
from ankiforge.services.ai.mcp_server import mcp

pytestmark = pytest.mark.integration


def test_find_available_port_never_probes_past_the_valid_range(monkeypatch):
    """
    La sonde ne doit jamais dépasser 65535, quoi que soit le port de départ.

    Le port de départ venait d'un port éphémère attribué par l'OS : selon le port attribué,
    la sonde levait `OverflowError` ou passait. On vérifie donc les ports réellement
    interrogés, en déclarant toute la plage occupée — sinon le test dépendrait de quels
    ports happen à être libres, ce qui le rendrait aussi aléatoire que le bug.
    """
    import ankiforge.services.ai.mcp_daemon as mcp_daemon

    probed: list[int] = []

    def always_occupied(port: int, host: str = "127.0.0.1") -> bool:
        probed.append(port)
        return True

    monkeypatch.setattr(mcp_daemon, "is_port_in_use", always_occupied)

    with pytest.raises(RuntimeError, match="Impossible de trouver un port libre"):
        mcp_daemon.find_available_port(start_port=65530, max_attempts=100, host="127.0.0.1")

    assert probed, "aucun port sondé : le test ne prouve rien"
    assert max(probed) <= 65535, f"un port hors de la plage valide a été sondé : {max(probed)}"
    assert probed == list(range(65530, 65536))


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

    # 3. Arrêt propre et fermeture des sessions (le jeton doit être conservé sur le disque)
    saved_token = daemon.token
    daemon.stop(timeout=5.0)
    assert daemon.is_running is False
    assert daemon.token_file.exists()
    assert daemon.token_file.read_text(encoding="utf-8") == saved_token
    assert daemon.state_file.exists()
    state = json.loads(daemon.state_file.read_text(encoding="utf-8"))
    assert state["status"] == "stopped"

    # 4. Redémarrage du daemon : le jeton Bearer reste identique et stable
    assert daemon.start(timeout=5.0) is True
    assert daemon.token == saved_token
    daemon.stop(timeout=5.0)


@contextmanager
def capture_uvicorn_logs():
    """
    Collecte les enregistrements du logger `uvicorn` pendant le bloc.

    Le logger `uvicorn` est configuré avec `propagate = False` (LOGGING_CONFIG d'Uvicorn) :
    ses enregistrements n'atteignent jamais le logger racine, donc ni `caplog` ni `ankiforge.log`
    ne les voient. Sans ce collecteur, la régression serait invisible.

    À n'englober qu'APRÈS `daemon.start()` : `uvicorn.Config.load()` appelle `fileConfig()`,
    qui réinstalle la liste de handlers du logger et effacerait un collecteur posé avant.
    """
    records: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    uvicorn_logger = logging.getLogger("uvicorn")
    collector = _Collector(level=logging.DEBUG)
    previous_level = uvicorn_logger.level
    uvicorn_logger.setLevel(logging.DEBUG)
    uvicorn_logger.addHandler(collector)
    try:
        yield records
    finally:
        uvicorn_logger.removeHandler(collector)
        uvicorn_logger.setLevel(previous_level)


def test_mcp_server_daemon_stop_does_not_log_cancelled_error(tmp_path, caplog):
    """Vérifie que l'arrêt du daemon n'émet aucun traceback CancelledError (Uvicorn/Starlette)."""
    dummy_mcp = MCPServer("GracefulStopServer")

    @dummy_mcp.tool()
    def ping() -> str:
        return "pong"

    daemon = MCPServerDaemon(
        mcp_server=dummy_mcp,
        host="127.0.0.1",
        base_port=9250,
        data_dir=tmp_path,
    )
    assert daemon.start(timeout=5.0) is True

    port = daemon.port
    assert port is not None
    headers = {"Authorization": f"Bearer {daemon.token}"}
    # Session SSE réellement ouverte : c'est elle qui bloque le shutdown gracieux d'Uvicorn.
    with capture_uvicorn_logs() as uvicorn_log_capture, httpx.stream("GET", f"http://127.0.0.1:{port}/sse", headers=headers, timeout=5.0) as resp:
        assert resp.status_code == 200
        time.sleep(0.3)
        uvicorn_log_capture.clear()
        caplog.clear()
        daemon.stop(timeout=5.0)

    # 1. Aucun traceback CancelledError journalisé par Uvicorn (donc absent du terminal).
    formatter = logging.Formatter()
    reported = "\n".join(formatter.format(r) if r.exc_info is None else formatter.formatException(r.exc_info) for r in uvicorn_log_capture)
    assert "CancelledError" not in reported, f"Arrêt du daemon bruyant :\n{reported}"

    # 2. Aucune exception journalisée par le code AnkiForge lui-même (donc absent d'ankiforge.log).
    assert "CancelledError" not in caplog.text, f"Arrêt du daemon bruyant :\n{caplog.text}"

    # 3. Le port réseau est libéré et l'état stopped marqué (jeton conservé sur disque pour stabilité).
    assert daemon.is_running is False
    assert daemon.token_file.exists()
    assert is_port_in_use(port, host="127.0.0.1") is False

    # 4. Le thread de travail est réellement terminé (et non simplement abandonné).
    assert [t.name for t in threading.enumerate() if t.name.startswith("MCPServerDaemon-")] == []


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


def test_mcp_streamable_http_post_initialize_returns_200_not_405(tmp_path):
    """
    Vérifie qu'un appel POST initialize sur /mcp retourne 200 (Streamable HTTP MCP 2.x standard)
    et non 405 Method Not Allowed (qui se produisait lorsque seul GET /sse était exposé).
    Vérifie également que BearerAuthMiddleware protège l'endpoint /mcp.
    """
    dummy_mcp = MCPServer("InitTestServer")

    @dummy_mcp.tool()
    def echo(msg: str) -> str:
        return msg

    daemon = MCPServerDaemon(
        mcp_server=dummy_mcp,
        host="127.0.0.1",
        base_port=9650,
        data_dir=tmp_path,
    )

    started = daemon.start(timeout=5.0)
    assert started is True
    assert daemon.is_running is True
    assert daemon.url == f"http://127.0.0.1:{daemon.port}/mcp"

    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "test-streamable-client",
                "version": "1.0.0",
            },
        },
    }

    try:
        # 1. Requête POST /mcp non authentifiée -> 401 Unauthorized (sécurité garantie)
        resp_unauth = httpx.post(daemon.url, json=init_payload, timeout=3.0)
        assert resp_unauth.status_code == 401
        assert "Bearer" in resp_unauth.headers.get("www-authenticate", "")

        # 2. Requête POST /mcp authentifiée avec Bearer token -> 200 OK (pas 405 !)
        auth_headers = {
            "Authorization": f"Bearer {daemon.token}",
            "Accept": "application/json, text/event-stream",
        }
        resp_init = httpx.post(daemon.url, json=init_payload, headers=auth_headers, timeout=3.0)
        assert resp_init.status_code == 200
        assert "mcp-session-id" in resp_init.headers

        # 3. Comparaison avec POST sur /sse -> retourne 405 Method Not Allowed
        resp_sse_post = httpx.post(daemon.sse_url, json=init_payload, headers=auth_headers, timeout=3.0)
        assert resp_sse_post.status_code == 405

    finally:
        daemon.stop(timeout=5.0)


def test_mcp_server_daemon_dual_stack_streamable_http_and_sse(tmp_path):
    """
    Vérifie le fonctionnement dual-stack : Streamable HTTP (/mcp) et SSE legacy (/sse)
    sont tous les deux opérationnels et permettent d'exécuter des outils MCP avec session client.
    """
    dummy_mcp = MCPServer("DualStackServer")

    @dummy_mcp.tool()
    def multiply(a: int, b: int) -> int:
        return a * b

    daemon = MCPServerDaemon(
        mcp_server=dummy_mcp,
        host="127.0.0.1",
        base_port=9700,
        data_dir=tmp_path,
    )

    started = daemon.start(timeout=5.0)
    assert started is True
    assert daemon.is_running is True

    async def _test_dual_stack():
        auth_headers = {"Authorization": f"Bearer {daemon.token}"}

        # 1. Client Streamable HTTP (MCP 2.x standard)
        async with (
            httpx.AsyncClient(headers=auth_headers) as http_client,
            streamable_http_client(daemon.url, http_client=http_client) as (read_stream, write_stream),
            ClientSession(read_stream, write_stream) as streamable_session,
        ):
            await streamable_session.initialize()
            tools_res = await streamable_session.list_tools()
            assert any(t.name == "multiply" for t in tools_res.tools)

            mult_res = await streamable_session.call_tool("multiply", arguments={"a": 6, "b": 7})
            assert mult_res is not None
            assert not mult_res.is_error
            assert any("42" in str(c) for c in mult_res.content)

        # 2. Client SSE legacy
        async with (
            sse_client(daemon.sse_url, headers=auth_headers) as (read_sse, write_sse),
            ClientSession(read_sse, write_sse) as sse_session,
        ):
            await sse_session.initialize()
            tools_res_sse = await sse_session.list_tools()
            assert any(t.name == "multiply" for t in tools_res_sse.tools)

            mult_res_sse = await sse_session.call_tool("multiply", arguments={"a": 3, "b": 4})
            assert mult_res_sse is not None
            assert not mult_res_sse.is_error
            assert any("12" in str(c) for c in mult_res_sse.content)

    try:
        asyncio.run(_test_dual_stack())
    finally:
        daemon.stop(timeout=5.0)


def test_mcp_server_daemon_live_token_rotation(tmp_path):
    """Vérifie que rotate_token() renouvelle le jeton en direct et invalide l'ancien immédiatement."""
    dummy_mcp = MCPServer("RotationServer")

    @dummy_mcp.tool()
    def status() -> str:
        return "ok"

    daemon = MCPServerDaemon(
        mcp_server=dummy_mcp,
        host="127.0.0.1",
        base_port=9800,
        data_dir=tmp_path,
    )

    assert daemon.start(timeout=5.0) is True
    initial_token = daemon.token
    assert initial_token is not None

    # Requête avec initial_token -> 200
    with httpx.stream("GET", f"http://127.0.0.1:{daemon.port}/sse", headers={"Authorization": f"Bearer {initial_token}"}, timeout=3.0) as r1:
        assert r1.status_code == 200

    # Rotation en direct
    new_token = daemon.rotate_token()
    assert new_token != initial_token
    assert daemon.token == new_token
    assert daemon.token_file.read_text(encoding="utf-8") == new_token

    # Requête avec initial_token -> 401 Unauthorized
    r_old = httpx.get(f"http://127.0.0.1:{daemon.port}/sse", headers={"Authorization": f"Bearer {initial_token}"}, timeout=3.0)
    assert r_old.status_code == 401

    # Requête avec new_token -> 200 OK
    with httpx.stream("GET", f"http://127.0.0.1:{daemon.port}/sse", headers={"Authorization": f"Bearer {new_token}"}, timeout=3.0) as r_new:
        assert r_new.status_code == 200

    daemon.stop(timeout=5.0)
