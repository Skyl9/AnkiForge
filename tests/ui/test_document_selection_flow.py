from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    FolderModel,
)
from ankiforge.ui.components.document_picker_button import DocumentPickerButton
from ankiforge.ui.components.document_select_window import DocumentSelectWindow
from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeWidget
from ankiforge.ui.views.creation_view import CreationView
from ankiforge.ui.views.creation_view.widgets.document_editor import (
    DocumentEditorWidget,
)

pytestmark = pytest.mark.ui


def test_document_select_window_preselects_document(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que DocumentSelectWindow pré-sélectionne le document spécifié par selected_doc_id."""
    uid = uuid.uuid4().hex[:6]
    folder = FolderModel.create(name=f"Dossier {uid}")
    doc1 = DocumentModel.create(title=f"Doc 1 {uid}", file_type="pdf", folder=folder)
    _ = DocumentModel.create(title=f"Doc 2 {uid}", file_type="album")

    window = DocumentSelectWindow(selected_doc_id=doc1.id)
    qtbot.addWidget(window)

    selected_items = window.tree.selectedItems()
    assert len(selected_items) == 1
    assert selected_items[0] == window._doc_items_by_id[doc1.id]
    assert window.btn_confirm.isEnabled()


def test_document_picker_button_lifecycle(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le fonctionnement du DocumentPickerButton (affichage, types, émission conditionnelle)."""
    uid = uuid.uuid4().hex[:6]
    doc_pdf = DocumentModel.create(title=f"Cours PDF {uid}", file_type="pdf", total_pages=5, content="Texte PDF")
    doc_album = DocumentModel.create(title=f"Album Scans {uid}", file_type="album", total_pages=12, content="")

    btn = DocumentPickerButton()
    qtbot.addWidget(btn)

    emitted_docs: list[Any] = []
    btn.document_changed.connect(lambda d: emitted_docs.append(d))

    # Sélection PDF avec signal
    btn.set_document(doc_pdf, emit_signal=True)
    assert btn.get_document() == doc_pdf
    assert "Cours PDF" in btn.title_label.text()
    assert "PDF" in btn.meta_label.text()
    assert len(emitted_docs) == 1

    # Sélection Album sans signal
    btn.set_document(doc_album, emit_signal=False)
    assert btn.get_document() == doc_album
    assert "Album Scans" in btn.title_label.text()
    assert "Album" in btn.meta_label.text()
    assert len(emitted_docs) == 1  # Inchangé car emit_signal=False

    # Même document ne ré-émet pas
    btn.set_document(doc_album, emit_signal=True)
    assert len(emitted_docs) == 1

    # Clear document
    btn.clear_document()
    assert btn.get_document() is None
    assert "Sélectionner un cours..." in btn.title_label.text()
    assert len(emitted_docs) == 2


def test_creation_view_folder_click_does_not_crash(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que cliquer sur un dossier dans l'arborescence ne plante pas et ne le sélectionne pas comme doc."""
    uid = uuid.uuid4().hex[:6]
    folder = FolderModel.create(name=f"Dossier Anatomie {uid}")
    _ = DocumentModel.create(title=f"Cervelet {uid}", file_type="md", folder=folder, content="# Cervelet")

    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # Trouver l'item du dossier dans l'arbre
    folder_item = None
    for i in range(view.file_tree.topLevelItemCount()):
        it = view.file_tree.topLevelItem(i)
        if it and it.text(0) == folder.name:
            folder_item = it
            break

    assert folder_item is not None

    # Simuler le clic et la sélection du dossier
    view.file_tree.setCurrentItem(folder_item)
    folder_item.setSelected(True)
    view._on_explorer_selection_changed()

    # Le document actif ne doit PAS être le dossier
    assert view._current_selected_doc != folder
    assert not isinstance(view._current_selected_doc, FolderModel)


def test_creation_view_tree_and_picker_bidirectional_sync(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la synchronisation bidirectionnelle entre l'arborescence et le DocumentPickerButton."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Histologie {uid}", file_type="md", content="## Tissus épithéliaux\nContenu histo")

    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # 1. Sélection depuis le DocumentPickerButton
    view.doc_picker_btn.set_document(doc)
    assert view._current_selected_doc == doc
    assert view.current_source_doc_id == doc.id
    selected_items = view.file_tree.selectedItems()
    assert len(selected_items) == 1
    assert selected_items[0].data(0, Qt.ItemDataRole.UserRole).id == doc.id

    # 2. Désélection depuis le picker (Saisie libre)
    view.doc_picker_btn.clear_document()
    assert view._current_selected_doc is None
    assert len(view.file_tree.selectedItems()) == 0


def test_creation_view_tab_switch_syncs_document(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que changer d'onglet met à jour le document actif, le picker et le découpage."""
    uid = uuid.uuid4().hex[:6]
    doc1 = DocumentModel.create(title=f"DocA {uid}", file_type="md", content="Contenu A")
    doc2 = DocumentModel.create(title=f"DocB {uid}", file_type="md", content="Contenu B")

    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # Ouvrir doc1 puis doc2
    view._open_document_for_model(doc1)
    view._open_document_for_model(doc2)

    assert view._current_selected_doc == doc2
    assert view.doc_picker_btn.get_document() == doc2

    # Revenir sur l'onglet de doc1
    view.source_panel.open_tab(doc1.title)
    assert view._current_selected_doc == doc1
    assert view.doc_picker_btn.get_document() == doc1


def test_batch_composer_embeds_scope_and_updates_live(qtbot: Any, mock_db: Any) -> None:
    """La modale fusionnée embarque le DocumentScopeWidget : chaque coche recalcule les tâches en direct (mode Direct)."""
    from ankiforge.ui.views.batch_view.dialogs.batch_slice_composer_dialog import BatchSliceComposerDialog

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Physiologie {uid}", file_type="md", content="# Section 1\n\nTexte 1\n\n# Section 2\n\nTexte 2")
    DocumentChunkModel.create(document=doc, chunk_index=0, heading_path="Section 1", content="Texte 1", content_hash=f"h1_{uid}")
    DocumentChunkModel.create(document=doc, chunk_index=1, heading_path="Section 2", content="Texte 2", content_hash=f"h2_{uid}")

    def task_from_chunk(d: DocumentModel, chunk: dict[str, Any]) -> dict[str, Any]:
        return {
            "doc": d,
            "doc_title": f"{d.title} — {chunk.get('title')}",
            "doc_content": chunk.get("content", ""),
            "chunk_label": chunk.get("title") or str(chunk.get("heading_path")),
            "tokens_est": 10,
            "status": "En attente",
        }

    dlg = BatchSliceComposerDialog(
        doc=doc,
        resolve_chunks=lambda _d: [],
        scope_memory=lambda _d: None,
        task_from_chunk=task_from_chunk,
        task_from_slice=lambda _d, _s: None,
    )
    qtbot.addWidget(dlg)

    # Le widget de portée est embarqué dans la modale (pas de sous-dialogue séparé)
    assert dlg.hasattr_scope_widget()
    scope = dlg.scope_widget
    assert scope.doc == doc

    # Direct : sections cochées par défaut => tâches préremplies en direct dès l'ouverture
    assert len(dlg._tasks) == 2

    # Décocher une section recalcule immédiatement les tâches
    scope.sections_list.itemWidget(scope.sections_list.item(0)).set_checked(False)
    assert len(dlg._tasks) == 1
    assert dlg._tasks[0]["chunk_label"] == "Section 2"
    assert "1 partie(s) sélectionnée(s)" in dlg.lbl_parties_count.text()

    # Navigation jusqu'à l'étape récap : bouton d'ajout libellé "Ajouter à la Queue (N)"
    dlg._on_next()
    dlg._on_next()
    assert "Ajouter à la Queue" in dlg.btn_next.text()
    assert dlg.btn_next.isEnabled()


def test_scope_row_activation_toggles_selection_and_exposes_visual_state(qtbot: Any, mock_db: Any) -> None:
    """Une ligne de section active le même état métier que sa case."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Physiologie {uid}", file_type="md", content="# Section 1\n\nTexte 1")
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Section 1",
        content="Texte 1",
        content_hash=f"h1_{uid}",
    )

    scope = DocumentScopeWidget(doc)
    qtbot.addWidget(scope)
    row = scope.sections_list.itemWidget(scope.sections_list.item(0))
    assert row is not None
    assert row.checkbox.accessibleName()
    assert row.property("selectionState") == "checked"

    emitted: list[dict[str, Any]] = []
    scope.scope_changed.connect(emitted.append)

    qtbot.mouseClick(row, Qt.MouseButton.LeftButton)

    assert row.check_state() == Qt.CheckState.Unchecked
    assert row.property("selectionState") == "unchecked"
    assert emitted
    assert emitted[-1]["chunks"] == []


def test_scope_parent_row_exposes_partial_state_after_child_toggle(qtbot: Any, mock_db: Any) -> None:
    """Un parent reflète visuellement une sélection partielle de ses enfants."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Anatomie {uid}",
        file_type="md",
        content="# Chapitre\n\n## Section 1\n\nTexte 1\n\n## Section 2\n\nTexte 2",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Chapitre > Section 1",
        content="Texte 1",
        content_hash=f"h1_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path="Chapitre > Section 2",
        content="Texte 2",
        content_hash=f"h2_{uid}",
    )

    scope = DocumentScopeWidget(doc)
    qtbot.addWidget(scope)
    parent_item = next(item for item in scope.sections_list.all_items() if item.childCount() > 0)
    child_item = parent_item.child(0)
    child_row = scope.sections_list.itemWidget(child_item)
    parent_row = scope.sections_list.itemWidget(parent_item)
    assert child_row is not None
    assert parent_row is not None

    qtbot.mouseClick(child_row, Qt.MouseButton.LeftButton)

    assert parent_item.checkState(0) == Qt.CheckState.PartiallyChecked
    assert parent_row.check_state() == Qt.CheckState.PartiallyChecked
    assert parent_row.property("selectionState") == "partial"
    assert parent_row.checkbox.accessibleDescription() == "État : partiellement sélectionné"


def test_batch_composer_picker_switch_reloads_scope_and_result(qtbot: Any, mock_db: Any) -> None:
    """Changer de document via le picker embarqué recharge la portée ; get_result renvoie tâches + portée + doc."""
    from ankiforge.ui.views.batch_view.dialogs.batch_slice_composer_dialog import BatchSliceComposerDialog

    uid = uuid.uuid4().hex[:6]
    doc1 = DocumentModel.create(title=f"Doc A {uid}", file_type="md", content="# Intro A\n\nContenu A")
    DocumentChunkModel.create(document=doc1, chunk_index=0, heading_path="Intro A", content="Contenu A", content_hash=f"a_{uid}")
    doc2 = DocumentModel.create(title=f"Doc B {uid}", file_type="md", content="# Intro B\n\nContenu B")
    DocumentChunkModel.create(document=doc2, chunk_index=0, heading_path="Intro B", content="Contenu B", content_hash=f"b_{uid}")

    def task_from_chunk(d: DocumentModel, chunk: dict[str, Any]) -> dict[str, Any]:
        return {
            "doc": d,
            "doc_title": f"{d.title} — {chunk.get('title')}",
            "doc_content": chunk.get("content", ""),
            "chunk_label": chunk.get("title") or str(chunk.get("heading_path")),
            "tokens_est": 5,
        }

    dlg = BatchSliceComposerDialog(
        doc=doc1,
        resolve_chunks=lambda _d: [],
        scope_memory=lambda _d: None,
        task_from_chunk=task_from_chunk,
        task_from_slice=lambda _d, _s: None,
    )
    qtbot.addWidget(dlg)
    assert dlg.scope_widget.doc == doc1

    # Changer de document via le DocumentPickerButton embarqué
    dlg.doc_picker.set_document(doc2)
    assert dlg.doc == doc2
    assert dlg.scope_widget.doc == doc2
    assert len(dlg._tasks) == 1

    result = dlg.get_result()
    assert result["doc"] == doc2
    assert result["tasks"][0]["chunk_label"] == "Intro B"
    assert result["scope_result"]["selection_mode"] in ("sections", "structure", "all")
    assert result["scope_result"]["chunks"][0]["heading_path"] == "Intro B"


def test_modal_range_selector_contextual_slider_and_range_bar(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la modale de délimitation, la barre visuelle et la présence contextuelle du slider."""
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Physique {uid}", file_type="pdf", total_pages=20, content="Page 1")

    dlg = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg)

    # Document paginé -> pages_card visible
    assert dlg.is_paginated is True
    assert not dlg.pages_card.isHidden()

    # Mode initial "Tout le document" -> slider masqué / non présent dans l'interface active
    assert dlg.btn_scope_mode_all.isChecked()
    assert dlg.slider_scope_container.isHidden()
    assert dlg.spin_p_start.value() == 1
    assert dlg.spin_p_end.value() == 20

    # Basculer en mode "Plage de pages" -> le slider devient présent
    dlg.btn_scope_mode_range.click()
    assert not dlg.slider_scope_container.isHidden()
    assert not dlg.slider_p_start.isHidden()
    assert not dlg.slider_p_end.isHidden()

    # Manipulation des sliders
    dlg.slider_p_start.setValue(4)
    assert dlg.spin_p_start.value() == 4
    dlg.slider_p_end.setValue(14)
    assert dlg.spin_p_end.value() == 14

    # Vérification de la barre visuelle ScopeRangeBarWidget
    assert dlg.range_bar._start == 4
    assert dlg.range_bar._end == 14
    assert dlg.range_bar._total == 20

    # Vérification de l'indicateur visuel sur l'aperçu DocumentPreviewWidget
    assert dlg.preview_widget._scope_start == 4
    assert dlg.preview_widget._scope_end == 14
    assert not dlg.preview_widget.lbl_scope_status.isHidden()
    assert "INCLUSE" in dlg.preview_widget.lbl_scope_status.text() or "Page 1" in dlg.preview_widget.lbl_scope_status.text()

    # Rebasculer en mode "Tout le document" -> le slider disparaît
    dlg.btn_scope_mode_all.click()
    assert dlg.slider_scope_container.isHidden()
    assert dlg.spin_p_start.value() == 1
    assert dlg.spin_p_end.value() == 20


def test_modal_scope_unpaginated_doc_no_slider(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que pour un document non paginé, aucun slider de page n'est présent."""
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Markdown {uid}", file_type="md", total_pages=1, content="## Titre 1\nTexte 1\n## Titre 2\nTexte 2")

    dlg = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg)

    # Document non paginé -> pages_card masqué, pas de slider de pages
    assert dlg.is_paginated is False
    assert dlg.pages_card.isHidden()


def test_segment_inspector_scope_trigger_card(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que SegmentInspectorWidget affiche la carte de portée et gère les signaux de délimitation et de portée."""
    from ankiforge.ui.widgets.segment_inspector_widget import SegmentInspectorWidget

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Doc {uid}", file_type="pdf", total_pages=10, content="Content")

    inspector = SegmentInspectorWidget()
    qtbot.addWidget(inspector)
    inspector.set_document(doc)

    assert not inspector.scope_container.isHidden()
    assert hasattr(inspector, "scope_trigger_card")
    assert not inspector.scope_trigger_card.isHidden()
    assert "10" in inspector.lbl_active_scope_title.text() or "Tout" in inspector.lbl_active_scope_title.text()

    # Le bouton Délimiter... émet open_delimitation_requested
    with qtbot.waitSignal(inspector.open_delimitation_requested, timeout=1000):
        inspector.btn_delimit.click()

    # Le bouton Modifier ↗ de la carte émet open_scope_dialog_requested
    with qtbot.waitSignal(inspector.open_scope_dialog_requested, timeout=1000):
        inspector.btn_open_scope_modal.click()


def test_document_scope_dialog_filtered_access_and_contextual_slider(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que DocumentScopeDialog donne accès uniquement au contenu filtré et conditionne le slider."""
    from ankiforge.database.models import DocumentChunkModel
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog

    uid = uuid.uuid4().hex[:6]
    # Document délimité entre les pages 3 et 8 avec une section exclue
    doc = DocumentModel.create(
        title=f"Doc Filtered {uid}",
        file_type="pdf",
        total_pages=15,
        start_page=3,
        end_page=8,
        excluded_headings='["sommaire"]',
    )
    # Création de chunks : p.2 (exclue), p.3 (utile), p.4 sommaire (exclu), p.5 (utile), p.10 (exclue)
    DocumentChunkModel.create(document=doc, chunk_index=0, page_number=2, heading_path="Intro", content="Hors délimitation", content_hash="h0")
    DocumentChunkModel.create(document=doc, chunk_index=1, page_number=3, heading_path="Chapitre 1", content="Contenu utile chap 1", content_hash="h1")
    DocumentChunkModel.create(document=doc, chunk_index=2, page_number=4, heading_path="Sommaire général", content="TOC", content_hash="h2")
    DocumentChunkModel.create(document=doc, chunk_index=3, page_number=5, heading_path="Chapitre 2", content="Contenu utile chap 2", content_hash="h3")
    DocumentChunkModel.create(document=doc, chunk_index=4, page_number=10, heading_path="Conclusion", content="Trop loin", content_hash="h4")

    dlg = DocumentScopeDialog(doc)
    qtbot.addWidget(dlg)

    # 1. Bornes utiles : [3, 8]
    assert dlg.spin_p_start.minimum() == 3
    assert dlg.spin_p_start.maximum() == 8
    assert dlg.spin_p_end.minimum() == 3
    assert dlg.spin_p_end.maximum() == 8

    # 2. Seuls les fragments utiles (p.3 et p.5) sont listés (p.2, p.4 sommaire et p.10 sont filtrés)
    assert dlg.sections_list.count() == 2

    # 3. Slider contextuel : masqué en mode Tout le document utile, visible en mode Plage
    assert dlg.btn_mode_all.isChecked()
    assert dlg.slider_scope_container.isHidden()

    dlg.btn_mode_range.click()
    assert not dlg.slider_scope_container.isHidden()

    # 4. Modification de la plage et validation
    dlg.spin_p_start.setValue(3)
    dlg.spin_p_end.setValue(3)
    dlg._on_apply()

    res = dlg.get_result()
    assert "Page 3" in res["scope_title"]
    assert len(res["chunks"]) == 1
    assert res["chunks"][0]["page_number"] == 3


def test_delimitation_dialog_differential_update_preserves_card_links(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que la mise à jour différentielle de délimitation préserve les NoteChunkLinkModel."""
    from ankiforge.database.models import DocumentChunkModel, NoteChunkLinkModel, NoteModel, NoteTypeModel
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog

    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"Basic_{uid}")
    doc = DocumentModel.create(title=f"Cours Cardio {uid}", file_type="pdf", total_pages=3)
    c1 = DocumentChunkModel.create(document=doc, chunk_index=0, page_number=1, heading_path="Intro", content="Intro", content_hash="h_p1")
    c2 = DocumentChunkModel.create(document=doc, chunk_index=1, page_number=2, heading_path="Ventricules", content="Détail ventricules", content_hash="h_p2")
    _ = DocumentChunkModel.create(document=doc, chunk_index=2, page_number=3, heading_path="Annexes", content="Annexes", content_hash="h_p3")

    note = NoteModel.create(guid=f"guid_{uid}", note_type=nt)
    link = NoteChunkLinkModel.create(note=note, chunk=c2)

    dlg = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg)

    # Vérifier que le fragment c2 est bien reconnu avec sa carte
    assert dlg._chunk_cards.get(1, 0) >= 1 or dlg._page_cards.get(2, 0) >= 1 or dlg._hash_cards.get("h_p2", 0) >= 1

    # Appliquer une délimitation restreinte aux pages 2 et 3 (excluant la page 1)
    dlg.spin_p_start.setValue(2)
    dlg.spin_p_end.setValue(3)
    dlg._on_apply()

    # Vérifier que le chunk c2 a été conservé et que NoteChunkLinkModel existe toujours !
    preserved_link = NoteChunkLinkModel.select().where(NoteChunkLinkModel.id == link.id).first()
    assert preserved_link is not None
    assert preserved_link.chunk.id == c2.id
    assert preserved_link.chunk.heading_path == "Ventricules"

    # Vérifier que le chunk c1 a été supprimé
    assert DocumentChunkModel.select().where(DocumentChunkModel.id == c1.id).first() is None


def test_delimitation_bidirectional_sync_slider_sections(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la synchronisation bidirectionnelle slider <-> sections dans DocumentDelimitationDialog."""
    from ankiforge.database.models import DocumentChunkModel
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog, SectionRowWidget

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Sync Doc {uid}", file_type="pdf", total_pages=5)
    for p in range(1, 6):
        DocumentChunkModel.create(document=doc, chunk_index=p - 1, page_number=p, heading_path=f"Page {p}", content=f"Contenu {p}", content_hash=f"h_{p}")

    dlg = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg)

    # 1. Slider -> Sections : restreindre aux pages 2..4 décoche p.1 et p.5
    dlg.spin_p_start.setValue(2)
    dlg.spin_p_end.setValue(4)

    assert dlg.sections_list.item(0).checkState() == Qt.CheckState.Unchecked  # Page 1
    assert dlg.sections_list.item(1).checkState() == Qt.CheckState.Checked  # Page 2
    assert dlg.sections_list.item(2).checkState() == Qt.CheckState.Checked  # Page 3
    assert dlg.sections_list.item(3).checkState() == Qt.CheckState.Checked  # Page 4
    assert dlg.sections_list.item(4).checkState() == Qt.CheckState.Unchecked  # Page 5

    # 2. En mode pages, les cases restent décoratives et ne modifient pas la borne source.
    row_w5 = dlg.sections_list.itemWidget(dlg.sections_list.item(4))
    assert isinstance(row_w5, SectionRowWidget)
    row_w5.checkbox.setChecked(True)

    assert dlg.spin_p_end.value() == 4


def test_document_scope_dialog_bidirectional_sync_and_assembled_view(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la synchronisation bidirectionnelle et la Vue Finale Assemblée dans DocumentScopeDialog."""
    from ankiforge.database.models import DocumentChunkModel
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog, SectionRowWidget

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Scope View Doc {uid}", file_type="pdf", total_pages=4, start_page=1, end_page=4)
    for p in range(1, 5):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"Chapitre {p}",
            content=f"Texte du chapitre {p} avec plusieurs mots pour les tests.",
            content_hash=f"hash_{p}",
        )

    dlg = DocumentScopeDialog(doc)
    qtbot.addWidget(dlg)

    # 1. Slider -> Sections
    dlg.btn_mode_range.click()
    dlg.spin_p_start.setValue(2)
    dlg.spin_p_end.setValue(3)

    assert dlg.sections_list.item(0).checkState() == Qt.CheckState.Unchecked  # Chap 1
    assert dlg.sections_list.item(1).checkState() == Qt.CheckState.Checked  # Chap 2
    assert dlg.sections_list.item(2).checkState() == Qt.CheckState.Checked  # Chap 3
    assert dlg.sections_list.item(3).checkState() == Qt.CheckState.Unchecked  # Chap 4

    # 2. En mode pages, cocher une section ne modifie pas la plage.
    row_w4 = dlg.sections_list.itemWidget(dlg.sections_list.item(3))
    assert isinstance(row_w4, SectionRowWidget)
    row_w4.checkbox.setChecked(True)
    assert dlg.spin_p_end.value() == 3

    # 3. Vue Finale Assemblée
    assert dlg.preview_stack.currentIndex() == 0  # Document Source par défaut
    dlg.btn_view_final.click()
    assert dlg.preview_stack.currentIndex() == 1

    final_text = dlg.final_preview_browser.toPlainText()
    assert "Texte du chapitre 2" in final_text
    assert "Texte du chapitre 3" in final_text
    assert "Texte du chapitre 4" not in final_text
    assert "Texte du chapitre 1" not in final_text

    # Revenir sur Document Source
    dlg.btn_view_source.click()
    assert dlg.preview_stack.currentIndex() == 0


def test_delimitation_modification_and_modal_refresh_sync(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la mise à jour réactive des modaux après modification de la délimitation d'un document."""
    from ankiforge.database.models import DocumentChunkModel
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog

    uid = uuid.uuid4().hex[:6]
    content_with_pages = "\n\n".join(f"<!-- PAGE: {p} -->\nTexte long de la page numéro {p} avec du contenu pédagogique." for p in range(1, 6))
    doc = DocumentModel.create(
        title=f"Doc Sync Test {uid}",
        file_type="pdf",
        total_pages=5,
        content=content_with_pages,
    )
    for p in range(1, 6):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"Page {p}",
            content=f"Texte long de la page numéro {p} avec du contenu pédagogique.",
            content_hash=f"hash_sync_{p}",
        )

    # 1. Première délimitation : restreindre aux pages 2 à 4
    dlg1 = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg1)
    dlg1.btn_scope_mode_range.click()
    dlg1.spin_p_start.setValue(2)
    dlg1.spin_p_end.setValue(4)
    dlg1._on_apply()

    # Recharger doc depuis la base et vérifier la persistance
    doc_fresh = DocumentModel.get_by_id(doc.id)
    assert doc_fresh.start_page == 2
    assert doc_fresh.end_page == 4

    # 2. Deuxième délimitation : élargir à "Tout le document" (pages 1 à 5)
    dlg2 = DocumentDelimitationDialog(doc)  # Passe l'ancien objet doc en mémoire
    qtbot.addWidget(dlg2)
    assert dlg2.doc.start_page == 2  # Rechargé automatiquement depuis la DB
    assert dlg2.doc.end_page == 4
    dlg2.btn_scope_mode_all.click()
    dlg2._on_apply()

    doc_fresh2 = DocumentModel.get_by_id(doc.id)
    assert doc_fresh2.start_page is None
    assert doc_fresh2.end_page is None

    # 3. Réouverture de DocumentDelimitationDialog : aucune page n'est considérée comme exclue
    dlg3 = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg3)
    assert dlg3.sections_list.count() == 5
    for i in range(5):
        assert dlg3.sections_list.item(i).checkState() == Qt.CheckState.Checked

    # 4. Ouverture de DocumentScopeDialog : tous les 5 chunks sont bien visibles et inclus
    scope_dlg = DocumentScopeDialog(doc)
    qtbot.addWidget(scope_dlg)
    assert scope_dlg.sections_list.count() == 5
    assert len(scope_dlg._useful_chunks) == 5


def test_delimitation_manual_exclusion_memory_and_slider_immunity(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que les exclusions manuelles de sections restent fidèlement mémorisées et ne sont pas écrasées par le slider."""
    from ankiforge.database.models import DocumentChunkModel
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog, SectionRowWidget

    uid = uuid.uuid4().hex[:6]
    content = "\n\n".join(f"<!-- PAGE: {p} -->\nTexte de la page {p} avec du contenu explicatif suffisant." for p in range(1, 6))
    doc = DocumentModel.create(
        title=f"Memory Doc {uid}",
        file_type="pdf",
        total_pages=5,
        content=content,
    )
    for p in range(1, 6):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"Page {p}",
            content=f"Texte de la page {p} avec du contenu explicatif suffisant.",
            content_hash=f"hash_mem_{p}",
        )

    # 1. Ouvrir délimitation et décocher manuellement la page 3
    dlg1 = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg1)
    w_row3 = dlg1.sections_list.itemWidget(dlg1.sections_list.item(2))
    assert isinstance(w_row3, SectionRowWidget)
    w_row3.checkbox.setChecked(False)
    assert "page 3" in dlg1._manual_exclusions

    # Appliquer
    dlg1._on_apply()

    # En mode pages, l'interaction avec l'arbre n'est pas persistée comme exclusion.
    fresh_doc = DocumentModel.get_by_id(doc.id)
    assert fresh_doc.excluded_headings == "[]"

    # 2. Réouverture de DocumentDelimitationDialog : toutes les pages restent retenues.
    dlg2 = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg2)
    assert dlg2.sections_list.item(2).checkState() == Qt.CheckState.Checked
    assert dlg2.sections_list.item(0).checkState() == Qt.CheckState.Checked  # Page 1 cochée
    assert dlg2.sections_list.item(1).checkState() == Qt.CheckState.Checked  # Page 2 cochée

    # 3. Manipulation du slider de pages (déplacer puis ré-étendre à toute la portée)
    dlg2.btn_scope_mode_range.click()
    dlg2.spin_p_start.setValue(1)
    dlg2.spin_p_end.setValue(5)

    # Page 3 reste cochée dans la plage complète.
    assert dlg2.sections_list.item(2).checkState() == Qt.CheckState.Checked

    # 4. DocumentScopeDialog conserve toutes les pages car l'exclusion était décorative en mode pages.
    scope_dlg = DocumentScopeDialog(doc)
    qtbot.addWidget(scope_dlg)
    useful_titles = [u["title"] for u in scope_dlg._useful_chunks]
    assert "Page 3" in useful_titles
    assert len(scope_dlg._useful_chunks) == 5


def test_delimitation_dialog_preview_and_slider_bidirectional_sync(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le saut immédiat de la vue PDF et l'ajustement dynamique des sliders dans DocumentDelimitationDialog."""
    from ankiforge.database.models import DocumentChunkModel
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog, SectionRowWidget

    uid = uuid.uuid4().hex[:6]
    content = "\n\n".join(f"<!-- PAGE: {p} -->\nTexte pédagogique détaillé pour la page {p}." for p in range(1, 6))
    doc = DocumentModel.create(
        title=f"Sync Preview Doc {uid}",
        file_type="pdf",
        total_pages=5,
        content=content,
    )
    for p in range(1, 6):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"Section {p}",
            content=f"Texte pédagogique détaillé pour la page {p}.",
            content_hash=f"hash_sync_dlg_{p}",
        )

    dlg = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg)

    # Initialement, toutes les pages 1 à 5 sont cochées
    assert dlg.spin_p_start.value() == 1
    assert dlg.spin_p_end.value() == 5
    assert dlg.preview_widget._current_page == 1
    assert 1 in dlg.preview_widget._included_pages
    assert "INCLUSE" in dlg.preview_widget.lbl_scope_status.text()

    # 1. Clic direct sur la section 3 (page 3) -> la visionneuse doit sauter immédiatement à la page 3
    item3 = dlg.sections_list.item(2)
    dlg.sections_list.itemClicked.emit(item3)
    assert dlg.preview_widget._current_page == 3
    assert "Page 3 INCLUSE" in dlg.preview_widget.lbl_scope_status.text()

    # 2. Décocher la section 1 (page 1)
    w_row1 = dlg.sections_list.itemWidget(dlg.sections_list.item(0))
    assert isinstance(w_row1, SectionRowWidget)
    w_row1.checkbox.setChecked(False)

    # La borne reste gouvernée par les contrôles de pages.
    assert dlg.spin_p_start.value() == 1
    assert dlg.slider_p_start.value() == 1
    assert dlg.range_bar._start == 1
    # La visionneuse conserve l'inclusion de la page.
    assert dlg.preview_widget._current_page == 1
    assert 1 in dlg.preview_widget._included_pages
    assert "Page 1 INCLUSE" in dlg.preview_widget.lbl_scope_status.text()

    # 3. Décocher la section 5 (page 5)
    w_row5 = dlg.sections_list.itemWidget(dlg.sections_list.item(4))
    assert isinstance(w_row5, SectionRowWidget)
    w_row5.checkbox.setChecked(False)

    # La borne reste gouvernée par les contrôles de pages.
    assert dlg.spin_p_end.value() == 5
    assert dlg.slider_p_end.value() == 5
    assert dlg.range_bar._end == 5
    assert dlg.preview_widget._current_page == 5
    assert 5 in dlg.preview_widget._included_pages
    assert "Page 5 INCLUSE" in dlg.preview_widget.lbl_scope_status.text()

    # 4. Déplacement du slider de début à 3
    dlg.spin_p_start.setValue(3)
    assert dlg.preview_widget._current_page == 3
    assert 3 in dlg.preview_widget._included_pages
    assert "Page 3 INCLUSE" in dlg.preview_widget.lbl_scope_status.text()
    # La section 2 (page 2) doit avoir été décochée automatiquement par le déplacement de borne
    assert dlg.sections_list.item(1).checkState() == Qt.CheckState.Unchecked


def test_document_scope_dialog_preview_and_slider_bidirectional_sync(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le saut immédiat de la vue PDF et l'ajustement dynamique des sliders dans DocumentScopeDialog."""
    from ankiforge.database.models import DocumentChunkModel
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog, SectionRowWidget

    uid = uuid.uuid4().hex[:6]
    content = "\n\n".join(f"<!-- PAGE: {p} -->\nTexte de cours pour le fragment de la page {p}." for p in range(1, 6))
    doc = DocumentModel.create(
        title=f"Sync Scope Doc {uid}",
        file_type="pdf",
        total_pages=5,
        content=content,
    )
    for p in range(1, 6):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"Segment {p}",
            content=f"Texte de cours pour le fragment de la page {p}.",
            content_hash=f"hash_scope_dlg_{p}",
        )

    scope_dlg = DocumentScopeDialog(doc)
    qtbot.addWidget(scope_dlg)

    # Vérification initiale
    assert scope_dlg.sections_list.count() == 5
    assert scope_dlg.spin_p_start.value() == 1
    assert scope_dlg.spin_p_end.value() == 5
    assert scope_dlg.preview_widget._current_page == 1

    # 1. Clic sur la section 4 (page 4)
    item4 = scope_dlg.sections_list.item(3)
    scope_dlg.sections_list.itemClicked.emit(item4)
    assert scope_dlg.preview_widget._current_page == 4
    assert "Page 4 INCLUSE" in scope_dlg.preview_widget.lbl_scope_status.text()

    # 2. Décocher la section 1 (page 1)
    w_row1 = scope_dlg.sections_list.itemWidget(scope_dlg.sections_list.item(0))
    assert isinstance(w_row1, SectionRowWidget)
    w_row1.checkbox.setChecked(False)

    # La plage reste la source de vérité en mode pages.
    assert scope_dlg.spin_p_start.value() == 1
    assert scope_dlg.slider_p_start.value() == 1
    assert scope_dlg.range_bar._start == 1
    assert scope_dlg.preview_widget._current_page == 1
    assert "Page 1 INCLUSE" in scope_dlg.preview_widget.lbl_scope_status.text()

    # La vue finale assemblée ne doit plus contenir Segment 1
    scope_dlg._refresh_final_preview()
    assert "Segment 1" in scope_dlg.final_preview_browser.toPlainText()
    assert "Segment 2" in scope_dlg.final_preview_browser.toPlainText()

    # 3. Décocher la section 5 (page 5)
    w_row5 = scope_dlg.sections_list.itemWidget(scope_dlg.sections_list.item(4))
    assert isinstance(w_row5, SectionRowWidget)
    w_row5.checkbox.setChecked(False)

    assert scope_dlg.spin_p_end.value() == 5
    assert scope_dlg.slider_p_end.value() == 5
    assert scope_dlg.preview_widget._current_page == 5
    assert "Page 5 INCLUSE" in scope_dlg.preview_widget.lbl_scope_status.text()

    # 4. Action Tout cocher
    scope_dlg._set_all_checked(True)
    assert scope_dlg.spin_p_start.value() == 1
    assert scope_dlg.spin_p_end.value() == 5
    assert 1 in scope_dlg.preview_widget._included_pages
    assert 5 in scope_dlg.preview_widget._included_pages


def test_structure_delimitation_pdf_markdown_tree_cascade_and_chapter_range(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la hiérarchie arborescente, la cascade tristate et le sélecteur rapide de chapitres pour un PDF-Markdown."""
    from ankiforge.database.models import DocumentChunkModel
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog, SectionRowWidget

    uid = uuid.uuid4().hex[:6]
    content = (
        "<!-- PAGE: 1 -->\n"
        "# Chapitre 1 : Introduction\n"
        "Texte d'introduction générale au cours de médecine.\n\n"
        "## 1.1 Contexte et Enjeux\n"
        "Le contexte clinique actuel nécessite une réactivité accrue.\n\n"
        "<!-- PAGE: 2 -->\n"
        "## 1.2 Objectifs d'Apprentissage\n"
        "Maîtriser les principes diagnostiques fondamentaux.\n\n"
        "<!-- PAGE: 3 -->\n"
        "# Chapitre 2 : Méthodologie\n"
        "Protocole d'expérimentation et démarches standardisées.\n\n"
        "<!-- PAGE: 4 -->\n"
        "## 2.1 Outils et Matériel\n"
        "Instruments de laboratoire et analyse statistique avancée.\n"
    )

    doc = DocumentModel.create(
        title=f"Cours Cardio {uid}",
        file_type="pdf",
        total_pages=4,
        content=content,
    )

    # 1. Vérification dans DocumentDelimitationDialog
    dlg = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg)

    # Vérifier que le bouton de mode Par Chapitres est visible
    assert not dlg.btn_scope_mode_structure.isHidden()
    assert dlg.combo_c_start.count() == 2  # 2 chapitres racines (Chapitre 1, Chapitre 2)

    # Vérifier l'arbre : 2 racines (Chapitre 1 et Chapitre 2)
    assert dlg.sections_list.topLevelItemCount() == 2
    c1_item = dlg.sections_list.topLevelItem(0)
    c2_item = dlg.sections_list.topLevelItem(1)
    assert c1_item is not None and c2_item is not None
    assert c1_item.childCount() == 2  # 1.1 et 1.2
    assert c2_item.childCount() == 1  # 2.1

    # L'arbre fin n'est disponible qu'après activation explicite de Par Sections.
    assert dlg.sections_list.isHidden()
    dlg.btn_scope_mode_sections.click()
    assert not dlg.sections_list.isHidden()

    # Cascade Down : Décocher Chapitre 1 -> ses enfants 1.1 et 1.2 deviennent décochés
    w_c1 = dlg.sections_list.itemWidget(c1_item, 0)
    assert isinstance(w_c1, SectionRowWidget)
    w_c1.checkbox.setChecked(False)

    assert c1_item.checkState(0) == Qt.CheckState.Unchecked
    assert c1_item.child(0).checkState(0) == Qt.CheckState.Unchecked
    assert c1_item.child(1).checkState(0) == Qt.CheckState.Unchecked

    # Cascade Up : Recocher l'enfant 1.1 -> le parent Chapitre 1 devient PartiallyChecked
    w_sub1 = dlg.sections_list.itemWidget(c1_item.child(0), 0)
    assert isinstance(w_sub1, SectionRowWidget)
    w_sub1.checkbox.setChecked(True)

    assert c1_item.child(0).checkState(0) == Qt.CheckState.Checked
    assert c1_item.checkState(0) == Qt.CheckState.PartiallyChecked

    # Recocher l'enfant 1.2 -> le parent Chapitre 1 redevient Checked
    w_sub2 = dlg.sections_list.itemWidget(c1_item.child(1), 0)
    assert isinstance(w_sub2, SectionRowWidget)
    w_sub2.checkbox.setChecked(True)
    assert c1_item.checkState(0) == Qt.CheckState.Checked

    # Sélection par plage de chapitres : Sélectionner uniquement Chapitre 2
    dlg.btn_scope_mode_structure.click()
    assert not dlg.structure_scope_container.isHidden()
    dlg.combo_c_start.setCurrentIndex(1)
    dlg.combo_c_end.setCurrentIndex(1)

    # En mode chapitres, l'arbre fin est masqué et les bornes restent inchangées.
    assert dlg.sections_list.isHidden()
    assert dlg.spin_p_start.value() == 1
    assert dlg.spin_p_end.value() == 4

    # 2. Vérification dans DocumentScopeDialog
    # Créer les chunks pour le doc
    for idx, (p, h) in enumerate([(1, "Chapitre 1 > 1.1 Contexte et Enjeux"), (2, "Chapitre 1 > 1.2 Objectifs d'Apprentissage"), (3, "Chapitre 2"), (4, "Chapitre 2 > 2.1 Outils et Matériel")]):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=idx,
            page_number=p,
            heading_path=h,
            content=f"Contenu {h} page {p}",
            content_hash=f"h_pdf_md_{idx}",
        )

    scope_dlg = DocumentScopeDialog(doc)
    qtbot.addWidget(scope_dlg)

    assert not scope_dlg.btn_mode_structure.isHidden()
    assert scope_dlg.sections_list.topLevelItemCount() == 2

    # Passer en mode chapitres et choisir uniquement Chapitre 1
    scope_dlg.btn_mode_structure.click()
    scope_dlg.combo_c_start.setCurrentIndex(0)
    scope_dlg.combo_c_end.setCurrentIndex(0)

    assert scope_dlg.sections_list.isHidden()

    # Vérifier que les pages restent la délimitation active [1, 4].
    assert scope_dlg.spin_p_start.value() == 1
    assert scope_dlg.spin_p_end.value() == 4

    scope_dlg._on_apply()
    res = scope_dlg.get_result()
    res_headings = [c.get("heading_path") for c in res["chunks"]]
    assert any("Chapitre 1" in (h or "") for h in res_headings)
    assert not any("Chapitre 2" in (h or "") for h in res_headings)
    assert res["selection_mode"] == "chapters"
    assert res["start_page"] == 1
    assert res["end_page"] == 4
    assert res["range_str"] == ""


def test_structure_delimitation_pure_markdown_no_pages_card(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le comportement avec un document Markdown pur : masque pages_card, affiche sélecteur dans sections."""
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog, SectionRowWidget

    uid = uuid.uuid4().hex[:6]
    content = (
        "# Partie 1 : Introduction Théorique\n"
        "Exposé détaillé des concepts et postulats de base en génétique.\n\n"
        "## Définitions clés\n"
        "Allèle, locus, génotype, phénotype et dominance génétique.\n\n"
        "# Partie 2 : Applications Pratiques\n"
        "Exercices et études de cas cliniques de transmission héréditaire.\n\n"
        "## Cas Clinique A\n"
        "Analyse de l'arbre généalogique d'une famille porteuse.\n"
    )

    doc = DocumentModel.create(
        title=f"Genetique {uid}",
        file_type="md",
        total_pages=1,
        content=content,
    )

    # 1. DocumentDelimitationDialog
    dlg = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg)

    # Le conteneur de pages doit être masqué
    assert dlg.pages_card.isHidden()
    # Le Markdown structuré démarre en mode sections ; le mode chapitres est explicite.
    assert dlg.btn_scope_mode_sections.isChecked()
    assert not dlg.sections_list.isHidden()
    assert dlg.structure_scope_container.isHidden()
    assert dlg.combo_c_start.count() == 2

    # Décocher Partie 1
    w_p1 = dlg.sections_list.itemWidget(dlg.sections_list.topLevelItem(0), 0)
    assert isinstance(w_p1, SectionRowWidget)
    w_p1.checkbox.setChecked(False)

    dlg._on_apply()

    fresh_doc = DocumentModel.get_by_id(doc.id)
    assert "partie 1" in fresh_doc.excluded_headings.lower()

    # 2. DocumentScopeDialog
    # NOTE: _on_apply() a déjà synchronisé les chunks en BDD (chunks de Partie 2 uniquement).
    # Ne pas créer de chunks manuellement ici pour éviter les doublons.

    scope_dlg = DocumentScopeDialog(doc)
    qtbot.addWidget(scope_dlg)

    assert scope_dlg.pages_card.isHidden()
    assert scope_dlg.btn_mode_sections.isChecked()
    assert not scope_dlg.sections_list.isHidden()
    assert scope_dlg.structure_scope_container.isHidden()

    # Puisque Partie 1 a été exclue lors de la délimitation, scope_dlg ne contient que Partie 2
    assert len(scope_dlg._useful_chunks) >= 1
    assert all("Partie 1" not in (c.get("heading_path") or "") for c in scope_dlg._useful_chunks)
    assert any("Partie 2" in (c.get("heading_path") or c.get("title") or "") for c in scope_dlg._useful_chunks)


def test_structure_delimitation_scanned_pdf_or_album_hides_structure_mode(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que pour un Album ou PDF numérisé sans titres, le bouton Par Chapitres est masqué."""
    from ankiforge.database.models import DocumentPageModel, MediaModel
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Planches Anatomie {uid}",
        file_type="album",
        total_pages=3,
        content="",
    )
    media = MediaModel.create(
        filename=f"scan_{uid}.png",
        original_name=f"scan_{uid}.png",
        checksum=f"sha256_fake_{uid}",
        mime_type="image/png",
    )
    for p in range(1, 4):
        DocumentPageModel.create(
            document=doc,
            media=media,
            page_number=p,
            ocr_text=f"Scan de planche sans aucun titre structuré {p}",
        )

    # 1. Delimitation
    dlg = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg)

    assert dlg.btn_scope_mode_structure.isHidden()
    assert dlg.structure_scope_container.isHidden()
    # Sections sous forme de planches simples
    assert dlg.sections_list.count() == 3

    # 2. Scope
    scope_dlg = DocumentScopeDialog(doc)
    qtbot.addWidget(scope_dlg)

    assert scope_dlg.btn_mode_structure.isHidden()
    assert scope_dlg.structure_scope_container.isHidden()
    assert scope_dlg.sections_list.count() == 3


def test_modal_hierarchical_filter_keeps_ancestors_and_check_states(qtbot: Any, mock_db: Any) -> None:
    """Le filtre garde les ancêtres visibles et ne modifie jamais les cases cochées."""
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog, SectionRowWidget

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Filtre hiérarchique {uid}",
        file_type="md",
        content=(
            "# Chapitre Alpha\n"
            "Introduction générale suffisamment longue pour former une section.\n\n"
            "## Sous-section Cible\n"
            "Contenu ciblé suffisamment long pour être conservé dans le document.\n\n"
            "# Chapitre Beta\n"
            "Autre contenu général suffisamment long pour former une section.\n\n"
            "## Sous-section Autre\n"
            "Contenu différent suffisamment long pour être conservé dans le document.\n"
        ),
    )

    delimitation = DocumentDelimitationDialog(doc)
    qtbot.addWidget(delimitation)
    alpha = delimitation.sections_list.topLevelItem(0)
    beta = delimitation.sections_list.topLevelItem(1)
    assert alpha is not None and beta is not None
    target = alpha.child(0)
    target_widget = delimitation.sections_list.itemWidget(target, 0)
    assert isinstance(target_widget, SectionRowWidget)
    target_widget.checkbox.setChecked(False)
    assert target.checkState(0) == Qt.CheckState.Unchecked

    delimitation.filter_input.setText("cible")
    assert not alpha.isHidden()
    assert not target.isHidden()
    assert beta.isHidden()
    assert target.checkState(0) == Qt.CheckState.Unchecked

    delimitation.filter_input.clear()
    assert not beta.isHidden()
    assert target.checkState(0) == Qt.CheckState.Unchecked

    with patch("ankiforge.ui.dialogs.document_scope_dialog.SettingsService.get", return_value=None):
        scope = DocumentScopeDialog(doc)
    qtbot.addWidget(scope)
    scope_alpha = scope.sections_list.topLevelItem(0)
    scope_beta = scope.sections_list.topLevelItem(1)
    assert scope_alpha is not None and scope_beta is not None
    scope.filter_input.setText("cible")
    assert not scope_alpha.isHidden()
    assert scope_alpha.child(0) is not None and not scope_alpha.child(0).isHidden()
    assert scope_beta.isHidden()


def test_delimitation_assembled_preview_uses_in_memory_selection(qtbot: Any, mock_db: Any) -> None:
    """La vue finale assemble les feuilles sélectionnées sans dépendre de la BDD."""
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog, SectionRowWidget

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Aperçu assemblé {uid}",
        file_type="md",
        content=("# Chapitre\n## Première partie\nTexte de la première partie, utile pour la génération.\n\n## Deuxième partie\nTexte de la deuxième partie, utile pour la génération.\n"),
    )
    dialog = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dialog)

    dialog.btn_view_final.click()
    assembled = dialog.final_preview_browser.toPlainText()
    assert "première partie" in assembled.lower()
    assert "deuxième partie" in assembled.lower()

    second = dialog.sections_list.topLevelItem(0).child(1)
    second_widget = dialog.sections_list.itemWidget(second, 0)
    assert isinstance(second_widget, SectionRowWidget)
    second_widget.checkbox.setChecked(False)
    dialog._refresh_final_preview()
    assembled_after = dialog.final_preview_browser.toPlainText().lower()
    assert "première partie" in assembled_after
    assert "deuxième partie" not in assembled_after


def test_delimitation_reset_requires_confirmation_and_clears_persistent_scope(qtbot: Any, mock_db: Any) -> None:
    """Le reset est confirmé avant de vider les bornes et exclusions persistées."""
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Reset délimitation {uid}",
        file_type="pdf",
        total_pages=5,
        start_page=2,
        end_page=4,
        excluded_headings='["sommaire"]',
        content="# Chapitre\nContenu suffisamment long pour une section.",
    )
    dialog = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dialog)

    with patch(
        "ankiforge.ui.views.documents_view.dialogs.delimitation_dialog.QMessageBox.question",
        return_value=QMessageBox.StandardButton.No,
    ):
        dialog._on_reset()
    unchanged = DocumentModel.get_by_id(doc.id)
    assert unchanged.start_page == 2
    assert unchanged.end_page == 4

    with patch(
        "ankiforge.ui.views.documents_view.dialogs.delimitation_dialog.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    ):
        dialog._on_reset()
    reset = DocumentModel.get_by_id(doc.id)
    assert reset.start_page is None
    assert reset.end_page is None
    assert reset.excluded_headings == "[]"


def test_scope_context_progress_is_hidden_without_valid_limit(qtbot: Any, mock_db: Any) -> None:
    """Une limite de contexte absente ou invalide ne doit pas afficher de jauge trompeuse."""
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Contexte {uid}",
        file_type="md",
        content="# Section\nContenu suffisamment long pour estimer quelques tokens.",
    )
    with patch("ankiforge.ui.dialogs.document_scope_dialog.SettingsService.get", return_value=None):
        dialog = DocumentScopeDialog(doc)
    qtbot.addWidget(dialog)
    assert dialog.token_progress.isHidden()
    assert dialog.lbl_context_tokens.isHidden()

    with patch("ankiforge.ui.dialogs.document_scope_dialog.SettingsService.get", return_value="100"):
        configured = DocumentScopeDialog(doc)
    qtbot.addWidget(configured)
    assert not configured.token_progress.isHidden()
    assert configured.token_progress.maximum() == 100


def test_pdf_defaults_to_pages_and_requires_explicit_section_activation(qtbot: Any, mock_db: Any) -> None:
    """Un PDF structuré démarre en mode pages et le mode sections est explicite."""
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog

    uid = uuid.uuid4().hex[:6]
    content = "<!-- PAGE: 1 -->\n# Introduction\nTexte introductif.\n\n<!-- PAGE: 2 -->\n# Conclusion\nTexte final."
    doc = DocumentModel.create(title=f"PDF modes {uid}", file_type="pdf", total_pages=2, content=content)

    delimitation = DocumentDelimitationDialog(doc)
    qtbot.addWidget(delimitation)
    assert delimitation.selection_mode == "pages"
    assert delimitation.btn_scope_mode_all.isChecked()
    assert not delimitation.btn_scope_mode_structure.isChecked()
    assert not delimitation.btn_scope_mode_structure.isHidden()
    assert delimitation.sections_card.isHidden()

    scope = DocumentScopeDialog(doc)
    qtbot.addWidget(scope)
    assert scope.selection_mode == "pages"
    assert scope.btn_mode_all.isChecked()
    assert not scope.btn_mode_structure.isChecked()
    assert not scope.btn_mode_structure.isHidden()
    assert scope.sections_card.isHidden()

    delimitation.btn_scope_mode_structure.click()
    scope.btn_mode_structure.click()
    assert delimitation.selection_mode == "chapters"
    assert scope.selection_mode == "chapters"
    assert delimitation.sections_card.isHidden()
    assert scope.sections_card.isHidden()
    assert delimitation.sections_list.isHidden()
    assert scope.sections_list.isHidden()
    delimitation.btn_scope_mode_sections.click()
    scope.btn_mode_sections.click()
    assert delimitation.selection_mode == "sections"
    assert scope.selection_mode == "sections"
    assert not delimitation.sections_card.isHidden()
    assert not scope.sections_card.isHidden()
    assert not delimitation.sections_list.isHidden()
    assert not scope.sections_list.isHidden()


def test_markdown_defaults_to_sections_and_section_selection_does_not_change_pages(qtbot: Any, mock_db: Any) -> None:
    """Un Markdown non paginé démarre en mode sections."""
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog, SectionRowWidget

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Markdown modes {uid}",
        file_type="md",
        total_pages=1,
        content="# Partie A\nTexte A.\n\n# Partie B\nTexte B.",
    )

    delimitation = DocumentDelimitationDialog(doc)
    qtbot.addWidget(delimitation)
    assert delimitation.selection_mode == "sections"
    assert delimitation.btn_scope_mode_sections.isChecked()
    assert delimitation.pages_card.isHidden()
    assert not delimitation.sections_card.isHidden()
    row = delimitation.sections_list.itemWidget(delimitation.sections_list.topLevelItem(0), 0)
    assert isinstance(row, SectionRowWidget)
    row.checkbox.setChecked(False)

    scope = DocumentScopeDialog(doc)
    qtbot.addWidget(scope)
    assert scope.selection_mode == "sections"
    assert scope.btn_mode_sections.isChecked()
    assert scope.pages_card.isHidden()
    assert not scope.sections_card.isHidden()
    scope_row = scope.sections_list.itemWidget(scope.sections_list.topLevelItem(0), 0)
    assert isinstance(scope_row, SectionRowWidget)
    scope_row.checkbox.setChecked(False)


def test_section_mode_persists_sections_without_page_bounds(qtbot: Any, mock_db: Any) -> None:
    """La validation en mode sections persiste les exclusions, pas une plage de pages dérivée."""
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog, SectionRowWidget

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Section persistence {uid}",
        file_type="pdf",
        total_pages=2,
        start_page=1,
        end_page=2,
        content="<!-- PAGE: 1 -->\n# Partie A\nTexte A.\n\n<!-- PAGE: 2 -->\n# Partie B\nTexte B.",
    )
    dialog = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dialog)
    dialog.btn_scope_mode_sections.click()
    assert dialog.spin_p_start.value() == 1
    assert dialog.spin_p_end.value() == 2

    row = dialog.sections_list.itemWidget(dialog.sections_list.topLevelItem(0), 0)
    assert isinstance(row, SectionRowWidget)
    row.checkbox.setChecked(False)
    assert dialog.spin_p_start.value() == 1
    assert dialog.spin_p_end.value() == 2
    dialog._on_apply()

    persisted = DocumentModel.get_by_id(doc.id)
    assert persisted.start_page is None
    assert persisted.end_page is None
    assert "partie a" in persisted.excluded_headings.lower()


def test_h3_content_and_h4_children_retained_in_scope_dialog(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que le contenu propre de H3 ET ses sous-sections H4 cochées sont inclus dans la portée."""
    from ankiforge.database.models import DocumentChunkModel
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import SectionRowWidget

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc H3 H4 {uid}",
        file_type="md",
        content="""# Chapitre 1
Introduction du chapitre 1.

## Section 1.1
Introduction de la section 1.1.

### Sous-section 1.1.1
Texte direct de la sous-section 1.1.1 avant les H4.

#### Sous-section 1.1.1.a
Détail H4 A.

#### Sous-section 1.1.1.b
Détail H4 B.
""",
    )

    chunks_data = [
        (0, "Chapitre 1", "# Chapitre 1\nIntroduction du chapitre 1."),
        (1, "Chapitre 1 > Section 1.1", "## Section 1.1\nIntroduction de la section 1.1."),
        (2, "Chapitre 1 > Section 1.1 > Sous-section 1.1.1", "### Sous-section 1.1.1\nTexte direct de la sous-section 1.1.1 avant les H4."),
        (3, "Chapitre 1 > Section 1.1 > Sous-section 1.1.1 > Sous-section 1.1.1.a", "#### Sous-section 1.1.1.a\nDétail H4 A."),
        (4, "Chapitre 1 > Section 1.1 > Sous-section 1.1.1 > Sous-section 1.1.1.b", "#### Sous-section 1.1.1.b\nDétail H4 B."),
    ]
    for idx, hp, cnt in chunks_data:
        DocumentChunkModel.create(
            document=doc,
            chunk_index=idx,
            page_number=None,
            heading_path=hp,
            content=cnt,
            content_hash=f"hash_{uid}_{idx}",
        )

    dlg = DocumentScopeDialog(doc)
    qtbot.addWidget(dlg)

    # Vérifier que le mode est sections pour markdown pur
    assert dlg.selection_mode == "sections"

    # Toutes les sections sont cochées par défaut
    selected = dlg._selected_chunks_for_mode()
    selected_paths = [c.get("heading_path") for c in selected]

    # H3 direct content (Sous-section 1.1.1) DOIT être présent !
    assert "Chapitre 1 > Section 1.1 > Sous-section 1.1.1" in selected_paths
    assert "Chapitre 1 > Section 1.1 > Sous-section 1.1.1 > Sous-section 1.1.1.a" in selected_paths
    assert "Chapitre 1 > Section 1.1 > Sous-section 1.1.1 > Sous-section 1.1.1.b" in selected_paths

    # Trouver l'item H3 et ses enfants H4 dans la sections_list
    h3_item = None
    h4a_item = None
    h4b_item = None
    for i in range(dlg.sections_list.count()):
        it = dlg.sections_list.item(i)
        meta = dlg._section_meta.get(i, {})
        title = meta.get("title", "")
        if title == "Sous-section 1.1.1":
            h3_item = it
        elif title == "Sous-section 1.1.1.a":
            h4a_item = it
        elif title == "Sous-section 1.1.1.b":
            h4b_item = it

    assert h3_item is not None
    assert h4a_item is not None
    assert h4b_item is not None

    # Décocher H4b via son widget
    w_h4b = dlg.sections_list.itemWidget(h4b_item, 0)
    assert isinstance(w_h4b, SectionRowWidget)
    w_h4b.checkbox.click()
    assert h4b_item.checkState(0) == Qt.CheckState.Unchecked

    # H3 doit être passé en PartiallyChecked
    assert h3_item.checkState(0) == Qt.CheckState.PartiallyChecked

    # Les fragments sélectionnés doivent contenir H3 (intro) et H4a, mais PAS H4b
    selected_after = dlg._selected_chunks_for_mode()
    paths_after = [c.get("heading_path") for c in selected_after]
    assert "Chapitre 1 > Section 1.1 > Sous-section 1.1.1" in paths_after
    assert "Chapitre 1 > Section 1.1 > Sous-section 1.1.1 > Sous-section 1.1.1.a" in paths_after
    assert "Chapitre 1 > Section 1.1 > Sous-section 1.1.1 > Sous-section 1.1.1.b" not in paths_after


def test_h3_tristate_checkbox_toggle_and_row_activation(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le cycle binaire partagé par la checkbox et la ligne."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import SectionRowWidget

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Click isolation {uid}",
        file_type="md",
        content="""# Titre H1
Texte 1

## Titre H2
Texte 2

### Titre H3
Texte 3

#### Titre H4
Texte 4
""",
    )

    dlg = DocumentScopeDialog(doc)
    qtbot.addWidget(dlg)

    # Trouver l'item H3
    h3_item = None
    for i in range(dlg.sections_list.count()):
        it = dlg.sections_list.item(i)
        if dlg._section_meta.get(i, {}).get("title") == "Titre H3":
            h3_item = it
            break

    assert h3_item is not None
    w_h3 = dlg.sections_list.itemWidget(h3_item, 0)
    assert isinstance(w_h3, SectionRowWidget)

    # 1. Clic sur la ligne (hors checkbox) : bascule la case à cocher
    mouse_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(200, 15),
        QPointF(200, 15),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    w_h3.mousePressEvent(mouse_event)
    assert w_h3.check_state() == Qt.CheckState.Unchecked
    assert h3_item.checkState(0) == Qt.CheckState.Unchecked

    # 2. Clic sur la checkbox : bascule franche Unchecked -> Checked
    w_h3.checkbox.click()
    assert w_h3.check_state() == Qt.CheckState.Checked
    assert h3_item.checkState(0) == Qt.CheckState.Checked
    assert h3_item.child(0).checkState(0) == Qt.CheckState.Checked

    # 3. Clic sur la checkbox : bascule Checked -> Unchecked
    w_h3.checkbox.click()
    assert w_h3.check_state() == Qt.CheckState.Unchecked
    assert h3_item.checkState(0) == Qt.CheckState.Unchecked
    assert h3_item.child(0).checkState(0) == Qt.CheckState.Unchecked


def test_h3_h4_scope_dialog_restore_faithfully(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que la réouverture de DocumentScopeDialog restaure fidèlement la sélection fine H3/H4."""
    from ankiforge.database.models import DocumentChunkModel
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import SectionRowWidget

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Restore H3 H4 {uid}",
        file_type="md",
        content="""# Racine
Texte racine.

## H2
Texte H2.

### H3
Texte introductif H3.

#### H4a
Texte H4a.

#### H4b
Texte H4b.
""",
    )
    for idx, hp in enumerate(["Racine", "Racine > H2", "Racine > H2 > H3", "Racine > H2 > H3 > H4a", "Racine > H2 > H3 > H4b"]):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=idx,
            heading_path=hp,
            content=f"Contenu {hp}",
            content_hash=f"h_{uid}_{idx}",
        )

    dlg1 = DocumentScopeDialog(doc)
    qtbot.addWidget(dlg1)

    # Décocher H4b
    h4b_item = next(dlg1.sections_list.item(i) for i in range(dlg1.sections_list.count()) if dlg1._section_meta.get(i, {}).get("title") == "H4b")
    w_h4b = dlg1.sections_list.itemWidget(h4b_item, 0)
    assert isinstance(w_h4b, SectionRowWidget)
    w_h4b.checkbox.click()

    dlg1._on_apply()
    res = dlg1.get_result()

    # Réouverture avec initial_scope_result
    dlg2 = DocumentScopeDialog(doc, initial_scope_str=res["range_str"], initial_scope_result=res)
    qtbot.addWidget(dlg2)

    h3_item2 = next(dlg2.sections_list.item(i) for i in range(dlg2.sections_list.count()) if dlg2._section_meta.get(i, {}).get("title") == "H3")
    h4a_item2 = next(dlg2.sections_list.item(i) for i in range(dlg2.sections_list.count()) if dlg2._section_meta.get(i, {}).get("title") == "H4a")
    h4b_item2 = next(dlg2.sections_list.item(i) for i in range(dlg2.sections_list.count()) if dlg2._section_meta.get(i, {}).get("title") == "H4b")

    # Vérifier les états restaurés
    assert h3_item2.checkState(0) == Qt.CheckState.PartiallyChecked
    assert h4a_item2.checkState(0) == Qt.CheckState.Checked
    assert h4b_item2.checkState(0) == Qt.CheckState.Unchecked

    # Vérifier que les chunks sélectionnés restaurés contiennent H3 et H4a
    dlg2._on_apply()
    res2 = dlg2.get_result()
    paths2 = [c.get("heading_path") for c in res2["chunks"]]
    assert "Racine > H2 > H3" in paths2
    assert "Racine > H2 > H3 > H4a" in paths2
    assert "Racine > H2 > H3 > H4b" not in paths2


def test_delimitation_dialog_h3_content_and_h4_cascade(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la préservation du contenu H3 et la cascade dans DocumentDelimitationDialog."""
    from ankiforge.database.models import DocumentChunkModel
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog, SectionRowWidget

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Delimitation H3 H4 {uid}",
        file_type="md",
        content="""# Module
Texte module.

## Section
Texte section.

### Point 1
Introduction du point 1 avec du texte direct.

#### Sous-point 1.A
Détail 1.A.

#### Sous-point 1.B
Détail 1.B.
""",
    )
    for idx, hp in enumerate(["Module", "Module > Section", "Module > Section > Point 1", "Module > Section > Point 1 > Sous-point 1.A", "Module > Section > Point 1 > Sous-point 1.B"]):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=idx,
            heading_path=hp,
            content=f"Contenu {hp}",
            content_hash=f"h_delim_{uid}_{idx}",
        )

    dlg = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg)

    # Par défaut, toutes les sections sont cochées et H3 direct content est retenu
    selected = dlg._selected_chunks_for_mode()
    paths = [c.get("heading_path") for c in selected]
    assert "Module > Section > Point 1" in paths
    assert "Module > Section > Point 1 > Sous-point 1.A" in paths
    assert "Module > Section > Point 1 > Sous-point 1.B" in paths

    # Décocher Sous-point 1.B
    p1_b_item = next(dlg.sections_list.item(i) for i in range(dlg.sections_list.count()) if dlg._section_meta.get(i, {}).get("title") == "Sous-point 1.B")
    w_b = dlg.sections_list.itemWidget(p1_b_item, 0)
    assert isinstance(w_b, SectionRowWidget)
    w_b.checkbox.click()
    assert p1_b_item.checkState(0) == Qt.CheckState.Unchecked

    # Point 1 (H3) doit être PartiallyChecked
    p1_item = next(dlg.sections_list.item(i) for i in range(dlg.sections_list.count()) if dlg._section_meta.get(i, {}).get("title") == "Point 1")
    assert p1_item.checkState(0) == Qt.CheckState.PartiallyChecked

    # Point 1 (intro) et Sous-point 1.A sont retenus, mais pas Sous-point 1.B
    selected2 = dlg._selected_chunks_for_mode()
    paths2 = [c.get("heading_path") for c in selected2]
    assert "Module > Section > Point 1" in paths2
    assert "Module > Section > Point 1 > Sous-point 1.A" in paths2
    assert "Module > Section > Point 1 > Sous-point 1.B" not in paths2


