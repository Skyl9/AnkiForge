"""Tests unitaires purs pour le middleware et les utilitaires du daemon MCP."""

from __future__ import annotations

import os
import stat
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
    generate_auth_token,
    read_daemon_state,
    save_auth_token,
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
    import asyncio

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
    assert state["url"] == "http://127.0.0.1:8765/sse"
    assert state["token"] == token
    assert state["pid"] == 1234

    # Nettoyage avec marquage stopped
    cleanup_daemon_state(token_file=token_file, state_file=state_file, mark_stopped=True)
    assert not token_file.exists()
    assert state_file.exists()
    state_after = read_daemon_state(state_file)
    assert state_after is not None
    assert state_after["status"] == "stopped"

    # Nettoyage complet
    cleanup_daemon_state(token_file=token_file, state_file=state_file, mark_stopped=False)
    assert not state_file.exists()
