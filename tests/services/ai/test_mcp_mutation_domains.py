"""Tests unitaires de la résolution du domaine fonctionnel des mutations MCP.

Couvre les types canoniques, les alias historiques émis par
`ConsultantToolRegistry.apply_patch` (`card`, `split`, `model`, `css`), la priorité
d'un domaine explicite et le repli sûr pour un type inconnu.
"""

from __future__ import annotations

from typing import Any

import pytest

from ankiforge.services.ai.mcp_server import (
    DEFAULT_MCP_MUTATION_DOMAIN,
    MCP_MUTATION_DOMAINS,
    _notify_mcp_mutation,
    normalize_mutation_type,
    register_mutation_listener,
    resolve_mcp_mutation_domain,
    unregister_mutation_listener,
)
from ankiforge.utils.event_bus import MCPDataMutatedEvent, event_bus

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("mutation_type", "expected_domain"),
    [
        ("note_update", "cards"),
        ("batch_note_create", "cards"),
        ("sanitize_fields_html", "cards"),
        ("card", "cards"),
        ("split", "cards"),
        ("note_type_update", "models"),
        ("css_tune", "models"),
        ("model", "models"),
        ("css", "models"),
        ("create_deck", "decks"),
        ("document_update", "docs"),
        ("type_inconnu", DEFAULT_MCP_MUTATION_DOMAIN),
        ("", DEFAULT_MCP_MUTATION_DOMAIN),
    ],
)
def test_resolve_mcp_mutation_domain(mutation_type: str, expected_domain: str) -> None:
    """Chaque type connu (y compris legacy) est routé vers son domaine de vue."""
    assert resolve_mcp_mutation_domain({"type": mutation_type}) == expected_domain


def test_resolve_mcp_mutation_domain_accepts_mutation_type_key() -> None:
    """La clé historique `mutation_type` est normalisée comme `type`."""
    assert normalize_mutation_type({"mutation_type": "MODEL"}) == "model"
    assert resolve_mcp_mutation_domain({"mutation_type": "model"}) == "models"


def test_resolve_mcp_mutation_domain_respects_explicit_domain() -> None:
    """Un domaine explicite valide est prioritaire sur la table de routage."""
    assert resolve_mcp_mutation_domain({"type": "note_update", "domain": "docs"}) == "docs"


def test_resolve_mcp_mutation_domain_ignores_invalid_explicit_domain() -> None:
    """Un domaine explicite inconnu retombe sur la résolution par type."""
    assert resolve_mcp_mutation_domain({"type": "model", "domain": "bogus"}) == "models"


def test_mutation_domains_are_closed_set() -> None:
    """Le vocabulaire exposé reste un ensemble fermé et stable."""
    assert frozenset({"cards", "decks", "models", "docs"}) == MCP_MUTATION_DOMAINS


@pytest.mark.parametrize(
    ("mutation_type", "expected_domain"),
    [
        ("note_update", "cards"),
        ("card", "cards"),
        ("model", "models"),
        ("css", "models"),
        ("create_deck", "decks"),
        ("document_update", "docs"),
    ],
)
def test_notify_mcp_mutation_resolves_domain(mutation_type: str, expected_domain: str) -> None:
    """Le domaine résolu est injecté dans le payload et dans l'événement publié."""
    received: list[dict[str, Any]] = []
    published: list[MCPDataMutatedEvent] = []

    def on_mutation(payload: dict[str, Any]) -> None:
        received.append(payload)

    def on_event(event: MCPDataMutatedEvent) -> None:
        published.append(event)

    register_mutation_listener(on_mutation)
    event_bus.subscribe(MCPDataMutatedEvent, on_event)
    try:
        _notify_mcp_mutation({"type": mutation_type, "target_id": 7})
    finally:
        unregister_mutation_listener(on_mutation)
        event_bus.unsubscribe(MCPDataMutatedEvent, on_event)

    assert received and received[0]["domain"] == expected_domain
    assert published and published[0].domain == expected_domain
    assert published[0].mutation_type == mutation_type


def test_notify_mcp_mutation_uses_mutation_type_key_in_event() -> None:
    """Un payload exprimé avec `mutation_type` publie un événement correctement typé."""
    published: list[MCPDataMutatedEvent] = []

    def on_event(event: MCPDataMutatedEvent) -> None:
        published.append(event)

    event_bus.subscribe(MCPDataMutatedEvent, on_event)
    try:
        _notify_mcp_mutation({"mutation_type": "model", "note_type_id": 42})
    finally:
        event_bus.unsubscribe(MCPDataMutatedEvent, on_event)

    assert published[0].mutation_type == "model"
    assert published[0].domain == "models"
    assert published[0].target_id == 42


def test_notify_mcp_mutation_respects_explicit_domain() -> None:
    """Un domaine explicite valide prime sur la table de routage par type."""
    received: list[dict[str, Any]] = []

    def on_mutation(payload: dict[str, Any]) -> None:
        received.append(payload)

    register_mutation_listener(on_mutation)
    try:
        _notify_mcp_mutation({"type": "note_update", "domain": "docs", "document_id": 3})
    finally:
        unregister_mutation_listener(on_mutation)

    assert received[0]["domain"] == "docs"