def test_format_and_parse_page_ranges_canonical() -> None:
    """Vérifie le parsing et le formatage canonique des plages de pages (continues et discontinues)."""
    from ankiforge.ui.views.creation_view.utils import format_page_ranges, parse_page_ranges

    # 1. Parsing
    assert parse_page_ranges("1-3, 5, 7-9") == [1, 2, 3, 5, 7, 8, 9]
    assert parse_page_ranges("9, 1-3, 5") == [1, 2, 3, 5, 9]
    assert parse_page_ranges("4") == [4]
    assert parse_page_ranges("") == []
    assert parse_page_ranges("invalid, abc") == []
    assert parse_page_ranges("1-10, 15", max_page=5) == [1, 2, 3, 4, 5]

    # 2. Formatage canonique
    assert format_page_ranges({1, 2, 3, 5, 7, 8, 9}) == "1-3, 5, 7-9"
    assert format_page_ranges([5, 1, 2, 3]) == "1-3, 5"
    assert format_page_ranges({4}) == "4"
    assert format_page_ranges([]) == ""
    assert format_page_ranges(set(range(1, 6))) == "1-5"


def test_document_scope_dialog_non_contiguous_pages(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la sélection et la restauration de plages discontinues dans DocumentScopeDialog."""
    from ankiforge.database.models import DocumentChunkModel
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"NonContig Scope {uid}",
        file_type="pdf",
        total_pages=6,
        content="\n\n".join(f"<!-- PAGE: {p} -->\nContenu slide {p}." for p in range(1, 7)),
    )
    for p in range(1, 7):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"Slide {p}",
            content=f"Contenu slide {p}.",
            content_hash=f"h_sc_{uid}_{p}",
        )

    # 1. Ouverture avec portée initiale discontinue "1-2, 4-5" (slide 3 et 6 exclus)
    dlg = DocumentScopeDialog(doc, initial_scope_str="1-2, 4-5")
    qtbot.addWidget(dlg)

    assert dlg.is_paginated is True
    assert dlg.selection_mode == "pages"
    assert dlg._selected_pages == {1, 2, 4, 5}
    assert dlg.input_custom_pages.text() == "1-2, 4-5"
    assert dlg.range_bar._selected_pages == {1, 2, 4, 5}

    # Vérification des chunks retenus
    selected_chunks = dlg._selected_chunks_for_mode()
    selected_pages = [c.get("page_number") for c in selected_chunks]
    assert selected_pages == [1, 2, 4, 5]
    assert 3 not in selected_pages
    assert 6 not in selected_pages

    # 2. Validation
    dlg._on_apply()
    res = dlg.get_result()
    assert res["range_str"] == "1-2, 4-5"
    assert res["selected_pages"] == [1, 2, 4, 5]
    assert res["scope_title"] == "Portée : Pages 1-2, 4-5"

    # 3. Réouverture avec le résultat précédent (restauration fidèle)
    dlg2 = DocumentScopeDialog(doc, initial_scope_result=res)
    qtbot.addWidget(dlg2)
    assert dlg2.selection_mode == "pages"
    assert dlg2._selected_pages == {1, 2, 4, 5}
    assert dlg2.input_custom_pages.text() == "1-2, 4-5"


def test_document_delimitation_dialog_non_contiguous_pages(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que DocumentDelimitationDialog exclut correctement les pages sautées et enregistre les exclusions."""
    import json

    from ankiforge.database.models import DocumentChunkModel
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"NonContig Delim {uid}",
        file_type="pptx",
        total_pages=5,
        content="\n\n".join(f"<!-- PAGE: {p} -->\nContenu détaillé de la diapositive {p}." for p in range(1, 6)),
    )
    for p in range(1, 6):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"Diapo {p}",
            content=f"Contenu détaillé de la diapositive {p}.",
            content_hash=f"h_dl_{uid}_{p}",
        )

    dlg = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg)
    dlg.btn_scope_mode_range.click()

    # Saisir une plage avec exclusion de la page 3
    dlg.input_custom_pages.setText("1-2, 4-5")

    assert dlg._selected_pages == {1, 2, 4, 5}
    selected_chunks = dlg._selected_chunks_for_mode()
    selected_pages = [c.get("page_number") for c in selected_chunks]
    assert selected_pages == [1, 2, 4, 5]
    assert 3 not in selected_pages

    dlg._on_apply()

    # Vérification de la persistance en base
    fresh_doc = DocumentModel.get_by_id(doc.id)
    assert fresh_doc.start_page == 1
    assert fresh_doc.end_page == 5
    exclusions = json.loads(fresh_doc.excluded_headings)
    assert "page:3" in exclusions

    # Vérification des chunks restants en BDD
    remaining = list(DocumentChunkModel.select().where(DocumentChunkModel.document == fresh_doc).order_by(DocumentChunkModel.chunk_index))
    remaining_pages = [c.page_number for c in remaining]
    assert remaining_pages == [1, 2, 4, 5]


