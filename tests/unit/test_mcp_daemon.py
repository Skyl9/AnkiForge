"""Tests unitaires purs pour le middleware et les utilitaires du daemon MCP."""

from __future__ import annotations

import asyncio
import os
import stat
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from ankiforge.services.ai.mcp_daemon import (
    BearerAuthMiddleware,
    cleanup_daemon_state,
    drain_pending_tasks,
    generate_auth_token,
    get_known_mcp_client_config_paths,
    get_or_create_auth_token,
    load_auth_token,
    read_daemon_state,
    rotate_auth_token,
    save_auth_token,
    sync_mcp_client_config,
    write_daemon_state,
)


@pytest.fixture
def dummy_app():
    async def endpoint(request: Request) -> PlainTextResponse:
        return PlainTextResponse("hello secure world")

    return Starlette(routes=[Route("/test", endpoint=endpoint)])


@pytest.mark.unit
def test_bearer_auth_middleware_unauthorized_when_missing_header(dummy_app):
    """Vérifie qu'une requête sans en-tête Authorization est rejetée avec un code 401."""
    secured_app = BearerAuthMiddleware(dummy_app, token="secret-token-123")
    client = TestClient(secured_app)

    response = client.get("/test")
    assert response.status_code == 401
    assert "Bearer" in response.headers.get("www-authenticate", "")


@pytest.mark.unit
def test_bearer_auth_middleware_unauthorized_when_invalid_token(dummy_app):
    """Vérifie qu'un token invalide ou malformé est rejeté avec un code 401."""
    secured_app = BearerAuthMiddleware(dummy_app, token="secret-token-123")
    client = TestClient(secured_app)

    # Token erroné
    res_wrong = client.get("/test", headers={"Authorization": "Bearer wrong-token"})
    assert res_wrong.status_code == 401

    # Schéma non Bearer
    res_basic = client.get("/test", headers={"Authorization": "Basic secret-token-123"})
    assert res_basic.status_code == 401


@pytest.mark.unit
def test_bearer_auth_middleware_unauthorized_when_non_utf8_header(dummy_app):
    """Vérifie qu'un en-tête Authorization avec des octets non-UTF8 retourne 401 et non 500."""
    secured_app = BearerAuthMiddleware(dummy_app, token="secret-token-123")
    sent_messages: list[dict[str, Any]] = []

    async def dummy_send(msg: dict[str, Any]) -> None:
        sent_messages.append(msg)

    async def dummy_receive() -> dict[str, Any]:
        return {"type": "http.request"}

    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/test",
        "headers": [(b"authorization", b"Bearer \xff\xfe")],
    }

    asyncio.run(secured_app(scope, dummy_receive, dummy_send))
    assert any(m.get("status") == 401 for m in sent_messages if m.get("type") == "http.response.start")


@pytest.mark.unit
def test_bearer_auth_middleware_authorized_when_valid_token(dummy_app):
    """Vérifie qu'un token Bearer valide permet d'accéder à l'endpoint avec succès."""
    secured_app = BearerAuthMiddleware(dummy_app, token="secret-token-123")
    client = TestClient(secured_app)

    response = client.get("/test", headers={"Authorization": "Bearer secret-token-123"})
    assert response.status_code == 200
    assert response.text == "hello secure world"


@pytest.mark.unit
def test_token_and_state_persistence_and_permissions(tmp_path):
    """Vérifie la génération du jeton et du fichier d'état avec droits 0600 et le marquage stopped."""
    token_file = tmp_path / "mcp_auth_token"
    state_file = tmp_path / "mcp_server.json"

    token = generate_auth_token()
    assert len(token) >= 32

    save_auth_token(token, token_file)
    assert token_file.exists()
    assert token_file.read_text(encoding="utf-8") == token

    # Vérification des permissions 0600 sur token_file
    if os.name == "posix":
        file_mode = stat.S_IMODE(token_file.stat().st_mode)
        assert file_mode == 0o600

    # Publication de l'état
    write_daemon_state(
        state_file=state_file,
        status="running",
        host="127.0.0.1",
        port=8765,
        token=token,
        token_file=token_file,
        pid=1234,
    )
    assert state_file.exists()

    # Vérification des permissions 0600 sur state_file
    if os.name == "posix":
        file_mode = stat.S_IMODE(state_file.stat().st_mode)
        assert file_mode == 0o600

    state = read_daemon_state(state_file)
    assert state is not None
    assert state["status"] == "running"
    assert state["port"] == 8765
    assert state["url"] == "http://127.0.0.1:8765/mcp"
    assert state["sse_url"] == "http://127.0.0.1:8765/sse"
    assert state["token"] == token
    assert state["pid"] == 1234

    # Nettoyage avec marquage stopped (le jeton reste persistant sur le disque pour les prochains redémarrages)
    cleanup_daemon_state(token_file=token_file, state_file=state_file, mark_stopped=True)
    assert token_file.exists()
    assert token_file.read_text(encoding="utf-8") == token
    assert state_file.exists()
    state_after = read_daemon_state(state_file)
    assert state_after is not None
    assert state_after["status"] == "stopped"

    # Nettoyage complet avec révocation/suppression explicite du jeton
    cleanup_daemon_state(token_file=token_file, state_file=state_file, mark_stopped=False, delete_token=True)
    assert not token_file.exists()
    assert not state_file.exists()


