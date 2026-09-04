"""
Tests unitaires PySide6 / pytest-qt pour la vue d'Édition avec Progressive Disclosure,
navigation compacte par ruban, IntelliSense et nettoyage des balises HTML.
"""

import json
import uuid

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent

from ankiforge.database.models import DeckModel, NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.ui.views.edition_view import EditionView, format_tags_display, strip_html_tags
from ankiforge.ui.widgets.editor_toolbar_widget import EditorToolbarWidget
from ankiforge.ui.widgets.note_editor_widget import (
    NoteFieldEditorWidget,
    NoteFieldTextEdit,
)


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


@pytest.mark.ui
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


@pytest.mark.ui
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


@pytest.mark.ui
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


@pytest.mark.ui
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


@pytest.mark.ui
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


@pytest.mark.ui
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
