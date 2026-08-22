from typing import Any, List
import json
import uuid
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from ankiforge.database.models import NoteTypeModel
from ankiforge.services.cards.snippet_library import SnippetLibrary
from ankiforge.ui.dialogs.css_conflict_dialog import CSSConflictDialog
from ankiforge.ui.dialogs.model_import_dialog import ModelImportDialog
from ankiforge.ui.views.card_models_view import CardModelsView


def _get_flow_layout_texts(flow_layout: Any) -> List[str]:
    texts: List[str] = []
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

    # Le bouton Cloze doit être masqué pour un modèle basique
    assert view._is_cloze_active() is False
    assert view.helper_category_buttons["Cloze"].isHidden() is True

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
    assert view.helper_category_buttons["Cloze"].isHidden() is False

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
    """Vérifie que les boutons Nouveau, Dupliquer, Importer JSON et Supprimer appliquent WA_Hover et leurs rôles."""
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent

    view = CardModelsView()
    qtbot.addWidget(view)

    btn_new = view.btn_new
    btn_dup = view.btn_duplicate
    btn_imp = view.btn_import_json
    btn_del = view.btn_del

    # Vérification des rôles sémantiques
    assert btn_new.property("role") == "primary"
    assert btn_dup.property("role") == "secondary"
    assert btn_imp.property("role") == "secondary"
    assert btn_del.property("role") == "danger"

    # Vérification de l'activation de WA_Hover pour les transitions
    assert btn_new.testAttribute(Qt.WidgetAttribute.WA_Hover)
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
    from ankiforge.ui.components.snippet_drawer import SnippetCardWidget
    from ankiforge.services.cards.snippet_library import SnippetLibrary

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
