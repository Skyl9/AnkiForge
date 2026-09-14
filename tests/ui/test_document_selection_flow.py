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


@pytest.mark.ui
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


@pytest.mark.ui
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

    # 2. Section -> Slider : cocher la section de la page 5 élargit spin_p_end à 5
    row_w5 = dlg.sections_list.itemWidget(dlg.sections_list.item(4))
    assert isinstance(row_w5, SectionRowWidget)
    row_w5.checkbox.setChecked(True)

    assert dlg.spin_p_end.value() == 5


@pytest.mark.ui
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

    # 2. Section -> Slider : cocher Chapitre 4 élargit spin_p_end à 4
    row_w4 = dlg.sections_list.itemWidget(dlg.sections_list.item(3))
    assert isinstance(row_w4, SectionRowWidget)
    row_w4.checkbox.setChecked(True)
    assert dlg.spin_p_end.value() == 4

    # 3. Vue Finale Assemblée
    assert dlg.preview_stack.currentIndex() == 0  # Document Source par défaut
    dlg.btn_view_final.click()
    assert dlg.preview_stack.currentIndex() == 1

    final_text = dlg.final_preview_browser.toPlainText()
    assert "Texte du chapitre 2" in final_text
    assert "Texte du chapitre 3" in final_text
    assert "Texte du chapitre 4" in final_text
    assert "Texte du chapitre 1" not in final_text

    # Revenir sur Document Source
    dlg.btn_view_source.click()
    assert dlg.preview_stack.currentIndex() == 0


@pytest.mark.ui
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


@pytest.mark.ui
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

    # Vérifier que "page 3" est persisté dans doc.excluded_headings
    fresh_doc = DocumentModel.get_by_id(doc.id)
    assert "page 3" in fresh_doc.excluded_headings

    # 2. Réouverture de DocumentDelimitationDialog : Page 3 DOIT rester décochée
    dlg2 = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg2)
    assert dlg2.sections_list.item(2).checkState() == Qt.CheckState.Unchecked
    assert dlg2.sections_list.item(0).checkState() == Qt.CheckState.Checked  # Page 1 cochée
    assert dlg2.sections_list.item(1).checkState() == Qt.CheckState.Checked  # Page 2 cochée

    # 3. Manipulation du slider de pages (déplacer puis ré-étendre à toute la portée)
    dlg2.btn_scope_mode_range.click()
    dlg2.spin_p_start.setValue(1)
    dlg2.spin_p_end.setValue(5)

    # Page 3 NE DOIT PAS être cochée par le mouvement du slider
    assert dlg2.sections_list.item(2).checkState() == Qt.CheckState.Unchecked

    # 4. DocumentScopeDialog ne contient pas la page 3
    scope_dlg = DocumentScopeDialog(doc)
    qtbot.addWidget(scope_dlg)
    useful_titles = [u["title"] for u in scope_dlg._useful_chunks]
    assert "Page 3" not in useful_titles
    assert len(scope_dlg._useful_chunks) == 4


@pytest.mark.ui
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

    # Le curseur de début doit se rétrécir automatiquement à 2
    assert dlg.spin_p_start.value() == 2
    assert dlg.slider_p_start.value() == 2
    assert dlg.range_bar._start == 2
    # La visionneuse doit avoir sauté à la page 1 et afficher EXCLUE
    assert dlg.preview_widget._current_page == 1
    assert 1 not in dlg.preview_widget._included_pages
    assert "Page 1 EXCLUE" in dlg.preview_widget.lbl_scope_status.text()

    # 3. Décocher la section 5 (page 5)
    w_row5 = dlg.sections_list.itemWidget(dlg.sections_list.item(4))
    assert isinstance(w_row5, SectionRowWidget)
    w_row5.checkbox.setChecked(False)

    # Le curseur de fin doit se rétrécir automatiquement à 4
    assert dlg.spin_p_end.value() == 4
    assert dlg.slider_p_end.value() == 4
    assert dlg.range_bar._end == 4
    assert dlg.preview_widget._current_page == 5
    assert 5 not in dlg.preview_widget._included_pages
    assert "Page 5 EXCLUE" in dlg.preview_widget.lbl_scope_status.text()

    # 4. Déplacement du slider de début à 3
    dlg.spin_p_start.setValue(3)
    assert dlg.preview_widget._current_page == 3
    assert 3 in dlg.preview_widget._included_pages
    assert "Page 3 INCLUSE" in dlg.preview_widget.lbl_scope_status.text()
    # La section 2 (page 2) doit avoir été décochée automatiquement par le déplacement de borne
    assert dlg.sections_list.item(1).checkState() == Qt.CheckState.Unchecked


@pytest.mark.ui
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

    # Rétrécissement dynamique des sliders vers la plage réelle [2, 5]
    assert scope_dlg.spin_p_start.value() == 2
    assert scope_dlg.slider_p_start.value() == 2
    assert scope_dlg.range_bar._start == 2
    assert scope_dlg.preview_widget._current_page == 1
    assert "Page 1 EXCLUE" in scope_dlg.preview_widget.lbl_scope_status.text()

    # La vue finale assemblée ne doit plus contenir Segment 1
    scope_dlg._refresh_final_preview()
    assert "Segment 1" not in scope_dlg.final_preview_browser.toPlainText()
    assert "Segment 2" in scope_dlg.final_preview_browser.toPlainText()

    # 3. Décocher la section 5 (page 5)
    w_row5 = scope_dlg.sections_list.itemWidget(scope_dlg.sections_list.item(4))
    assert isinstance(w_row5, SectionRowWidget)
    w_row5.checkbox.setChecked(False)

    assert scope_dlg.spin_p_end.value() == 4
    assert scope_dlg.slider_p_end.value() == 4
    assert scope_dlg.preview_widget._current_page == 5
    assert "Page 5 EXCLUE" in scope_dlg.preview_widget.lbl_scope_status.text()

    # 4. Action Tout cocher
    scope_dlg._set_all_checked(True)
    assert scope_dlg.spin_p_start.value() == 1
    assert scope_dlg.spin_p_end.value() == 5
    assert 1 in scope_dlg.preview_widget._included_pages
    assert 5 in scope_dlg.preview_widget._included_pages
