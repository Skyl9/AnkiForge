import json
import uuid
from typing import Any
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from ankiforge.database.models import NoteTypeModel
from ankiforge.services.cards.snippet_library import SnippetLibrary
from ankiforge.ui.dialogs.css_conflict_dialog import CSSConflictDialog
from ankiforge.ui.dialogs.model_import_dialog import ModelImportDialog
from ankiforge.ui.views.card_models_view import CardModelsView

pytestmark = pytest.mark.ui


def _get_flow_layout_texts(flow_layout: Any) -> list[str]:
    texts: list[str] = []
    for i in range(flow_layout.count()):
        item = flow_layout.itemAt(i)
        if item is not None:
            w = item.widget()
            if w is not None and hasattr(w, "text"):
                texts.append(str(w.text()))
    return texts


def test_card_models_view_creation(qtbot, mock_db):
    """Vérifie l'instanciation de CardModelsView et le chargement initial des modèles."""
    uid = uuid.uuid4().hex[:6]
    NoteTypeModel.create(
        name=f"Modèle Base {uid}",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
        css_style=".card { color: #000; }",
    )

    view = CardModelsView()
    qtbot.addWidget(view)

    assert view.list_widget.count() >= 1
    assert view.fields_input.text() == "Front, Back"
    assert view.css_editor_wrapper.toPlainText() == ".card { color: #000; }"
    assert view.front_html_wrapper.toPlainText() == "{{Front}}"
    assert view.back_html_wrapper.toPlainText() == "{{Back}}"
    assert view.left_panel.content_stack.currentIndex() == 0
    assert view.left_panel.tabs_bar.tabs[0].isChecked()


def test_card_models_view_template_management(qtbot, mock_db):
    """Vérifie l'ajout, la duplication et la navigation entre gabarits multi-cartes."""
    uid = uuid.uuid4().hex[:6]
    NoteTypeModel.create(
        name=f"Modèle Multi {uid}",
        fields_schema=json.dumps(["Front", "Back", "Extra"]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
        css_style=".card {}",
    )

    view = CardModelsView()
    qtbot.addWidget(view)

    # 1. Duplication de gabarit
    view._on_dup_template()
    assert len(view._templates_list) == 2
    assert view.card_selector_combo.count() == 2
    assert "Copie" in view._templates_list[1]["name"]

    # 2. Changement d'onglet de gabarit
    view.card_selector_combo.setCurrentIndex(0)
    assert view._current_template_idx == 0

    # 3. Modification de code HTML et synchronisation
    view.front_html_wrapper.setPlainText("{{Front}} <b>Modifié</b>")
    view._sync_current_template_from_editors()
    assert view._templates_list[0]["qfmt"] == "{{Front}} <b>Modifié</b>"


def test_card_models_view_snippet_insertion(qtbot, mock_db):
    """Vérifie l'insertion d'un snippet modulaire sans collision CSS."""
    view = CardModelsView()
    qtbot.addWidget(view)

    snippet = SnippetLibrary.get_by_id("callout_info")
    assert snippet is not None

    view._on_insert_snippet(snippet, target="front")
    assert "af-callout-info" in view.front_html_wrapper.toPlainText()
    assert ".af-callout-info" in view.css_editor_wrapper.toPlainText()


def test_css_conflict_dialog(qtbot):
    """Vérifie le fonctionnement de la modale d'arbitrage de conflits CSS."""
    dlg = CSSConflictDialog(
        conflicting_classes=["af-callout", "af-callout-info"],
        snippet_name="Encadré Info",
    )
    qtbot.addWidget(dlg)

    assert "af-callout" in dlg.text() if hasattr(dlg, "text") else True

    # Test clic action 'rename'
    dlg.btn_rename.click()
    assert dlg.selected_action == "rename"


def test_model_import_dialog(qtbot, mock_db):
    """Vérifie la prévisualisation et l'importation de modèle via ModelImportDialog."""
    uid = uuid.uuid4().hex[:6]
    model_data = {
        "name": f"Modèle Import Test {uid}",
        "fields_schema": ["Question", "Reponse", "Source"],
        "templates": [{"name": "Carte Directe", "qfmt": "{{Question}}", "afmt": "{{Reponse}}"}],
        "css_style": ".card { font-size: 14px; }",
        "metadata": {"author": "Dr. Test", "tags": ["import", "med"]},
    }

    dlg = ModelImportDialog(model_data=model_data)
    qtbot.addWidget(dlg)

    assert dlg.name_input.text() == f"Modèle Import Test {uid}"

    # Valider l'import
    dlg.btn_import.click()
    assert dlg.imported_model is not None
    assert dlg.imported_model.name == f"Modèle Import Test {uid}"


def test_card_models_view_cloze_and_css_class_detection(qtbot, mock_db):
    """Vérifie la détection conditionnelle Cloze et l'extraction automatique des classes CSS."""
    uid = uuid.uuid4().hex[:6]
    # 1. Modèle standard sans Cloze
    nt_basic = NoteTypeModel.create(
        name=f"Modèle Standard Basique {uid}",
        fields_schema=json.dumps(["Question", "Reponse"]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Question}}", "afmt": "{{Reponse}}"}]),
        css_style=".card { color: #1e293b; }\n.af-callout-info { border: 1px solid blue; }",
    )

    view = CardModelsView()
    qtbot.addWidget(view)

    # Sélectionner nt_basic
    for i in range(view.list_widget.count()):
        item = view.list_widget.item(i)
        if item.data(Qt.ItemDataRole.UserRole).id == nt_basic.id:
            view.list_widget.setCurrentItem(item)
            break

    # Le modèle basique n'est pas Cloze
    assert view._is_cloze_active() is False

    # Les classes CSS doivent être extraites dans le FlowLayout
    pills_text = _get_flow_layout_texts(view.tags_flow_layout)
    assert "{{Question}}" in pills_text
    assert ".card" in pills_text
    assert ".af-callout-info" in pills_text
    # Aucune balise cloze
    assert not any("cloze" in p for p in pills_text)

    # 2. Modèle avec Cloze
    nt_cloze = NoteTypeModel.create(
        name=f"Modèle Texte à Trou (Cloze) {uid}",
        fields_schema=json.dumps(["Texte", "Extra"]),
        templates=json.dumps([{"name": "Cloze", "qfmt": "{{cloze:Texte}}", "afmt": "{{cloze:Texte}}<br>{{Extra}}"}]),
        css_style=".card {}\n.cloze { font-weight: bold; }",
    )
    view.refresh_data()

    # Sélectionner le modèle Cloze
    for i in range(view.list_widget.count()):
        item = view.list_widget.item(i)
        if item.data(Qt.ItemDataRole.UserRole).id == nt_cloze.id:
            view.list_widget.setCurrentItem(item)
            break

    assert view._is_cloze_active() is True

    pills_cloze = _get_flow_layout_texts(view.tags_flow_layout)
    assert "{{cloze:Texte}}" in pills_cloze
    assert ".cloze" in pills_cloze


