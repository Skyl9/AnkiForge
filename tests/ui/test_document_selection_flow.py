from __future__ import annotations

import uuid
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from ankiforge.database.models import (
    DocumentModel,
    FolderModel,
)
from ankiforge.ui.components.document_picker_button import DocumentPickerButton
from ankiforge.ui.components.document_select_window import DocumentSelectWindow
from ankiforge.ui.views.batch_view import BatchView
from ankiforge.ui.views.creation_view import CreationView


@pytest.mark.ui
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


@pytest.mark.ui
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


@pytest.mark.ui
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


@pytest.mark.ui
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


@pytest.mark.ui
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


@pytest.mark.ui
def test_batch_view_document_item_click_and_segments(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que cliquer sur un document dans BatchView active le SegmentInspector et gère les segments."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Physiologie {uid}", file_type="md", content="## Section 1\nTexte 1\n## Section 2\nTexte 2")

    view = BatchView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # Trouver l'item du document dans docs_list
    doc_item: QListWidgetItem | None = None
    for i in range(view.docs_list.count()):
        it = view.docs_list.item(i)
        if it.data(Qt.ItemDataRole.UserRole) and it.data(Qt.ItemDataRole.UserRole).id == doc.id:
            doc_item = it
            break

    assert doc_item is not None

    # Clic sur le document -> doit afficher et configurer le segment inspector
    view._on_doc_item_clicked(doc_item)
    assert not view.segment_inspector.isHidden()
    assert view._segment_inspector_doc == doc
    assert view.segment_inspector._doc == doc

    # Double clic -> bascule la case à cocher
    assert doc_item.checkState() == Qt.CheckState.Unchecked
    view._on_doc_item_double_clicked(doc_item)
    assert doc_item.checkState() == Qt.CheckState.Checked

    # Ajouter à la queue avec segments configurés
    view._on_add_to_queue_clicked()
    assert len(view.queue_tasks_data) >= 1
    added_task = view.queue_tasks_data[-1]
    assert added_task["doc"].id == doc.id


@pytest.mark.ui
def test_batch_view_picker_button_and_queue_flow(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que la sélection de document par DocumentPickerButton dans BatchView fonctionne en miroir de CreationView."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours Bio {uid}", file_type="pdf", total_pages=15, content="Page 1\n<!-- PAGE: 2 -->\nPage 2")

    view = BatchView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # Initialement masqué
    assert view.segment_inspector.isHidden()
    assert view.doc_picker_btn.get_document() is None

    # Sélection via doc_picker_btn
    view.doc_picker_btn.set_document(doc)
    assert not view.segment_inspector.isHidden()
    assert view._segment_inspector_doc == doc
    assert view.segment_inspector._doc == doc
    assert "Cours Bio" in view.doc_picker_btn.title_label.text()
    assert "1 sélectionné(s)" in view.lbl_selected_docs_count.text()

    # Ajout à la queue
    view._on_add_to_queue_clicked()
    assert len(view.queue_tasks_data) >= 1
    assert view.queue_tasks_data[-1]["doc"].id == doc.id

    # Désélection
    view.doc_picker_btn.clear_document()
    assert view.segment_inspector.isHidden()
    assert view._segment_inspector_doc is None


@pytest.mark.ui
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


@pytest.mark.ui
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


@pytest.mark.ui
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


@pytest.mark.ui
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
