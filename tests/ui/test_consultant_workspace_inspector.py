"""
Tests UI PySide6 pour WorkspaceInspectorWidget avec Garde-Fou, Patch Queue, Direct Edit et InlineDiffCardWidget.
"""

import json
import uuid

from PySide6.QtWidgets import QTextEdit

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.ui.views.consultant_view.widgets.inline_diff_card_widget import InlineDiffCardWidget
from ankiforge.ui.views.consultant_view.widgets.mention_completer import MentionCompleter
from ankiforge.ui.views.consultant_view.widgets.workspace_inspector_widget import WorkspaceInspectorWidget


def test_workspace_inspector_widget_init(qtbot):
    widget = WorkspaceInspectorWidget()
    qtbot.addWidget(widget)

    assert widget.status_badge.text() == "En veille"
    assert not widget.btn_apply.isEnabled()
    assert not widget.btn_reject.isEnabled()
    assert not widget.btn_copy_patch.isEnabled()


def test_workspace_inspector_update_diff_and_apply_garde_fou(qtbot):
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"NT_{uid}", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    note = NoteModel.create(guid=f"g_{uid}", note_type=nt)
    NoteVersionModel.create(note=note, version_number=1, content='{"Front": "Old text"}', is_active=True)

    widget = WorkspaceInspectorWidget()
    qtbot.addWidget(widget)

    # 1. Mise à jour de la vue diff avec Garde-Fou
    widget.update_diff_view(
        title="Refactor Note",
        original_text='{"Front": "Old text"}',
        modified_text='{"Front": "New refactored text"}',
        patch_type="card",
        metadata={"note_id": note.id},
    )

    assert "En attente" in widget.status_badge.text()
    assert widget.btn_apply.isEnabled()
    assert widget.btn_reject.isEnabled()
    assert widget.btn_copy_patch.isEnabled()

    # 2. Clic sur appliquer (Validation Garde-Fou)
    with qtbot.waitSignal(widget.action_applied, timeout=1000):
        widget.btn_apply.click()

    assert "Appliqué en BDD" in widget.status_badge.text()

    # Vérification que la BDD a bien été modifiée après confirmation
    v_active = NoteVersionModel.get(note=note, is_active=True)
    assert "New refactored text" in v_active.content


def test_workspace_inspector_direct_edit(qtbot):
    """Vérifie que l'édition directe dans le champ texte est prise en compte lors de l'application."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"NT_Edit_{uid}", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    note = NoteModel.create(guid=f"g_edit_{uid}", note_type=nt)
    NoteVersionModel.create(note=note, version_number=1, content='{"Front": "Old text"}', is_active=True)

    widget = WorkspaceInspectorWidget()
    qtbot.addWidget(widget)

    widget.update_diff_view(
        title="Refactor Note",
        original_text={"Front": "Old text"},
        modified_text={"Front": "AI text"},
        patch_type="card",
        metadata={"note_id": note.id},
    )

    # Modification directe par l'utilisateur
    widget.direct_edit.setPlainText('{"Front": "User Manually Edited Text"}')

    with qtbot.waitSignal(widget.action_applied, timeout=1000):
        widget.btn_apply.click()

    v_active = NoteVersionModel.get(note=note, is_active=True)
    assert "User Manually Edited Text" in v_active.content


def test_workspace_inspector_patch_queue_batch(qtbot):
    """Vérifie la file d'attente de propositions et l'application par lot."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"NT_Queue_{uid}", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    note1 = NoteModel.create(guid=f"g_q1_{uid}", note_type=nt)
    NoteVersionModel.create(note=note1, version_number=1, content='{"Front": "Card 1"}', is_active=True)
    note2 = NoteModel.create(guid=f"g_q2_{uid}", note_type=nt)
    NoteVersionModel.create(note=note2, version_number=1, content='{"Front": "Card 2"}', is_active=True)

    widget = WorkspaceInspectorWidget()
    qtbot.addWidget(widget)

    # Ajouter 2 propositions à la file
    widget.add_patch_to_queue({"title": "Patch 1", "type": "card", "original": "Card 1", "modified": {"Front": "Card 1 Updated"}, "note_id": note1.id})
    widget.add_patch_to_queue({"title": "Patch 2", "type": "card", "original": "Card 2", "modified": {"Front": "Card 2 Updated"}, "note_id": note2.id})

    assert len(widget._patch_queue) == 2
    assert not widget.queue_bar.isHidden()

    # Clic sur tout appliquer
    with qtbot.waitSignal(widget.action_applied, timeout=1000):
        widget.btn_apply_all.click()

    assert "modifications appliquées" in widget.status_badge.text().lower()
    v1 = NoteVersionModel.get(note=note1, is_active=True)
    v2 = NoteVersionModel.get(note=note2, is_active=True)
    assert "Card 1 Updated" in v1.content
    assert "Card 2 Updated" in v2.content