def test_card_models_view_category_filtering(qtbot, mock_db):
    """Vérifie le filtrage dynamique des balises d'aides par catégorie."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(
        name=f"Modèle Test Filtres {uid}",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
        css_style=".card { color: #000; }\n.af-badge-warning { background: yellow; }",
    )

    view = CardModelsView()
    qtbot.addWidget(view)

    for i in range(view.list_widget.count()):
        item = view.list_widget.item(i)
        if item.data(Qt.ItemDataRole.UserRole).id == nt.id:
            view.list_widget.setCurrentItem(item)
            break

    # 1. Filtre 'Champs'
    view._on_helper_category_selected("Champs")
    pills_champs = _get_flow_layout_texts(view.tags_flow_layout)
    assert "{{Front}}" in pills_champs
    assert "{{Back}}" in pills_champs
    assert ".card" not in pills_champs

    # 2. Filtre 'Classes CSS'
    view._on_helper_category_selected("Classes CSS")
    pills_css = _get_flow_layout_texts(view.tags_flow_layout)
    assert ".card" in pills_css
    assert ".af-badge-warning" in pills_css
    assert "{{Front}}" not in pills_css

    # 3. Filtre 'Structure'
    view._on_helper_category_selected("Structure")
    pills_struct = _get_flow_layout_texts(view.tags_flow_layout)
    assert "{{FrontSide}}" in pills_struct
    assert '<hr id="answer">' in pills_struct


def test_card_models_view_vertical_splitter_and_collider(qtbot, mock_db):
    """Vérifie le redimensionnement vertical par splitter et le pliage/dépliage du volet d'aides (Collider)."""
    uid = uuid.uuid4().hex[:6]
    NoteTypeModel.create(
        name=f"Modèle Splitter {uid}",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
        css_style=".card { color: #000; }",
    )

    view = CardModelsView()
    qtbot.addWidget(view)

    # 1. Vérifier la présence et la configuration du splitter vertical
    assert view.editor_vertical_splitter is not None
    assert view.editor_vertical_splitter.orientation() == Qt.Orientation.Vertical
    assert view.editor_vertical_splitter.count() == 2

    # Modifier la hauteur par le splitter
    view.editor_vertical_splitter.setSizes([150, 450])
    sizes = view.editor_vertical_splitter.sizes()
    assert len(sizes) == 2

    # 2. Vérifier le Collider (replier / déplier les aides)
    assert not view.tags_scroll_area.isHidden()
    # Replier
    view.btn_collapse_helpers.click()
    assert view.tags_scroll_area.isHidden()

    # Déplier
    view.btn_collapse_helpers.click()
    assert not view.tags_scroll_area.isHidden()


def test_snippet_drawer_master_detail_and_creation(qtbot):
    """Vérifie la navigation Master-Detail, l'inspection de code et la création in-place de snippets."""
    from ankiforge.ui.components.snippet_drawer import SnippetLibraryDrawer

    drawer = SnippetLibraryDrawer()
    qtbot.addWidget(drawer)

    # 1. Vue initiale (Liste / Master view)
    assert drawer.stack.currentIndex() == 0

    # 2. Navigation vers la création in-place
    drawer._open_create_view()
    assert drawer.stack.currentIndex() == 2

    # Remplir le formulaire de création
    uid = uuid.uuid4().hex[:6]
    drawer.create_name_input.setText(f"Mon Snippet Test {uid}")
    drawer.create_cat_input.setText("Custom Tests")
    drawer.create_desc_input.setText("Super composant")
    drawer.create_html_editor.setPlainText('<div class="box">{{Test}}</div>')
    drawer.create_css_editor.setPlainText(".box { color: blue; }")

    # Soumettre
    drawer._submit_create_snippet()
    assert drawer.stack.currentIndex() == 0

    # Vérifier que le snippet créé est présent dans la liste
    created_snippet = next((s for s in drawer._all_snippets if f"Mon Snippet Test {uid}" in s.name), None)
    assert created_snippet is not None

    # 3. Navigation vers le détail / édition (Zoom view)
    drawer._open_detail_view(created_snippet)
    assert drawer.stack.currentIndex() == 1
    assert drawer.detail_name_input.text() == f"Mon Snippet Test {uid}"
    assert drawer.detail_html_editor.toPlainText() == '<div class="box">{{Test}}</div>'

    # Modifier le code dans la vue détail
    drawer.detail_name_input.setText(f"Mon Snippet Édité {uid}")
    drawer._save_detail_snippet()
    assert drawer.stack.currentIndex() == 0

    # 4. Suppression du snippet
    drawer._open_detail_view(created_snippet)
    assert drawer.stack.currentIndex() == 1
    with patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
        drawer._delete_current_detail_snippet()
    assert drawer.stack.currentIndex() == 0
    assert not any(s.id == created_snippet.id for s in drawer._all_snippets)


def test_glow_line_edit_hover_and_focus_state(qtbot, mock_db):
    """Vérifie que la barre de recherche applique l'accentuation au survol et le contour persistant au focus."""
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent, QFocusEvent

    from ankiforge.ui.components.inputs import GlowLineEdit

    search_input = GlowLineEdit(placeholder="Rechercher un modèle...")
    qtbot.addWidget(search_input)

    assert search_input.testAttribute(Qt.WidgetAttribute.WA_Hover)
    assert search_input.property("role") == "search"

    # 1. État initial (Default)
    assert hasattr(search_input, "_shadow_effect")
    assert search_input._shadow_effect.blurRadius() == search_input.default_blur

    # 2. Survol (Hover)
    enter_ev = QEnterEvent(QPointF(10, 10), QPointF(10, 10), QPointF(10, 10))
    search_input.enterEvent(enter_ev)
    assert search_input.anim.endValue() == search_input.hover_blur

    # 3. Clic / Focus (Active state)
    focus_in = QFocusEvent(QEvent.Type.FocusIn)
    search_input.focusInEvent(focus_in)
    assert search_input.anim.endValue() == search_input.focus_blur
    assert search_input._shadow_effect.color().alpha() > 0

    # 4. Déplacement de la souris pendant le focus : reste en focus_blur
    leave_ev = QEvent(QEvent.Type.Leave)
    search_input.leaveEvent(leave_ev)
    assert search_input.anim.endValue() == search_input.focus_blur

    # 5. Perte de focus (FocusOut)
    focus_out = QFocusEvent(QEvent.Type.FocusOut)
    search_input.focusOutEvent(focus_out)
    assert search_input.anim.endValue() == search_input.default_blur


