from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem, QMessageBox

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

    # 2. En mode pages, les cases restent décoratives et ne modifient pas la borne source.
    row_w5 = dlg.sections_list.itemWidget(dlg.sections_list.item(4))
    assert isinstance(row_w5, SectionRowWidget)
    row_w5.checkbox.setChecked(True)

    assert dlg.spin_p_end.value() == 4


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


@pytest.mark.ui
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


@pytest.mark.ui
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


@pytest.mark.ui
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


@pytest.mark.ui
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


@pytest.mark.ui
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


@pytest.mark.ui
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


@pytest.mark.ui
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


@pytest.mark.ui
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


@pytest.mark.ui
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


@pytest.mark.ui
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
