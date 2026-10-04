"""
Tests unitaires PySide6 / pytest-qt pour la vue d'Édition avec Progressive Disclosure,
navigation compacte par ruban, IntelliSense et nettoyage des balises HTML.
"""

import json
import uuid
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QMessageBox

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.ui.views.edition_view import EditionView, format_tags_display, strip_html_tags
from ankiforge.ui.widgets.editor_toolbar_widget import EditorToolbarWidget
from ankiforge.ui.widgets.note_editor_widget import (
    NoteFieldEditorWidget,
    NoteFieldTextEdit,
)

pytestmark = pytest.mark.ui


def test_strip_html_tags_and_format_tags():
    """Vérifie le nettoyage du HTML brut et des tags vides."""
    assert strip_html_tags("<b>Hello</b> <code>world</code>") == "Hello world"
    assert strip_html_tags("<pre><code>x = runif(n)</code></pre>") == "x = runif(n)"
    assert strip_html_tags("&lt;tag&gt; &amp; &nbsp;") == "<tag> &"
    assert strip_html_tags("") == ""

    assert format_tags_display("[]") == ""
    assert format_tags_display([]) == ""
    assert format_tags_display(None) == ""
    assert format_tags_display('["r", "stats"]') == "#r  #stats"
    assert format_tags_display(["medecine", "cardio"]) == "#medecine  #cardio"


def test_edition_view_progressive_disclosure_and_navigation(qtbot, mock_db):
    """Vérifie la disposition verticale avec Progressive Disclosure (repliement en ruban) et la navigation."""
    uid1 = uuid.uuid4().hex[:6]
    uid2 = uuid.uuid4().hex[:6]
    templates_json = '[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]'
    nt = NoteTypeModel.create(name=f"Model {uid1}", fields_schema='["Front", "Back"]', templates=templates_json, css_style="")
    n1 = NoteModel.create(guid=f"g1_{uid1}", note_type=nt, tags='["tag1"]')
    NoteVersionModel.create(note=n1, content=json.dumps({"Front": "Question 1", "Back": "Reponse 1"}), is_active=True)
    n2 = NoteModel.create(guid=f"g2_{uid2}", note_type=nt, tags='["tag2"]')
    NoteVersionModel.create(note=n2, content=json.dumps({"Front": "Question 2", "Back": "Reponse 2"}), is_active=True)

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    assert view.main_splitter.count() == 2
    assert not view.table_box.isHidden()
    assert view.nav_ribbon.isHidden()
    assert view.editor_stack.currentIndex() == 0  # Placeholder

    # Sélection de la première carte
    view.select_note_by_id(n1.id)
    assert view._current_note is not None
    assert view._current_note.id == n1.id
    assert view.editor_stack.currentIndex() == 1

    # Repliement en ruban de navigation (Progressive Disclosure)
    view._toggle_table_collapsed()
    assert view._table_collapsed is True
    assert view.table_box.isHidden()
    assert not view.nav_ribbon.isHidden()
    assert "Carte #" in view.lbl_card_ribbon_info.text()
    assert "Question 1" in view.lbl_card_ribbon_info.text()

    # Navigation vers la carte suivante via le ruban
    view._select_next_card()
    assert view._current_note.id == n2.id
    assert "Question 2" in view.lbl_card_ribbon_info.text()

    # Navigation vers la carte précédente via le ruban
    view._select_previous_card()
    assert view._current_note.id == n1.id
    assert "Question 1" in view.lbl_card_ribbon_info.text()

    # Dépliement du tableau
    view._toggle_table_collapsed()
    assert view._table_collapsed is False
    assert not view.table_box.isHidden()
    assert view.nav_ribbon.isHidden()