def test_card_models_view_bottom_toolbar_buttons_affordance(qtbot, mock_db):
    """Vérifie que les boutons Nouveau, Starter Pack, Dupliquer, Importer JSON et Supprimer appliquent WA_Hover et leurs rôles."""
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent

    view = CardModelsView()
    qtbot.addWidget(view)

    btn_new = view.btn_new
    btn_starter = view.btn_starter_pack
    btn_dup = view.btn_duplicate
    btn_imp = view.btn_import_json
    btn_del = view.btn_del

    # Vérification des rôles sémantiques
    assert btn_new.property("role") == "primary"
    assert btn_new.text() == "Nouveau"
    assert not btn_new.icon().isNull()
    assert btn_starter.property("role") == "secondary"
    assert btn_dup.property("role") == "icon"
    assert btn_imp.property("role") == "icon"
    assert btn_del.property("role") == "icon"

    # Vérification de l'activation de WA_Hover pour les transitions
    assert btn_new.testAttribute(Qt.WidgetAttribute.WA_Hover)
    assert btn_starter.testAttribute(Qt.WidgetAttribute.WA_Hover)
    assert btn_dup.testAttribute(Qt.WidgetAttribute.WA_Hover)
    assert btn_imp.testAttribute(Qt.WidgetAttribute.WA_Hover)
    assert btn_del.testAttribute(Qt.WidgetAttribute.WA_Hover)

    # Vérification de l'animation d'ombre sur btn_dup
    enter_ev = QEnterEvent(QPointF(10, 10), QPointF(10, 10), QPointF(10, 10))
    btn_dup.enterEvent(enter_ev)
    assert btn_dup.anim.endValue() == btn_dup.hover_blur

    leave_ev = QEvent(QEvent.Type.Leave)
    btn_dup.leaveEvent(leave_ev)
    assert btn_dup.anim.endValue() == btn_dup.default_blur


def test_snippet_card_click_opens_detail_and_insert_at_cursor(qtbot):
    """Vérifie que le clic sur la carte bascule vers l'édition et que le bouton Insérer au curseur émet le signal."""
    from ankiforge.services.cards.snippet_library import SnippetLibrary
    from ankiforge.ui.components.snippet_drawer import SnippetCardWidget

    snippet = SnippetLibrary.get_by_id("callout_info")
    assert snippet is not None

    card = SnippetCardWidget(snippet)
    qtbot.addWidget(card)
    card.show()

    edit_signals = []
    insert_signals = []

    card.edit_requested.connect(lambda s: edit_signals.append(s))
    card.insert_requested.connect(lambda s: insert_signals.append(s))

    # 1. Clic sur la carte -> déclenche edit_requested
    qtbot.mouseClick(card, Qt.MouseButton.LeftButton)
    assert len(edit_signals) == 1
    assert edit_signals[0].id == snippet.id

    # 2. Clic sur le bouton Insérer au curseur -> déclenche insert_requested
    card.btn_insert.click()
    assert len(insert_signals) == 1
    assert insert_signals[0].id == snippet.id


def test_card_models_view_cursor_linked_insertion(qtbot, mock_db):
    """Vérifie que l'insertion de snippet s'effectue précisément à la position du curseur dans l'éditeur actif."""
    from ankiforge.services.cards.snippet_library import SnippetLibrary

    view = CardModelsView()
    qtbot.addWidget(view)

    snippet = SnippetLibrary.get_by_id("badge_difficulty")
    assert snippet is not None

    # 1. Insertion dans le Recto HTML au milieu du texte
    view._switch_subtab(1)
    view.front_html_wrapper.setPlainText("START_FRONT__END_FRONT")
    cursor = view.front_html_wrapper.editor.textCursor()
    cursor.setPosition(12)  # Entre START_FRONT_ et _END_FRONT
    view.front_html_wrapper.editor.setTextCursor(cursor)

    view._on_insert_snippet(snippet)

    front_text = view.front_html_wrapper.toPlainText()
    assert "START_FRONT_" in front_text
    assert "_END_FRONT" in front_text
    assert snippet.html_template in front_text
    assert ".af-badge-diff" in view.css_editor_wrapper.toPlainText()

    # 2. Insertion dans le Verso HTML au curseur
    view._switch_subtab(2)
    view.back_html_wrapper.setPlainText("START_BACK__END_BACK")
    cursor_back = view.back_html_wrapper.editor.textCursor()
    cursor_back.setPosition(11)  # Entre START_BACK_ et _END_BACK
    view.back_html_wrapper.editor.setTextCursor(cursor_back)

    snippet_warn = SnippetLibrary.get_by_id("callout_warning")
    assert snippet_warn is not None

    view._on_insert_snippet(snippet_warn)

    back_text = view.back_html_wrapper.toPlainText()
    assert "START_BACK_" in back_text
    assert "_END_BACK" in back_text
    assert snippet_warn.html_template in back_text
    assert ".af-callout-warning" in view.css_editor_wrapper.toPlainText()


def test_html_linter_and_css_linter():
    """Vérifie la détection précise des erreurs de syntaxe par HTMLLinter et CSSLinter."""
    from ankiforge.ui.components.code_editor import CSSLinter, HTMLLinter

    # 1. HTML Linter : balises orphelines, non fermées, champs Anki inconnus
    html_valid = '<div class="card">\n  <p>{{Front}}</p>\n  <hr id="answer">\n</div>'
    assert len(HTMLLinter.lint(html_valid, ["Front", "Back"])) == 0

    html_unclosed_tag = '<div class="card">\n  <span>{{Front}}\n</div>'
    issues_html = HTMLLinter.lint(html_unclosed_tag, ["Front", "Back"])
    assert len(issues_html) >= 1
    assert any("span" in iss.message for iss in issues_html)

    html_orphan_brace = "<div>{{Front</div>"
    issues_brace = HTMLLinter.lint(html_orphan_brace, ["Front", "Back"])
    assert len(issues_brace) >= 1
    assert any("Accolade double" in iss.message for iss in issues_brace)

    html_unknown_field = "<div>{{ChampInexistant}}</div>"
    issues_field = HTMLLinter.lint(html_unknown_field, ["Front", "Back"])
    assert len(issues_field) >= 1
    assert any("ChampInexistant" in iss.message for iss in issues_field)

    # 2. CSS Linter : accolades non fermées, propriétés sans séparateur, valeurs vides
    css_valid = ".card {\n  background-color: #fff;\n  font-size: 14px;\n}"
    assert len(CSSLinter.lint(css_valid)) == 0

    css_unclosed_brace = ".card {\n  color: red;\n"
    issues_css = CSSLinter.lint(css_unclosed_brace)
    assert len(issues_css) >= 1
    assert any("Accolade ouvrante" in iss.message for iss in issues_css)

    css_missing_colon = ".card {\n  color red;\n}"
    issues_colon = CSSLinter.lint(css_missing_colon)
    assert len(issues_colon) >= 1
    assert any("manquant" in iss.message for iss in issues_colon)


