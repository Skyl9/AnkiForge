"""Bout-en-bout : proposition émise par un client MCP externe → inspecteur Espace de Travail → application en BDD.

Chaîne vérifiée par ce test (ticket « Patchs MCP impossibles à valider ») :
1. un client MCP externe appelle `propose_card_refactor` via le daemon (SSE, auth Bearer) ;
2. l'outil crée un `StagedPatchModel` encore « pending » et renvoie un `staged_diff` ;
3. l'ouverture de `ConsultantView` recharge la file depuis `StagedPatchRegistry.list_pending()` ;
4. le clic sur « Appliquer » persouiste le patch comme « applied » et écrit la nouvelle version active.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

from ankiforge.database.models import NoteModel, NoteTypeModel, NoteVersionModel, StagedPatchModel
from ankiforge.services.ai.mcp_daemon import MCPServerDaemon
from ankiforge.services.ai.mcp_server import mcp
from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

pytestmark = [pytest.mark.integration, pytest.mark.ui]


def test_mcp_proposal_reaches_workspace_inspector_and_applies(qtbot, tmp_path):
    """Vérifie la boucle complète MCP externe → file de l'inspecteur → validation → BDD."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"NT_E2E_{uid}", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    note = NoteModel.create(guid=f"g_e2e_{uid}", note_type=nt)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Front": "Question d'origine", "Back": "Réponse d'origine"}),
        is_active=True,
    )

    daemon = MCPServerDaemon(mcp_server=mcp, base_port=9850, data_dir=tmp_path)
    assert daemon.start(timeout=5.0) is True

    async def _propose_via_client() -> dict:
        auth_headers = {"Authorization": f"Bearer {daemon.token}"}
        async with (
            sse_client(daemon.sse_url, headers=auth_headers) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            assert "propose_card_refactor" in [t.name for t in tools.tools]

            result = await session.call_tool(
                "propose_card_refactor",
                arguments={
                    "note_id": note.id,
                    "new_fields_json": json.dumps({"Front": "Question reformulée", "Back": "Réponse reformulée"}),
                    "explanation": "Formulation plus claire (E2E MCP)",
                },
            )
            assert result is not None
            assert not result.is_error
            return json.loads(result.content[0].text)

    try:
        staged_payload = asyncio.run(_propose_via_client())
    finally:
        daemon.stop(timeout=5.0)

    # 2. La proposition est persistée « pending » et son payload est complet
    assert staged_payload.get("status") == "staged_diff"
    patch_id = staged_payload["patch_id"]
    pending_rows = list(StagedPatchRegistry.list_pending())
    assert [row.patch_id for row in pending_rows] == [patch_id]
    assert StagedPatchModel.get(StagedPatchModel.patch_id == patch_id).status == "pending"

    # 3. L'ouverture de la vue recharge la file et bascule sur l'onglet Espace de Travail
    from ankiforge.ui.views.consultant_view.view import ConsultantView

    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)
    view.show()

    inspector = view.workspace_inspector
    assert [item.get("patch_id") for item in inspector._patch_queue] == [patch_id]
    assert view.context_panel.content_stack.currentWidget() is inspector
    assert inspector.isVisible()
    assert "En attente" in inspector.status_badge.text()
    assert inspector.btn_apply.isEnabled()

    # 4. Validation : le patch passe à « applied » et la nouvelle version devient active
    with qtbot.waitSignal(inspector.action_applied, timeout=5000):
        inspector.btn_apply.click()

    assert StagedPatchRegistry.get_patch(patch_id).status == "applied"
    assert not StagedPatchRegistry.list_pending()
    assert not inspector._patch_queue

    active_version = NoteVersionModel.get(NoteVersionModel.note == note, NoteVersionModel.is_active == True)  # noqa: E712
    fields = json.loads(active_version.content)
    assert fields["Front"] == "Question reformulée"