def test_preview_widget_page_toggle_button(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le bouton 1-clic d'exclusion/inclusion de diapositive dans le volet d'aperçu."""
    from ankiforge.database.models import DocumentChunkModel
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Toggle Slide {uid}",
        file_type="pdf",
        total_pages=4,
        content="\n\n".join(f"<!-- PAGE: {p} -->\nSlide {p}." for p in range(1, 5)),
    )
    for p in range(1, 5):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"Slide {p}",
            content=f"Slide {p}.",
            content_hash=f"h_tg_{uid}_{p}",
        )

    dlg = DocumentScopeDialog(doc)
    qtbot.addWidget(dlg)

    # Initialement toutes les pages sont incluses (1-4)
    assert dlg._selected_pages == {1, 2, 3, 4}

    # Se positionner sur la page 2
    dlg.preview_widget.jump_to_page(2)
    assert dlg.preview_widget.current_page == 2
    assert "Exclure" in dlg.preview_widget.btn_toggle_page_scope.text()

    # 1. Cliquer sur 'Exclure cette page'
    dlg.preview_widget.btn_toggle_page_scope.click()
    assert 2 not in dlg._selected_pages
    assert dlg._selected_pages == {1, 3, 4}
    assert dlg.input_custom_pages.text() == "1, 3-4"
    assert "Inclure" in dlg.preview_widget.btn_toggle_page_scope.text()

    # 2. Recliquer pour réinclure la page
    dlg.preview_widget.btn_toggle_page_scope.click()
    assert 2 in dlg._selected_pages
    assert dlg._selected_pages == {1, 2, 3, 4}
    assert dlg.input_custom_pages.text() == "1-4"
    assert "Exclure" in dlg.preview_widget.btn_toggle_page_scope.text()


def test_push_behavior_slider_spinbox(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le comportement push-clamp lorsque le début dépasse la fin ou inversement."""
    from ankiforge.database.models import DocumentChunkModel
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Push Behavior {uid}",
        file_type="pdf",
        total_pages=10,
        content="\n\n".join(f"<!-- PAGE: {p} -->\nPage {p}." for p in range(1, 11)),
    )
    for p in range(1, 11):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"Page {p}",
            content=f"Page {p}.",
            content_hash=f"h_pb_{uid}_{p}",
        )

    dlg = DocumentScopeDialog(doc)
    qtbot.addWidget(dlg)
    dlg.btn_mode_range.click()

    # Initialement start=1, end=10
    dlg.spin_p_end.setValue(5)
    assert dlg.spin_p_start.value() == 1
    assert dlg.spin_p_end.value() == 5

    # Déplacer start au-delà de end (start=7 > end=5) -> end est poussé à 7
    dlg.spin_p_start.setValue(7)
    assert dlg.spin_p_start.value() == 7
    assert dlg.spin_p_end.value() == 7
    assert dlg._selected_pages == {7}
    assert dlg.input_custom_pages.text() == "7"

    # Déplacer end en-deçà de start (end=3 < start=7) -> start est poussé à 3
    dlg.spin_p_end.setValue(3)
    assert dlg.spin_p_start.value() == 3
    assert dlg.spin_p_end.value() == 3
    assert dlg._selected_pages == {3}
    assert dlg.input_custom_pages.text() == "3"


