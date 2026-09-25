import uuid

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSizePolicy, QTreeWidgetItem

from ankiforge.database.models import (
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
)
from ankiforge.ui.views.documents_view import (
    DocumentDelimitationDialog,
    DocumentsView,
    RAGTestDialog,
)

pytestmark = pytest.mark.ui


@pytest.mark.slow
def test_documents_view_selection_and_coverage(qtbot):
    """Vérifie le chargement des chapitres et les indicateurs de couverture dans DocumentsView."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Anatomie {uid}",
        content="# Chapitre 1 : Le Cœur\n\nLe cœur est un organe musculaire creux qui assure la circulation sanguine.\n\n# Chapitre 2 : Les Poumons\n\nLes poumons sont les organes de la respiration.",
        file_type="md",
    )

    chunk1 = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Anatomie > Chapitre 1 : Le Cœur",
        page_number=1,
        content="Le cœur est un organe musculaire creux qui assure la circulation sanguine.",
        content_hash=f"hash1_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path="Anatomie > Chapitre 2 : Les Poumons",
        page_number=2,
        content="Les poumons sont les organes de la respiration.",
        content_hash=f"hash2_{uid}",
    )

    deck = DeckModel.create(name=f"Deck Médecine {uid}")
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(
        name=f"Model {uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]',
        css_style="",
    )
    note1 = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt)
    note1.add_version({"Front": "Rôle du cœur ?", "Back": "Pompe sanguine"}, source="manual")
    from ankiforge.database.models import CardModel

    CardModel.create(note=note1, deck=deck, template_index=0)
    NoteChunkLinkModel.create(note=note1, chunk=chunk1)

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)

    # Simuler la sélection du document
    view._current_doc_id = doc.id
    view._refresh_chapters_list()
    view._update_rag_status_pill()

    # Vérifications du sommaire
    assert view.chapters_list.count() == 2
    item1 = view.chapters_list.item(0)
    assert "🟢" in item1.text()
    assert "Couvert" in item1.text()

    item2 = view.chapters_list.item(1)
    assert "⚠️" in item2.text()
    assert "Non couvert" in item2.text()

    assert "50%" in view.lbl_coverage_summary.text()
    assert "2 chunks" in view.rag_status_pill.text()

    # Vérifier l'émission du signal de navigation vers la création
    emitted_nav = []
    view.request_navigation.connect(lambda target, payload: emitted_nav.append((target, payload)))

    view.chapters_list.setCurrentRow(1)
    view._on_forge_selected_chapter()

    assert len(emitted_nav) == 1
    target, payload = emitted_nav[0]
    assert target == "creation"
    assert "poumons" in payload["text_source"].lower()


def test_documents_view_import_button_has_stable_initial_size(qtbot):
    """Le bouton Importer reste lisible dès l'ouverture de My Documents."""
    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)

    assert view.explorer_panel.minimumWidth() == 300
    assert view.explorer_panel.maximumWidth() == 360
    assert view.btn_import.minimumWidth() == 96
    assert view.btn_import.height() == 30
    assert view.btn_import.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.MinimumExpanding
    assert view.btn_marker.isHidden()


def test_documents_view_shows_marker_ocr_only_for_pdf(qtbot):
    """Le bouton Marker OCR est réservé aux documents PDF."""
    uid = uuid.uuid4().hex[:6]
    markdown_doc = DocumentModel.create(
        title=f"Notes {uid}",
        content="# Notes",
        file_type="md",
    )
    pdf_doc = DocumentModel.create(
        title=f"Document PDF {uid}",
        content="Texte extrait",
        file_type="pdf",
    )

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)

    markdown_item = QTreeWidgetItem(view.tree_explorer)
    markdown_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "doc", "id": markdown_doc.id})
    view.tree_explorer.setCurrentItem(markdown_item)
    view._on_document_selected()
    assert view.btn_marker.isHidden()

    pdf_item = QTreeWidgetItem(view.tree_explorer)
    pdf_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "doc", "id": pdf_doc.id})
    view.tree_explorer.setCurrentItem(pdf_item)
    view._on_document_selected()
    assert not view.btn_marker.isHidden()