def test_inline_diff_card_widget(qtbot):
    """Vérifie le fonctionnement de la carte de diff inline."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"NT_Inline_{uid}", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    note = NoteModel.create(guid=f"g_inl_{uid}", note_type=nt)
    NoteVersionModel.create(note=note, version_number=1, content='{"Front": "Original"}', is_active=True)

    patch = {
        "title": "Inline Patch",
        "type": "card",
        "note_id": note.id,
        "original": {"Front": "Original"},
        "modified": {"Front": "Refactored Inline"},
    }

    card = InlineDiffCardWidget(patch)
    qtbot.addWidget(card)

    assert "En attente" in card.status_badge.text()
    with qtbot.waitSignal(card.applied, timeout=1000):
        card.btn_apply.click()

    assert "Appliqué en BDD" in card.status_badge.text()
    v = NoteVersionModel.get(note=note, is_active=True)
    assert "Refactored Inline" in v.content

    # Annulation 1-clic (Revert)
    with qtbot.waitSignal(card.reverted, timeout=1000):
        card.btn_apply.click()

    assert "Annulé" in card.status_badge.text()
    v_rev = NoteVersionModel.get(note=note, is_active=True)
    assert "Original" in v_rev.content


def test_workspace_inspector_revert(qtbot):
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"NT_Rev_{uid}", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    note = NoteModel.create(guid=f"g_rev_{uid}", note_type=nt)
    NoteVersionModel.create(note=note, version_number=1, content='{"Front": "Original Workspace"}', is_active=True)

    widget = WorkspaceInspectorWidget()
    qtbot.addWidget(widget)

    widget.update_diff_view(
        title="Refactor Note Revert",
        original_text='{"Front": "Original Workspace"}',
        modified_text='{"Front": "Modified Workspace"}',
        patch_type="card",
        metadata={"note_id": note.id},
    )

    with qtbot.waitSignal(widget.action_applied, timeout=1000):
        widget.btn_apply.click()

    assert not widget.btn_revert.isHidden()
    v_applied = NoteVersionModel.get(note=note, is_active=True)
    assert "Modified Workspace" in v_applied.content

    with qtbot.waitSignal(widget.action_reverted, timeout=1000):
        widget.btn_revert.click()

    assert "Annulé en BDD" in widget.status_badge.text()
    v_reverted = NoteVersionModel.get(note=note, is_active=True)
    assert "Original Workspace" in v_reverted.content


def test_workspace_inspector_card_preview_tab(qtbot):
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(
        name=f"NT_Prev_{uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "C1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]',
        css_style=".card { color: blue; }",
    )
    note = NoteModel.create(guid=f"g_prev_{uid}", note_type=nt)

    widget = WorkspaceInspectorWidget()
    qtbot.addWidget(widget)

    assert hasattr(widget, "card_preview")

    widget.update_diff_view(
        title="Preview Test",
        original_text='{"Front": "Q Old"}',
        modified_text='{"Front": "Q New", "Back": "A New"}',
        patch_type="card",
        metadata={"note_id": note.id},
    )

    assert widget.card_preview.current_fields.get("Front") == "Q New"
    assert widget.card_preview.current_fields.get("Back") == "A New"


def test_mention_completer(qtbot):
    uid = uuid.uuid4().hex[:6]
    DeckModel.create(name=f"DeckMention_{uid}")
    DocumentModel.create(title=f"DocMention_{uid}", file_path=f"/{uid}.pdf", format="pdf")

    editor = QTextEdit()
    qtbot.addWidget(editor)

    completer = MentionCompleter(editor)
    completer.update_completions("Deck")

    model = completer.model()
    items = [model.data(model.index(i, 0)) for i in range(model.rowCount())]
    assert any(f"@deck:DeckMention_{uid}" in item for item in items)


def test_inline_diff_card_field_diff_and_direct_editing(qtbot):
    """Vérifie la comparaison mot à mot par champ et la prise en compte de l'édition directe avant application."""
    from ankiforge.ui.views.consultant_view.widgets.inline_diff_card_widget import (
        FieldDiffWidget,
        compute_word_diff_html,
    )

    # 1. Vérification de l'algorithme word-level diff
    diff_html = compute_word_diff_html("Ancienne question longue", "Nouvelle question")
    assert "line-through" in diff_html
    assert "Ancienne" in diff_html
    assert "Nouvelle" in diff_html

    # 2. Création de note en BDD
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"NT_Diff_{uid}", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    note = NoteModel.create(guid=f"g_diff_{uid}", note_type=nt)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Front": "Capitale de la France", "Back": "Paris est la capitale"}),
        is_active=True,
    )

    patch = {
        "status": "staged_diff",
        "type": "card",
        "note_id": note.id,
        "title": "Refactorisation Ciblée",
        "original": {"Front": "Capitale de la France", "Back": "Paris est la capitale"},
        "modified": {"Front": "Capitale de la France ?", "Back": "Paris"},
        "explanation": "Formulation plus directe et concise.",
    }

    card = InlineDiffCardWidget(patch)
    qtbot.addWidget(card)

    assert len(card.field_widgets) == 2
    front_fw = card.field_widgets[0]
    back_fw = card.field_widgets[1]
    assert isinstance(front_fw, FieldDiffWidget)
    assert front_fw.field_name == "Front"

    # Bascule en mode édition directe sur le champ 'Back'
    assert not back_fw._is_editing
    back_fw._toggle_edit_mode()
    assert back_fw._is_editing
    assert back_fw.stack.currentIndex() == 2

    # Modification manuelle par l'utilisateur
    back_fw.editor.setPlainText("Paris (Île-de-France)")

    # Application en BDD
    with qtbot.waitSignal(card.applied, timeout=1000):
        card.btn_apply.click()

    # Vérification que la retouche de l'utilisateur a bien été persistée
    active_v = NoteVersionModel.get(note=note, is_active=True)
    saved_data = json.loads(active_v.content)
    assert saved_data["Back"] == "Paris (Île-de-France)"
    assert saved_data["Front"] == "Capitale de la France ?"