@pytest.mark.unit
def test_drain_pending_tasks_cancels_residual_tasks_without_raising():
    """Vérifie que la vidange finale annule puis attend les tâches résiduelles sans rien laisser remonter."""
    client_cancelled = False

    async def _lingering_session() -> None:
        nonlocal client_cancelled
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            client_cancelled = True
            raise

    async def _raises_cancelled_error() -> None:
        # CancelledError est une BaseException : la vidange doit l'absorber elle aussi.
        await asyncio.sleep(0)
        raise asyncio.CancelledError

    loop = asyncio.new_event_loop()
    try:
        asyncio.ensure_future(_lingering_session(), loop=loop)
        asyncio.ensure_future(_raises_cancelled_error(), loop=loop)
        loop.run_until_complete(asyncio.sleep(0))

        drain_pending_tasks(loop)
    finally:
        loop.close()

    assert client_cancelled is True


@pytest.mark.unit
def test_mcp_server_daemon_url_properties(tmp_path):
    """Vérifie que les propriétés url (Streamable HTTP), mcp_url et sse_url sont correctement formées."""
    from ankiforge.services.ai.mcp_daemon import MCPServerDaemon

    daemon = MCPServerDaemon(host="127.0.0.1", base_port=8765, data_dir=tmp_path)
    assert daemon.url is None
    assert daemon.sse_url is None

    daemon._port = 9123
    assert daemon.url == "http://127.0.0.1:9123/mcp"
    assert daemon.sse_url == "http://127.0.0.1:9123/sse"


@pytest.mark.unit
def test_load_auth_token_behavior(tmp_path: Path) -> None:
    """Vérifie la lecture, la validation et les cas d'erreur de load_auth_token."""
    token_file = tmp_path / "mcp_auth_token"

    # Fichier inexistant
    assert load_auth_token(token_file) is None

    # Fichier vide ou espaces blancs
    token_file.write_text("   \n  ", encoding="utf-8")
    assert load_auth_token(token_file) is None

    # Jeton trop court (< 16 caractères)
    token_file.write_text("court", encoding="utf-8")
    assert load_auth_token(token_file) is None

    # Jeton valide avec espaces autour
    valid_token = generate_auth_token()
    token_file.write_text(f"  {valid_token}\n", encoding="utf-8")
    assert load_auth_token(token_file) == valid_token


@pytest.mark.unit
def test_get_or_create_auth_token_stability_and_rotation(tmp_path: Path) -> None:
    """Vérifie que get_or_create_auth_token réutilise le jeton existant ou le renouvelle si rotate=True."""
    token_file = tmp_path / "mcp_auth_token"
    state_file = tmp_path / "mcp_server.json"

    # 1. Premier appel : création initiale
    token1 = get_or_create_auth_token(token_file, state_file=state_file)
    assert len(token1) >= 32
    assert token_file.is_file()
    assert token_file.read_text(encoding="utf-8") == token1

    # 2. Deuxième appel sans rotation : réutilisation stable à l'identique
    token2 = get_or_create_auth_token(token_file, state_file=state_file, rotate=False)
    assert token2 == token1

    # 3. Troisième appel avec rotation forcée : nouveau jeton distinct
    token3 = get_or_create_auth_token(token_file, state_file=state_file, rotate=True)
    assert token3 != token1
    assert token_file.read_text(encoding="utf-8") == token3


@pytest.mark.unit
def test_get_or_create_auth_token_restores_from_state_file_if_token_file_missing(tmp_path: Path) -> None:
    """Vérifie qu'un jeton présent dans mcp_server.json est restauré dans mcp_auth_token s'il avait été perdu."""
    token_file = tmp_path / "mcp_auth_token"
    state_file = tmp_path / "mcp_server.json"

    recovered_token = "vVPUNdimr9lErJtFr65nKSZcjNAWFpChGLBl-G0xsDY"
    write_daemon_state(
        state_file=state_file,
        status="stopped",
        host="127.0.0.1",
        port=8765,
        token=recovered_token,
        token_file=token_file,
    )
    assert not token_file.exists()

    token = get_or_create_auth_token(token_file, state_file=state_file)
    assert token == recovered_token
    assert token_file.is_file()
    assert token_file.read_text(encoding="utf-8") == recovered_token