def test_edition_view_preview_toggle_and_modes(qtbot, mock_db):
    """Vérifie le masquage et l'affichage du volet de prévisualisation dans l'éditeur bas."""
    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)

    assert not view.preview_container.isHidden()

    # Toggle preview
    view._toggle_preview_pane()
    assert view.preview_container.isHidden()
    assert view._preview_visible is False

    view._toggle_preview_pane()
    assert not view.preview_container.isHidden()
    assert view._preview_visible is True

    # Mode fields_only / preview_only / split
    view.set_view_mode("fields_only")
    assert view.preview_container.isHidden()
    assert not view.fields_scroll_area.isHidden()

    view.set_view_mode("preview_only")
    assert not view.preview_container.isHidden()
    assert view.fields_scroll_area.isHidden()

    view.set_view_mode("split")
    assert not view.preview_container.isHidden()
    assert not view.fields_scroll_area.isHidden()


def test_note_field_editor_and_highlighter(qtbot):
    """Vérifie le widget de champ NoteFieldEditorWidget, le repliage et la coloration syntaxique."""
    widget = NoteFieldEditorWidget("Recto", "<b>Hello</b> $\\alpha$ {{c1::test}}", is_first=True)
    qtbot.addWidget(widget)

    assert widget.get_text() == "<b>Hello</b> $\\alpha$ {{c1::test}}"
    assert widget.btn_header.text().startswith("▼")

    # Test du repliage / dépliage
    widget.toggle_collapsed()
    assert widget.btn_header.text().startswith("▶")
    assert widget.editor.isHidden()

    widget.toggle_collapsed()
    assert widget.btn_header.text().startswith("▼")
    assert not widget.editor.isHidden()

    # Test de mise à jour du texte
    widget.set_text("Nouveau contenu")
    assert widget.get_text() == "Nouveau contenu"


def test_katex_completer_and_auto_closing_pairs(qtbot):
    """Vérifie l'IntelliSense (LaTeX, HTML, Modèle) et la fermeture automatique des délimiteurs."""
    editor = NoteFieldTextEdit()
    qtbot.addWidget(editor)
    editor.set_known_fields(["Front", "Back", "Exemple"])

    completer = editor.completer

    # 1. Préfixe LaTeX
    completer.update_model_for_prefix("\\")
    assert any(r"\frac" in item for item in completer.list_model.stringList())
    assert any(r"\alpha" in item for item in completer.list_model.stringList())

    # 2. Préfixe HTML
    completer.update_model_for_prefix("<")
    assert any("<b>" in item for item in completer.list_model.stringList())
    assert any("<code>" in item for item in completer.list_model.stringList())

    # 3. Préfixe Champs Modèle
    completer.update_model_for_prefix("{")
    assert any("{{Front}}" in item for item in completer.list_model.stringList())
    assert any("{{Back}}" in item for item in completer.list_model.stringList())

    # 4. Auto-fermeture des délimiteurs
    editor.setPlainText("")
    event_paren = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_ParenLeft, Qt.KeyboardModifier.NoModifier, "(")
    editor.keyPressEvent(event_paren)
    assert editor.toPlainText() == "()"

    editor.setPlainText("")
    event_brace = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_BraceLeft, Qt.KeyboardModifier.NoModifier, "{")
    editor.keyPressEvent(event_brace)
    assert editor.toPlainText() == "{}"

    editor.setPlainText("")
    event_dollar = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Dollar, Qt.KeyboardModifier.NoModifier, "$")
    editor.keyPressEvent(event_dollar)
    assert editor.toPlainText() == "$$"