def test_documents_view_progressive_disclosure_panel(qtbot):
    """Le panneau droit (Sommaire/RAG/Plan) n'apparaît que lorsqu'un document est sélectionné."""
    from ankiforge.database.models import FolderModel

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Progressive {uid}",
        content="# Chapitre\n\nContenu.",
        file_type="md",
    )
    folder = FolderModel.create(name=f"Dossier {uid}")

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)

    # Initialement : aucun document sélectionné → panneau masqué
    assert view.coverage_panel.isHidden()

    # Sélection d'un document → panneau visible
    doc_item = QTreeWidgetItem(view.tree_explorer)
    doc_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "doc", "id": doc.id})
    view.tree_explorer.setCurrentItem(doc_item)
    view._on_document_selected()
    assert not view.coverage_panel.isHidden()

    # Désélection → panneau masqué
    view.tree_explorer.clearSelection()
    view._on_document_selected()
    assert view.coverage_panel.isHidden()

    # Sélection d'un dossier → panneau masqué
    folder_item = QTreeWidgetItem(view.tree_explorer)
    folder_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": folder.id})
    view.tree_explorer.setCurrentItem(folder_item)
    view._on_document_selected()
    assert view.coverage_panel.isHidden()


def test_document_delimitation_dialog(qtbot):
    """Vérifie la modale de délimitation de pages et de filtrage des chapitres."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Livre Biologie {uid}",
        content="# Sommaire\n\nPage 1.\n\n# Chapitre 1 : La Cellule\n\nStructure cellulaire.\n\n# Bibliographie\n\nOuvrages de référence.",
        file_type="md",
    )

    dlg = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg)

    # Vérifier les sections peuplées (toutes cochées par défaut car filtre anti-bruit défaillant supprimé)
    assert dlg.sections_list.count() == 3
    assert dlg.sections_list.item(0).checkState() == Qt.CheckState.Checked
    assert dlg.sections_list.item(1).checkState() == Qt.CheckState.Checked
    assert dlg.sections_list.item(2).checkState() == Qt.CheckState.Checked

    # Exclure manuellement Sommaire et Bibliographie
    dlg.sections_list.item(0).setCheckState(Qt.CheckState.Unchecked)
    dlg.sections_list.item(2).setCheckState(Qt.CheckState.Unchecked)

    # Appliquer la délimitation
    dlg.chk_revectorize.setChecked(False)
    dlg._on_apply()

    # Vérifier les chunks mis à jour en base
    chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc))
    assert len(chunks) == 1
    assert "Cellule" in chunks[0].heading_path


def test_document_delimitation_applies_pdf_page_range(qtbot):
    """La sélection de pages PDF filtre réellement les chunks avant le RAG."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Pages PDF {uid}",
        file_type="pdf",
        content=(
            "<!-- PAGE: 1 -->\n"
            "Introduction générale suffisamment longue pour créer un chunk.\n"
            "<!-- PAGE: 2 -->\n"
            "Contenu du chapitre principal suffisamment long pour créer un chunk.\n"
            "<!-- PAGE: 3 -->\n"
            "Annexe documentaire suffisamment longue pour créer un chunk."
        ),
    )

    dlg = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg)
    dlg.spin_p_start.setValue(2)
    dlg.spin_p_end.setValue(2)
    dlg.chk_revectorize.setChecked(False)
    dlg._on_apply()

    chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc))
    assert len(chunks) == 1
    assert chunks[0].page_number == 2
    assert "Contenu du chapitre" in chunks[0].content


