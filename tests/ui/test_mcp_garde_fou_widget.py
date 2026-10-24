"""Tests unitaires et UI headless pour MCPGardeFouWidget (Master-Detail).

Vérifie le chargement de la file d'attente des patchs, la sélection dans la liste,
la synchronisation de l'édition directe, l'application et le rejet transactionnel.
"""

from __future__ import annotations

import json
import uuid

import pytest

from ankiforge.database.models import NoteModel, NoteTypeModel, NoteVersionModel, StagedPatchModel
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


def test_mcp_garde_fou_widget_selection_advances_on_apply(qtbot):
    """Vérifie que la sélection avance au patch suivant après validation, ou affiche l'état vide."""
    nt = NoteTypeModel.create(name=f"NT_GF_ADV_{uuid.uuid4().hex[:6]}", fields_schema='["Front", "Back"]', templates="[]", css_style="")

    def _make_note_and_patch(idx: int) -> StagedPatchModel:
        note = NoteModel.create(guid=f"g_adv_{idx}_{uuid.uuid4().hex[:6]}", note_type=nt)
        NoteVersionModel.create(
            note=note,
            version_number=1,
            content=json.dumps({"Front": f"Q{idx}", "Back": f"R{idx}"}),
            is_active=True,
        )
        return StagedPatchRegistry.create_patch(
            patch_type="card",
            target_id=note.id,
            diff_payload={
                "type": "card",
                "note_id": note.id,
                "title": f"Proposition #{idx}",
                "original": {"Front": f"Q{idx}"},
                "modified": {"Front": f"Q{idx} mod"},
            },
        )

    p1 = _make_note_and_patch(1)
    p2 = _make_note_and_patch(2)
    p3 = _make_note_and_patch(3)

    widget = MCPGardeFouWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.reload_pending_patches()

    assert widget.count() == 3
    assert widget.current_patch_id == p1.patch_id

    # Validation du premier patch -> avance au 2ème
    widget.btn_apply.click()
    assert widget.count() == 2
    assert widget.current_patch_id == p2.patch_id
    assert widget.detail_stack.currentWidget() is widget.detail_view

    # Validation du 2ème -> avance au 3ème
    widget.btn_apply.click()
    assert widget.count() == 1
    assert widget.current_patch_id == p3.patch_id
    assert widget.detail_stack.currentWidget() is widget.detail_view

    # Validation du dernier -> file épuisée, vue vide affichée
    widget.btn_apply.click()
    assert widget.count() == 0
    assert widget.current_patch_id is None
    assert widget.detail_stack.currentWidget() is widget.empty_view


def test_mcp_garde_fou_widget_selection_advances_from_middle_item(qtbot):
    """Vérifie que la validation d'un élément au milieu avance au suivant et ne repart pas à zéro."""
    nt = NoteTypeModel.create(name=f"NT_GF_MID_{uuid.uuid4().hex[:6]}", fields_schema='["Front", "Back"]', templates="[]", css_style="")

    def _make(idx: int) -> StagedPatchModel:
        note = NoteModel.create(guid=f"g_mid_{idx}_{uuid.uuid4().hex[:6]}", note_type=nt)
        NoteVersionModel.create(
            note=note,
            version_number=1,
            content=json.dumps({"Front": f"Q{idx}", "Back": f"R{idx}"}),
            is_active=True,
        )
        return StagedPatchRegistry.create_patch(
            patch_type="card",
            target_id=note.id,
            diff_payload={
                "type": "card",
                "note_id": note.id,
                "title": f"Proposition #{idx}",
                "original": {"Front": f"Q{idx}"},
                "modified": {"Front": f"Q{idx} mod"},
            },
        )

    _make(1)
    p2 = _make(2)
    p3 = _make(3)

    widget = MCPGardeFouWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.reload_pending_patches()

    # Sélectionner le 2ème élément (index 1 = p2)
    widget.patch_list.setCurrentRow(1)
    assert widget.current_patch_id == p2.patch_id

    # Validation de p2 -> doit avancer vers p3 (index 1 dans la nouvelle liste [p1, p3])
    widget.btn_apply.click()
    assert widget.count() == 2
    assert widget.current_patch_id == p3.patch_id