def test_editor_toolbar_actions_and_custom_registration(qtbot):
    """Vérifie l'exécution des actions de la barre d'outils et l'enregistrement d'une action personnalisée."""
    toolbar = EditorToolbarWidget()
    qtbot.addWidget(toolbar)

    triggered_actions = []
    toolbar.action_triggered.connect(lambda act: triggered_actions.append(act))

    assert "bold" in toolbar._actions
    assert "math" in toolbar._actions
    assert "cloze" in toolbar._actions

    toolbar._actions["bold"].callback()
    assert "bold" in triggered_actions

    # Test d'ajout d'action personnalisée
    custom_called = []
    toolbar.register_action(
        action_id="custom_stamp",
        icon_name="stamp",
        label="Tampon",
        tooltip="Insère un tampon",
        shortcut="Ctrl+Alt+T",
        callback=lambda: custom_called.append(True),
    )

    assert "custom_stamp" in toolbar._actions
    toolbar._actions["custom_stamp"].callback()
    assert len(custom_called) == 1

    toolbar.remove_action("custom_stamp")
    assert "custom_stamp" not in toolbar._actions


def test_edition_view_card_selection_smart_cloze_and_saving(qtbot, mock_db):
    """Vérifie la sélection de carte, l'enrichissement par la toolbar avec Cloze incrémental et la sauvegarde épurée."""
    uid = uuid.uuid4().hex[:6]
    _ = DeckModel.create(name=f"Deck Cardio {uid}")
    nt = NoteTypeModel.create(
        name=f"Cloze Cardio {uid}",
        fields_schema='["Texte", "Extra"]',
        templates='[{"name": "Cloze 1", "qfmt": "{{cloze:Texte}}", "afmt": "{{cloze:Texte}}<br>{{Extra}}"}]',
        css_style=".card {}",
    )
    note = NoteModel.create(guid=f"guid_{uid}", note_type=nt, tags="medecine")
    NoteVersionModel.create(note=note, content=json.dumps({"Texte": "Le cœur possède 4 cavités.", "Extra": "Anatomie"}), is_active=True)

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # Sélection de la note
    view.select_note_by_id(note.id)
    assert view._current_note is not None
    assert view._current_note.id == note.id
    assert view.editor_stack.currentIndex() == 1
    assert "Texte" in view.dynamic_field_widgets
    assert "Extra" in view.dynamic_field_widgets

    # Test Cloze intelligent : le premier trou sera {{c1::...}}
    texte_editor = view.dynamic_field_widgets["Texte"].editor
    texte_editor.setFocus()
    cursor = texte_editor.textCursor()
    cursor.select(cursor.SelectionType.WordUnderCursor)
    texte_editor.setTextCursor(cursor)

    view._handle_editor_action("cloze")
    assert "{{c1::" in texte_editor.toPlainText()

    # Deuxième trou cloze -> doit automatiquement proposer c2
    cursor = texte_editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    texte_editor.setTextCursor(cursor)
    view._handle_editor_action("cloze")
    assert "{{c2::" in texte_editor.toPlainText()

    # Sauvegarde
    view._save_card()
    assert not view.is_dirty()

    latest_v = NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.desc()).first()
    assert latest_v is not None
    assert latest_v.version_number >= 2
    assert "c1::" in latest_v.content


def test_edition_view_consult_ai_button(qtbot):
    """Vérifie que le clic sur 'Consulter l'IA' émet l'événement OpenConsultantRequestedEvent."""
    from ankiforge.utils.event_bus import OpenConsultantRequestedEvent, event_bus

    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"NT_Cons_{uid}", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    note = NoteModel.create(guid=f"g_cons_{uid}", note_type=nt)
    NoteVersionModel.create(note=note, version_number=1, content='{"Front": "Card to consult"}', is_active=True)

    view = EditionView()
    qtbot.addWidget(view)
    view.select_note_by_id(note.id)

    received_events = []
    event_bus.subscribe(OpenConsultantRequestedEvent, lambda e: received_events.append(e))

    view.editor_toolbar.btn_consult_ai.click()

    assert len(received_events) == 1
    assert received_events[0].context_item == f"card_{note.id}"
    assert f"#{note.id}" in received_events[0].initial_prompt