def test_document_delimitation_rejects_page_range_outside_markdown(qtbot):
    """Une borne dépassant les pages détectées est refusée pour un document paginé."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Pages PDF {uid}",
        file_type="pdf",
        content=("<!-- PAGE: 1 -->\nPremière page Markdown suffisamment longue pour créer un chunk.\n<!-- PAGE: 2 -->\nDeuxième page Markdown suffisamment longue pour créer un chunk."),
    )

    dlg = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg)
    dlg.spin_p_end.setValue(2)
    dlg.spin_p_start.setValue(1)
    dlg.spin_p_end.setRange(1, 99)
    dlg.chk_revectorize.setChecked(False)
    dlg.spin_p_end.setValue(99)
    dlg._on_apply()

    assert dlg.result() == 0
    assert DocumentChunkModel.select().where(DocumentChunkModel.document == doc).count() == 0


def test_rag_test_dialog(qtbot):
    """Vérifie le dialogue de recherche sémantique interactive RAG."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc RAG {uid}",
        content="Les mitochondries produisent l'énergie sous forme d'ATP.",
        file_type="md",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Bioénergétique",
        page_number=5,
        content="Les mitochondries produisent l'énergie sous forme d'ATP.",
        content_hash=f"hash_{uid}",
    )

    from ankiforge.services.ai.rag_service import RAGService

    rag = RAGService()
    rag.create_index(doc.id)

    dlg = RAGTestDialog(doc)
    qtbot.addWidget(dlg)

    dlg.search_input.setText("ATP")
    dlg._on_search()

    assert dlg.results_list.count() >= 1
    res_text = dlg.results_list.item(0).text()
    assert "Bioénergétique" in res_text or "ATP" in res_text


def test_rag_test_dialog_modes(qtbot, tmp_path, monkeypatch):
    """Vérifie le dialogue de recherche interactive avec bascule des modes RAG Hybride, Dense et Sparse."""
    from ankiforge.services.ai.rag_service import RAGService

    monkeypatch.setattr("ankiforge.services.rag.vector_manager.get_app_data_dir", lambda: tmp_path)
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc RAG Multimodal {uid}",
        content="# Section A\nL'insuline régule la glycémie sanguine.\n\n# Section B\nLe glucagon stimule la glycogénolyse hépatique.",
        file_type="md",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Endocrinologie > Insuline",
        page_number=1,
        content="L'insuline régule la glycémie sanguine.",
        content_hash=f"hash_ins_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path="Endocrinologie > Glucagon",
        page_number=2,
        content="Le glucagon stimule la glycogénolyse hépatique.",
        content_hash=f"hash_gluc_{uid}",
    )

    rag = RAGService()
    rag.create_index(doc.id)

    dlg = RAGTestDialog(doc)
    qtbot.addWidget(dlg)

    # 1. Mode Hybride (défaut)
    dlg.search_input.setText("insuline glycémie")
    dlg._on_search()
    assert dlg.results_list.count() >= 1
    assert "insuline" in dlg.results_list.item(0).text().lower()

    # 2. Mode Sparse BM25
    dlg.mode_cb.setCurrentIndex(2)  # sparse
    dlg.search_input.setText("glucagon")
    dlg._on_search()
    assert dlg.results_list.count() >= 1
    assert "glucagon" in dlg.results_list.item(0).text().lower()

    # 3. Mode Dense FAISS
    dlg.mode_cb.setCurrentIndex(1)  # dense
    dlg.search_input.setText("glycémie régulation")
    dlg._on_search()
    assert dlg.results_list.count() >= 1


def test_documents_view_smart_align_button(qtbot):
    """Vérifie le déclenchement de la synchronisation par tags depuis le bouton de DocumentsView."""
    import json

    from ankiforge.utils.tags import build_document_tags

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Réseaux Test {uid}",
        content="Les adresses IP et protocoles TCP assurent le routage.",
        file_type="md",
    )
    chunk1 = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Réseau > Protocole TCP",
        content="Le protocole TCP garantit la fiabilité des échanges de paquets.",
        content_hash=f"hash_tcp_{uid}",
    )

    deck = DeckModel.create(name=f"Deck IP {uid}")
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Model IP {uid}")
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt)
    note.add_version({"Front": "Rôle du protocole TCP ?", "Back": "Fiabilité des paquets réseau."}, source="manual")
    note.tags = json.dumps(build_document_tags(doc_id=doc.id, section_name=chunk1.heading_path))
    note.save()
    from ankiforge.database.models import CardModel

    CardModel.create(note=note, deck=deck, template_index=0)

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)
    view._current_doc_id = doc.id
    view._refresh_chapters_list()

    # Initialement non couvert (0 carte liée)
    assert view.chapters_list.count() == 1
    assert "Non couvert" in view.chapters_list.item(0).text()
    assert "0%" in view.lbl_coverage_summary.text()

    # Clic sur le bouton de synchronisation par tags
    view.btn_align_cards.click()

    # Après synchronisation : couvert à 100%
    assert "Couvert" in view.chapters_list.item(0).text()
    assert "100%" in view.lbl_coverage_summary.text()
    assert NoteChunkLinkModel.select().where(NoteChunkLinkModel.chunk == chunk1).count() == 1