def test_code_editor_gutter_autocomplete_and_lint_status(qtbot):
    """Vérifie la synchronisation de la gouttière native, le statut du linter et l'autocomplétion."""
    from ankiforge.ui.components.code_editor import CodeEditorWithGutter

    editor_wrapper = CodeEditorWithGutter(placeholder="{{Front}}", mode="html")
    qtbot.addWidget(editor_wrapper)
    editor_wrapper.show()

    # 1. Gouttière native synchronisée
    native = editor_wrapper.editor
    native.setPlainText("Ligne 1\nLigne 2\nLigne 3\nLigne 4\nLigne 5")
    assert native.blockCount() == 5
    assert native.line_number_area.width() > 20

    # 2. Synchronisation des champs et autocomplétion
    editor_wrapper.set_known_fields(["Front", "Back", "Extra"])
    model = native.completer.model()
    assert model is not None
    string_list = model.stringList()
    assert "{{Front}}" in string_list
    assert "{{cloze:Front}}" in string_list
    assert '<div class="card">' in string_list

    # 3. Lintage temps réel et mise à jour de la barre de statut
    native.setPlainText("<div class='box'>\n  <span>{{Front}}\n</div>")
    native.run_linter()

    issues = editor_wrapper.get_lint_issues()
    assert len(issues) >= 1
    assert "erreur" in editor_wrapper.lint_status_bar.status_lbl.text()

    # 4. Correction du code -> retour à la syntaxe valide
    native.setPlainText("<div class='box'>\n  <span>{{Front}}</span>\n</div>")
    native.run_linter()
    assert len(editor_wrapper.get_lint_issues()) == 0
    assert "valide" in editor_wrapper.lint_status_bar.status_lbl.text()


def test_code_editor_auto_closing_tags_and_braces(qtbot):
    """Vérifie l'auto-fermeture automatique des balises HTML (<test> -> <test></test>) et accolades."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    from ankiforge.ui.components.code_editor import CodeEditorWithGutter

    wrapper = CodeEditorWithGutter(placeholder="", mode="html")
    qtbot.addWidget(wrapper)
    wrapper.show()
    native = wrapper.editor

    # 1. Balise standard/personnalisée <test> -> auto-fermeture </test>
    native.setPlainText("<test")
    cursor = native.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    native.setTextCursor(cursor)

    key_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Greater, Qt.KeyboardModifier.NoModifier, ">")
    native.keyPressEvent(key_event)

    assert native.toPlainText() == "<test></test>"
    # Le curseur doit être situé à l'intérieur entre <test> et </test>
    assert native.textCursor().position() == 6

    # 2. Balise vide void (ex: <br>) -> PAS d'auto-fermeture </br>
    native.setPlainText("<br")
    cursor = native.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    native.setTextCursor(cursor)

    key_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Greater, Qt.KeyboardModifier.NoModifier, ">")
    native.keyPressEvent(key_event)
    assert native.toPlainText() == "<br>"

    # 3. Accolades doubles Anki : { puis { -> auto-fermeture }}
    native.setPlainText("{")
    cursor = native.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    native.setTextCursor(cursor)

    key_brace = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_BraceLeft, Qt.KeyboardModifier.NoModifier, "{")
    native.keyPressEvent(key_brace)
    assert native.toPlainText() == "{{}}"
    assert native.textCursor().position() == 2


def test_syntax_highlighters(qtbot):
    """Vérifie l'application de la coloration syntaxique HTML et CSS."""
    from PySide6.QtWidgets import QTextEdit

    from ankiforge.ui.components.code_editor import CSSSyntaxHighlighter, HTMLSyntaxHighlighter

    # 1. HTML Highlighter
    ed_html = QTextEdit()
    qtbot.addWidget(ed_html)
    hl_html = HTMLSyntaxHighlighter(ed_html.document())
    assert len(hl_html.rules) >= 5

    # 2. CSS Highlighter
    ed_css = QTextEdit()
    qtbot.addWidget(ed_css)
    hl_css = CSSSyntaxHighlighter(ed_css.document())
    assert len(hl_css.rules) >= 5


def test_modern_css_linter_no_false_positives():
    """Vérifie que le CSS moderne (variables, clamp, calc, at-rules, multi-lignes) ne génère aucun faux positif."""
    from ankiforge.ui.components.code_editor import CSSLinter

    modern_css = """
    :root {
        --bg-color: #ffffff;
        --text-color: #080808;
        --question-color: #5c6bc0;
        --ref-color: #D3D3D3;
    }

    .nightMode,
    :root[data-theme="dark"] {
        --bg-color: #2b2b2b;
        --text-color: #a9b7c6;
    }

    .card {
        font-size: clamp(16px, 1.1vw, 19px);
        background-color: var(--bg-color);
        background: linear-gradient(to right,
                transparent,
                var(--border-color),
                transparent);
        transition: all 0.2s ease;
    }

    .important {
        background-color: color-mix(in srgb, var(--remarque-accent) 10%, transparent);
    }

    @media (max-width: 600px) {
        .card {
            width: 96%;
            padding: 15px;
        }
    }

    @keyframes slideIn {
        from { opacity: 0; transform: translateY(8px); }
        to { opacity: 1; transform: translateY(0); }
    }
    """

    issues = CSSLinter.lint(modern_css)
    assert len(issues) == 0

    # Vérification que les vraies erreurs sont bien captées
    err_css = ".card { color red; font-size: clamp(16px, 1.1vw; }"
    err_issues = CSSLinter.lint(err_css)
    assert any(i.rule_id == "css-missing-colon" for i in err_issues)
    assert any(i.rule_id == "css-unbalanced-parens" for i in err_issues)


def test_color_swatches_detection():
    """Vérifie l'extraction précise des codes couleurs (hex, rgb, rgba, hsl)."""
    from ankiforge.ui.components.code_editor import extract_colors_from_text

    line_1 = "--bg-color: #ffffff; --accent: #5c6bc0;"
    colors_1 = extract_colors_from_text(line_1)
    assert len(colors_1) == 2
    assert colors_1[0][0] == "#ffffff"
    assert colors_1[1][0] == "#5c6bc0"

    line_2 = "box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);"
    colors_2 = extract_colors_from_text(line_2)
    assert len(colors_2) == 1
    assert "rgba" in colors_2[0][0]


