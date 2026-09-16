import json
import uuid

from PySide6.QtCore import Qt

from ankiforge.database.models import DocumentChunkModel, DocumentModel, NoteChunkLinkModel, NoteModel
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog


def test_coverage_stats_with_delimited_pages():
    """Vérifie que la délimitation de pages restreint le calcul de couverture sans pénaliser les pages exclues."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Doc Délimité {uid}",
        file_type="pdf",
        total_pages=50,
        start_page=10,
        end_page=20,
    )

    # Création de fragments pour les pages utiles (10 à 20)
    for p in range(10, 21):
        DocumentChunkModel.create(
            document=doc,
            chunk_index=p - 10,
            page_number=p,
            content=f"Contenu page {p}",
        )

    doc_repo = DocumentRepository()
    stats = doc_repo.get_coverage_stats(doc.id)

    # 1. Périmètre utile : 11 pages (10 à 20 inclus), 0 carte -> 0%
    assert stats["total_units"] == 11
    assert stats["covered_units"] == 0
    assert stats["coverage_pct"] == 0.0
    assert stats["excluded_units"] == 39  # 50 - 11 = 39 pages hors portée
    assert len(stats["orphan_units"]) == 11
    assert all(10 <= p <= 20 for p in stats["orphan_units"])
    assert 1 not in stats["orphan_units"]
    assert 50 not in stats["orphan_units"]

    # 2. Création de cartes pour TOUTES les 11 pages utiles (10 à 20)
    from ankiforge.database.models import NoteTypeModel

    nt = NoteTypeModel.select().first() or NoteTypeModel.create(
        name=f"Model {uid}",
        fields_schema='["Front", "Back"]',
        templates="[]",
    )

    chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc))
    for c in chunks:
        note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt, raw_content=f"Question sur page {c.page_number}")
        NoteChunkLinkModel.create(note=note, chunk=c)

    stats_full = doc_repo.get_coverage_stats(doc.id)
    # Couverture complète à 100% sur le domaine utile !
    assert stats_full["total_units"] == 11
    assert stats_full["covered_units"] == 11
    assert stats_full["coverage_pct"] == 100.0
    assert stats_full["orphan_units"] == []
    assert stats_full["excluded_units"] == 39


def test_delimitation_dialog_persists_settings_and_filters_chunks(qtbot):
    """Vérifie que DocumentDelimitationDialog enregistre durablement les bornes et filtre les fragments."""
    uid = uuid.uuid4().hex[:6]
    content = (
        "<!-- PAGE: 1 -->\n# Sommaire\nTable des matières du cours.\n"
        "<!-- PAGE: 2 -->\n# Introduction\nIntroduction générale au sujet.\n"
        "<!-- PAGE: 3 -->\n# Physiologie Rénale\nLe néphron est l'unité fonctionnelle du rein.\n"
        "<!-- PAGE: 4 -->\n# Bibliographie\nRéférences et ouvrages recommandés.\n"
    )
    doc = DocumentModel.create(
        title=f"Cours Cardio {uid}",
        file_type="pdf",
        content=content,
        total_pages=4,
    )

    dlg = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg)

    # Bornes détectées
    assert dlg._max_page >= 4
    # Toutes les sections sont incluses par défaut (le filtre anti-bruit défaillant a été supprimé)
    assert dlg.sections_list.count() == 4
    assert dlg.sections_list.item(0).checkState() == Qt.CheckState.Checked  # Sommaire
    assert dlg.sections_list.item(1).checkState() == Qt.CheckState.Checked  # Intro
    assert dlg.sections_list.item(2).checkState() == Qt.CheckState.Checked  # Physio
    assert dlg.sections_list.item(3).checkState() == Qt.CheckState.Checked  # Biblio

    # On restreint de page 2 à page 3 via le slider -> les pages gouvernent la sélection.
    dlg.spin_p_start.setValue(2)
    dlg.spin_p_end.setValue(3)
    assert dlg.sections_list.item(0).checkState() == Qt.CheckState.Unchecked  # Page 1 exclue
    assert dlg.sections_list.item(1).checkState() == Qt.CheckState.Checked  # Page 2 incluse
    assert dlg.sections_list.item(2).checkState() == Qt.CheckState.Checked  # Page 3 incluse
    assert dlg.sections_list.item(3).checkState() == Qt.CheckState.Unchecked  # Page 4 exclue

    dlg.chk_revectorize.setChecked(False)
    dlg._on_apply()

    # Vérification de la persistance sur DocumentModel
    reloaded_doc = DocumentModel.get_by_id(doc.id)
    assert reloaded_doc.start_page == 2
    assert reloaded_doc.end_page == 3
    assert reloaded_doc.excluded_headings == "[]"

    # Vérification des chunks actifs restants en BDD
    active_chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc))
    assert len(active_chunks) == 2
    pages_active = [c.page_number for c in active_chunks]
    assert 2 in pages_active
    assert 3 in pages_active
    assert 1 not in pages_active
    assert 4 not in pages_active


def test_delimitation_dialog_markdown_document_without_pages(qtbot):
    """Vérifie que pour un document Markdown non paginé, la carte de pagination est masquée et la désélection individuelle fonctionne."""
    uid = uuid.uuid4().hex[:6]
    content = "# Chapitre 1\nContenu du chapitre 1.\n\n# Chapitre 2\nContenu du chapitre 2.\n\n# Annexes\nContenu des annexes.\n"
    doc = DocumentModel.create(
        title=f"Doc Markdown {uid}",
        file_type="md",
        content=content,
        total_pages=1,
    )

    dlg = DocumentDelimitationDialog(doc)
    qtbot.addWidget(dlg)

    # 1. Vérification que la notion de page est désactivée
    assert not dlg.is_paginated
    assert dlg.pages_card is not None
    assert dlg.pages_card.isHidden()

    # 2. Désélection individuelle via SectionRowWidget
    assert dlg.sections_list.count() == 3
    assert dlg.sections_list.item(0).checkState() == Qt.CheckState.Checked

    row_w = dlg.sections_list.itemWidget(dlg.sections_list.item(0))
    assert row_w is not None
    # On décoche individuellement la section
    row_w.set_checked(False)
    assert dlg.sections_list.item(0).checkState() == Qt.CheckState.Unchecked

    # 3. Application de la délimitation
    dlg.chk_revectorize.setChecked(False)
    dlg._on_apply()

    reloaded_doc = DocumentModel.get_by_id(doc.id)
    assert reloaded_doc.start_page is None
    assert reloaded_doc.end_page is None
    assert reloaded_doc.excluded_headings is not None
    excl = json.loads(reloaded_doc.excluded_headings)
    assert any("Chapitre 1" in s for s in excl)


def test_coverage_stats_pdf_marker_uses_fine_sections():
    """Un PDF indexé par Marker (sections fines) est couvert par section, pas par page."""
    from ankiforge.database.models import NoteTypeModel

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"PDF Marker {uid}",
        content="{1}---\n# Anatomie > Le Cœur\nLe cœur pompe le sang.\n{2}---\n# Anatomie > Les Poumons\nRespirer.",
        file_type="pdf",
        total_pages=2,
    )
    chunk_c = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        page_number=1,
        heading_path="Anatomie > Le Cœur",
        content="Le cœur pompe le sang.",
        content_hash=f"h_c_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        page_number=2,
        heading_path="Anatomie > Les Poumons",
        content="Respirer.",
        content_hash=f"h_p_{uid}",
    )

    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Model Marker {uid}")
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt, raw_content="Q")
    NoteChunkLinkModel.create(note=note, chunk=chunk_c)

    stats = DocumentRepository().get_coverage_stats(doc.id)
    assert stats["unit_type"] == "sections"
    assert stats["total_units"] == 2
    assert stats["covered_units"] == 1
    assert stats["coverage_pct"] == 50.0
    assert stats["orphan_units"] == ["Anatomie > Les Poumons"]


def test_coverage_stats_native_pdf_with_page_labels_stays_paginated():
    """Un PDF natif (fragments 'Page N' uniquement) conserve une couverture par pages."""
    from ankiforge.database.models import NoteTypeModel

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"PDF Natif {uid}", file_type="pdf", total_pages=3)
    chunk_p1 = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        page_number=1,
        heading_path="Page 1",
        content="P1",
        content_hash=f"hp1_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        page_number=2,
        heading_path="Page 2",
        content="P2",
        content_hash=f"hp2_{uid}",
    )

    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Model Natif {uid}")
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt, raw_content="Q")
    NoteChunkLinkModel.create(note=note, chunk=chunk_p1)

    stats = DocumentRepository().get_coverage_stats(doc.id)
    assert stats["unit_type"] == "pages"
    assert stats["total_units"] == 3
    assert stats["covered_units"] == 1
    assert stats["coverage_pct"] == round(1 / 3 * 100, 1)


def test_coverage_stats_fine_sections_respect_excluded_headings():
    """Les sections exclues (délimitation) sont retirées du dénominateur de couverture."""
    from ankiforge.database.models import NoteTypeModel

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"PDF Marker Exclu {uid}",
        content="# Intro\n..\n# Partie 1\n..\n# Partie 2\n..",
        file_type="pdf",
        total_pages=3,
        excluded_headings=json.dumps(["Partie 2"], ensure_ascii=False),
    )
    chunk1 = DocumentChunkModel.create(document=doc, chunk_index=0, page_number=1, heading_path="Intro", content="Intro", content_hash=f"e1_{uid}")
    DocumentChunkModel.create(document=doc, chunk_index=1, page_number=2, heading_path="Partie 1", content="P1", content_hash=f"e2_{uid}")
    DocumentChunkModel.create(document=doc, chunk_index=2, page_number=3, heading_path="Partie 2", content="P2", content_hash=f"e3_{uid}")

    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Model Exclu {uid}")
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt, raw_content="Q")
    NoteChunkLinkModel.create(note=note, chunk=chunk1)

    stats = DocumentRepository().get_coverage_stats(doc.id)
    assert stats["unit_type"] == "sections"
    assert stats["total_units"] == 2
    assert stats["covered_units"] == 1
    assert stats["coverage_pct"] == 50.0
    assert stats["excluded_units"] == 1
    assert stats["orphan_units"] == ["Partie 1"]