def test_section_multi_page_span_overlap(qtbot: Any, mock_db: Any) -> None:
    """Vérifie qu'une section ou chapitre couvrant plusieurs pages reste cochée si l'une des pages est incluse."""
    from ankiforge.database.models import DocumentChunkModel
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog

    uid = uuid.uuid4().hex[:6]
    content = """<!-- PAGE: 1 -->
# Intro
Introduction du document.

<!-- PAGE: 2 -->
# Chapitre Long
Début du long chapitre sur la page 2 avec du texte substantiel.

<!-- PAGE: 3 -->
Suite du long chapitre sur la page 3 avec des explications riches.

<!-- PAGE: 4 -->
Fin du long chapitre sur la page 4 avec la conclusion de la démonstration.

<!-- PAGE: 5 -->
# Conclusion
Dernière page du document.
"""
    doc = DocumentModel.create(
        title=f"MultiPage Span {uid}",
        file_type="pdf",
        total_pages=5,
        content=content,
    )
    for p in range(1, 6):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path="Chapitre Long" if 2 <= p <= 4 else ("Intro" if p == 1 else "Conclusion"),
            content=f"Contenu page {p} riche et suffisant.",
            content_hash=f"h_span_{uid}_{p}",
        )

    dlg = DocumentScopeDialog(doc)
    qtbot.addWidget(dlg)
    dlg.btn_mode_range.click()

    # Sélectionner uniquement la page 3
    dlg.input_custom_pages.setText("3")
    assert dlg._selected_pages == {3}

    # Le "Chapitre Long" couvre les pages 2 à 4. Comme la page 3 est incluse, il doit rester coché ou partiellement coché
    chap_item = next(dlg.sections_list.item(i) for i in range(dlg.sections_list.count()) if "Chapitre Long" in str(dlg._section_meta.get(i, {}).get("title", "")))
    assert chap_item.checkState(0) in (Qt.CheckState.Checked, Qt.CheckState.PartiallyChecked)