@pytest.mark.unit
def test_rotate_auth_token_updates_files_and_permissions(tmp_path: Path) -> None:
    """Vérifie que rotate_auth_token met à jour le fichier de token et mcp_server.json en conservant 0600."""
    token_file = tmp_path / "mcp_auth_token"
    state_file = tmp_path / "mcp_server.json"

    token_init = get_or_create_auth_token(token_file, state_file=state_file)
    write_daemon_state(
        state_file=state_file,
        status="running",
        host="127.0.0.1",
        port=8765,
        token=token_init,
        token_file=token_file,
    )

    new_token = rotate_auth_token(token_file, state_file=state_file)
    assert new_token != token_init
    assert token_file.read_text(encoding="utf-8") == new_token

    # Vérification que state_file a été synchronisé
    state = read_daemon_state(state_file)
    assert state is not None
    assert state["token"] == new_token
    assert state["status"] == "running"

    if os.name == "posix":
        assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
        assert stat.S_IMODE(state_file.stat().st_mode) == 0o600


@pytest.mark.unit
def test_bearer_auth_middleware_dynamic_token_update(dummy_app) -> None:
    """Vérifie que la modification de middleware.token prend effet immédiatement sur les requêtes suivantes."""
    token_v1 = "initial-token-12345678"
    token_v2 = "rotated-token-87654321"

    secured_app = BearerAuthMiddleware(dummy_app, token=token_v1)
    client = TestClient(secured_app)

    # v1 fonctionne, v2 échoue
    assert client.get("/test", headers={"Authorization": f"Bearer {token_v1}"}).status_code == 200
    assert client.get("/test", headers={"Authorization": f"Bearer {token_v2}"}).status_code == 401

    # Rotation dynamique sans reconstruire l'application
    secured_app.token = token_v2

    # v1 échoue désormais, v2 fonctionne
    assert client.get("/test", headers={"Authorization": f"Bearer {token_v1}"}).status_code == 401
    assert client.get("/test", headers={"Authorization": f"Bearer {token_v2}"}).status_code == 200


@pytest.mark.unit
def test_sync_mcp_client_config_atomic_and_permissions(tmp_path: Path) -> None:
    """Vérifie que sync_mcp_client_config met à jour Authorization et l'URL en écriture atomique (0600)."""
    import json

    client_cfg = tmp_path / "mcp_config.json"
    initial_data = {
        "mcpServers": {
            "ankiforge": {
                "url": "http://127.0.0.1:8765/mcp",
                "headers": {"Authorization": "Bearer old-token-12345"},
            },
            "other_server": {"url": "http://127.0.0.1:9000/sse"},
        }
    }
    client_cfg.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")

    # 1. Mise à jour token seul
    updated = sync_mcp_client_config(
        token="new-token-67890",
        config_paths=[client_cfg],
    )
    assert updated is True

    parsed = json.loads(client_cfg.read_text(encoding="utf-8"))
    assert parsed["mcpServers"]["ankiforge"]["headers"]["Authorization"] == "Bearer new-token-67890"
    assert parsed["mcpServers"]["ankiforge"]["url"] == "http://127.0.0.1:8765/mcp"
    assert "other_server" in parsed["mcpServers"]

    if os.name == "posix":
        assert stat.S_IMODE(client_cfg.stat().st_mode) == 0o600

    # 2. Mise à jour token et port
    updated = sync_mcp_client_config(
        token="another-token-99999",
        port=9999,
        config_paths=[client_cfg],
    )
    assert updated is True

    parsed = json.loads(client_cfg.read_text(encoding="utf-8"))
    assert parsed["mcpServers"]["ankiforge"]["headers"]["Authorization"] == "Bearer another-token-99999"
    assert parsed["mcpServers"]["ankiforge"]["url"] == "http://127.0.0.1:9999/mcp"

    # 3. Fichier sans entrée ankiforge ou fichier absent
    empty_cfg = tmp_path / "empty_config.json"
    empty_cfg.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    assert sync_mcp_client_config(token="foo", config_paths=[empty_cfg, tmp_path / "nonexistent.json"]) is False


@pytest.mark.unit
def test_get_known_mcp_client_config_paths() -> None:
    """Vérifie que la liste des chemins de clients connus inclut le config Antigravity."""
    paths = get_known_mcp_client_config_paths()
    assert any(".gemini" in str(p) for p in paths)
