"""Tests unitaires pour MCPActivityTracker et la télémétrie des outils MCP."""

from __future__ import annotations

import asyncio

import pytest
from mcp.server.mcpserver import MCPServer

from ankiforge.services.ai.mcp_tracker import (
    MCPActivityTracker,
    get_mcp_activity_tracker,
    reset_mcp_activity_tracker,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    reset_mcp_activity_tracker()


def test_tracker_initialization_and_empty() -> None:
    """Vérifie l'initialisation du tracker avec un historique vide."""
    tracker = MCPActivityTracker(max_history=10)
    assert tracker.max_history == 10
    assert tracker.get_history() == []
    assert tracker.total_calls == 0


def test_start_tracking_creates_running_record() -> None:
    """Vérifie la création d'un enregistrement à l'état 'running'."""
    tracker = MCPActivityTracker(max_history=10)
    call_id = tracker.start_tracking(
        tool_name="audit_deck_wozniak",
        arguments={"deck_name": "Vocabulaire Japonais", "threshold": 0.8},
    )

    assert isinstance(call_id, str)
    assert len(call_id) > 0

    history = tracker.get_history()
    assert len(history) == 1
    record = history[0]

    assert record.call_id == call_id
    assert record.tool_name == "audit_deck_wozniak"
    assert record.status == "running"
    assert record.duration_ms == 0.0
    assert "Vocabulaire Japonais" in record.args_summary
    assert record.args_full == {"deck_name": "Vocabulaire Japonais", "threshold": 0.8}
    assert record.result_summary == ""
    assert record.error_message is None


def test_record_success_updates_record() -> None:
    """Vérifie la transition vers l'état 'success' et l'enregistrement de la durée."""
    tracker = MCPActivityTracker()
    call_id = tracker.start_tracking("get_deck_stats", {"deck_name": "Default"})

    updated = tracker.record_success(call_id, result="Cartes: 42, Vues: 10", duration_ms=125.5)

    assert updated is not None
    assert updated.status == "success"
    assert updated.duration_ms == 125.5
    assert updated.result_summary == "Cartes: 42, Vues: 10"
    assert updated.error_message is None

    # Vérifie dans l'historique
    history = tracker.get_history()
    assert history[0].status == "success"


def test_record_error_updates_record() -> None:
    """Vérifie la transition vers l'état 'error' avec message d'erreur."""
    tracker = MCPActivityTracker()
    call_id = tracker.start_tracking("propose_card_refactor", {"note_id": 999})

    updated = tracker.record_error(call_id, error=ValueError("Note introuvable"), duration_ms=42.0)

    assert updated is not None
    assert updated.status == "error"
    assert updated.duration_ms == 42.0
    assert "Note introuvable" in (updated.error_message or "")
    assert "Note introuvable" in updated.result_summary


def test_circular_buffer_capacity() -> None:
    """Vérifie le respect de la capacité max du tampon circulaire."""
    tracker = MCPActivityTracker(max_history=5)
    call_ids = []
    for i in range(10):
        cid = tracker.start_tracking(f"tool_{i}", {"i": i})
        tracker.record_success(cid, f"result_{i}", duration_ms=1.0)
        call_ids.append(cid)

    history = tracker.get_history()
    assert len(history) == 5
    # Doit contenir les 5 derniers (indices 5 à 9)
    assert [r.tool_name for r in history] == [f"tool_{i}" for i in range(5, 10)]
    assert tracker.total_calls == 10


def test_secret_redaction_in_arguments_and_results() -> None:
    """Vérifie le masquage systématique des clés et tokens dans les résumés et détails."""
    tracker = MCPActivityTracker()
    secret_key = "sk-ant-api03-abcdef1234567890abcdef1234"
    secret_openai = "sk-proj-12345678901234567890abcdef"
    bearer_token = "Bearer secret_bearer_token_xyz_12345"

    call_id = tracker.start_tracking(
        "query_api",
        {
            "api_key": secret_key,
            "auth_header": bearer_token,
            "nested": {"key": secret_openai, "password": "supersecretpassword"},
        },
    )

    history = tracker.get_history()
    rec = history[0]

    # Aucun secret en clair dans le résumé
    assert secret_key not in rec.args_summary
    assert secret_openai not in rec.args_summary
    assert "supersecretpassword" not in rec.args_summary
    assert "[REDACTED" in rec.args_summary

    # Aucun secret en clair dans args_full
    args_str = str(rec.args_full)
    assert secret_key not in args_str
    assert secret_openai not in args_str
    assert "supersecretpassword" not in args_str

    # Masquage dans le résultat
    tracker.record_success(call_id, result=f"Connexion réussie avec {bearer_token}", duration_ms=10.0)
    assert bearer_token not in rec.result_summary
    assert "[REDACTED_TOKEN]" in rec.result_summary or "[REDACTED" in rec.result_summary


def test_clear_history() -> None:
    """Vérifie la réinitialisation de l'historique."""
    tracker = MCPActivityTracker()
    tracker.start_tracking("tool_a", {})
    tracker.start_tracking("tool_b", {})
    assert len(tracker.get_history()) == 2

    tracker.clear_history()
    assert tracker.get_history() == []


def test_singleton_accessor() -> None:
    """Vérifie le bon fonctionnement du singleton."""
    t1 = get_mcp_activity_tracker()
    t2 = get_mcp_activity_tracker()
    assert t1 is t2


def test_attach_to_mcp_server_auto_tracking() -> None:
    """Vérifie l'interception automatique de call_tool sur un MCPServer."""
    server = MCPServer("TestServer")

    @server.tool()
    def compute_sum(a: int, b: int) -> int:
        if a < 0:
            raise ValueError("a doit être positif")
        return a + b

    tracker = MCPActivityTracker()
    tracker.attach_to_server(server)

    async def _run() -> None:
        # 1. Appel réussi
        res = await server.call_tool("compute_sum", {"a": 2, "b": 3})
        assert res is not None

        history = tracker.get_history()
        assert len(history) == 1
        assert history[0].tool_name == "compute_sum"
        assert history[0].status == "success"
        assert history[0].duration_ms > 0.0

        # 2. Appel avec exception
        with pytest.raises(Exception, match="compute_sum"):
            await server.call_tool("compute_sum", {"a": -1, "b": 5})

        history = tracker.get_history()
        assert len(history) == 2
        assert history[1].status == "error"
        assert history[1].duration_ms > 0.0

    asyncio.run(_run())