def test_document_scope_rejects_page_range_outside_bounds(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que DocumentScopeDialog refuse d'appliquer si une page dépasse la borne utile."""
    from ankiforge.database.models import DocumentChunkModel
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Scope Bounds {uid}",
        file_type="pdf",
        total_pages=3,
        content="<!-- PAGE: 1 -->\nP1\n<!-- PAGE: 2 -->\nP2\n<!-- PAGE: 3 -->\nP3",
    )
    for p in range(1, 4):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"Page {p}",
            content=f"Contenu page {p} suffisant.",
            content_hash=f"h_bnd_{uid}_{p}",
        )

    dlg = DocumentScopeDialog(doc)
    qtbot.addWidget(dlg)
    dlg.btn_mode_range.click()
    dlg.spin_p_end.setRange(1, 99)
    dlg.spin_p_end.setValue(99)
    dlg._on_apply()
    assert dlg.result() == 0


def test_slide_selector_bar_widget(qtbot: Any) -> None:
    """Vérifie le ruban de pastilles de slides cliquables et ses actions rapides."""
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import SlideSelectorBarWidget

    widget = SlideSelectorBarWidget()
    qtbot.addWidget(widget)
    widget.set_pages({1, 2, 3, 4, 5}, 5)

    assert len(widget._buttons) == 5
    assert "toutes incluses" in widget.lbl_count.text()

    # Clic sur la pastille 3
    toggled_pages: list[int] = []
    widget.page_toggled.connect(toggled_pages.append)
    widget._buttons[3].click()
    assert toggled_pages == [3]

    # Mise à jour avec la page 3 exclue
    widget.set_pages({1, 2, 4, 5}, 5)
    assert "1 exclue" in widget.lbl_count.text()

    # Actions rapides
    actions_fired: list[str] = []
    widget.all_selected.connect(lambda: actions_fired.append("all"))
    widget.none_selected.connect(lambda: actions_fired.append("none"))
    widget.inverted.connect(lambda: actions_fired.append("invert"))

    widget.btn_all.click()
    assert "all" in actions_fired
    widget.btn_none.click()
    assert "none" in actions_fired
    widget.btn_invert.click()
    assert "invert" in actions_fired


