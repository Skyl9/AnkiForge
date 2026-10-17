"""Tests unitaires et UI headless pour MCPGardeFouWidget (Master-Detail).

Vérifie le chargement de la file d'attente des patchs, la sélection dans la liste,
la synchronisation de l'édition directe, l'application et le rejet transactionnel.
"""

from __future__ import annotations

import json
import uuid

import pytest

from ankiforge.database.models import NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry
from ankiforge.ui.views.consultant_view.widgets.mcp_garde_fou_widget import MCPGardeFouWidget

pytestmark = [pytest.mark.ui]


@pytest.fixture
def sample_note():
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"NT_GF_{uid}", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    note = NoteModel.create(guid=f"g_gf_{uid}", note_type=nt)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Front": "Question Initiale", "Back": "Réponse Initiale"}),
        is_active=True,
    )
    return note


def test_mcp_garde_fou_widget_empty_state(qtbot):
    """Vérifie l'affichage de l'état vide quand aucun patch n'est en attente."""
    widget = MCPGardeFouWidget()
    qtbot.addWidget(widget)
    widget.show()

    assert widget.count() == 0
    assert widget.detail_stack.currentWidget() is widget.empty_view


def test_mcp_garde_fou_widget_populate_and_select(qtbot, sample_note):
    """Vérifie le chargement d'un patch staged et sa sélection dans la liste."""
    patch = StagedPatchRegistry.create_patch(
        patch_type="card",
        target_id=sample_note.id,
        diff_payload={
            "type": "card",
            "note_id": sample_note.id,
            "title": "Proposition Refactor #1",
            "original": {"Front": "Question Initiale", "Back": "Réponse Initiale"},
            "modified": {"Front": "Question Proposée", "Back": "Réponse Proposée"},
        },
    )

    widget = MCPGardeFouWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.reload_pending_patches()

    assert widget.count() == 1
    assert widget.detail_stack.currentWidget() is widget.detail_view
    assert widget.current_patch_id == patch.patch_id

    # Vérifie que le CardSemanticDiffWidget a bien été alimenté
    rows = widget.diff_viewer.get_field_rows()
    assert "Front" in rows
    assert rows["Front"].mod_editor.toPlainText() == "Question Proposée"


def test_mcp_garde_fou_widget_apply_with_direct_edit(qtbot, sample_note):
    """Vérifie que l'édition directe dans le comparateur est synchronisée et appliquée en BDD."""
    patch = StagedPatchRegistry.create_patch(
        patch_type="card",
        target_id=sample_note.id,
        diff_payload={
            "type": "card",
            "note_id": sample_note.id,
            "title": "Proposition Refactor #2",
            "original": {"Front": "Question Initiale", "Back": "Réponse Initiale"},
            "modified": {"Front": "Question Proposée", "Back": "Réponse Proposée"},
        },
    )

    widget = MCPGardeFouWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.reload_pending_patches()

    # Simulation d'édition directe par l'utilisateur
    rows = widget.diff_viewer.get_field_rows()
    rows["Front"].mod_editor.setPlainText("Question Retouchée par Utilisateur")

    # Clic sur Appliquer
    applied_signals: list[str] = []
    widget.patch_applied.connect(applied_signals.append)

    widget.btn_apply.click()

    assert len(applied_signals) == 1
    assert applied_signals[0] == patch.patch_id
    assert widget.count() == 0

    # Vérification BDD
    updated_patch = StagedPatchRegistry.get_patch(patch.patch_id)
    assert updated_patch.status == "applied"

    active_v = NoteVersionModel.get(NoteVersionModel.note == sample_note, NoteVersionModel.is_active == True)  # noqa: E712
    content = json.loads(active_v.content)
    assert content["Front"] == "Question Retouchée par Utilisateur"


def test_mcp_garde_fou_widget_reject(qtbot, sample_note):
    """Vérifie le rejet d'un patch staged."""
    patch = StagedPatchRegistry.create_patch(
        patch_type="card",
        target_id=sample_note.id,
        diff_payload={
            "type": "card",
            "note_id": sample_note.id,
            "title": "Proposition à Rejeter",
            "original": {"Front": "Q"},
            "modified": {"Front": "Q rejetée"},
        },
    )

    widget = MCPGardeFouWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.reload_pending_patches()

    rejected_signals: list[str] = []
    widget.patch_rejected.connect(rejected_signals.append)

    widget.btn_reject.click()

    assert len(rejected_signals) == 1
    assert rejected_signals[0] == patch.patch_id
    assert widget.count() == 0

    updated_patch = StagedPatchRegistry.get_patch(patch.patch_id)
    assert updated_patch.status == "rejected"