def test_inline_diff_card_split_partial_selection(qtbot):
    """Vérifie la scission atomique avec sélection partielle (décochage d'une carte fille)."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"DeckSplit_{uid}")
    nt = NoteTypeModel.create(name=f"NT_Split_{uid}", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    note = NoteModel.create(guid=f"g_sp_{uid}", note_type=nt)
    CardModel.create(note=note, deck=deck, template_index=0)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Front": "Question Complexe", "Back": "Partie 1 et Partie 2 et Partie 3"}),
        is_active=True,
    )

    patch = {
        "status": "staged_diff",
        "type": "split",
        "note_id": note.id,
        "title": "Scission en 3 cartes",
        "original": {"Front": "Question Complexe", "Back": "Partie 1 et 2 et 3"},
        "modified": [
            {"Front": "Question A", "Back": "Réponse A"},
            {"Front": "Question B", "Back": "Réponse B"},
            {"Front": "Question C", "Back": "Réponse C"},
        ],
        "explanation": "Découpage de 3 concepts indépendants.",
    }

    card = InlineDiffCardWidget(patch)
    qtbot.addWidget(card)

    assert len(card.split_widgets) == 3

    # L'utilisateur décoche la 2ème carte (ne veut créer que A et C)
    card.split_widgets[1].chk_include.setChecked(False)

    # Et retouche la question de la 1ère carte
    card.split_widgets[0].field_editors["Front"].setPlainText("Question A Retouchée")

    with qtbot.waitSignal(card.applied, timeout=1000):
        card.btn_apply.click()

    # La note d'origine doit être archivée
    note = NoteModel.get_by_id(note.id)
    assert note.status == "archived"

    # Vérification que seules 2 notes ont été créées
    created_notes = list(NoteModel.select().where(NoteModel.guid != note.guid, NoteModel.note_type == nt))
    assert len(created_notes) == 2

    # Vérification que le texte retouché de A a bien été pris en compte
    contents = [NoteVersionModel.get(note=n, is_active=True).content for n in created_notes]
    assert any("Question A Retouchée" in c for c in contents)
    assert not any("Question B" in c for c in contents)


def test_inline_diff_card_view_modes_toggle(qtbot):
    """Vérifie la bascule entre la vue unifiée et la vue côte à côte ainsi que la synchronisation."""
    from PySide6.QtCore import QSettings

    QSettings("AnkiForge", "AnkiForge").setValue("consultant/diff_view_mode", "unified")

    patch = {
        "title": "Bascule de Mode",
        "type": "card",
        "original": {"Front": "Question Longue", "Back": "Reponse Detaillee"},
        "modified": {"Front": "Question Courte", "Back": "Reponse"},
    }

    card = InlineDiffCardWidget(patch)
    qtbot.addWidget(card)

    # 1. Mode par défaut : Unifié
    assert card.current_view_mode == "unified"
    assert card.btn_view_unified.property("active") is True
    assert card.btn_view_split.property("active") is False
    assert card.field_widgets[0].stack.currentIndex() == 0

    # 2. Clic sur le bouton Vue Côte à côte
    card.btn_view_split.click()
    assert card.current_view_mode == "split"
    assert card.btn_view_split.property("active") is True
    assert card.btn_view_unified.property("active") is False
    assert card.field_widgets[0].stack.currentIndex() == 1

    # Modification dans la colonne droite de la vue côte à côte
    fw = card.field_widgets[0]
    fw.sbs_editor.setPlainText("Question Super Courte")
    assert fw.get_current_value() == "Question Super Courte"

    # 3. Retour en Vue Unifiée : le diff doit refléter le nouveau texte
    card.btn_view_unified.click()
    assert card.current_view_mode == "unified"
    assert fw.stack.currentIndex() == 0
    assert "Super Courte" in fw.diff_label.text()


def test_inline_diff_card_open_editor_requested(qtbot):
    """Vérifie que le clic sur 'Ouvrir dans l'Éditeur' émet open_editor_requested avec le note_id."""
    patch = {
        "title": "Navigation Éditeur",
        "type": "card",
        "note_id": 99,
        "original": {"Front": "Q", "Back": "A"},
        "modified": {"Front": "Q2", "Back": "A2"},
    }

    card = InlineDiffCardWidget(patch)
    qtbot.addWidget(card)

    with qtbot.waitSignal(card.open_editor_requested, timeout=1000) as blocker:
        card.btn_open_editor.click()

    assert blocker.args == [99]