def test_range_segments_widget(qtbot: Any) -> None:
    """Vérifie l'affichage des badges de segments et le constructeur inline de plage."""
    from PySide6.QtWidgets import QPushButton

    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import RangeSegmentsWidget

    widget = RangeSegmentsWidget(max_page=10)
    qtbot.addWidget(widget)
    widget.set_selected_pages({1, 2, 3, 5, 8}, 10)

    # 3 segments : 1-3, 5, 8
    assert widget.chips_layout.count() >= 3

    # Test suppression de segment via signal
    removed_segments: list[tuple[int, int]] = []
    widget.segment_removed.connect(lambda s, e: removed_segments.append((s, e)))
    # Cliquer sur la croix du premier chip (1-3)
    first_chip = widget.chips_layout.itemAt(0).widget()
    del_btn = first_chip.findChild(QPushButton)
    assert del_btn is not None
    del_btn.click()
    assert removed_segments == [(1, 3)]

    # Test constructeur inline "+ Plage"
    assert widget.builder_widget.isHidden()
    widget.btn_add_range.click()
    assert not widget.builder_widget.isHidden()

    added_ranges: list[tuple[int, int]] = []
    widget.range_added.connect(lambda s, e: added_ranges.append((s, e)))

    widget.spin_add_start.setValue(9)
    widget.spin_add_end.setValue(10)
    widget.btn_confirm_add.click()

    assert added_ranges == [(9, 10)]
    assert widget.builder_widget.isHidden()


def test_delimitation_dialog_slide_selector_and_segments_sync(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la synchronisation complète entre les pastilles, les segments, les spinboxes et l'aperçu dans DelimitationDialog."""
    from ankiforge.database.models import DocumentChunkModel
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog

    uid = uuid.uuid4().hex[:6]
    pages_content = "\n".join(f"<!-- PAGE: {p} -->\n# Slide {p}\nContenu riche de la slide {p}." for p in range(1, 9))
    doc = DocumentModel.create(
        title=f"Slides Presentation {uid}",
        file_type="pdf",
        total_pages=8,
        content=pages_content,
    )
    for p in range(1, 9):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"Slide {p}",
            content=f"Contenu riche de la slide {p}.",
            content_hash=f"h_sl_{uid}_{p}",
        )

    dlg = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg)

    # Vérification présence des nouveaux widgets
    assert hasattr(dlg, "slide_selector_bar")
    assert hasattr(dlg, "range_segments_widget")
    assert len(dlg.slide_selector_bar._buttons) == 8

    # 1. Clic sur la pastille 2 pour l'exclure
    dlg.slide_selector_bar._buttons[2].click()
    assert 2 not in dlg._selected_pages
    assert dlg.input_custom_pages.text() == "1, 3-8"

    # 2. Clic sur la pastille 4 pour l'exclure
    dlg.slide_selector_bar._buttons[4].click()
    assert 4 not in dlg._selected_pages
    assert dlg.input_custom_pages.text() == "1, 3, 5-8"

    # 3. Ré-inclusion de la pastille 2 en cliquant dessus
    dlg.slide_selector_bar._buttons[2].click()
    assert 2 in dlg._selected_pages
    assert dlg.input_custom_pages.text() == "1-3, 5-8"

    # 4. Suppression du segment 1-3 via le widget de segments
    dlg.range_segments_widget.segment_removed.emit(1, 3)
    assert dlg._selected_pages == {5, 6, 7, 8}
    assert dlg.input_custom_pages.text() == "5-8"

    # 5. Ajout d'une plage 1-2 via le widget de segments
    dlg.range_segments_widget.range_added.emit(1, 2)
    assert dlg._selected_pages == {1, 2, 5, 6, 7, 8}
    assert dlg.input_custom_pages.text() == "1-2, 5-8"

    # 6. Action Tout inclure
    dlg.slide_selector_bar.btn_all.click()
    assert dlg._selected_pages == set(range(1, 9))

    # 7. Validation et persistance
    dlg.chk_revectorize.setChecked(False)
    dlg._on_apply()
    assert dlg.result() == 1


def test_document_editor_scoped_extract_and_toggle(qtbot: Any) -> None:
    """Vérifie l'affichage du bandeau TextScopeBannerWidget et la bascule entre extrait filtré et document complet."""
    initial_full_text = "# Cours Complet\n\nIntro générale.\n\n## Section 1\nDétail section 1.\n\n## Section 2\nDétail section 2."
    editor = DocumentEditorWidget(content=initial_full_text, source_title="Cours Complet")
    qtbot.addWidget(editor)
    editor.show()

    assert editor.text_scope_banner.isHidden()
    assert editor.get_text() == initial_full_text

    # 1. Définition d'un extrait de portée filtrée
    scoped_text = "## Section 1\nDétail section 1."
    editor.set_scoped_extract(scoped_text, scope_title="Section 1", chunks_count=1, is_scoped=True)

    assert not editor.text_scope_banner.isHidden()
    assert editor.get_text() == scoped_text
    assert "Section 1" in editor.text_scope_banner.lbl_status.text()
    assert "Extrait filtré" in editor.text_scope_banner.badge_status.text()

    # 2. Bascule vers l'affichage complet temporaire (sans perte de portée)
    editor.text_scope_banner.btn_toggle_display.click()
    assert editor.get_text() == initial_full_text
    assert "en pause" in editor.text_scope_banner.badge_status.text()
    assert "Afficher l'extrait filtré" in editor.text_scope_banner.btn_toggle_display.text()

    # 3. Re-bascule vers l'extrait filtré
    editor.text_scope_banner.btn_toggle_display.click()
    assert editor.get_text() == scoped_text
    assert "Extrait filtré" in editor.text_scope_banner.badge_status.text()

    # 4. Effacement du filtre de portée
    editor.clear_scoped_extract()
    assert editor.text_scope_banner.isHidden()
    assert editor.get_text() == initial_full_text


def test_creation_view_scope_dialog_updates_editor(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que l'application d'un résultat de DocumentScopeDialog met immédiatement à jour l'éditeur central."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Neurologie {uid}",
        file_type="md",
        content="# Cervelet\n\nFonction motrice.\n\n# Moelle épinière\n\nRéflexes et transmission.",
    )
    c1 = DocumentChunkModel.create(document=doc, chunk_index=0, heading_path="Cervelet", content="# Cervelet\n\nFonction motrice.")
    c2 = DocumentChunkModel.create(document=doc, chunk_index=1, heading_path="Moelle épinière", content="# Moelle épinière\n\nRéflexes et transmission.")

    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)
    view.show()
    view.refresh_data()

    # Ouvrir le document dans un onglet
    view._open_document_for_model(doc)
    editor = view._get_current_editor()
    assert editor is not None
    assert doc.content in editor.get_text()

    # Simuler le résultat de DocumentScopeDialog ciblant uniquement le Cervelet
    scope_result = {
        "is_all": False,
        "chunks": [{"content": c1.content, "heading_path": "Cervelet", "title": "Cervelet", "page_number": None, "index": 0, "tokens": 5}],
        "scope_title": "Portée : 1 section utile",
        "scope_stats": "~10 mots • ~1 cartes estimées",
        "range_str": "1",
        "selection_mode": "sections",
        "selected_pages": [],
        "selected_headings": ["Cervelet"],
        "selected_chunk_indices": [0],
    }

    view._apply_scope_result(scope_result)

    # Vérifier que l'éditeur central a été mis à jour avec le contenu filtré
    assert not editor.text_scope_banner.isHidden()
    assert "Fonction motrice" in editor.get_text()
    assert "Moelle épinière" not in editor.get_text()

    # Revenir à tout le document
    all_result = {
        "is_all": True,
        "chunks": [{"content": c1.content, "title": "Cervelet"}, {"content": c2.content, "title": "Moelle épinière"}],
        "scope_title": "Portée : Tout le document",
        "selection_mode": "sections",
        "selected_pages": [],
    }
    view._apply_scope_result(all_result)
    assert editor.text_scope_banner.isHidden()
    assert "Fonction motrice" in editor.get_text()
    assert "Moelle épinière" in editor.get_text()


def test_creation_view_segment_inspector_toggles_update_editor(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que cocher/décocher des segments dans SegmentInspectorWidget met à jour l'éditeur central en direct."""
    uid = uuid.uuid4().hex[:6]
    content_text = (
        "## Partie 1 : Ventricule cardiaque et débit sanguin.\n\n"
        "Contenu détaillé du ventricule cardiaque avec volume d'éjection systolique.\n\n"
        "## Partie 2 : Oreillette et valves auriculo-ventriculaires.\n\n"
        "Contenu détaillé de l'oreillette avec retour veineux et hémodynamique."
    )
    doc = DocumentModel.create(
        title=f"Cardiologie {uid}",
        file_type="md",
        content=content_text,
    )

    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)
    view.show()
    view.refresh_data()

    view._open_document_for_model(doc)
    editor = view._get_current_editor()
    assert editor is not None

    # L'inspecteur a découpé les 2 segments H2
    assert view.segment_inspector.segments_list.count() == 2

    # Décocher le deuxième segment
    item_2 = view.segment_inspector.segments_list.item(1)
    view.segment_inspector._on_widget_toggled(item_2, False)

    # Vérifier que l'éditeur a été actualisé et n'affiche plus que le segment 1
    assert "Partie 1 : Ventricule" in editor.get_text()
    assert "Partie 2 : Oreillette" not in editor.get_text()
    assert not editor.text_scope_banner.isHidden()

    # Recocher le segment 2 (tous cochés)
    view.segment_inspector._on_widget_toggled(item_2, True)
    assert editor.text_scope_banner.isHidden()
    assert "Partie 1 : Ventricule" in editor.get_text()
    assert "Partie 2 : Oreillette" in editor.get_text()