def test_mcp_garde_fou_widget_apply_split(qtbot, sample_note) -> None:
    """Vérifie l'application d'une scission (split) dans le Garde-Fou : N notes créées, note mère archivée."""
    payload = {
        "type": "split",
        "note_id": sample_note.id,
        "title": f"Scission Note #{sample_note.id}",
        "original": {"Front": "Question dense", "Back": "R1 et R2"},
        "modified": [
            {"Front": "Question atomique 1 ?", "Back": "Réponse 1"},
            {"Front": "Question atomique 2 ?", "Back": "Réponse 2"},
        ],
    }
    patch = StagedPatchRegistry.create_patch(
        patch_type="split",
        target_id=sample_note.id,
        diff_payload=payload,
    )

    widget = MCPGardeFouWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.reload_pending_patches()

    assert widget.count() == 1
    assert widget.current_patch_id == patch.patch_id

    applied_signals: list[str] = []
    widget.patch_applied.connect(applied_signals.append)

    # Clic sur Appliquer
    widget.btn_apply.click()

    assert len(applied_signals) == 1
    assert widget.count() == 0

    # Vérification BDD
    updated_patch = StagedPatchRegistry.get_patch(patch.patch_id)
    assert updated_patch is not None
    assert updated_patch.status == "applied"

    # La note mère doit être archivée
    mother = NoteModel.get_by_id(sample_note.id)
    assert mother.status == "archived"

    # Vérification que 2 nouvelles notes ont été créées
    created_notes = list(NoteModel.select().where(NoteModel.id != sample_note.id))
    assert len(created_notes) == 2


def test_mcp_garde_fou_widget_apply_note_type_create(qtbot) -> None:
    """Vérifie l'application d'un note_type_create via le Garde-Fou."""
    unique_name = f"NT_Create_GF_{uuid.uuid4().hex[:6]}"
    payload = {
        "type": "note_type_create",
        "name": unique_name,
        "fields_schema": ["Front", "Back"],
        "templates": [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}],
        "css_style": ".card { color: purple; }",
        "description": "Nouveau type créé via GF",
        "title": f"Création de {unique_name}",
    }
    StagedPatchRegistry.create_patch(
        patch_type="note_type_create",
        diff_payload=payload,
    )

    widget = MCPGardeFouWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.reload_pending_patches()

    assert widget.count() == 1
    widget.btn_apply.click()

    assert widget.count() == 0
    created_nt = NoteTypeModel.get_or_none(NoteTypeModel.name == unique_name)
    assert created_nt is not None
    assert created_nt.description == "Nouveau type créé via GF"


def test_mcp_garde_fou_widget_apply_note_type_change(qtbot, sample_note) -> None:
    """Vérifie l'application d'un note_type_change via le Garde-Fou."""
    target_nt = NoteTypeModel.create(
        name=f"NT_Target_GF_{uuid.uuid4().hex[:6]}",
        fields_schema='["Recto", "Verso"]',
        templates='[{"name": "C1", "qfmt": "{{Recto}}", "afmt": "{{Verso}}"}]',
    )
    payload = {
        "type": "note_type_change",
        "note_ids": [sample_note.id],
        "target_model": target_nt.name,
        "target_model_id": target_nt.id,
        "mapping_champs": {"Front": "Recto", "Back": "Verso"},
        "title": f"Migration vers {target_nt.name}",
    }
    StagedPatchRegistry.create_patch(
        patch_type="note_type_change",
        target_id=target_nt.id,
        diff_payload=payload,
    )

    widget = MCPGardeFouWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.reload_pending_patches()

    assert widget.count() == 1
    widget.btn_apply.click()

    assert widget.count() == 0
    reloaded_note = NoteModel.get_by_id(sample_note.id)
    assert reloaded_note.note_type.id == target_nt.id