def test_edition_view_model_filter_modal(qtbot: Any, mock_db: Any) -> None:
    """Vérifie l'ouverture de ModelSelectWindow depuis la barre de filtres et l'application du filtre."""
    from ankiforge.ui.components.model_select_window import ModelSelectWindow

    uid = uuid.uuid4().hex[:6]
    nt1 = NoteTypeModel.create(name=f"ModelA {uid}", fields_schema='["Front", "Back"]')
    nt2 = NoteTypeModel.create(name=f"ModelB {uid}", fields_schema='["Text", "Extra"]')

    NoteModel.create(guid=f"na_{uid}", note_type=nt1)
    NoteModel.create(guid=f"nb_{uid}", note_type=nt2)

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # Clic sur le bouton pour ouvrir la modale
    view.btn_open_model.click()
    assert view._model_modal is not None
    assert isinstance(view._model_modal, ModelSelectWindow)
    assert view._model_modal.allow_all is True

    # Sélectionner le filtre ModelA
    view._on_model_selected_from_modal(nt1.id, nt1.name)
    assert view._active_model_id == nt1.id
    assert nt1.name in view.btn_open_model.text()

    # Réinitialiser vers "Tous les modèles"
    view._on_model_selected_from_modal(-1, "Tous les modèles")
    assert view._active_model_id is None
    assert "Tous" in view.btn_open_model.text()