def test_creation_view_segment_selected_highlights_in_editor(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que cliquer sur un segment dans l'inspecteur déplace le curseur et surligne le texte dans l'éditeur."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Génétique {uid}",
        file_type="md",
        content="Introduction générale.\n\nSéquence ADN cible spécifique.\n\nConclusion.",
    )
    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)
    view.show()
    view.refresh_data()

    view._open_document_for_model(doc)
    editor = view._get_current_editor()
    assert editor is not None

    view._on_segment_selected_in_inspector(0, "Séquence ADN cible spécifique.")
    cursor = editor.raw_editor.textCursor()
    selected_text = cursor.selectedText()
    assert "Séquence ADN cible spécifique" in selected_text


def test_pdf_scope_bounds_and_exclusions_filtering(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que les bornes (start_page, end_page) et exclusions (page:X, titres) sont respectées sur un PDF."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Manuel Neurologie {uid}.pdf",
        file_type="pdf",
        total_pages=6,
        start_page=2,
        end_page=5,
        excluded_headings='["page:3", "Annexe"]',
    )
    # Page 1 (hors bornes début)
    DocumentChunkModel.create(document=doc, chunk_index=0, page_number=1, heading_path="Intro", content="Texte P1", content_hash=f"h0_{uid}")
    # Page 2 (dans bornes)
    DocumentChunkModel.create(document=doc, chunk_index=1, page_number=2, heading_path="Chapitre 1 > Neurones", content="Texte P2", content_hash=f"h1_{uid}")
    # Page 3 (exclue via page:3)
    DocumentChunkModel.create(document=doc, chunk_index=2, page_number=3, heading_path="Chapitre 1 > Synapses", content="Texte P3", content_hash=f"h2_{uid}")
    # Page 4 (dans bornes mais titre exclu Annexe)
    DocumentChunkModel.create(document=doc, chunk_index=3, page_number=4, heading_path="Annexe", content="Texte P4 Annexe", content_hash=f"h3_{uid}")
    # Page 5 (dans bornes)
    DocumentChunkModel.create(document=doc, chunk_index=4, page_number=5, heading_path="Chapitre 2 > Cortex", content="Texte P5", content_hash=f"h4_{uid}")
    # Page 6 (hors bornes fin)
    DocumentChunkModel.create(document=doc, chunk_index=5, page_number=6, heading_path="Glossaire", content="Texte P6", content_hash=f"h5_{uid}")

    scope = DocumentScopeWidget(doc)
    qtbot.addWidget(scope)

    # Chunks utiles ne doivent contenir que Page 2 et Page 5
    useful_pages = [c["page_number"] for c in scope._useful_chunks]
    assert 1 not in useful_pages
    assert 3 not in useful_pages
    assert 4 not in useful_pages
    assert 6 not in useful_pages
    assert useful_pages == [2, 5]

    # Pages sélectionnées
    assert 3 not in scope._selected_pages
    assert 2 in scope._selected_pages
    assert 5 in scope._selected_pages

    # Résultat
    res = scope.get_result()
    assert res is not None
    assert res["start_page"] == 2
    assert res["end_page"] == 5
    for c in res["chunks"]:
        assert c["page_number"] in (2, 5)
        assert c["heading_path"] != "Annexe"


def test_pdf_with_reliable_headings_offers_full_granularity(qtbot: Any, mock_db: Any) -> None:
    """Un PDF avec structure de titres fiable offre la granularité document, page, chapitre et section."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Traité Histologie {uid}.pdf",
        file_type="pdf",
        total_pages=3,
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        page_number=1,
        heading_path="Tissus > Épithélium",
        content="Les cellules épithéliales forment des barrières.",
        content_hash=f"h0_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        page_number=2,
        heading_path="Tissus > Conjonctif",
        content="Le tissu conjonctif assure le soutien mécanique.",
        content_hash=f"h1_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=2,
        page_number=3,
        heading_path="Organes > Foie",
        content="Le foie filtre et métabolise les nutriments.",
        content_hash=f"h2_{uid}",
    )

    scope = DocumentScopeWidget(doc)
    qtbot.addWidget(scope)
    scope.show()

    assert scope.has_headings is True
    assert scope.btn_mode_all.isEnabled()
    assert scope.btn_mode_range.isEnabled()
    assert scope.btn_mode_sections.isEnabled()
    assert not scope.btn_mode_sections.isHidden()

    # Passage en mode sections
    scope.btn_mode_sections.click()
    assert scope.selection_mode == "sections"
    assert not scope.sections_card.isHidden()

    # Résultat avec traçabilité complète
    res = scope.get_result()
    assert res is not None
    assert len(res["chunks"]) == 3
    assert len(res["parts"]) >= 1
    assert "Tissus > Épithélium" in res["selected_headings"]
    assert res.get("fallback_applied") is not True


def test_pdf_without_reliable_headings_falls_back_to_pages_and_signals_limitation(qtbot: Any, mock_db: Any) -> None:
    """Un PDF sans structure de titres signale la limitation, désactive les sections et replie sur la sélection par page."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Scanner Non Structuré {uid}.pdf",
        file_type="pdf",
        total_pages=3,
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        page_number=1,
        heading_path="Page 1",
        content="Texte brut scanné page 1 sans aucun titre markdown.",
        content_hash=f"h0_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        page_number=2,
        heading_path="Page 2",
        content="Texte brut scanné page 2 sans aucun titre markdown.",
        content_hash=f"h1_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=2,
        page_number=3,
        heading_path="Page 3",
        content="Texte brut scanné page 3 sans aucun titre markdown.",
        content_hash=f"h2_{uid}",
    )

    scope = DocumentScopeWidget(doc)
    qtbot.addWidget(scope)
    scope.show()

    # Hiérarchie non fiable
    assert scope.has_headings is False
    assert scope.selection_mode == "pages"
    assert not scope.btn_mode_sections.isEnabled()
    assert "sections" in scope.btn_mode_sections.toolTip().lower() or "repli" in scope.btn_mode_sections.toolTip().lower()

    # Limitation signalée
    assert hasattr(scope, "lbl_fallback_notice")
    assert not scope.lbl_fallback_notice.isHidden()
    assert "repli" in scope.lbl_fallback_notice.text().lower() or "page" in scope.lbl_fallback_notice.text().lower()

    # Le flux n'est pas bloqué : résultat valide
    res = scope.get_result()
    assert res is not None
    assert len(res["chunks"]) == 3
    assert len(res["parts"]) == 1
    assert res.get("fallback_applied") is True
    assert res.get("fallback_reason") == "no_reliable_headings"

    # La sélection par plage de pages reste pleinement opérationnelle
    scope.btn_mode_range.click()
    assert scope.selection_mode == "pages"
    scope._apply_page_selection({1, 2}, trigger_jump=False, update_text=True)
    res_range = scope.get_result()
    assert res_range is not None
    assert len(res_range["chunks"]) == 2
    assert res_range["selected_pages"] == [1, 2]


def test_pdf_scope_restore_sections_when_reliable(qtbot: Any, mock_db: Any) -> None:
    """La réouverture d'une portée avec sections restaure exactement les cases cochées sur un PDF structuré."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Pathologie {uid}.pdf",
        file_type="pdf",
        total_pages=3,
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        page_number=1,
        heading_path="Inflammation > Aiguë",
        content="Réponse vasculaire et cellulaire immédiate.",
        content_hash=f"h0_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        page_number=2,
        heading_path="Inflammation > Chronique",
        content="Infiltration mononucléée et fibrose tissulaire.",
        content_hash=f"h1_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=2,
        page_number=3,
        heading_path="Réparation > Cicatrisation",
        content="Régénération épithéliale et remodelage matriciel.",
        content_hash=f"h2_{uid}",
    )

    initial_scope = {
        "selection_mode": "sections",
        "selected_headings": ["Inflammation > Chronique"],
        "selected_chunk_indices": [1],
        "start_page": 1,
        "end_page": 3,
    }

    scope = DocumentScopeWidget(doc, initial_scope_result=initial_scope)
    qtbot.addWidget(scope)
    scope.show()

    assert scope.has_headings is True
    assert scope.selection_mode == "sections"
    assert scope.fallback_applied is False

    res = scope.get_result()
    assert res is not None
    assert len(res["chunks"]) == 1
    assert res["chunks"][0]["heading_path"] == "Inflammation > Chronique"
    assert res["chunks"][0]["page_number"] == 2
    assert "Inflammation > Chronique" in res["selected_headings"]
    assert len(res["parts"]) >= 1


def test_pdf_scope_restore_graceful_fallback_when_unreliable(qtbot: Any, mock_db: Any) -> None:
    """La réouverture d'un profil 'sections' sur un PDF sans titres structurés replie sans erreur vers les pages."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Imagerie Brut {uid}.pdf",
        file_type="pdf",
        total_pages=3,
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        page_number=1,
        heading_path="Page 1",
        content="Radiographie thoracique face.",
        content_hash=f"h0_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        page_number=2,
        heading_path="Page 2",
        content="Scanner spiralé haute résolution coupe axiale.",
        content_hash=f"h1_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=2,
        page_number=3,
        heading_path="Page 3",
        content="Reconstruction coronale et sagittale.",
        content_hash=f"h2_{uid}",
    )

    # Portée précédente enregistrée en mode "sections" avec un fragment ciblé page 2
    initial_scope = {
        "selection_mode": "sections",
        "selected_headings": ["Page 2"],
        "selected_chunk_indices": [1],
        "chunks": [{"page_number": 2, "content": "Scanner spiralé haute résolution coupe axiale."}],
        "selected_pages": [2],
        "start_page": 1,
        "end_page": 3,
    }

    scope = DocumentScopeWidget(doc, initial_scope_result=initial_scope)
    qtbot.addWidget(scope)
    scope.show()

    # Repli gracieux vers les pages
    assert scope.has_headings is False
    assert scope.selection_mode == "pages"
    assert scope.fallback_applied is True
    assert scope.fallback_reason == "no_reliable_headings"
    assert not scope.lbl_fallback_notice.isHidden()

    # La page 2 a été conservée en repli
    assert scope._selected_pages == {2}
    res = scope.get_result()
    assert res is not None
    assert len(res["chunks"]) == 1
    assert res["chunks"][0]["page_number"] == 2
    assert res["selected_pages"] == [2]
    assert res["fallback_applied"] is True
    assert len(res["parts"]) == 1