def test_code_formatter_css_and_html_and_shortcuts(qtbot):
    """Vérifie le formateur de code CSS et HTML et son déclenchement via raccourci clavier / bouton."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    from ankiforge.ui.components.code_editor import CodeEditorWithGutter, CSSFormatter, HTMLFormatter

    # 1. Formatage CSS
    unformatted_css = ":root{--bg:#fff;--fg:#000;}.card{padding:10px;margin:0 auto;}"
    formatted_css = CSSFormatter.format(unformatted_css)
    assert ":root {\n  --bg: #fff;\n  --fg: #000;\n}" in formatted_css
    assert ".card {\n  padding: 10px;\n  margin: 0 auto;\n}" in formatted_css

    # 2. Formatage HTML
    unformatted_html = "<div class='card'><h1>{{Front}}</h1><hr id='answer'><p>Texte</p></div>"
    formatted_html = HTMLFormatter.format(unformatted_html)
    assert "<div class='card'>" in formatted_html
    assert "  <h1>" in formatted_html
    assert "    {{Front}}" in formatted_html

    # 3. Déclenchement via raccourci Ctrl+Alt+L dans l'éditeur
    wrapper = CodeEditorWithGutter(placeholder="", mode="css")
    qtbot.addWidget(wrapper)
    wrapper.show()
    wrapper.setPlainText(":root{color:red;}")

    key_event = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_L,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
    )
    wrapper.editor.keyPressEvent(key_event)
    assert ":root {\n  color: red;\n}" in wrapper.toPlainText()

    # 4. Déclenchement via le bouton Formater de la barre de statut
    wrapper.setPlainText(".box{width:100px;}")
    wrapper.lint_status_bar.format_btn.click()
    assert ".box {\n  width: 100px;\n}" in wrapper.toPlainText()


def test_card_models_13inch_responsive_layout_and_flow_widget(qtbot, mock_db):
    """Vérifie la robustesse du layout responsive (TopBar compacte, FlowWidget sans collision, SnippetCards)."""
    uid = uuid.uuid4().hex[:6]
    NoteTypeModel.create(
        name=f"Modèle Responsive 13in {uid}",
        fields_schema=json.dumps(["Question", "Explication", "Source"]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Question}}", "afmt": "{{Explication}} <br> {{Source}}"}]),
        css_style=".card { font-size: 14px; }\n.af-callout-info { color: blue; }",
    )

    view = CardModelsView()
    qtbot.addWidget(view)
    view.show()
    view.resize(1024, 700)  # Simulation largeur écran 13 pouces avec sidebar

    # 1. Vérification de la Top Action Bar Responsive
    top_bar = view.top_action_bar
    assert top_bar.lbl_editor_title is not None
    assert top_bar.btn_save.text() == "Sauvegarder"
    assert top_bar.btn_export_json.property("role") == "icon"
    assert top_bar.btn_refresh.property("role") == "icon"

    # 2. Vérification de FlowLayout
    flow_l = view.tags_flow_layout
    assert flow_l.hasHeightForWidth() is True
    h1 = flow_l.heightForWidth(300)
    h2 = flow_l.heightForWidth(800)
    assert h1 >= h2  # Plus la largeur est petite, plus la hauteur s'adapte en passant à la ligne

    # 3. Vérification des Snippet Cards sans débordement horizontal
    drawer = view.snippet_drawer
    assert drawer.category_container.flow_layout.count() > 0


def test_card_models_role_guide_button_presence_and_properties(qtbot, mock_db):
    """Vérifie la présence et le style du bouton 'Prompt pour l'IA' dans CardModelsView."""
    view = CardModelsView()
    qtbot.addWidget(view)

    assert hasattr(view, "btn_role_guide")
    assert view.btn_role_guide.text() == "Prompt pour l'IA"
    assert view.btn_role_guide.height() == 26


def test_card_models_role_guide_apply_to_description(qtbot, mock_db):
    """Vérifie l'injection de la directive IA depuis le dialogue dans le champ description_input."""
    uid = uuid.uuid4().hex[:6]
    NoteTypeModel.create(
        name=f"Modèle Test Rôle {uid}",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
        css_style=".card {}",
        description="",
    )

    view = CardModelsView()
    qtbot.addWidget(view)

    assert view.btn_role_guide.text() == "Prompt pour l'IA"
    assert view.btn_role_guide.height() == 26

    test_directive = "Gabarit pour questions médicales à choix multiples (QCM)."

    with patch("ankiforge.ui.views.card_models_view.view.NoteTypeRoleGuideDialog") as mock_dialog_cls:
        mock_dlg = mock_dialog_cls.return_value
        mock_dlg.exec.return_value = 1  # QDialog.DialogCode.Accepted
        mock_dlg.selected_directive = test_directive

        view._on_open_role_guide()

    assert view.description_input.text() == test_directive


def test_card_models_role_guide_direct_apply_without_popup(qtbot, mock_db):
    """Vérifie que l'application d'une nouvelle directive remplace directement le texte sans pop-up bloquante."""
    view = CardModelsView()
    qtbot.addWidget(view)

    view.description_input.setText("Ancienne directive personnalisée")
    new_directive = "| Concept | Directive | Champs |\n|---|---|---|\n| Q/R | Direct | Front, Back |"

    with patch("ankiforge.ui.views.card_models_view.view.NoteTypeRoleGuideDialog") as mock_dialog_cls:
        mock_dlg = mock_dialog_cls.return_value
        mock_dlg.exec.return_value = 1
        mock_dlg.selected_directive = new_directive

        view._on_open_role_guide()

        # Application directe sans confirmation modale bloquante
        assert view.description_input.text() == new_directive


def test_card_models_table_badge_detection(qtbot, mock_db):
    """Vérifie la détection dynamique de tableau Markdown et l'affichage du badge."""
    view = CardModelsView()
    qtbot.addWidget(view)

    assert hasattr(view, "btn_role_guide")
    assert hasattr(view, "badge_role_table")

    # Texte standard : pas de badge
    view.description_input.setText("Directive texte simple")
    assert view.badge_role_table.isHidden() is True

    # Tableau Markdown : le badge s'affiche automatiquement
    sample_table = "| Concept | Directive | Champs |\n|---|---|---|\n| Test | Faire X | Front |"
    view.description_input.setText(sample_table)
    assert view.badge_role_table.isHidden() is False


def test_responsive_top_action_bar_preview_sync(qtbot):
    """Vérifie l'API de synchronisation et l'état checkable du bouton d'aperçu dans ResponsiveTopActionBar."""
    from ankiforge.ui.views.card_models_view.widgets.responsive_action_bar import ResponsiveTopActionBar

    bar = ResponsiveTopActionBar()
    qtbot.addWidget(bar)

    assert bar.btn_toggle_preview.isCheckable() is True
    assert bar.btn_toggle_preview.isChecked() is True

    bar.set_preview_visible(False)
    assert bar.btn_toggle_preview.isChecked() is False

    bar.set_preview_visible(True)
    assert bar.btn_toggle_preview.isChecked() is True


def test_card_models_view_preview_button_neutral_border_and_sync(qtbot, mock_db):
    """Vérifie l'absence de QSS inline forcé et la synchronisation du bouton Aperçu en direct."""
    view = CardModelsView()
    qtbot.addWidget(view)
    view.show()

    btn = view.top_action_bar.btn_toggle_preview
    assert btn.isCheckable() is True
    assert btn.isChecked() is True
    assert view.preview_container.isVisible() is True
    # Pas de QSS inline imposant une bordure bleue permanente
    assert btn.styleSheet() == ""

    # Bascule : masque le panneau
    view._toggle_preview_panel()
    assert view.preview_container.isVisible() is False
    assert btn.isChecked() is False
    assert btn.styleSheet() == ""

    # Bascule : réaffiche le panneau
    view._toggle_preview_panel()
    assert view.preview_container.isVisible() is True
    assert btn.isChecked() is True
    assert btn.styleSheet() == ""

    # Fermeture par la croix de l'aperçu
    view._hide_preview_panel()
    assert view.preview_container.isVisible() is False
    assert btn.isChecked() is False
    assert btn.styleSheet() == ""


# --- Autocomplétion non intrusive et priorité Entrée (NativeCodeEditor) ---