def test_edition_view_change_note_model_modal(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le changement de modèle d'une note via la modale dans l'éditeur."""
    from ankiforge.ui.components.model_select_window import ModelSelectWindow

    uid = uuid.uuid4().hex[:6]
    nt_old = NoteTypeModel.create(name=f"OldModel {uid}", fields_schema='["Front", "Back"]')
    nt_new = NoteTypeModel.create(name=f"NewModel {uid}", fields_schema='["Question", "Answer", "Notes"]')

    note = NoteModel.create(guid=f"chg_{uid}", note_type=nt_old)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Front": "Contenu Question", "Back": "Contenu Reponse"}),
        is_active=True,
    )

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.select_note_by_id(note.id)

    # Vérifier que les éditeurs initiaux correspondent à l'ancien modèle
    assert "Front" in view.dynamic_field_widgets
    assert "Back" in view.dynamic_field_widgets

    # Déclencher l'ouverture de la modale de changement de modèle
    view._open_change_model_modal(note)
    assert view._change_model_modal is not None
    assert isinstance(view._change_model_modal, ModelSelectWindow)
    assert view._change_model_modal.allow_all is False

    # Appliquer le nouveau modèle
    view._on_note_model_changed(note, nt_new.id, nt_new.name)

    # Vérifier que le modèle a été mis à jour en BDD
    refreshed_note = NoteModel.get_by_id(note.id)
    assert refreshed_note.note_type.id == nt_new.id
    assert refreshed_note.note_type.name == nt_new.name

    # Vérifier le remappage des champs dans les widgets de l'éditeur
    assert "Question" in view.dynamic_field_widgets
    assert "Answer" in view.dynamic_field_widgets
    assert "Notes" in view.dynamic_field_widgets
    assert view.dynamic_field_widgets["Question"].get_text() == "Contenu Question"
    assert view.dynamic_field_widgets["Answer"].get_text() == "Contenu Reponse"


def test_edition_view_move_card_to_deck(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le déplacement d'une note vers un autre paquet via la modale."""
    uid = uuid.uuid4().hex[:6]
    deck_old = DeckModel.create(name=f"Deck_Old_{uid}")
    deck_new = DeckModel.create(name=f"Deck_New_{uid}")

    nt = NoteTypeModel.create(name=f"NT_{uid}", fields_schema='["Front", "Back"]')
    note = NoteModel.create(guid=f"g_{uid}", note_type=nt)
    card = CardModel.create(note=note, deck=deck_old, template_index=0)
    NoteVersionModel.create(note=note, version_number=1, content='{"Front": "Q", "Back": "A"}', is_active=True)

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.select_note_by_id(note.id)

    # Déclencher le déplacement
    view._open_move_to_deck_modal(fallback_note_id=note.id)
    assert view._move_deck_modal is not None
    assert view._move_deck_modal.allow_all is False

    # Appliquer le déplacement
    view._on_cards_moved_to_deck(deck_new.id, deck_new.name)

    # Vérifier que CardModel a été mis à jour
    refreshed_card = CardModel.get_by_id(card.id)
    assert refreshed_card.deck.id == deck_new.id
    assert refreshed_card.deck.name == deck_new.name


def test_edition_view_batch_move_cards_to_deck(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le déplacement par lot de plusieurs notes cochées vers un paquet."""
    uid = uuid.uuid4().hex[:6]
    deck_old = DeckModel.create(name=f"Batch_Old_{uid}")
    deck_new = DeckModel.create(name=f"Batch_New_{uid}")

    nt = NoteTypeModel.create(name=f"NT_Batch_{uid}", fields_schema='["Front", "Back"]')
    note1 = NoteModel.create(guid=f"g1_{uid}", note_type=nt)
    note2 = NoteModel.create(guid=f"g2_{uid}", note_type=nt)
    card1 = CardModel.create(note=note1, deck=deck_old, template_index=0)
    card2 = CardModel.create(note=note2, deck=deck_old, template_index=0)
    NoteVersionModel.create(note=note1, version_number=1, content='{"Front": "Q1", "Back": "A1"}', is_active=True)
    NoteVersionModel.create(note=note2, version_number=1, content='{"Front": "Q2", "Back": "A2"}', is_active=True)

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # Cocher les deux notes
    view.note_table_model._checked_note_ids.add(note1.id)
    view.note_table_model._checked_note_ids.add(note2.id)

    view._open_move_to_deck_modal()
    assert set(view._move_target_note_ids) == {note1.id, note2.id}

    view._on_cards_moved_to_deck(deck_new.id, deck_new.name)

    assert CardModel.get_by_id(card1.id).deck.id == deck_new.id
    assert CardModel.get_by_id(card2.id).deck.id == deck_new.id


def test_edition_view_save_card_preserves_proven_and_migrated_links(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que la sauvegarde dans EditionView ne détruit pas les liens prouvés ni migrés."""
    from ankiforge.utils.tags import build_document_tags

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours Cardio {uid}", file_type="md")
    chunk = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Cardiologie > Valvule",
        content="La valvule mitrale sépare l'atrium gauche du ventricule gauche.",
        content_hash=f"h_valv_{uid}",
    )
    deck = DeckModel.create(name=f"Deck_{uid}")
    nt = NoteTypeModel.create(name=f"NT_Cov_{uid}", fields_schema='["Front", "Back"]')

    # Note 1 : Lien prouvé (resolution="section")
    tags1 = build_document_tags(doc_id=doc.id, section_name=chunk.heading_path)
    note1 = NoteModel.create(guid=f"g_cov1_{uid}", note_type=nt, tags=json.dumps(tags1))
    CardModel.create(note=note1, deck=deck, template_index=0)
    NoteVersionModel.create(note=note1, version_number=1, content='{"Front": "Q1", "Back": "A1"}', is_active=True)
    link1 = NoteChunkLinkModel.create(note=note1, chunk=chunk, resolution="section")

    # Note 2 : Lien migré (resolution=None)
    tags2 = build_document_tags(doc_id=doc.id, section_name=chunk.heading_path)
    note2 = NoteModel.create(guid=f"g_cov2_{uid}", note_type=nt, tags=json.dumps(tags2))
    CardModel.create(note=note2, deck=deck, template_index=0)
    NoteVersionModel.create(note=note2, version_number=1, content='{"Front": "Q2", "Back": "A2"}', is_active=True)
    link2 = NoteChunkLinkModel.create(note=note2, chunk=chunk, resolution=None)

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # 1. Sauvegarde de la Note 1 : le lien prouvé doit être conservé
    view.select_note_by_id(note1.id)
    view._save_card()

    refreshed_links1 = list(NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == note1))
    assert len(refreshed_links1) == 1
    assert refreshed_links1[0].id == link1.id
    assert refreshed_links1[0].chunk_id == chunk.id
    assert refreshed_links1[0].resolution == "section"

    # 2. Sauvegarde de la Note 2 : le lien migré doit être conservé avec resolution=None
    view.select_note_by_id(note2.id)
    view._save_card()

    refreshed_links2 = list(NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == note2))
    assert len(refreshed_links2) == 1
    assert refreshed_links2[0].id == link2.id
    assert refreshed_links2[0].chunk_id == chunk.id
    assert refreshed_links2[0].resolution is None


