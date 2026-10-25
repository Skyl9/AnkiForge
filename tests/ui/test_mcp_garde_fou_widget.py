"""Tests unitaires et UI headless pour MCPGardeFouWidget (Master-Detail).

Vérifie le chargement de la file d'attente des patchs, la sélection dans la liste,
la synchronisation de l'édition directe, l'application et le rejet transactionnel.
"""

from __future__ import annotations

import json
import uuid

import pytest

from ankiforge.database.models import (
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    StagedPatchModel,
)
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


def test_mcp_garde_fou_bundle_hierarchical_display(qtbot) -> None:
    """Vérifie l'affichage groupé des bundles et de leurs sous-étapes dans le volet maître."""
    bundle_id = StagedPatchRegistry.begin_bundle(
        title="Restructuration Neurologie",
        explanation="Création du paquet et insertion de cartes.",
    )
    p1 = StagedPatchRegistry.create_patch(
        patch_type="deck_create",
        diff_payload={"deck_name": "Médecine::Neurologie", "title": "Créer Paquet Neuro"},
    )
    StagedPatchRegistry.create_patch(
        patch_type="card",
        diff_payload={"title": "Carte Synapse", "original": {"Front": "Q1"}, "modified": {"Front": "Q1 mod"}},
    )
    StagedPatchRegistry.commit_bundle(bundle_id)

    widget = MCPGardeFouWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.reload_pending_patches()

    # Le widget contient 2 étapes en attente
    assert widget.count() == 2

    # Le volet maître affiche l'arborescence
    assert hasattr(widget, "patch_tree")
    assert widget.patch_tree.topLevelItemCount() == 1
    bundle_item = widget.patch_tree.topLevelItem(0)
    assert bundle_item is not None
    assert bundle_item.childCount() == 2

    # L'étape 1 est sélectionnée automatiquement
    assert widget.current_patch_id == p1.patch_id
    # La zone de détail polymorphe est à l'index 1 (vue paquet)
    assert widget.polymorphic_stack.currentIndex() == 1
    assert widget.btn_apply.text() == "Valider cette étape"
    assert widget.btn_reject.text() == "Rejeter la suite du bloc"
    assert widget.btn_apply_bundle_all.isVisible()


def test_mcp_garde_fou_polymorphic_stack_views(qtbot, sample_note) -> None:
    """Vérifie la commutation des 4 pages du QStackedWidget polymorphe selon le type d'opération."""
    p_card = StagedPatchRegistry.create_patch(
        patch_type="card",
        target_id=sample_note.id,
        diff_payload={"title": "Diff Carte", "original": {"Front": "A"}, "modified": {"Front": "B"}},
    )
    p_deck = StagedPatchRegistry.create_patch(
        patch_type="deck_create",
        diff_payload={"deck_name": "Sciences::Biologie::Cellule", "title": "Nouveau Paquet"},
    )
    p_tags = StagedPatchRegistry.create_patch(
        patch_type="set_tags",
        diff_payload={
            "title": "Ajustement Tags",
            "note_ids": [sample_note.id],
            "tags_added": ["neuro", "anatomie"],
            "tags_removed": ["brouillon"],
        },
    )
    p_del = StagedPatchRegistry.create_patch(
        patch_type="card_delete",
        target_id=sample_note.id,
        diff_payload={"title": "Suppression Carte", "reason": "Doublon obsolète"},
    )

    widget = MCPGardeFouWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.reload_pending_patches()

    # 1. Sélectionner patch carte -> Page 0 (Diff sémantique)
    widget.select_patch_by_id(p_card.patch_id)
    assert widget.polymorphic_stack.currentIndex() == 0
    assert widget.polymorphic_stack.currentWidget() is widget.diff_viewer

    # 2. Sélectionner patch deck -> Page 1 (Arborescence paquet)
    widget.select_patch_by_id(p_deck.patch_id)
    assert widget.polymorphic_stack.currentIndex() == 1
    assert widget.polymorphic_stack.currentWidget() is widget.deck_view
    assert "Cellule" in widget.deck_view.get_deck_name()

    # 3. Sélectionner patch tags -> Page 2 (Tableau comparatif tags)
    widget.select_patch_by_id(p_tags.patch_id)
    assert widget.polymorphic_stack.currentIndex() == 2
    assert widget.polymorphic_stack.currentWidget() is widget.tag_view
    assert "neuro" in widget.tag_view.get_added_tags()
    assert "brouillon" in widget.tag_view.get_removed_tags()

    # 4. Sélectionner patch suppression -> Page 3 (Bannière rouge vif)
    widget.select_patch_by_id(p_del.patch_id)
    assert widget.polymorphic_stack.currentIndex() == 3
    assert widget.polymorphic_stack.currentWidget() is widget.deletion_view
    assert "Doublon obsolète" in widget.deletion_view.get_reason()