def test_documents_view_marker_installation_switches_to_console(qtbot, monkeypatch):
    """Vérifie que le lancement de l'installation de Marker bascule automatiquement sur la console de logs."""
    from PySide6.QtCore import QObject, Signal

    class DummyWorker:
        def __init__(self) -> None:
            class Emitter(QObject):
                sig = Signal(str)

            self._em1 = Emitter()
            self._em2 = Emitter()
            self._em3 = Emitter()
            self.progress = self._em1.sig
            self.installed = self._em2.sig
            self.failed = self._em3.sig

        def start(self) -> None:
            pass

    monkeypatch.setattr("ankiforge.ui.views.documents_view.view.MarkerInstallerWorker", DummyWorker)

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)

    # Initialement sur le visualiseur PDF
    view._on_view_toggled("pdf")
    assert view.btn_view_term.isChecked() is False

    view._install_marker_and_start("/dummy/test.pdf")

    # La vue console doit être activée et les boutons mis à jour
    assert view.btn_view_term.isChecked() is True
    assert view.inner_editor_stack.currentIndex() == 2
    assert "Installation de Marker OCR" in view.terminal_view.toPlainText()
    assert view.btn_marker.isEnabled() is False

    # Simuler des logs reçus en temps réel
    view._on_worker_log("Downloading torch-2.1.0-cp312-none-any.whl (750 MB)")
    assert "Downloading torch" in view.terminal_view.toPlainText()


def test_documents_view_coverage_aggregates_duplicate_headings(qtbot):
    """Le Sommaire agrège les fragments d'une même section et reste cohérent avec le %."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Dupliqué {uid}",
        content="# Anatomie > Le Cœur\n\nTexte.",
        file_type="md",
    )
    chunk1 = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Anatomie > Le Cœur",
        content="Le cœur pompe le sang.",
        content_hash=f"hash_c1_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path="Anatomie > Le Cœur",
        content="Le cœur pompe le sang (suite).",
        content_hash=f"hash_c2_{uid}",
    )

    deck = DeckModel.create(name=f"Deck Dup {uid}")
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Model Dup {uid}")
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt)
    note.add_version({"Front": "Rôle du cœur ?", "Back": "Pompe sanguine"}, source="manual")
    from ankiforge.database.models import CardModel

    CardModel.create(note=note, deck=deck, template_index=0)
    NoteChunkLinkModel.create(note=note, chunk=chunk1)

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)
    view._current_doc_id = doc.id
    view._refresh_chapters_list()

    assert view.chapters_list.count() == 1
    row = view.chapters_list.item(0)
    assert "🟢" in row.text()
    assert "Couvert" in row.text()
    assert "2 fragments" in row.text()
    assert "100%" in view.lbl_coverage_summary.text()
    # L'unité de couverture est la section, pas le fragment
    assert view.chapters_list.item(0).data(Qt.ItemDataRole.UserRole + 1) is True


def test_documents_view_coverage_filter(qtbot):
    """Le filtre couvert/non-couvert masque les lignes selon leur état."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Filtre {uid}",
        content="# A\n\nAA.\n\n# B\n\nBB.",
        file_type="md",
    )
    chunk_a = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="A",
        content="AA.",
        content_hash=f"hash_a_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path="B",
        content="BB.",
        content_hash=f"hash_b_{uid}",
    )
    deck = DeckModel.create(name=f"Deck Filtre {uid}")
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Model Filtre {uid}")
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt)
    note.add_version({"Front": "A ?", "Back": "AA"}, source="manual")
    from ankiforge.database.models import CardModel

    CardModel.create(note=note, deck=deck, template_index=0)
    NoteChunkLinkModel.create(note=note, chunk=chunk_a)

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)
    view._current_doc_id = doc.id
    view._refresh_chapters_list()
    assert view.chapters_list.count() == 2

    # Couvertes uniquement
    view.chapters_filter.setCurrentIndex(1)
    assert not view.chapters_list.item(0).isHidden()
    assert view.chapters_list.item(1).isHidden()

    # Non couvertes uniquement
    view.chapters_filter.setCurrentIndex(2)
    assert view.chapters_list.item(0).isHidden()
    assert not view.chapters_list.item(1).isHidden()

    # Toutes
    view.chapters_filter.setCurrentIndex(0)
    assert not view.chapters_list.item(0).isHidden()
    assert not view.chapters_list.item(1).isHidden()