def _type_free_text(native: Any, text: str) -> None:
    """Simule la frappe caractère par caractère en passant par ``keyPressEvent``."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    for char in text:
        native.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_unknown, Qt.KeyboardModifier.NoModifier, char))


def _press_key(native: Any, key: Any, modifiers: Any = Qt.KeyboardModifier.NoModifier, text: str = "") -> None:
    """Simule une frappe de touche spéciale (Entrée, Tab, Échap, flèches…)."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    native.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text))


def _place_cursor_at_end(native: Any) -> None:
    """Place le curseur en fin de document."""
    cursor = native.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    native.setTextCursor(cursor)


def _make_html_editor(qtbot: Any) -> Any:
    """Construit un éditeur HTML headless enrichi de champs Anki connus.

    Retourne le conteneur ``CodeEditorWithGutter`` : le conserver vivant est
    indispensable car son éditeur natif et son completer en dépendent.
    """
    from ankiforge.ui.components.code_editor import CodeEditorWithGutter

    wrapper = CodeEditorWithGutter(placeholder="", mode="html")
    qtbot.addWidget(wrapper)
    wrapper.show()
    wrapper.editor.set_known_fields(["Front", "Back", "Extra"])
    return wrapper


def test_code_editor_free_typing_never_opens_completion_popup(qtbot):
    """La frappe de texte libre n'ouvre plus le popup d'autocomplétion de façon intempestive."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor

    _type_free_text(native, "bonjour le monde")

    assert native.toPlainText() == "bonjour le monde"
    assert native.completer.popup().isVisible() is False


def test_code_editor_enter_after_free_typing_inserts_newline(qtbot):
    """Texte libre suivi d'Entrée : saut de ligne, sans insertion de champ Anki parasite."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor

    _type_free_text(native, "bonjour")
    assert native.completer.popup().isVisible() is False

    _press_key(native, Qt.Key.Key_Return, text="\n")

    assert native.toPlainText() == "bonjour\n"
    assert "{{" not in native.toPlainText()


def test_code_editor_anki_trigger_opens_popup_without_preselection(qtbot):
    """Le déclencheur ``{{`` ouvre le popup sans présélectionner le premier élément."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor

    _type_free_text(native, "{{")

    popup = native.completer.popup()
    assert popup.isVisible() is True
    assert popup.currentIndex().isValid() is False


def test_code_editor_enter_without_navigation_does_not_insert_field(qtbot):
    """Popup ouvert mais aucun élément navigué : Entrée produit un saut de ligne."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor
    _type_free_text(native, "{{")

    popup = native.completer.popup()
    assert popup.isVisible() is True

    _press_key(native, Qt.Key.Key_Return, text="\n")

    assert popup.isVisible() is False
    assert "{{Front}}" not in native.toPlainText()
    # Saut de ligne inséré au curseur (entre les accolades auto-appairées), pas de champ.
    assert native.toPlainText() == "{{\n}}"


def test_code_editor_arrow_navigation_then_enter_inserts_selection(qtbot):
    """Une navigation explicite (flèche bas) autorise l'insertion par la touche Entrée."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor
    _type_free_text(native, "<di")

    popup = native.completer.popup()
    assert popup.isVisible() is True
    assert popup.currentIndex().isValid() is False

    _press_key(native, Qt.Key.Key_Down)
    assert popup.currentIndex().isValid() is True

    _press_key(native, Qt.Key.Key_Return, text="\n")

    assert popup.isVisible() is False
    assert native.toPlainText() == '<div class="card">'


def test_code_editor_tab_validates_selected_completion(qtbot):
    """La touche Tab valide et insère l'élément sélectionné dans la liste."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor
    _type_free_text(native, "<di")

    popup = native.completer.popup()
    assert popup.isVisible() is True
    assert popup.currentIndex().isValid() is False

    _press_key(native, Qt.Key.Key_Down)
    _press_key(native, Qt.Key.Key_Tab)

    assert native.toPlainText() == '<div class="card">'
    assert popup.isVisible() is False


def test_code_editor_mouse_click_validates_selection(qtbot):
    """Le clic souris sur un élément du popup valide et insère la complétion."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor
    _type_free_text(native, "<di")

    popup = native.completer.popup()
    index = native.completer.completionModel().index(0, 0)
    assert index.isValid()

    popup.clicked.emit(index)

    assert native.toPlainText() == '<div class="card">'
    assert popup.isVisible() is False


def test_code_editor_css_free_typing_then_enter_inserts_newline(qtbot):
    """En CSS — où le bug d'ouverture intempestive se manifestait — la frappe libre reste inerte.

    Taper un mot libre ne doit ni ouvrir le popup, ni permettre à Entrée d'insérer une
    propriété CSS (ex. ``background-color: ``).
    """
    from ankiforge.ui.components.code_editor import CodeEditorWithGutter

    wrapper = CodeEditorWithGutter(placeholder="", mode="css")
    qtbot.addWidget(wrapper)
    wrapper.show()
    native = wrapper.editor

    _type_free_text(native, "background")

    assert native.completer.popup().isVisible() is False

    _press_key(native, Qt.Key.Key_Return, text="\n")

    assert native.toPlainText() == "background\n"
    assert "background-color" not in native.toPlainText()


def test_code_editor_escape_hides_popup_without_altering_cursor(qtbot):
    """Échap masque le popup sans modifier ni le texte ni la position du curseur."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor
    _type_free_text(native, "<di")

    text_before = native.toPlainText()
    cursor_before = native.textCursor().position()

    _press_key(native, Qt.Key.Key_Escape)

    assert native.completer.popup().isVisible() is False
    assert native.toPlainText() == text_before
    assert native.textCursor().position() == cursor_before


def test_code_editor_ctrl_space_opens_catalog(qtbot):
    """Ctrl+Espace ouvre explicitement le catalogue de complétion, sans présélection."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor
    _type_free_text(native, "bonjour ")

    assert native.completer.popup().isVisible() is False

    _press_key(native, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)

    popup = native.completer.popup()
    assert popup.isVisible() is True
    assert popup.currentIndex().isValid() is False


def test_code_editor_css_prefix_ignores_decimals_and_detects_classes(qtbot):
    """Le déclencheur CSS `.` couvre les sélecteurs composés mais ignore les nombres décimaux."""
    from ankiforge.ui.components.code_editor import CodeEditorWithGutter

    wrapper = CodeEditorWithGutter(placeholder="", mode="css")
    qtbot.addWidget(wrapper)
    wrapper.show()
    native = wrapper.editor

    native.setPlainText(".card")
    _place_cursor_at_end(native)
    kind, prefix = native._get_completion_prefix()
    assert (kind, prefix) == ("css_class", ".card")

    native.setPlainText("div.af-callout-info")
    _place_cursor_at_end(native)
    kind, prefix = native._get_completion_prefix()
    assert (kind, prefix) == ("css_class", ".af-callout-info")

    native.setPlainText("width: 1.1vw")
    _place_cursor_at_end(native)
    kind, prefix = native._get_completion_prefix()
    assert kind == ""
    assert prefix == ""


# --- Remplacement chirurgical des tokens et complétion attribut class ---


def test_code_editor_anki_completion_after_auto_pairing_removes_orphan_brackets(qtbot):
    """La complétion d'un champ Anki après auto-appairage {{}} produit {{Champ}} sans }} orphelin."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor

    # 1. Frappe de {{ déclenchant l'auto-appairage {}}
    _type_free_text(native, "{{")
    assert native.toPlainText() == "{{}}"
    # Le curseur est positionné entre {{ et }} (position 2)
    assert native.textCursor().position() == 2

    # 2. Frappe du préfixe 'F'
    _type_free_text(native, "F")
    assert native.toPlainText() == "{{F}}"

    # 3. Validation de la complétion {{Front}}
    _press_key(native, Qt.Key.Key_Down)
    _press_key(native, Qt.Key.Key_Tab)

    assert native.toPlainText() == "{{Front}}"
    assert native.completer.popup().isVisible() is False