def test_inline_diff_card_mode_persistence_and_total_unification(qtbot):
    """Vérifie l'unification totale sans ratures par défaut, le toggle des ratures et la persistance inter-cartes."""
    from PySide6.QtCore import QSettings

    QSettings("AnkiForge", "AnkiForge").setValue("consultant/diff_view_mode", "unified")

    patch1 = {
        "title": "Carte 1",
        "type": "card",
        "original": {"Front": "Ancienne Question Longue", "Back": "Reponse"},
        "modified": {"Front": "Question Courte", "Back": "Reponse"},
    }
    patch2 = {
        "title": "Carte 2",
        "type": "card",
        "original": {"Front": "Old", "Back": "Old"},
        "modified": {"Front": "New", "Back": "New"},
    }

    card1 = InlineDiffCardWidget(patch1)
    card2 = InlineDiffCardWidget(patch2)
    qtbot.addWidget(card1)
    qtbot.addWidget(card2)

    # 1. Unification totale par défaut (aucun mot supprimé barré en rouge visible)
    fw1 = card1.field_widgets[0]
    assert "line-through" not in fw1.diff_label.text()
    assert "Ancienne" not in fw1.diff_label.text()  # Mot supprimé masqué en unification totale
    assert "Courte" in fw1.diff_label.text()

    # 2. Clic sur le bouton [ 🔍 Ratures ] : les suppressions apparaissent
    fw1.btn_toggle_deletions.click()
    assert fw1.show_deletions is True
    assert "line-through" in fw1.diff_label.text()
    assert "Ancienne" in fw1.diff_label.text()

    # Clic à nouveau : retour à l'unification totale
    fw1.btn_toggle_deletions.click()
    assert fw1.show_deletions is False
    assert "line-through" not in fw1.diff_label.text()
    assert "Ancienne" not in fw1.diff_label.text()

    # 3. Persistance et synchronisation inter-cartes
    card1.btn_view_split.click()
    assert card1.current_view_mode == "split"
    assert card2.current_view_mode == "split"
    assert QSettings("AnkiForge", "AnkiForge").value("consultant/diff_view_mode") == "split"

    # Remettre en mode unifié
    card2.btn_view_unified.click()
    assert card1.current_view_mode == "unified"
    assert card2.current_view_mode == "unified"
    assert QSettings("AnkiForge", "AnkiForge").value("consultant/diff_view_mode") == "unified"


def test_inline_diff_card_already_applied_db_detection(qtbot):
    """Vérifie que si la note en BDD a déjà la valeur proposée, la carte s'affiche comme déjà appliquée sans diff résiduel."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"NT_Cache_{uid}", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    note = NoteModel.create(guid=f"g_cache_{uid}", note_type=nt)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Front": "Version Déjà Unifiée", "Back": "Réponse"}),
        is_active=True,
    )

    patch = {
        "title": "Déjà appliqué",
        "type": "card",
        "note_id": note.id,
        "original": {"Front": "Vieille Version Obsolète", "Back": "Réponse"},
        "modified": {"Front": "Version Déjà Unifiée", "Back": "Réponse"},
    }

    card = InlineDiffCardWidget(patch)
    qtbot.addWidget(card)

    # Détection automatique en base : la carte est marquée comme appliquée
    assert card.is_applied is True
    assert "Appliqué en BDD" in card.status_badge.text()
    # En unification totale sans ratures
    assert "line-through" not in card.field_widgets[0].diff_label.text()
    assert "Version Déjà Unifiée" in card.field_widgets[0].diff_label.text()