def test_documents_view_refresh_does_not_write_db(qtbot, monkeypatch):
    """Un simple rafraîchissement de couverture n'écrit jamais en base quand des chunks existent."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Doc NoWrite {uid}", content="# X\n\nXX.", file_type="md")
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="X",
        content="XX.",
        content_hash=f"hash_x_{uid}",
    )

    def raise_if_created(*args, **kwargs):
        raise AssertionError("Un rafraîchissement ne doit pas écrire de chunks")

    monkeypatch.setattr(DocumentChunkModel, "create", raise_if_created)

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)
    view._current_doc_id = doc.id
    view._refresh_chapters_list()
    view._refresh_chapters_list(allow_synthesis=False)
    assert view.chapters_list.count() == 1


def test_documents_view_coverage_paginated_groups_by_page(qtbot):
    """Pour un document paginé, une ligne = une page et le % suit la couverture par page."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Pages {uid}",
        content="{1}---\nP1\n{2}---\nP2",
        file_type="pdf",
    )
    chunk_p1 = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        page_number=1,
        heading_path="Page 1",
        content="P1",
        content_hash=f"hash_p1_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        page_number=2,
        heading_path="Page 2",
        content="P2",
        content_hash=f"hash_p2_{uid}",
    )

    deck = DeckModel.create(name=f"Deck Pages {uid}")
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Model Pages {uid}")
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt)
    note.add_version({"Front": "P1 ?", "Back": "P1"}, source="manual")
    from ankiforge.database.models import CardModel

    CardModel.create(note=note, deck=deck, template_index=0)
    NoteChunkLinkModel.create(note=note, chunk=chunk_p1)

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)
    view._current_doc_id = doc.id
    view._refresh_chapters_list()

    assert view.chapters_list.count() == 2
    assert "Page 1" in view.chapters_list.item(0).text()
    assert "Couvert" in view.chapters_list.item(0).text()
    assert "Page 2" in view.chapters_list.item(1).text()
    assert "Non couvert" in view.chapters_list.item(1).text()
    assert "pages" in view.lbl_coverage_details.text()
    assert "50%" in view.lbl_coverage_summary.text()


def test_documents_view_selection_preserved_across_reactive_refresh(qtbot):
    """Le rafraîchissement réactif préserve la sélection de l'utilisateur dans le Sommaire."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Sélection {uid}",
        content="# A\n\nAA.\n\n# B\n\nBB.",
        file_type="md",
    )
    DocumentChunkModel.create(document=doc, chunk_index=0, heading_path="A", content="AA.", content_hash=f"h1_{uid}")
    DocumentChunkModel.create(document=doc, chunk_index=1, heading_path="B", content="BB.", content_hash=f"h2_{uid}")

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)
    view._current_doc_id = doc.id
    view.coverage_panel.show()
    view._refresh_chapters_list()
    view.chapters_list.setCurrentRow(1)
    assert view.chapters_list.currentRow() == 1

    view._coverage_fingerprint = None
    view._on_coverage_refresh_trigger()
    assert view.chapters_list.currentRow() == 1

    # Un évènement sans changement d'empreinte ne doit pas rafraîchir (debounce/fermeture)
    view.chapters_list.setCurrentRow(0)
    view._on_coverage_refresh_trigger()
    assert view.chapters_list.currentRow() == 0


def test_documents_view_pdf_marker_coverage_uses_sections(qtbot):
    """Pour un PDF indexé par Marker, le Sommaire affiche le détail fin des sections, pas les pages."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"PDF Marker UI {uid}",
        content="{1}---\n# Anatomie > Le Cœur\nLe cœur.\n{2}---\n# Anatomie > Les Poumons\nRespirer.",
        file_type="pdf",
        total_pages=2,
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        page_number=1,
        heading_path="Anatomie > Le Cœur",
        content="Le cœur.",
        content_hash=f"u1_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        page_number=2,
        heading_path="Anatomie > Les Poumons",
        content="Respirer.",
        content_hash=f"u2_{uid}",
    )
    chunk_covered = DocumentChunkModel.get(chunk_index=0, document=doc)
    nt = NoteModel.create(
        guid=uuid.uuid4().hex,
        note_type=NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Marker UI {uid}"),
        raw_content="Q",
    )
    NoteChunkLinkModel.create(note=nt, chunk=chunk_covered)

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)
    view._current_doc_id = doc.id
    view._refresh_chapters_list()

    assert view.chapters_list.count() == 2
    assert "Anatomie > Le Cœur" in view.chapters_list.item(0).text()
    assert "Anatomie > Les Poumons" in view.chapters_list.item(1).text()
    assert "sections" in view.lbl_coverage_details.text()
    assert "50%" in view.lbl_coverage_summary.text()