def test_edition_view_tags_editor_inline_and_add_tag_with_spaces(qtbot, mock_db):
    """Vérifie l'éditeur inline de tags, l'ajout de tags avec espaces et leur persistance sans coupure."""
    from ankiforge.utils.tags import parse_note_tags

    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"NT_{uid}", fields_schema='["Front", "Back"]')
    note = NoteModel.create(guid=f"g_{uid}", note_type=nt, tags=json.dumps(["tag1", "doc:99"]))
    NoteVersionModel.create(note=note, version_number=1, content='{"Front": "Q", "Back": "A"}', is_active=True)

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()
    view.select_note_by_id(note.id)

    # 1. Vérification de la présence de l'éditeur inline (distinct du bouton filtre de la barre d'outils)
    assert hasattr(view, "tags_editor") and view.tags_editor is not None
    assert view.tags_editor.get_tags() == ["tag1", "doc:99"]

    # 2. Ajout d'un tag avec espaces ("médecine générale")
    view.tags_editor.input_new_tag.setText("médecine générale")
    view.tags_editor.btn_add_tag.click()

    assert "médecine générale" in view.tags_editor.get_tags()
    refreshed_note = NoteModel.get_by_id(note.id)
    # Vérification que le round-trip n'a pas découpé le tag en deux
    assert parse_note_tags(refreshed_note.tags) == ["tag1", "doc:99", "médecine générale"]


def test_edition_view_tags_editor_visual_distinction_and_reorder(qtbot, mock_db):
    """Vérifie la distinction visuelle des tags de provenance et la réorganisation."""
    from ankiforge.ui.views.edition_view.note_tags_editor import NoteTagChipWidget

    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"NT_{uid}", fields_schema='["Front", "Back"]')
    note = NoteModel.create(guid=f"g_{uid}", note_type=nt, tags=json.dumps(["section:intro", "cardiologie"]))
    NoteVersionModel.create(note=note, version_number=1, content='{"Front": "Q", "Back": "A"}', is_active=True)

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()
    view.select_note_by_id(note.id)

    editor = view.tags_editor
    assert editor is not None

    chips = [editor.chips_flow.flow_layout.itemAt(i).widget() for i in range(editor.chips_flow.flow_layout.count())]
    chip_widgets = [c for c in chips if isinstance(c, NoteTagChipWidget)]
    assert len(chip_widgets) == 2

    # section:intro est un tag de provenance
    assert chip_widgets[0].is_provenance is True
    # cardiologie est un tag ordinaire
    assert chip_widgets[1].is_provenance is False

    # Réorganisation : déplacer cardiologie vers la gauche
    editor._on_move_tag_left("cardiologie")
    assert editor.get_tags() == ["cardiologie", "section:intro"]

    refreshed_note = NoteModel.get_by_id(note.id)
    from ankiforge.utils.tags import parse_note_tags

    assert parse_note_tags(refreshed_note.tags) == ["cardiologie", "section:intro"]