def test_code_editor_html_tag_completion_consumes_adjacent_closing_angle(qtbot):
    """La complétion des balises HTML après < consomme le chevron fermant adjacent s'il existe."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor

    # Pré-configuration avec un chevron fermant existant : <|>
    native.setPlainText("<>")
    cursor = native.textCursor()
    cursor.setPosition(1)
    native.setTextCursor(cursor)

    # Frappe de 'di'
    _type_free_text(native, "di")
    assert native.toPlainText() == "<di>"

    # Sélection et validation de <div class="card">
    _press_key(native, Qt.Key.Key_Down)
    _press_key(native, Qt.Key.Key_Tab)

    assert native.toPlainText() == '<div class="card">'
    assert not native.toPlainText().endswith(">>")


def test_code_editor_css_hyphenated_properties_and_selectors_no_duplication(qtbot):
    """Les propriétés CSS et sélecteurs à tirets sont complétés sans duplication de préfixe."""
    from ankiforge.ui.components.code_editor import CodeEditorWithGutter

    wrapper = CodeEditorWithGutter(placeholder="", mode="css")
    qtbot.addWidget(wrapper)
    wrapper.show()
    native = wrapper.editor

    # 1. Propriété à tiret 'font-s' -> 'font-size: '
    _type_free_text(native, "font-s")
    _press_key(native, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    _press_key(native, Qt.Key.Key_Down)
    _press_key(native, Qt.Key.Key_Tab)
    assert native.toPlainText() == "font-size: "

    # 2. Sélecteur à tiret '.af-' -> '.af-callout-info'
    native.setPlainText("")
    _type_free_text(native, ".af-")
    _press_key(native, Qt.Key.Key_Down)
    _press_key(native, Qt.Key.Key_Tab)
    assert native.toPlainText() == ".af-callout-info"

    # 3. Variable CSS 'var(--'
    native.setPlainText("")
    _type_free_text(native, "var(--")
    _press_key(native, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    _press_key(native, Qt.Key.Key_Down)
    _press_key(native, Qt.Key.Key_Tab)
    assert native.toPlainText() == "var(--"


def test_code_editor_html_class_attribute_triggers_css_classes_completion(qtbot):
    """La frappe dans l'attribut HTML class="..." ou class='...' suggère les classes CSS."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor
    native.set_custom_classes(["my-custom-box"])

    # 1. Ouverture avec guillemets doubles class="
    _type_free_text(native, '<div class="')
    popup = native.completer.popup()
    assert popup.isVisible() is True

    # 2. Frappe du préfixe 'af-'
    _type_free_text(native, "af-")
    assert popup.isVisible() is True

    # Validation d'une classe CSS (ex. af-callout-info)
    _press_key(native, Qt.Key.Key_Down)
    _press_key(native, Qt.Key.Key_Tab)
    assert native.toPlainText() == '<div class="af-callout-info'

    # 3. Deuxième classe après espace
    _type_free_text(native, " my-")
    assert popup.isVisible() is True
    _press_key(native, Qt.Key.Key_Down)
    _press_key(native, Qt.Key.Key_Tab)
    assert native.toPlainText() == '<div class="af-callout-info my-custom-box'

    # 4. Même comportement avec guillemets simples class='...'
    native.setPlainText("")
    _type_free_text(native, "<span class='af-")
    assert native.completer.popup().isVisible() is True
    _press_key(native, Qt.Key.Key_Down)
    _press_key(native, Qt.Key.Key_Tab)
    assert native.toPlainText() == "<span class='af-callout-info"


def test_code_editor_anki_direct_completion_without_typing_prefix(qtbot):
    """Après auto-appairage {{}}, la sélection immédiate sans frappe de lettre remplace tout {{}}."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor

    _type_free_text(native, "{{")
    assert native.toPlainText() == "{{}}"

    # Flèche bas puis Tab directement sur {{Front}}
    _press_key(native, Qt.Key.Key_Down)
    _press_key(native, Qt.Key.Key_Tab)

    assert native.toPlainText() == "{{Front}}"


def test_code_editor_html_class_completion_preserves_adjacent_closing_quote(qtbot):
    """La complétion dans class="..." avec guillemet fermant adjacent préserve le guillemet."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor

    # Structure avec guillemets préexistants : <div class="">
    native.setPlainText('<div class="">')
    cursor = native.textCursor()
    cursor.setPosition(len('<div class="'))
    native.setTextCursor(cursor)

    _type_free_text(native, "card")
    _press_key(native, Qt.Key.Key_Down)
    _press_key(native, Qt.Key.Key_Tab)

    assert native.toPlainText() == '<div class="card">'


# --- Enveloppement non destructif et menu contextuel ---


def test_code_editor_wrap_selection_atomic_undo(qtbot):
    """wrap_selection encapsule la sélection dans un bloc d'édition atomique réversible via Ctrl+Z."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor

    native.setPlainText("Texte brut")
    # Sélectionner 'Texte'
    cursor = native.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, cursor.MoveMode.KeepAnchor)
    native.setTextCursor(cursor)
    assert native.textCursor().selectedText() == "Texte"

    # Envelopper dans <b>...</b>
    native.wrap_selection("<b>", "</b>")
    assert native.toPlainText() == "<b>Texte</b> brut"

    # Annulation atomique (un seul undo rétablit le texte initial)
    native.undo()
    assert native.toPlainText() == "Texte brut"


def test_code_editor_wrap_selection_empty_placeholder_positions_cursor(qtbot):
    """Sans sélection active, wrap_selection insère le placeholder et positionne le curseur au centre."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor

    native.setPlainText("")
    with patch.object(native, "setFocus") as mock_focus:
        native.wrap_selection("<div>\n", "\n</div>", empty_placeholder="  ")
        mock_focus.assert_called_once()

    assert native.toPlainText() == "<div>\n  \n</div>"
    # Curseur positionné après les 2 espaces d'indentation
    assert native.textCursor().position() == len("<div>\n  ")