def test_documents_view_worker_finished_updates_existing_pdf_doc(qtbot):
    """Vérifie que la fin de l'extraction met à jour le document existant sans lever d'AttributeError sur self.doc_repo."""
    from ankiforge.services.workers.document_worker import DocumentWorker

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Bio {uid}.pdf",
        content="",
        file_type="pdf",
    )

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)

    # Simuler le worker attaché pour l'extraction de ce document
    view.worker = DocumentWorker(f"/fake/path/Cours Bio {uid}.pdf", doc_id_to_update=doc.id)

    extracted_content = "# Introduction à la Biologie\n\nLa cellule est l'unité fondamentale de tout être vivant."
    view._on_worker_finished(doc.title, extracted_content)

    # Le document doit être persisté avec son contenu et ses chunks générés
    updated_doc = DocumentModel.get_by_id(doc.id)
    assert updated_doc.content == extracted_content
    assert DocumentChunkModel.select().where(DocumentChunkModel.document == doc).count() > 0

    # L'éditeur et l'UI doivent refléter les nouvelles données
    assert view.text_editor.get_content() == extracted_content
    assert view._current_doc_id == doc.id
    assert view.btn_import.isEnabled()


def test_documents_view_worker_finished_new_doc_without_prior_id(qtbot):
    """Vérifie que la fin d'un worker pour un nouveau fichier (sans doc_id préalable) crée le document."""
    from ankiforge.services.workers.document_worker import DocumentWorker

    uid = uuid.uuid4().hex[:6]
    doc_title = f"Nouveau Document {uid}"
    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)

    view.worker = DocumentWorker(f"/tmp/{doc_title}.txt")
    sample_content = "# Titre\n\nContenu importé sans ID préalable."

    view._on_worker_finished(doc_title, sample_content)

    created_doc = DocumentModel.get_or_none(DocumentModel.title == doc_title)
    assert created_doc is not None
    assert created_doc.content == sample_content
    assert view._current_doc_id == created_doc.id


def test_documents_view_worker_finished_handles_missing_doc_id_gracefully(qtbot):
    """Vérifie la robustesse si doc_id_to_update cible un identifiant inexistant."""
    from ankiforge.services.workers.document_worker import DocumentWorker

    uid = uuid.uuid4().hex[:6]
    doc_title = f"Fichier Orphelin {uid}"
    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)

    view.worker = DocumentWorker(f"/tmp/{doc_title}.md", doc_id_to_update=999999)
    sample_content = "# Contenu de secours"

    # Ne doit pas crasher avec un AttributeError
    view._on_worker_finished(doc_title, sample_content)

    saved_doc = DocumentModel.get_or_none(DocumentModel.title == doc_title)
    assert saved_doc is not None
    assert saved_doc.content == sample_content