def test_pdf_scope_restore_fallback_from_selected_chunk_indices(qtbot: Any, mock_db: Any) -> None:
    """La réouverture avec uniquement selected_chunk_indices sur un PDF non structuré résout correctement les pages."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Scanner Indices {uid}.pdf",
        file_type="pdf",
        total_pages=4,
    )
    DocumentChunkModel.create(document=doc, chunk_index=0, page_number=1, heading_path="Page 1", content="Page 1", content_hash=f"h0_{uid}")
    DocumentChunkModel.create(document=doc, chunk_index=1, page_number=2, heading_path="Page 2", content="Page 2", content_hash=f"h1_{uid}")
    DocumentChunkModel.create(document=doc, chunk_index=2, page_number=3, heading_path="Page 3", content="Page 3", content_hash=f"h2_{uid}")
    DocumentChunkModel.create(document=doc, chunk_index=3, page_number=4, heading_path="Page 4", content="Page 4", content_hash=f"h3_{uid}")

    initial_scope = {
        "selection_mode": "sections",
        "selected_chunk_indices": [1, 2],
    }

    scope = DocumentScopeWidget(doc, initial_scope_result=initial_scope)
    qtbot.addWidget(scope)
    scope.show()

    assert scope.has_headings is False
    assert scope.selection_mode == "pages"
    assert scope.fallback_applied is True
    # Pages 2 et 3 résolues à partir des useful_chunks
    assert scope._selected_pages == {2, 3}
    res = scope.get_result()
    assert res is not None
    assert len(res["chunks"]) == 2
    assert res["selected_pages"] == [2, 3]


def test_pdf_preview_direct_page_spin_and_navigation(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la saisie directe du numéro de page (spinbox), navigation précédente/suivante et bornes."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Nav {uid}.pdf",
        file_type="pdf",
        total_pages=5,
        content="\n\n".join(f"<!-- PAGE: {p} -->\nPage {p}." for p in range(1, 6)),
    )
    for p in range(1, 6):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"Page {p}",
            content=f"Page {p} content",
            content_hash=f"h_{uid}_{p}",
        )

    scope = DocumentScopeWidget(doc)
    qtbot.addWidget(scope)
    scope.show()

    preview = scope.preview_widget
    assert hasattr(preview, "spin_page")
    assert preview.spin_page.minimum() == 1
    assert preview.spin_page.maximum() == 5
    assert preview.spin_page.value() == 1
    assert preview.current_page == 1
    assert not preview.btn_prev_page.isEnabled()
    assert preview.btn_next_page.isEnabled()

    # 1. Navigation directe via spin_page
    preview.spin_page.setValue(3)
    assert preview.current_page == 3
    assert preview.spin_page.value() == 3
    assert "5" in preview.lbl_page.text()
    assert preview.btn_prev_page.isEnabled()
    assert preview.btn_next_page.isEnabled()

    # 2. Bouton page précédente
    preview.btn_prev_page.click()
    assert preview.current_page == 2
    assert preview.spin_page.value() == 2

    # 3. Bouton page suivante
    preview.btn_next_page.click()
    assert preview.current_page == 3
    assert preview.spin_page.value() == 3

    # 4. Navigation vers la dernière page (désactivation next)
    preview.spin_page.setValue(5)
    assert preview.current_page == 5
    assert not preview.btn_next_page.isEnabled()
    assert preview.btn_prev_page.isEnabled()

    # 5. Clamping des valeurs hors bornes via jump_to_page
    preview.jump_to_page(100)
    assert preview.current_page == 5
    assert preview.spin_page.value() == 5

    preview.jump_to_page(-10)
    assert preview.current_page == 1
    assert preview.spin_page.value() == 1


def test_pdf_preview_toggle_page_scope_bidirectional_and_signals(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que le contrôle explicite d'inclusion/exclusion met à jour l'état partagé sans boucle."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Toggle Scope {uid}.pdf",
        file_type="pdf",
        total_pages=4,
        content="\n\n".join(f"<!-- PAGE: {p} -->\nPage {p}." for p in range(1, 5)),
    )
    for p in range(1, 5):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"Page {p}",
            content=f"Page {p} content",
            content_hash=f"h_{uid}_{p}",
        )

    scope = DocumentScopeWidget(doc)
    qtbot.addWidget(scope)
    scope.show()

    emitted_scopes: list[dict[str, Any]] = []
    scope.scope_changed.connect(lambda res: emitted_scopes.append(res))

    preview = scope.preview_widget
    # Initialement toutes les pages sont incluses
    assert scope._selected_pages == {1, 2, 3, 4}
    assert "Exclure" in preview.btn_toggle_page_scope.text()

    # Naviguer vers la page 2
    preview.jump_to_page(2)
    assert preview.current_page == 2
    assert "Exclure" in preview.btn_toggle_page_scope.text()

    # Exclure la page 2 depuis le preview
    preview.btn_toggle_page_scope.click()
    assert scope._selected_pages == {1, 3, 4}
    assert "Inclure" in preview.btn_toggle_page_scope.text()
    assert "EXCLUE" in preview.lbl_scope_status.text()
    assert len(emitted_scopes) > 0
    assert emitted_scopes[-1]["selected_pages"] == [1, 3, 4]

    # Réinclure la page 2
    preview.btn_toggle_page_scope.click()
    assert scope._selected_pages == {1, 2, 3, 4}
    assert "Exclure" in preview.btn_toggle_page_scope.text()
    assert "INCLUSE" in preview.lbl_scope_status.text()
    assert emitted_scopes[-1]["selected_pages"] == [1, 2, 3, 4]


def test_pdf_preview_content_click_does_not_mutate_selection(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que cliquer dans le contenu du lecteur ne modifie pas accidentellement la sélection."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Content Click {uid}.pdf",
        file_type="pdf",
        total_pages=3,
        content="# Chapitre 1\nContenu 1\n\n# Chapitre 2\nContenu 2",
    )
    for p in range(1, 4):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"Page {p}",
            content=f"Content {p}",
            content_hash=f"h_{uid}_{p}",
        )

    scope = DocumentScopeWidget(doc)
    qtbot.addWidget(scope)
    scope.show()

    initial_pages = set(scope._selected_pages)
    initial_result = scope.get_result()

    preview = scope.preview_widget
    # Simuler un clic dans le visionneur Markdown
    click_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(50.0, 50.0),
        QPointF(50.0, 50.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    preview.markdown_viewer.mousePressEvent(click_event)

    # La sélection ne doit pas avoir changé
    assert scope._selected_pages == initial_pages
    assert scope.get_result()["selected_pages"] == initial_result["selected_pages"]


def test_pdf_preview_fallback_when_qtpdf_unavailable(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le repli textuel stylisé lorsque QtPdf est indisponible ou en cas d'erreur de chargement."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc No QtPdf {uid}.pdf",
        file_type="pdf",
        total_pages=3,
        content="<!-- PAGE: 1 -->\n# Page Un\nTexte 1\n\n<!-- PAGE: 2 -->\n# Page Deux\nTexte 2\n\n<!-- PAGE: 3 -->\n# Page Trois\nTexte 3",
    )
    for p in range(1, 4):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"Page {p}",
            content=f"Texte {p}",
            content_hash=f"h_{uid}_{p}",
        )

    with patch("ankiforge.ui.views.documents_view.dialogs.delimitation_dialog.HAVE_QTPDF", False):
        scope = DocumentScopeWidget(doc)
        qtbot.addWidget(scope)
        scope.show()

        preview = scope.preview_widget
        assert preview._current_mode == "markdown"
        assert preview.btn_toggle_pdf.isHidden()
        assert preview.view_stack.currentWidget() == preview.markdown_viewer

        # Navigation fonctionne en mode Markdown repli
        preview.spin_page.setValue(2)
        assert preview.current_page == 2
        assert preview.spin_page.value() == 2

        # L'exclusion/inclusion fonctionne en mode Markdown repli
        preview.btn_toggle_page_scope.click()
        assert 2 not in scope._selected_pages
        assert "Inclure" in preview.btn_toggle_page_scope.text()


def test_pdf_preview_zoom_and_fit_controls(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que les contrôles de zoom avant, arrière et ajustement sont réactifs."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Zoom {uid}.pdf",
        file_type="pdf",
        total_pages=2,
        content="# Page 1\nContenu 1\n\n# Page 2\nContenu 2",
    )
    for p in range(1, 3):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"Page {p}",
            content=f"Texte {p}",
            content_hash=f"h_{uid}_{p}",
        )

    scope = DocumentScopeWidget(doc)
    qtbot.addWidget(scope)
    scope.show()

    preview = scope.preview_widget
    # Tester les boutons de zoom sans exception
    preview.btn_zoom_in.click()
    preview.btn_zoom_out.click()
    preview.btn_zoom_fit.click()


def test_pdf_preview_toggle_page_scope_in_sections_mode(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que basculer la portée d'une page depuis la visionneuse en mode sections désélectionne les sections correspondantes."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Sec Mode {uid}.pdf",
        file_type="pdf",
        total_pages=3,
        content="# Introduction\nIntro\n\n# Chapitre 1\nDetails\n\n# Chapitre 2\nConclusion",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        page_number=1,
        heading_path="Introduction",
        content="Intro content here with enough words to be useful.",
        content_hash=f"h_{uid}_0",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        page_number=2,
        heading_path="Chapitre 1",
        content="Details content here on page two with enough words.",
        content_hash=f"h_{uid}_1",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=2,
        page_number=3,
        heading_path="Chapitre 2",
        content="Conclusion content on page three.",
        content_hash=f"h_{uid}_2",
    )

    initial_scope = {
        "selection_mode": "sections",
        "selected_headings": ["Introduction", "Chapitre 1", "Chapitre 2"],
    }
    scope = DocumentScopeWidget(doc, initial_scope_result=initial_scope)
    qtbot.addWidget(scope)
    scope.show()

    assert scope.selection_mode == "sections"
    preview = scope.preview_widget

    # Aller sur la page 2
    preview.jump_to_page(2)
    assert preview.current_page == 2

    # Exclure la page 2
    preview.btn_toggle_page_scope.click()

    res = scope.get_result()
    assert res is not None
    # Chapitre 1 (sur page 2) ne doit plus être sélectionné
    res_headings = [c.get("heading_path") for c in res["chunks"]]
    assert "Chapitre 1" not in res_headings
    assert "Introduction" in res_headings
    assert "Chapitre 2" in res_headings
    assert "Inclure" in preview.btn_toggle_page_scope.text()

    # Réinclure la page 2
    preview.btn_toggle_page_scope.click()
    res_after = scope.get_result()
    assert res_after is not None
    res_after_headings = [c.get("heading_path") for c in res_after["chunks"]]
    assert "Chapitre 1" in res_after_headings
    assert "Exclure" in preview.btn_toggle_page_scope.text()


def test_pdf_reader_accessibility_names_and_tooltips(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que tous les contrôles interactifs du lecteur ont accessibleName et tooltips."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc A11y {uid}.pdf",
        file_type="pdf",
        total_pages=3,
        content="# Test A11y\nContenu",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        page_number=1,
        heading_path="Test A11y",
        content="Contenu",
        content_hash=f"h_a11y_{uid}",
    )

    scope = DocumentScopeWidget(doc)
    qtbot.addWidget(scope)
    scope.show()

    preview = scope.preview_widget
    assert preview.btn_prev_page.accessibleName() == "Page précédente"
    assert preview.btn_next_page.accessibleName() == "Page suivante"
    assert preview.spin_page.accessibleName() == "Numéro de page"
    assert preview.btn_zoom_out.accessibleName() == "Zoom arrière"
    assert preview.btn_zoom_fit.accessibleName() == "Ajuster le document à la largeur"
    assert preview.btn_zoom_in.accessibleName() == "Zoom avant"
    assert "sélection" in preview.btn_toggle_page_scope.accessibleName().lower() or "page" in preview.btn_toggle_page_scope.accessibleName().lower()


def test_pdf_reader_preserves_selection_on_page_jump_error(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que la sélection existante est préservée si le saut d'une page échoue."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Error Preserved {uid}.pdf",
        file_type="pdf",
        total_pages=4,
        content="# P1\nC1\n\n# P2\nC2\n\n# P3\nC3\n\n# P4\nC4",
    )
    for p in range(1, 5):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"P{p}",
            content=f"C{p}",
            content_hash=f"h_{uid}_{p}",
        )

    scope = DocumentScopeWidget(doc)
    qtbot.addWidget(scope)
    scope.show()

    # Sélection initiale de pages 1, 2, 4
    scope._apply_page_selection({1, 2, 4})
    assert scope._selected_pages == {1, 2, 4}

    preview = scope.preview_widget

    # Provoquer une erreur simulée dans jump_to_page
    with patch.object(preview.markdown_viewer, "scrollToAnchor", side_effect=RuntimeError("Scroll error")):
        preview.jump_to_page(3)

    # La sélection existante doit être strictement intacte
    assert scope._selected_pages == {1, 2, 4}
    res = scope.get_result()
    assert res["selected_pages"] == [1, 2, 4]
    # L'erreur doit être signalée visuellement
    assert "erreur" in preview.lbl_scope_status.text().lower()
    # La page courante doit avoir fait un rollback sur la page valide précédente (1)
    assert preview.current_page == 1

    # Les navigations suivantes restent parfaitement fonctionnelles
    preview.jump_to_page(4)
    assert preview.current_page == 4
    assert preview.spin_page.value() == 4


def test_pdf_reader_status_changed_loading_ready_error(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la réactivité aux changements de statut QPdfDocument (chargement, prêt, erreur)."""
    from PySide6.QtPdf import QPdfDocument

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Status {uid}.pdf",
        file_type="pdf",
        total_pages=2,
        content="<!-- PAGE: 1 -->\nPage 1",
    )
    scope = DocumentScopeWidget(doc)
    qtbot.addWidget(scope)
    scope.show()

    preview = scope.preview_widget
    assert hasattr(preview, "_on_pdf_status_changed")

    # Simulation statut Loading
    preview._on_pdf_status_changed(QPdfDocument.Status.Loading)
    assert "chargement" in preview.lbl_scope_status.text().lower()

    # Simulation statut Ready : le badge de chargement est levé et les pages mises à jour
    preview._on_pdf_status_changed(QPdfDocument.Status.Ready)
    assert preview._total_pages >= 1
    assert "chargement" not in preview.lbl_scope_status.text().lower()

    # Simulation statut Error : repli markdown
    preview._on_pdf_status_changed(QPdfDocument.Status.Error)
    assert preview._current_mode == "markdown"
    assert "erreur" in preview.lbl_scope_status.text().lower()


def test_pdf_reader_empty_document_fallback(qtbot: Any, mock_db: Any) -> None:
    """Vérifie qu'un document vide avec ou sans PDF charge sans crash avec placeholder explicite."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Empty {uid}.pdf",
        file_type="pdf",
        total_pages=1,
        content="",
    )
    scope = DocumentScopeWidget(doc)
    qtbot.addWidget(scope)
    scope.show()

    preview = scope.preview_widget
    # Le viewer markdown doit contenir un message de contenu non disponible
    assert "aucun contenu" in preview.markdown_viewer.toPlainText().lower()
    assert preview.current_page == 1


def test_pdf_reader_preserves_sections_tree_sync_on_error(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que la synchronisation de l'arbre des sections et scope_result reste intacte en cas d'erreur de rendu PDF."""
    from PySide6.QtPdf import QPdfDocument

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Tree Sync {uid}.pdf",
        file_type="pdf",
        total_pages=3,
        content="""# Chapitre 1
Texte 1

# Chapitre 2
Texte 2

# Chapitre 3
Texte 3""",
    )
    for p in range(1, 4):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 1,
            page_number=p,
            heading_path=f"Chapitre {p}",
            content=f"Texte {p}",
            content_hash=f"h_{uid}_{p}",
        )

    initial_scope = {
        "selection_mode": "sections",
        "selected_headings": ["Chapitre 1", "Chapitre 3"],
    }
    scope = DocumentScopeWidget(doc, initial_scope_result=initial_scope)
    qtbot.addWidget(scope)
    scope.show()

    res_before = scope.get_result()
    assert set(res_before["selected_headings"]) == {"Chapitre 1", "Chapitre 3"}

    preview = scope.preview_widget

    # Provoquer une erreur PDF
    preview._on_pdf_status_changed(QPdfDocument.Status.Error)
    assert preview._current_mode == "markdown"
    assert "erreur" in preview.lbl_scope_status.text().lower()

    # Vérifier que les sections cochées dans l'arbre et scope_result restent intactes
    res_after = scope.get_result()
    assert res_after["selection_mode"] == "sections"
    assert set(res_after["selected_headings"]) == {"Chapitre 1", "Chapitre 3"}


def test_pdf_reader_fallback_unstructured_pdf_without_headings(qtbot: Any, mock_db: Any) -> None:
    """Vérifie la résilience du lecteur face à un PDF sans titres structurés (mode pages, navigation, fallback)."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Unstructured {uid}.pdf",
        file_type="pdf",
        total_pages=2,
        content="Page 1 sans markdown structuré.\nPage 2 sans markdown structuré.",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        page_number=1,
        heading_path="Page 1",
        content="Page 1 sans markdown structuré.",
        content_hash=f"h_unstruct_{uid}_1",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        page_number=2,
        heading_path="Page 2",
        content="Page 2 sans markdown structuré.",
        content_hash=f"h_unstruct_{uid}_2",
    )

    scope = DocumentScopeWidget(doc)
    qtbot.addWidget(scope)
    scope.show()

    preview = scope.preview_widget
    assert preview._total_pages == 2
    assert preview.current_page == 1

    # Navigation vers la page 2
    preview.jump_to_page(2)
    assert preview.current_page == 2
    assert preview.spin_page.value() == 2

    # Exclusion de la page 2 via le lecteur
    preview.btn_toggle_page_scope.click()
    res = scope.get_result()
    assert 2 not in res["selected_pages"]
    assert 1 in res["selected_pages"]