def test_code_editor_apply_css_class_html_inline(qtbot):
    """En HTML, une sélection mono-ligne est enveloppée dans <span class="{classe}">...</span>."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor

    native.setPlainText("Texte mono-ligne")
    cursor = native.textCursor()
    cursor.select(cursor.SelectionType.Document)
    native.setTextCursor(cursor)

    native.apply_css_class("highlight")
    assert native.toPlainText() == '<span class="highlight">Texte mono-ligne</span>'


def test_code_editor_apply_css_class_html_multiline(qtbot):
    """En HTML, une sélection multi-lignes est enveloppée dans <div class="{classe}">\n...\n</div>."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor

    native.setPlainText("Ligne 1\nLigne 2")
    cursor = native.textCursor()
    cursor.select(cursor.SelectionType.Document)
    native.setTextCursor(cursor)

    native.apply_css_class("card")
    assert native.toPlainText() == '<div class="card">\nLigne 1\nLigne 2\n</div>'


def test_code_editor_apply_css_class_html_empty_selection(qtbot):
    """En HTML sans sélection, l'application d'une classe insère la div vierge avec curseur au centre."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor

    native.setPlainText("")
    with patch.object(native, "setFocus") as mock_focus:
        native.apply_css_class("af-callout-info")
        mock_focus.assert_called_once()

    assert native.toPlainText() == '<div class="af-callout-info">\n  \n</div>'
    assert native.textCursor().position() == len('<div class="af-callout-info">\n  ')


def test_code_editor_apply_css_class_css_mode(qtbot):
    """En CSS, une sélection est enveloppée dans .{classe} { ... }, ou insère le squelette vierge."""
    from ankiforge.ui.components.code_editor import CodeEditorWithGutter

    wrapper = CodeEditorWithGutter(placeholder="", mode="css")
    qtbot.addWidget(wrapper)
    wrapper.show()
    native = wrapper.editor

    # 1. Avec sélection de déclarations
    native.setPlainText("color: red;\nfont-size: 14px;")
    cursor = native.textCursor()
    cursor.select(cursor.SelectionType.Document)
    native.setTextCursor(cursor)

    native.apply_css_class("custom-badge")
    assert native.toPlainText() == ".custom-badge {\ncolor: red;\nfont-size: 14px;\n}"

    # 2. Sans sélection : squelette vierge
    native.setPlainText("")
    with patch.object(native, "setFocus") as mock_focus:
        native.apply_css_class("empty-rule")
        mock_focus.assert_called_once()

    assert native.toPlainText() == ".empty-rule {\n  \n}"
    assert native.textCursor().position() == len(".empty-rule {\n  ")


def test_card_models_view_condition_pill_wraps_selection(qtbot, mock_db):
    """Dans CardModelsView, les pilules de condition Anki enveloppent la sélection existante."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(
        name=f"Modèle Cond {uid}",
        fields_schema=json.dumps(["Question", "Reponse"]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Question}}", "afmt": "{{Reponse}}"}]),
        css_style=".card {}",
    )

    view = CardModelsView()
    qtbot.addWidget(view)
    view.show()

    # Sélectionner le modèle
    for i in range(view.list_widget.count()):
        item = view.list_widget.item(i)
        if item.data(Qt.ItemDataRole.UserRole).id == nt.id:
            view.list_widget.setCurrentItem(item)
            break

    # Se positionner sur l'éditeur Front (index 1)
    view.editor_stack.setCurrentIndex(1)
    front_native = view.front_html_wrapper.editor
    front_native.setPlainText("Texte optionnel")
    cursor = front_native.textCursor()
    cursor.select(cursor.SelectionType.Document)
    front_native.setTextCursor(cursor)

    # Invoquer l'insertion de condition pour le champ 'Question'
    view._insert_condition_to_active_editor("Question")

    assert front_native.toPlainText() == "{{#Question}}\nTexte optionnel\n{{/Question}}"

    # Cas sans sélection
    front_native.setPlainText("")
    view._insert_condition_to_active_editor("Question")
    assert front_native.toPlainText() == "{{#Question}}\n  {{Question}}\n{{/Question}}"


def test_card_models_view_css_pill_wraps_selection_and_empty(qtbot, mock_db):
    """Dans CardModelsView, cliquer sur une pilule de classe CSS applique le wrapping à l'éditeur actif."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(
        name=f"Modèle PillWrap {uid}",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
        css_style=".card {}\n.highlight {}",
    )

    view = CardModelsView()
    qtbot.addWidget(view)
    view.show()

    for i in range(view.list_widget.count()):
        item = view.list_widget.item(i)
        if item.data(Qt.ItemDataRole.UserRole).id == nt.id:
            view.list_widget.setCurrentItem(item)
            break

    view.editor_stack.setCurrentIndex(1)
    front_native = view.front_html_wrapper.editor

    # 1. Sélection mono-ligne -> span
    front_native.setPlainText("Mot clé")
    cursor = front_native.textCursor()
    cursor.select(cursor.SelectionType.Document)
    front_native.setTextCursor(cursor)

    view._insert_css_class_to_active_editor("highlight")
    assert front_native.toPlainText() == '<span class="highlight">Mot clé</span>'

    # 2. Sélection multi-lignes -> div
    front_native.setPlainText("Para 1\nPara 2")
    cursor = front_native.textCursor()
    cursor.select(cursor.SelectionType.Document)
    front_native.setTextCursor(cursor)

    view._insert_css_class_to_active_editor("card")
    assert front_native.toPlainText() == '<div class="card">\nPara 1\nPara 2\n</div>'


def test_code_editor_context_menu_applies_css_class(qtbot):
    """Le menu contextuel propose 'Appliquer la classe CSS' et applique le wrapping au texte sélectionné."""
    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor
    native.set_custom_classes(["custom-alert"])

    native.setPlainText("Avertissement")
    cursor = native.textCursor()
    cursor.select(cursor.SelectionType.Document)
    native.setTextCursor(cursor)

    menu = native.create_context_menu()
    assert menu is not None

    # Trouver le sous-menu "Appliquer la classe CSS"
    sub_menu = None
    for action in menu.actions():
        if action.menu() and "Appliquer la classe CSS" in action.text():
            sub_menu = action.menu()
            break

    assert sub_menu is not None
    action_texts = [a.text() for a in sub_menu.actions()]
    assert ".card" in action_texts
    assert ".custom-alert" in action_texts

    # Déclencher l'action pour .custom-alert
    for a in sub_menu.actions():
        if a.text() == ".custom-alert":
            a.trigger()
            break

    assert native.toPlainText() == '<span class="custom-alert">Avertissement</span>'


def test_code_editor_context_menu_event_triggers_menu_exec(qtbot):
    """L'événement contextMenuEvent ouvre le menu contextuel sans bloquer l'exécution."""
    from unittest.mock import MagicMock

    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QContextMenuEvent

    wrapper = _make_html_editor(qtbot)
    native = wrapper.editor

    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(10, 10), QPoint(100, 100))
    dummy_menu = MagicMock()
    with patch.object(native, "create_context_menu", return_value=dummy_menu) as mock_create:
        native.contextMenuEvent(event)
        mock_create.assert_called_once_with(event.pos())
        dummy_menu.exec.assert_called_once_with(event.globalPos())