def test_documents_view_heal_hierarchies_ensures_all_user_roles(qtbot):
    """Vérifie que refresh_data auto-guérit les parents virtuels et assigne UserRole à chaque nœud."""
    from ankiforge.database.models import FolderModel

    uid = uuid.uuid4().hex[:6]
    FolderModel.create(name=f"Racine_{uid}::SousNiveau::Feuille")

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # Parcourir tous les items de l'arborescence et vérifier qu'aucun dossier n'a data == None
    def assert_items(parent):
        count = parent.topLevelItemCount() if hasattr(parent, "topLevelItemCount") else parent.childCount()
        for i in range(count):
            item = parent.topLevelItem(i) if hasattr(parent, "topLevelItem") else parent.child(i)
            data = item.data(0, Qt.ItemDataRole.UserRole)
            assert data is not None, f"Item {item.text(0)} a un UserRole None !"
            assert data.get("type") in ("folder", "doc")
            assert data.get("id") is not None
            assert_items(item)

    assert_items(view.tree_explorer)


def test_documents_view_context_menu_actions(qtbot, monkeypatch):
    """Vérifie que le menu contextuel clic-droit propose les actions attendues selon l'élément ciblé."""
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QMenu

    from ankiforge.database.models import FolderModel
    from ankiforge.ui.theme import StyledMenu

    uid = uuid.uuid4().hex[:6]
    folder = FolderModel.create(name=f"Dossier_{uid}")
    doc = DocumentModel.create(title=f"Doc_{uid}", folder=folder, content="Texte", file_type="md")

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    executed_menus = []

    def mock_exec(self, pos=None):
        actions = [a.text() for a in self.actions() if not a.isSeparator()]
        executed_menus.append(actions)
        return None

    monkeypatch.setattr(StyledMenu, "exec", mock_exec)
    monkeypatch.setattr(QMenu, "exec", mock_exec)

    # 1. Clic droit dans le vide (aucun item à cet endroit)
    view._on_tree_context_menu(QPoint(500, 500))
    assert len(executed_menus) == 1
    assert any("Nouveau dossier racine" in a for a in executed_menus[0])

    # 2. Clic droit sur le dossier
    view._select_folder_id_in_tree(folder.id)
    folder_item = view.tree_explorer.currentItem()
    rect = view.tree_explorer.visualItemRect(folder_item)
    view._on_tree_context_menu(rect.center())
    assert len(executed_menus) == 2
    assert any("Nouveau sous-dossier" in a for a in executed_menus[1])
    assert any("Renommer" in a for a in executed_menus[1])
    assert any("Supprimer le dossier" in a for a in executed_menus[1])

    # 3. Clic droit sur le document
    view._select_doc_id_in_tree(doc.id)
    doc_item = view.tree_explorer.currentItem()
    rect_doc = view.tree_explorer.visualItemRect(doc_item)
    view._on_tree_context_menu(rect_doc.center())
    assert len(executed_menus) == 3
    assert any("Ouvrir" in a for a in executed_menus[2])
    assert any("Supprimer" in a for a in executed_menus[2])


def test_documents_view_rename_folder_cascades(qtbot, monkeypatch):
    """Vérifie le renommage de dossier via _on_rename_folder avec cascade sur les sous-dossiers."""
    from PySide6.QtWidgets import QInputDialog

    from ankiforge.database.models import FolderModel

    uid = uuid.uuid4().hex[:6]
    parent_folder = FolderModel.create(name=f"Parent_{uid}")
    child_folder = FolderModel.create(name=f"Parent_{uid}::Enfant")
    doc = DocumentModel.create(title=f"Doc_{uid}", folder=child_folder, content="Texte", file_type="md")

    view = DocumentsView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    # Simuler la saisie du nouveau nom "NouveauParent"
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: (f"NouveauParent_{uid}", True))

    view._on_rename_folder(parent_folder.id)

    # Vérifier que le parent a été renommé
    updated_parent = FolderModel.get_by_id(parent_folder.id)
    assert updated_parent.name == f"NouveauParent_{uid}"

    # Vérifier que l'enfant a été mis à jour en cascade
    updated_child = FolderModel.get_by_id(child_folder.id)
    assert updated_child.name == f"NouveauParent_{uid}::Enfant"

    # Vérifier que le document est toujours attaché au même enfant
    doc_reloaded = DocumentModel.get_by_id(doc.id)
    assert doc_reloaded.folder_id == child_folder.id