def test_edition_view_tags_editor_provenance_deletion_annihilable(qtbot, mock_db, monkeypatch):
    """Vérifie que la suppression d'un tag de provenance est annulable puis effective si confirmée."""
    from ankiforge.utils.tags import build_document_tags

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours Cardio {uid}", file_type="md")
    chunk = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Cardiologie > Valvule",
        content="La valvule mitrale",
        content_hash=f"h_{uid}",
    )
    nt = NoteTypeModel.create(name=f"NT_{uid}", fields_schema='["Front", "Back"]')
    tags = build_document_tags(doc_id=doc.id, section_name=chunk.heading_path)
    note = NoteModel.create(guid=f"g_{uid}", note_type=nt, tags=json.dumps(tags))
    NoteChunkLinkModel.create(note=note, chunk=chunk, resolution="section")

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()
    view.select_note_by_id(note.id)

    editor = view.tags_editor
    assert editor is not None
    doc_tag = f"doc:{doc.id}"
    assert doc_tag in editor.get_tags()

    # 1. Annulation de la suppression : le tag et le lien doivent subsister
    monkeypatch.setattr(editor, "_confirm_provenance_removal", lambda tag: False)
    editor._on_delete_tag_requested(doc_tag)

    assert doc_tag in editor.get_tags()
    assert NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == note).count() == 1

    # 2. Confirmation de la suppression : le tag est retiré et la couverture re-synchronisée
    monkeypatch.setattr(editor, "_confirm_provenance_removal", lambda tag: True)
    editor._on_delete_tag_requested(doc_tag)

    assert doc_tag not in editor.get_tags()
    refreshed_note = NoteModel.get_by_id(note.id)
    assert doc_tag not in refreshed_note.tags
    # Le lien vers le document a été nettoyé car doc: a été retiré
    assert NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == note).count() == 0


def test_edition_view_tags_editor_regular_tag_deletion_immediate(qtbot, mock_db):
    """Vérifie que la suppression d'un tag ordinaire est immédiate sans confirmation."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"NT_{uid}", fields_schema='["Front", "Back"]')
    note = NoteModel.create(guid=f"g_{uid}", note_type=nt, tags=json.dumps(["tag_ordinaire", "autre"]))

    view = EditionView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()
    view.select_note_by_id(note.id)

    editor = view.tags_editor
    assert editor is not None

    editor._on_delete_tag_requested("tag_ordinaire")
    assert editor.get_tags() == ["autre"]

    refreshed_note = NoteModel.get_by_id(note.id)
    from ankiforge.utils.tags import parse_note_tags

    assert parse_note_tags(refreshed_note.tags) == ["autre"]


def test_edition_view_tags_editor_confirmation_box_content(qtbot, mock_db, monkeypatch):
    """Vérifie que la boîte de dialogue de confirmation nomme explicitement le lien de couverture."""
    from ankiforge.ui.views.edition_view.note_tags_editor import NoteTagsEditorWidget

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"NeuroAnatomie {uid}", file_type="md")
    chunk = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Cerveau > Cortex",
        content="Le cortex cérébral",
        content_hash=f"h_{uid}",
    )
    nt = NoteTypeModel.create(name=f"NT_{uid}", fields_schema='["Front", "Back"]')
    note = NoteModel.create(guid=f"g_{uid}", note_type=nt, tags=json.dumps([f"doc:{doc.id}"]))
    NoteChunkLinkModel.create(note=note, chunk=chunk, resolution="section")

    editor = NoteTagsEditorWidget(note=note)
    qtbot.addWidget(editor)

    captured_boxes: list[QMessageBox] = []

    def mock_exec(box_instance: QMessageBox) -> int:
        captured_boxes.append(box_instance)
        return 0

    monkeypatch.setattr(QMessageBox, "exec", mock_exec)
    editor._confirm_provenance_removal(f"doc:{doc.id}")

    assert len(captured_boxes) == 1
    box = captured_boxes[0]
    assert f"doc:{doc.id}" in box.text()
    assert f"NeuroAnatomie {uid} → Cerveau > Cortex" in box.informativeText()