def test_mcp_garde_fou_bundle_step_by_step_and_cascade(qtbot) -> None:
    """Vérifie la validation séquentielle pas-à-pas et la cascade de rejet sur un bundle."""
    deck_name = f"Deck_Seq_{uuid.uuid4().hex[:6]}"
    bundle_id = StagedPatchRegistry.begin_bundle(
        title="Bundle Séquentiel Test",
        explanation="Test de validation pas-à-pas et rejet en cascade.",
    )
    p1 = StagedPatchRegistry.create_patch(
        patch_type="deck_create",
        diff_payload={"deck_name": deck_name, "title": "Étape 1 Deck"},
    )
    p2 = StagedPatchRegistry.create_patch(
        patch_type="card",
        diff_payload={"title": "Étape 2 Carte", "original": {"Front": "Q"}, "modified": {"Front": "Q2"}},
    )
    p3 = StagedPatchRegistry.create_patch(
        patch_type="card",
        diff_payload={"title": "Étape 3 Carte", "original": {"Front": "Q"}, "modified": {"Front": "Q3"}},
    )
    StagedPatchRegistry.commit_bundle(bundle_id)

    widget = MCPGardeFouWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.reload_pending_patches()

    assert widget.count() == 3
    assert widget.current_patch_id == p1.patch_id

    # 1. Validation étape 1
    widget.btn_apply.click()
    assert DeckModel.get_or_none(DeckModel.name == deck_name) is not None
    assert widget.count() == 2
    assert widget.current_patch_id == p2.patch_id

    # 2. Rejet en cascade à l'étape 2 -> doit rejeter l'étape 2 ET l'étape 3
    widget.btn_reject.click()
    assert widget.count() == 0
    assert widget.detail_stack.currentWidget() is widget.empty_view

    # Vérification BDD : étape 1 appliquée, étapes 2 et 3 rejetées
    assert StagedPatchRegistry.get_patch(p1.patch_id).status == "applied"
    assert StagedPatchRegistry.get_patch(p2.patch_id).status == "rejected"
    assert StagedPatchRegistry.get_patch(p3.patch_id).status == "rejected"


def test_mcp_garde_fou_bundle_apply_all(qtbot) -> None:
    """Vérifie l'action 'Tout valider le bloc' en une transaction atomique."""
    d1 = f"Deck_All1_{uuid.uuid4().hex[:6]}"
    d2 = f"Deck_All2_{uuid.uuid4().hex[:6]}"
    bundle_id = StagedPatchRegistry.begin_bundle(title="Bundle Tout Valider")
    StagedPatchRegistry.create_patch(patch_type="deck_create", diff_payload={"deck_name": d1})
    StagedPatchRegistry.create_patch(patch_type="deck_create", diff_payload={"deck_name": d2})
    StagedPatchRegistry.commit_bundle(bundle_id)

    widget = MCPGardeFouWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.reload_pending_patches()

    assert widget.count() == 2
    widget.btn_apply_bundle_all.click()

    assert widget.count() == 0
    assert DeckModel.get_or_none(DeckModel.name == d1) is not None
    assert DeckModel.get_or_none(DeckModel.name == d2) is not None


def test_mcp_garde_fou_direct_edit_deck_create(qtbot) -> None:
    """Vérifie que la retouche du nom de paquet dans l'IHM est synchronisée et appliquée en base."""
    d_initial = f"Deck_Orig_{uuid.uuid4().hex[:6]}"
    d_retouche = f"Deck_Retouche_{uuid.uuid4().hex[:6]}"

    StagedPatchRegistry.create_patch(
        patch_type="deck_create",
        diff_payload={"deck_name": d_initial, "title": "Créer paquet"},
    )

    widget = MCPGardeFouWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.reload_pending_patches()

    assert widget.polymorphic_stack.currentIndex() == 1
    # Modification directe dans l'éditeur de nom de paquet
    widget.deck_view.deck_name_input.setText(d_retouche)

    widget.btn_apply.click()

    assert widget.count() == 0
    assert DeckModel.get_or_none(DeckModel.name == d_retouche) is not None
    assert DeckModel.get_or_none(DeckModel.name == d_initial) is None


def test_mcp_garde_fou_direct_edit_set_tags(qtbot, sample_note) -> None:
    """Vérifie que la retouche des tags dans l'IHM est synchronisée et appliquée."""
    StagedPatchRegistry.create_patch(
        patch_type="set_tags",
        diff_payload={
            "title": "Ajout tags",
            "note_ids": [sample_note.id],
            "tags_added": ["tag_a"],
        },
    )

    widget = MCPGardeFouWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.reload_pending_patches()

    assert widget.polymorphic_stack.currentIndex() == 2
    # Retouche utilisateur : ajoute tag_b
    widget.tag_view.tags_input.setText("tag_a, tag_b")

    widget.btn_apply.click()

    assert widget.count() == 0
    reloaded_note = NoteModel.get_by_id(sample_note.id)
    assert "tag_a" in reloaded_note.tags
    assert "tag_b" in reloaded_note.tags


def test_mcp_garde_fou_deck_rename(qtbot) -> None:
    """Vérifie la visualisation et validation d'un renommage de paquet."""
    old_name = f"Deck_Old_{uuid.uuid4().hex[:6]}"
    new_name = f"Deck_New_{uuid.uuid4().hex[:6]}"
    deck = DeckModel.create(name=old_name)

    StagedPatchRegistry.create_patch(
        patch_type="deck_rename",
        target_id=deck.id,
        diff_payload={"old_name": old_name, "new_name": new_name, "title": "Renommer deck"},
    )

    widget = MCPGardeFouWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.reload_pending_patches()

    assert widget.polymorphic_stack.currentIndex() == 1
    assert widget.deck_view.get_deck_name() == new_name

    widget.btn_apply.click()

    assert widget.count() == 0
    reloaded_deck = DeckModel.get_by_id(deck.id)
    assert reloaded_deck.name == new_name


def test_mcp_garde_fou_deletion_impact_and_apply(qtbot, sample_note) -> None:
    """Vérifie la vue d'avertissement de suppression et son application."""
    StagedPatchRegistry.create_patch(
        patch_type="card_delete",
        target_id=sample_note.id,
        diff_payload={"title": "Supprimer note test", "note_ids": [sample_note.id], "reason": "Test motif"},
    )

    widget = MCPGardeFouWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.reload_pending_patches()

    assert widget.polymorphic_stack.currentIndex() == 3
    assert "Test motif" in widget.deletion_view.get_reason()

    widget.btn_apply.click()

    assert widget.count() == 0
    assert NoteModel.get_or_none(NoteModel.id == sample_note.id) is None
