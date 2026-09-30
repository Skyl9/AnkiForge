import json
import uuid
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QTreeWidgetItem, QTreeWidgetItemIterator

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
)
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.ui.components.duplicate_widgets import (
    DuplicateMatrixTable,
    DuplicateMergeInspector,
)
from ankiforge.ui.components.linter_widgets import WozniakCardItemWidget
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.analysis_view import (
    AIDuplicatesMergeTab,
    AISourcesDiagnosticTab,
    AITokensSrsTab,
    AIWozniakLinterTab,
    AnalysisView,
    DocumentInspectorPanel,
)
from ankiforge.ui.views.analysis_view.tabs.sources_tab import _ROLE_HEADING
from ankiforge.utils.region_address import RegionScope
from ankiforge.utils.tags import build_document_tags

pytestmark = pytest.mark.ui


def _all_tree_items(panel: DocumentInspectorPanel) -> list[QTreeWidgetItem]:
    """Tous les items du sommaire, en profondeur (ordre de rendu)."""

    items: list[QTreeWidgetItem] = []
    it = QTreeWidgetItemIterator(panel.chapters_tree)
    while it.value():
        item = it.value()
        if item is not None:
            items.append(item)
        it += 1
    return items


def _item_by_heading(panel: DocumentInspectorPanel, heading: str) -> QTreeWidgetItem:
    """Ligne du sommaire portant ce fil d'Ariane, nœud virtuel compris.

    Adresser les lignes par leur rang dans un arbre n'a pas de sens : insérer un
    niveau intermédiaire décale tous les indices, et un test qui passe alors par
    accident vérifie plus grand-chose. On adresse donc par l'identité stable du nœud.
    """
    for item in _all_tree_items(panel):
        if str(item.data(0, _ROLE_HEADING) or "") == heading:
            return item
    raise AssertionError(f"aucune ligne de sommaire pour le fil « {heading} »")


def _leaf_items(panel: DocumentInspectorPanel) -> list[QTreeWidgetItem]:
    """Lignes sans sous-section (les fragments réellement rattachables à une carte)."""
    return [item for item in _all_tree_items(panel) if item.childCount() == 0]


# Titres réalistes de cours / fichiers importés : c'est la longueur du nom de fichier qui
# fait déborder la grille, pas un cas limite de laboratoire.
LONG_DOC_TITLES = [
    "Chapitre 3 - Les obligations du vendeur en droit romain des contrats.pdf",
    "Le Manuel Complet de Droit Constitutionnel - Tome II - Institutions et Libertes.pdf",
    "Introduction to Machine Learning and Statistical Inference - Third Edition.pdf",
    "Notes de cours - Economie behaviourale et rationalite limitee.docx",
]


def _create_long_titled_documents() -> list[DocumentModel]:
    """Crée des cours aux noms de fichiers réalistes (ceux d'un import de matière)."""
    docs = []
    for index, title in enumerate(LONG_DOC_TITLES):
        doc = DocumentModel.create(title=title, content="x" * 200, file_type="pdf" if index < 3 else "docx")
        for section in range(4 + index):
            DocumentChunkModel.create(document=doc, chunk_index=section, heading_path=f"S{section}", content="c", content_hash=f"h{index}_{section}")
        docs.append(doc)
    return docs


def test_sources_grid_never_overflows_horizontally(qtbot):
    """La grille des documents ne doit jamais exiger un défilement horizontal.

    Seam public : `AISourcesDiagnosticTab.scroll_area` / `grid_content` / `grid_layout`,
    tels qu'affichés à l'ouverture de l'onglet. Avec des noms de fichiers réalistes
    (et donc longs), les cartes ne doivent pas dépasser la largeur du viewport.
    """
    _create_long_titled_documents()

    tab = AISourcesDiagnosticTab()
    qtbot.addWidget(tab)
    tab.resize(1200, 700)
    tab.show()
    qtbot.waitExposed(tab)
    tab.refresh_data()
    qtbot.wait(60)

    scroll = tab.scroll_area
    grid = tab.grid_content
    assert tab.grid_layout.count() == len(LONG_DOC_TITLES)

    assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    for width in (1200, 1000, 800):
        tab.resize(width, 700)
        qtbot.wait(60)
        viewport_w = scroll.viewport().width()
        assert scroll.horizontalScrollBar().maximum() == 0, f"débordement horizontal à {width}px"
        assert not scroll.horizontalScrollBar().isVisible()
        assert grid.minimumSizeHint().width() <= viewport_w, f"grille plus large que le viewport à {width}px"
        assert grid.width() <= viewport_w


def test_sources_grid_title_wraps_instead_of_forcing_width(qtbot):
    """Le titre d'une carte doit se replier, et non imposer sa largeur au document."""
    _create_long_titled_documents()

    tab = AISourcesDiagnosticTab()
    qtbot.addWidget(tab)
    tab.resize(1200, 700)
    tab.show()
    qtbot.waitExposed(tab)
    tab.refresh_data()
    qtbot.wait(60)

    titles = [lbl for lbl in tab.grid_content.findChildren(QLabel) if lbl.text() in LONG_DOC_TITLES]
    assert len(titles) == len(LONG_DOC_TITLES)
    for lbl in titles:
        assert lbl.wordWrap(), f"le titre {lbl.text()!r} ne se replie pas"
        # Un QLabel sans word wrap reporte la largeur totale du texte dans son
        # minimumSizeHint ; avec le repli, il ne retient plus que son mot le plus long.
        assert lbl.minimumSizeHint().width() < lbl.sizeHint().width()


def test_sources_grid_column_count_follows_available_width(qtbot):
    """Le nombre de colonnes suit la largeur utile, sans jamais descendre sous 1."""
    tab = AISourcesDiagnosticTab()
    qtbot.addWidget(tab)

    spacing = tab.grid_layout.spacing()
    min_needed = tab.MIN_CARD_WIDTH + spacing
    assert tab._columns_for_width(0) == 1
    assert tab._columns_for_width(min_needed - 1) == 1
    assert tab._columns_for_width(min_needed) == 1
    assert tab._columns_for_width(2 * min_needed) == 2
    assert tab._columns_for_width(10 * min_needed) == tab.MAX_DOCUMENT_COLUMNS
    # Jamais plus que le maximum, quelle que soit la largeur.
    assert tab._columns_for_width(10_000) == tab.MAX_DOCUMENT_COLUMNS


def test_sources_grid_repacks_single_column_on_narrow_viewport(qtbot):
    """Le réagencement des cartes suit la largeur du viewport.

    L'en-tête de l'onglet (KPI + barre de filtres) impose aujourd'hui une largeur
    minimale d'environ 780 px, donc la bande « une colonne » n'est pas atteignable en
    redimensionnant une fenêtre. On exerce donc ici le chemin réel de reaction au
    `QEvent.Resize` du viewport, qui est celui qui s'exécutera dès que l'en-tête
    pourra se comprimer.
    """
    _create_long_titled_documents()

    tab = AISourcesDiagnosticTab()
    qtbot.addWidget(tab)
    tab.resize(1600, 700)
    tab.show()
    qtbot.waitExposed(tab)
    tab.refresh_data()
    qtbot.wait(60)

    viewport = tab.scroll_area.viewport()
    assert tab.document_column_count > 1

    # L'en-tête de l'onglet (KPI + barre de filtres) impose aujourd'hui une largeur
    # minimale d'environ 780 px, donc la bande « une colonne » n'est pas atteignable en
    # redimensionnant une fenêtre. On contraint donc réellement la zone de défilement
    # pour exercer le chemin de reaction au `QEvent.Resize` du viewport, qui est celui
    # qui s'exécutera dès que l'en-tête pourra se comprimer.
    tab.scroll_area.setMinimumWidth(0)
    tab.scroll_area.setMaximumWidth(tab.MIN_CARD_WIDTH)
    qtbot.wait(60)

    assert viewport.width() <= tab.MIN_CARD_WIDTH
    assert tab.document_column_count == 1
    grid = tab.grid_content
    assert grid.layout().count() == len(LONG_DOC_TITLES)
    assert tab.scroll_area.horizontalScrollBar().maximum() == 0

    # Retour au large : les colonnes reviennent et le contenu est intact.
    tab.scroll_area.setMinimumWidth(0)
    tab.scroll_area.setMaximumWidth(16777215)
    tab.resize(1600, 700)
    qtbot.wait(60)
    assert tab.document_column_count > 1
    assert tab.grid_layout.count() == len(LONG_DOC_TITLES)
    assert tab.scroll_area.horizontalScrollBar().maximum() == 0


def test_document_inspector_panel_chapter_coverage(qtbot):
    """Vérifie l'affichage du sommaire et des cartes liées dans DocumentInspectorPanel."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Droit {uid}",
        content="# Article 1\nLe contrat est un accord de volontés.\n\n# Article 2\nChacun est libre de contracter.",
        file_type="md",
    )

    chunk1 = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Droit > Article 1",
        content="Le contrat est un accord de volontés.",
        content_hash=f"hash1_{uid}",
    )
    chunk2 = DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path="Droit > Article 2",
        content="Chacun est libre de contracter.",
        content_hash=f"hash2_{uid}",
    )

    deck = DeckModel.create(name=f"Deck Droit {uid}")
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(
        name=f"Model Droit {uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]',
        css_style="",
    )
    note1 = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt)
    note1.add_version({"Front": "Définition du contrat ?", "Back": "Accord de volontés."}, source="manual")
    CardModel.create(note=note1, deck=deck, template_index=0)
    NoteChunkLinkModel.create(note=note1, chunk=chunk1)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)

    panel.load_chunks()

    # Vérification du sommaire (3 items: 1 conteneur "Droit" + 2 feuilles)
    assert len(_all_tree_items(panel)) == 3
    leaves = _leaf_items(panel)
    assert len(leaves) == 2
    item1 = leaves[0]
    assert "1 carte" in item1.text(0)

    item2 = leaves[1]
    assert "0 carte" in item2.text(0) or "Trou" in item2.text(0)

    # Inspecter le chunk couvert (chunk 1)
    panel.inspect_chunk(chunk1.id)
    assert "1 carte(s) Anki forgée(s)" in panel.cards_layout.itemAt(0).widget().text()

    # Inspecter le chunk orphelin (chunk 2)
    panel.inspect_chunk(chunk2.id)
    assert panel.cards_layout.count() >= 1

    # Navigation vers création
    emitted = []
    panel.request_navigation.connect(lambda target, payload: emitted.append((target, payload)))
    panel._on_forge_chunk(chunk2.id)
    assert len(emitted) == 1
    assert emitted[0][0] == "creation"
    assert "contracter" in emitted[0][1]["text_source"].lower()


def test_ai_sources_diagnostic_tab_grid_and_kpis(qtbot):
    """Vérifie la grille de diagnostic des sources et les KPIs globaux de la Forge."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Test {uid}",
        content="# Section 1\nContenu A\n\n# Section 2\nContenu B",
        file_type="md",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Section 1",
        content="Contenu A",
        content_hash=f"h1_{uid}",
    )

    tab = AISourcesDiagnosticTab()
    qtbot.addWidget(tab)

    tab.refresh_data()
    assert tab.lbl_kpi_docs_val.text() != "--"
    assert tab.grid_layout.count() >= 1

    # Test switch to inspector
    tab.show_inspector(doc.id)
    assert tab.stack.currentIndex() == 1


def _make_inspectable_document(uid: str) -> tuple[DocumentModel, list[DocumentChunkModel]]:
    """Cours de trois sections dont une seule est couverte, plus un fragment paginé non excluable."""
    doc = DocumentModel.create(
        title=f"Cours Delimitation {uid}",
        content="# Preface\nRien d'utile.\n\n# Partie 1\nLe contrat.\n\n# Corriges\nLes reponses.",
        file_type="md",
    )
    chunks = [
        DocumentChunkModel.create(document=doc, chunk_index=0, heading_path="Preface", content="Rien d'utile.", content_hash=f"dp_{uid}_0"),
        DocumentChunkModel.create(document=doc, chunk_index=1, heading_path="Partie 1", content="Le contrat.", content_hash=f"dp_{uid}_1"),
        DocumentChunkModel.create(document=doc, chunk_index=2, heading_path="Corriges", content="Les reponses.", content_hash=f"dp_{uid}_2"),
        DocumentChunkModel.create(document=doc, chunk_index=3, heading_path="Page 4", content="Page sans titre.", page_number=4, content_hash=f"dp_{uid}_3"),
    ]
    return doc, chunks


def _make_titled_only_document(uid: str) -> DocumentModel:
    """Document dont tous les fragments portent un titre de section, périmètre vidable."""
    doc = DocumentModel.create(
        title=f"Cours Entierement Exclu {uid}",
        content="# Preface\nRien d'utile.\n\n# Partie 1\nLe contrat.",
        file_type="md",
    )
    for index, name in enumerate(["Preface", "Partie 1"]):
        DocumentChunkModel.create(document=doc, chunk_index=index, heading_path=name, content=f"Contenu {name}.", content_hash=f"dt_{uid}_{index}")
    return doc


def _cover_chunk_with_card(doc: DocumentModel, chunk: DocumentChunkModel, uid: str) -> None:
    deck = DeckModel.create(name=f"Deck Delimitation {uid}")
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Model Delimitation {uid}")
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt)
    note.add_version({"Front": "Question ?", "Back": "Reponse."}, source="manual")
    CardModel.create(note=note, deck=deck, template_index=0)
    NoteChunkLinkModel.create(note=note, chunk=chunk)


def _stored_exclusions(doc_id: int) -> list[str]:
    return DocumentRepository().get_excluded_headings(DocumentModel.get_by_id(doc_id))


def test_document_inspector_excludes_and_reincludes_a_section_in_place(qtbot):
    """« Exclure cette section » retire la section de l'analyse sans recharger l'inspecteur."""
    uid = uuid.uuid4().hex[:6]
    doc, chunks = _make_inspectable_document(uid)
    _cover_chunk_with_card(doc, chunks[1], uid)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)
    panel.chapters_tree.setCurrentItem(_all_tree_items(panel)[2])
    qtbot.wait(10)

    assert "25%" in panel.lbl_doc_summary.text()
    assert "1/4 sections" in panel.lbl_doc_summary.text()
    assert "Exclure cette section" in panel.btn_exclude_section.text()
    assert panel.btn_exclude_section.isEnabled()

    panel.btn_exclude_section.click()

    # La section exclue n'est plus une lacune et ne plombe plus le ratio.
    assert _stored_exclusions(doc.id) == ["heading:Corriges"]
    assert "33%" in panel.lbl_doc_summary.text()
    assert "1/3 sections" in panel.lbl_doc_summary.text()
    assert "1 section hors périmètre" in panel.lbl_scope_status.text()

    # Le row porte un style d'exclusion et l'action bascule en ré-inclusion.
    excluded_row = _all_tree_items(panel)[2]
    assert "Exclue" in excluded_row.text(0)
    assert excluded_row.foreground(0).color() == QColor(DesignTokens.TEXT_MUTED)
    assert "Ré-inclure la section" in panel.btn_exclude_section.text()

    # Aucune relecture brutale : la sélection et l'aperçu restent sur la section traitée.
    assert panel.chapters_tree.currentItem() == _all_tree_items(panel)[2]
    assert "Les reponses" in panel.text_preview.toPlainText()

    panel.btn_exclude_section.click()

    assert _stored_exclusions(doc.id) == []
    assert "25%" in panel.lbl_doc_summary.text()
    assert "1/4 sections" in panel.lbl_doc_summary.text()
    assert "Exclue" not in _all_tree_items(panel)[2].text(0)
    assert "Exclure cette section" in panel.btn_exclude_section.text()


def test_document_inspector_exclusion_action_follows_the_selected_section(qtbot):
    """L'action d'exclusion décrit la section sélectionnée, et se désactive sans titre exploitable."""
    uid = uuid.uuid4().hex[:6]
    doc, _chunks = _make_inspectable_document(uid)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)

    panel.chapters_tree.setCurrentItem(_all_tree_items(panel)[1])
    qtbot.wait(10)
    assert "Exclure cette section" in panel.btn_exclude_section.text()

    panel.btn_exclude_section.click()
    assert _stored_exclusions(doc.id) == ["heading:Partie 1"]

    # « Partie 1 » est désormais exclue : la même ligne propose de la réintégrer…
    assert "Ré-inclure la section" in panel.btn_exclude_section.text()
    # … et une autre ligne, toujours incluse, propose de l'exclure.
    panel.chapters_tree.setCurrentItem(_all_tree_items(panel)[0])
    qtbot.wait(10)
    assert "Exclure cette section" in panel.btn_exclude_section.text()

    # Un fragment au libellé de page n'est pas une section : l'action n'a pas lieu d'être.
    panel.chapters_tree.setCurrentItem(_all_tree_items(panel)[3])
    qtbot.wait(10)
    assert not panel.btn_exclude_section.isEnabled()
    assert "titre" in panel.btn_exclude_section.toolTip().lower()


def test_document_inspector_exclusion_is_propagated_to_the_rest_of_the_app(qtbot):
    """Changer le périmètre d'un document est notifié aux autres vues de l'application."""
    from ankiforge.utils.event_bus import CoverageSyncedEvent, event_bus

    uid = uuid.uuid4().hex[:6]
    doc, _chunks = _make_inspectable_document(uid)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)
    panel.chapters_tree.setCurrentItem(_all_tree_items(panel)[2])
    qtbot.wait(10)

    captured: list[CoverageSyncedEvent] = []

    def _handler(event: CoverageSyncedEvent) -> None:
        captured.append(event)

    event_bus.subscribe(CoverageSyncedEvent, _handler)
    try:
        panel.btn_exclude_section.click()
    finally:
        event_bus.unsubscribe(CoverageSyncedEvent, _handler)

    assert [event.doc_id for event in captured] == [doc.id]
    # Le panneau a déjà rafraîchi ses propres lignes : il ne doit pas se recharger.
    assert "Exclue" in _all_tree_items(panel)[2].text(0)
    assert panel.chapters_tree.currentItem() == _all_tree_items(panel)[2]


def test_document_inspector_context_menu_toggles_section_exclusion(qtbot):
    """Le clic droit sur une section propose de l'exclure, et l'exclut réellement."""
    uid = uuid.uuid4().hex[:6]
    doc, _chunks = _make_inspectable_document(uid)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)

    assert panel.chapters_tree.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu

    menu = panel.chapter_context_menu(_all_tree_items(panel)[1])
    assert menu is not None
    labels = [action.text() for action in menu.actions() if action.text()]
    assert "Exclure cette section" in labels

    toggle_action = next(action for action in menu.actions() if action.text() == "Exclure cette section")
    toggle_action.trigger()

    assert _stored_exclusions(doc.id) == ["heading:Partie 1"]
    assert "Exclue" in _all_tree_items(panel)[1].text(0)
    assert panel.chapters_tree.currentItem() == _all_tree_items(panel)[1]

    # Le menu propose ensuite la réintégration, y compris pour la section déjà traitée.
    reinclude_labels = [action.text() for action in panel.chapter_context_menu(_all_tree_items(panel)[1]).actions() if action.text()]
    assert "Ré-inclure la section" in reinclude_labels


def test_document_inspector_context_menu_disables_exclusion_of_a_page_row(qtbot):
    """Une ligne au libellé de page reste inspectable mais ne propose pas d'exclusion."""
    uid = uuid.uuid4().hex[:6]
    doc, _chunks = _make_inspectable_document(uid)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)

    menu = panel.chapter_context_menu(_all_tree_items(panel)[3])
    assert menu is not None
    toggle_action = next(action for action in menu.actions() if action.text() == "Exclure cette section")
    assert not toggle_action.isEnabled()


def test_document_inspector_reports_an_empty_scope_instead_of_a_zero_coverage(qtbot):
    """Exclure toutes les sections affiche un périmètre vide, pas un 0 % rouge."""
    uid = uuid.uuid4().hex[:6]
    doc = _make_titled_only_document(uid)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)

    for item in _all_tree_items(panel):
        panel.chapters_tree.setCurrentItem(item)
        qtbot.wait(5)
        panel.btn_exclude_section.click()

    assert panel.lbl_doc_summary.text() == "Périmètre vide (0 section active)"
    assert "0%" not in panel.lbl_doc_summary.text()


#: Un chapitre réduit à son titre : six mots sous deux sous-sections, donc un conteneur.
CONTAINER_CHAPTER_BODY = "Ce chapitre présente les organites."

#: Le même chapitre porteur d'un vrai contenu : une unité de cours, pas un conteneur.
TEACHING_CHAPTER_BODY = (
    "Ce chapitre passe en revue l'ensemble des organites de la cellule eucaryote et précise, pour chacun d'eux, "
    "le rôle qu'il joue dans la survie et le fonctionnement de l'organisme, ainsi que les échanges de matière "
    "et d'énergie qu'il autorise avec l'environnement extérieur de la cellule."
)


def _make_nested_document(uid: str, *, chapter_body: str = CONTAINER_CHAPTER_BODY) -> tuple[DocumentModel, dict[str, DocumentChunkModel]]:
    """Cours « chapitre + sous-sections » dont une seule carte est rattachée au chapitre.

    Le drapeau de conteneur du chapitre est dérivé du corps par la règle de production :
    c'est lui qui décide si l'affinement a le droit de faire descendre la carte du
    chapitre, donc le figer en dur ferait passer les deux types de chapitre pour un seul.
    """
    doc = DocumentModel.create(
        title=f"Cours Cellulaire {uid}",
        content="# Biologie Cellulaire\n\n## 2 Les Structures Cellulaires\n\n### 2.1 La Membrane\n\n### 2.2 Le Noyau",
        file_type="md",
    )
    chapter = "Biologie Cellulaire > 2 Les Structures Cellulaires"
    chunks = {
        "chapter": DocumentChunkModel.create(
            document=doc,
            chunk_index=0,
            heading_path=chapter,
            content=chapter_body,
            content_hash=f"nest0_{uid}",
            is_structural_container=ChunkingService.is_structural_container(chapter, chapter_body, has_descendants=True),
        ),
        "membrane": DocumentChunkModel.create(
            document=doc,
            chunk_index=1,
            heading_path=f"{chapter} > 2.1 La Membrane",
            content="La membrane plasmique délimite la cellule.",
            content_hash=f"nest1_{uid}",
        ),
        "noyau": DocumentChunkModel.create(
            document=doc,
            chunk_index=2,
            heading_path=f"{chapter} > 2.2 Le Noyau",
            content="Le noyau abrite l'information génétique.",
            content_hash=f"nest2_{uid}",
        ),
    }
    return doc, chunks


def _card_linked_to(uid: str, doc: DocumentModel, chunk: DocumentChunkModel, front: str, back: str) -> NoteModel:
    """Note taguée sur le fragment donné, une version active et un lien de traçabilité."""
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Model Affinage {uid}")
    deck = DeckModel.get_or_none(DeckModel.name == f"Deck Affinage {uid}") or DeckModel.create(name=f"Deck Affinage {uid}")
    tags = build_document_tags(doc_id=doc.id, doc_title=doc.title, section_name=chunk.heading_path, page_number=chunk.page_number)
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt, tags=json.dumps(tags))
    note.add_version({"Front": front, "Back": back}, source="manual")
    CardModel.create(note=note, deck=deck, template_index=0)
    NoteChunkLinkModel.create(note=note, chunk=chunk)
    return note


def test_document_inspector_refines_links_towards_sub_sections(qtbot, monkeypatch):
    """« Affiner les liens » rattache les cartes de chapitre aux sous-sections et rafraîchit le sommaire."""
    toasts: list[str] = []
    monkeypatch.setattr("ankiforge.ui.views.analysis_view.tabs.sources_tab.show_toast", lambda _parent, msg, *a, **k: toasts.append(msg))

    uid = uuid.uuid4().hex[:6]
    doc, chunks = _make_nested_document(uid)
    card = _card_linked_to(uid, doc, chunks["chapter"], "Quelle est la fonction de la membrane plasmique ?", "Elle délimite la cellule et contrôle les échanges.")

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)
    chapter = "Biologie Cellulaire > 2 Les Structures Cellulaires"
    chapter_row = _item_by_heading(panel, chapter)
    panel.chapters_tree.setCurrentItem(chapter_row)
    qtbot.wait(10)

    assert "1 carte" in chapter_row.text(0)
    assert "0 carte" in _item_by_heading(panel, f"{chapter} > 2.1 La Membrane").text(0)

    panel.btn_refine_links.click()
    qtbot.wait(10)

    # La carte pointe désormais sur la sous-section, et son tag de provenance suit.
    assert NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == card, NoteChunkLinkModel.chunk == chunks["membrane"]).count() == 1
    assert NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == card, NoteChunkLinkModel.chunk == chunks["chapter"]).count() == 0
    assert "section:biologie_cellulaire_2_les_structures_cellulaires_2_1_la_membrane" in NoteModel.get_by_id(card.id).tags

    # Le sommaire et la pastille de couverture sont à jour, sans perdre la sélection.
    # La ligne du conteneur ne compte plus la carte comme la sienne : elle affiche le
    # total de sa branche, qui est désormais porté par la sous-section.
    assert "1 carte" in chapter_row.text(0)
    assert "1 carte" in _item_by_heading(panel, f"{chapter} > 2.1 La Membrane").text(0)
    assert "0 carte" in _item_by_heading(panel, f"{chapter} > 2.2 Le Noyau").text(0)
    assert "1/2 sections" in panel.lbl_doc_summary.text()
    assert panel.chapters_tree.currentItem() == chapter_row
    assert "organites" in panel.text_preview.toPlainText().lower()

    # La section sélectionnée est un conteneur : le panneau de droite le dit au lieu
    # d'annoncer un trou de cours, ce dernier n'étant pas une unité à couvrir.
    assert any("Conteneur structural" in lbl.text() for lbl in panel.findChildren(QLabel))
    assert not any("Trou de cours" in lbl.text() for lbl in panel.findChildren(QLabel))

    assert any("1 carte(s) réassignée(s)" in msg and "fausse(s) lacune(s) résolue(s)" in msg for msg in toasts)


def test_document_inspector_reports_a_refinement_without_effect(qtbot, monkeypatch):
    """Sans lien à affiner, l'action reste sans effet et le dit explicitement."""
    toasts: list[str] = []
    monkeypatch.setattr("ankiforge.ui.views.analysis_view.tabs.sources_tab.show_toast", lambda _parent, msg, *a, **k: toasts.append(msg))

    uid = uuid.uuid4().hex[:6]
    doc, _chunks = _make_nested_document(uid)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)

    panel.btn_refine_links.click()
    qtbot.wait(10)

    assert toasts == ["Aucune carte de chapitre à rattacher à une sous-section plus fine."]
    # Le chapitre est un conteneur : il ne compte pas dans le dénominateur, seules les
    # deux sous-sections restent à couvrir.
    assert "0/2 sections" in panel.lbl_doc_summary.text()


def test_document_inspector_keeps_sole_cards_on_a_teaching_chapter(qtbot, monkeypatch):
    """La dernière carte d'un chapitre de contenu n'est jamais déplacée vers une sous-section."""
    toasts: list[str] = []
    monkeypatch.setattr("ankiforge.ui.views.analysis_view.tabs.sources_tab.show_toast", lambda _parent, msg, *a, **k: toasts.append(msg))

    uid = uuid.uuid4().hex[:6]
    doc, chunks = _make_nested_document(uid, chapter_body=TEACHING_CHAPTER_BODY)
    assert not chunks["chapter"].is_structural_container
    card = _card_linked_to(uid, doc, chunks["chapter"], "Fonction de la membrane ?", "Elle contrôle les échanges.")

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)

    panel.btn_refine_links.click()
    qtbot.wait(10)

    assert NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == card, NoteChunkLinkModel.chunk == chunks["chapter"]).count() == 1
    assert "0 carte(s) réassignée(s)" in toasts[-1]
    assert "1 conservée(s) sur son chapitre" in toasts[-1]


def test_ai_sources_align_buttons(qtbot):
    """Vérifie les boutons et actions d'alignement intelligent des cartes dans AISourcesDiagnosticTab et DocumentInspectorPanel."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Réseau {uid}",
        content="# TCP Handshake\nLe protocole TCP utilise le syn syn-ack ack pour établir la connexion.\n\n# UDP Datagramme\nLe protocole UDP fonctionne sans connexion préalable.",
        file_type="md",
    )
    chunk1 = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Réseau > TCP Handshake",
        content="Le protocole TCP utilise le syn syn-ack ack pour établir la connexion.",
        content_hash=f"h_tcp_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path="Réseau > UDP Datagramme",
        content="Le protocole UDP fonctionne sans connexion préalable.",
        content_hash=f"h_udp_{uid}",
    )

    deck = DeckModel.create(name=f"Deck Réseau {uid}")
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(
        name=f"Model Réseau {uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]',
        css_style="",
    )
    note_tcp = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt)
    note_tcp.add_version(
        {"Front": "Comment fonctionne le handshake TCP ?", "Back": "Il utilise syn syn-ack ack pour établir la connexion."},
        source="manual",
    )
    note_tcp.tags = json.dumps(build_document_tags(doc_id=doc.id, section_name=chunk1.heading_path))
    note_tcp.save()
    CardModel.create(note=note_tcp, deck=deck, template_index=0)

    # 1. Test DocumentInspectorPanel btn_align_cards
    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)
    panel.load_chunks()

    # Initialement pas de lien
    assert NoteChunkLinkModel.select().where(NoteChunkLinkModel.chunk == chunk1).count() == 0

    # Clic sur Aligner les fiches
    panel.btn_align_cards.click()

    # Vérification que le lien a été créé
    assert NoteChunkLinkModel.select().where(NoteChunkLinkModel.chunk == chunk1).count() == 1

    # 2. Test AISourcesDiagnosticTab btn_align_all
    tab = AISourcesDiagnosticTab()
    qtbot.addWidget(tab)
    assert hasattr(tab, "btn_align_all")
    tab.btn_align_all.click()
    assert tab.lbl_kpi_docs_val.text() != ""


def test_ai_wozniak_linter_tab_and_widgets(qtbot):
    """Vérifie l'onglet Linter Wozniak, la sélection de catégorie et l'inspection de carte."""
    tab = AIWozniakLinterTab()
    qtbot.addWidget(tab)

    assert "Score :" in tab.score_badge.text()
    assert len(tab.kpi_cards) == 4

    # Tester le basculement de catégorie
    tab.on_category_kpi_clicked("cat-katex")
    assert tab.active_category == "cat-katex"

    # Tester le widget de carte problème Wozniak
    item_data: dict[str, Any] = {
        "title": "Carte #42 - Liste trop longue",
        "badge": "Viol Atomicité",
        "badge_color": "#f87171",
        "original": {"Recto": "Quels sont les 10 principes ?", "Verso": "1, 2, 3..."},
        "proposal": {"Recto": "Quel est le principe 1 ?", "Verso": "1"},
        "proposal_summary": "Scission en cartes atomiques univoques",
    }
    card_w = WozniakCardItemWidget(item_data)
    qtbot.addWidget(card_w)

    assert card_w.inspector_widget.isHidden()
    card_w.toggle_inspector()
    assert not card_w.inspector_widget.isHidden()


def test_ai_tokens_srs_tab(qtbot):
    """Vérifie le simulateur économique de jetons IA et d'impact SRS FSRS-4.5."""
    tab = AITokensSrsTab()
    qtbot.addWidget(tab)

    assert "Dépenses" in tab.lbl_spent.text()
    assert "carte" in tab.lbl_cost.text()
    tab.refresh_stats()
    assert tab.kpi_grid.count() == 4


def test_ai_sources_tab_refreshes_when_coverage_synced(qtbot):
    """La grille Analyse > Documents se rafraîchit après un alignement qui émet CoverageSyncedEvent."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Sync UI {uid}",
        content="# Section 1\nContenu A",
        file_type="md",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Section 1",
        content="Contenu A",
        content_hash=f"hs_{uid}",
    )

    tab = AISourcesDiagnosticTab()
    qtbot.addWidget(tab)
    tab.refresh_data()
    assert tab.lbl_kpi_coverage_val.text() == "0%"

    deck = DeckModel.create(name=f"Deck Sync UI {uid}")
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Model Sync UI {uid}")
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt, tags=json.dumps(build_document_tags(doc_id=doc.id, section_name="Section 1")))
    note.add_version({"Front": "Question ?", "Back": "Réponse."}, source="manual")
    CardModel.create(note=note, deck=deck, template_index=0)

    CoverageAlignmentService.align_document(doc.id)

    qtbot.waitUntil(lambda: tab.lbl_kpi_coverage_val.text() != "0%", timeout=3000)
    assert tab.lbl_kpi_coverage_val.text() == "100%"


def test_document_inspector_reloads_when_coverage_synced(qtbot):
    """L'inspecteur de document recharge son sommaire après un alignement ciblé."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Inspecteur Sync {uid}",
        content="# Article 1\nContenu.",
        file_type="md",
    )
    chunk = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Article 1",
        content="Contenu.",
        content_hash=f"hi_{uid}",
    )

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)
    panel.load_chunks()
    assert "0 carte" in _all_tree_items(panel)[0].text(0)

    deck = DeckModel.create(name=f"Deck Insp Sync {uid}")
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Model Insp Sync {uid}")
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt, tags=json.dumps(build_document_tags(doc_id=doc.id, section_name=chunk.heading_path)))
    note.add_version({"Front": "Question ?", "Back": "Réponse."}, source="manual")
    CardModel.create(note=note, deck=deck, template_index=0)

    CoverageAlignmentService.align_document(doc.id)

    qtbot.waitUntil(lambda: "1 carte" in _all_tree_items(panel)[0].text(0), timeout=3000)


def test_ai_duplicates_merge_tab_and_inspector(qtbot):
    """Vérifie l'inspecteur de fusion à 3 panneaux et la matrice de doublons."""
    matrix = DuplicateMatrixTable()
    qtbot.addWidget(matrix)
    assert matrix.table.columnCount() == 6

    nt = NoteTypeModel.select().first() or NoteTypeModel.create(
        name="Model Dup Test",
        fields_schema='["Front", "Back"]',
        templates="[]",
        css_style="",
    )
    note_a = NoteModel.create(guid="guid_a", note_type=nt)
    note_b = NoteModel.create(guid="guid_b", note_type=nt)

    inspector = DuplicateMergeInspector()
    qtbot.addWidget(inspector)

    # Tester la permutation A <-> B
    inspector.current_conflict = {
        "note_a": note_a,
        "content_a": {"Recto": "Question A", "Verso": "Réponse A"},
        "note_b": note_b,
        "content_b": {"Recto": "Question B", "Verso": "Réponse B"},
        "similarity": 0.92,
    }
    inspector.on_swap()
    assert inspector.current_conflict["content_a"]["Recto"] == "Question B"


def test_ai_duplicates_merge_tab_empty_state(qtbot):
    """Vérifie le retour visuel (badge + état vide) quand aucun doublon n'est détecté."""
    tab = AIDuplicatesMergeTab()
    qtbot.addWidget(tab)

    # Aucun doublon généré → badge 0 + état vide visible + table vide
    tab.on_scan_finished([])
    assert tab.matrix_table.badge_count.text() == "0 paire à examiner"
    assert tab.matrix_table.empty_state.isVisibleTo(tab)
    assert tab.matrix_table.table.rowCount() == 0
    assert tab.merge_inspector.isHidden()

    # Un doublon détecté → badge 1 + état vide masqué + ligne ajoutée
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(
        name="Model Dup Empty",
        fields_schema='["Front", "Back"]',
        templates="[]",
        css_style="",
    )
    note_a = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt)
    note_b = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt)

    tab.on_scan_finished(
        [
            (note_a, {"Recto": "Question A", "Verso": "Réponse A"}, note_b, {"Recto": "Question B", "Verso": "Réponse B"}, 0.96),
        ]
    )
    assert tab.matrix_table.badge_count.text() == "1 paire à examiner"
    assert not tab.matrix_table.empty_state.isVisibleTo(tab)
    assert tab.matrix_table.table.rowCount() == 1


def test_ai_duplicates_merge_tab_badge_plural(qtbot):
    """Vérifie la gestion singulier/pluriel du badge après suppression du dernier doublon."""
    tab = AIDuplicatesMergeTab()
    qtbot.addWidget(tab)

    nt = NoteTypeModel.select().first() or NoteTypeModel.create(
        name="Model Dup Plural",
        fields_schema='["Front", "Back"]',
        templates="[]",
        css_style="",
    )
    notes = [NoteModel.create(guid=uuid.uuid4().hex, note_type=nt) for _ in range(2)]

    tab.on_scan_finished([(notes[0], {"Recto": f"A{i}", "Verso": "R"}, notes[1], {"Recto": f"B{i}", "Verso": "R"}, 0.9) for i in range(2)])
    assert tab.matrix_table.badge_count.text() == "2 paires à examiner"
    assert tab.matrix_table.table.rowCount() == 2

    # Suppression successive → retour à l'état vide après la dernière paire
    tab.matrix_table.table.selectRow(1)
    tab.remove_current_conflict()
    assert tab.matrix_table.badge_count.text() == "1 paire à examiner"
    assert not tab.matrix_table.empty_state.isVisibleTo(tab)

    tab.matrix_table.table.selectRow(0)
    tab.remove_current_conflict()
    assert tab.matrix_table.badge_count.text() == "0 paire à examiner"
    assert tab.matrix_table.empty_state.isVisibleTo(tab)
    assert tab.matrix_table.table.rowCount() == 0


def test_analysis_view_main_container(qtbot):
    """Vérifie l'initialisation du conteneur principal de l'Hôpital (AnalysisView)."""
    view = AnalysisView()
    qtbot.addWidget(view)

    assert view is not None
    assert view.main_panel.content_stack.count() == 4  # 4 onglets : Wozniak, Sources, Jetons/SRS, Doublons


def _stored_neutralized(doc_id: int) -> list[str]:
    return [address.render() for address in DocumentRepository().get_neutralized_regions(DocumentModel.get_by_id(doc_id))]


def test_document_inspector_neutralizes_a_section_without_removing_its_content(qtbot):
    """« Neutraliser cette section » sort la section du dénominateur sans toucher à sa matière.

    Second verbe, distinct de l'exclusion : ici le contenu reste dans le document et
    dans l'index — l'unité de cours est déclarée non couvrable par une carte à elle seule,
    ce qui est différent d'une section retirée du périmètre.
    """
    uid = uuid.uuid4().hex[:6]
    doc, chunks = _make_inspectable_document(uid)
    _cover_chunk_with_card(doc, chunks[1], uid)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)
    panel.chapters_tree.setCurrentItem(_all_tree_items(panel)[2])
    qtbot.wait(10)

    assert "25%" in panel.lbl_doc_summary.text()
    assert "1/4 sections" in panel.lbl_doc_summary.text()
    assert "Neutraliser cette section" in panel.btn_neutralize_section.text()
    assert panel.btn_neutralize_section.isEnabled()

    panel.btn_neutralize_section.click()

    # Déclaration persistée comme adresse typée, et non comme fragment de la matière.
    assert _stored_neutralized(doc.id) == ["heading:Corriges"]
    assert _stored_exclusions(doc.id) == []

    # Le conteneur sort du dénominateur de couverture : 4 → 3 unités, la carte reste comptée.
    assert "1/3 sections" in panel.lbl_doc_summary.text()
    # …mais sa matière et sa carte restent en base, et l'action propose de la réactiver.
    assert DocumentChunkModel.select().where(DocumentChunkModel.document == doc, DocumentChunkModel.heading_path == "Corriges").exists()
    assert NoteChunkLinkModel.select().where(NoteChunkLinkModel.chunk == chunks[1]).exists()
    assert "Réactiver cette section" in panel.btn_neutralize_section.text()

    # Les deux verbes restent distincts sur la même ligne.
    assert "Exclure cette section" in panel.btn_exclude_section.text()

    panel.btn_neutralize_section.click()

    assert _stored_neutralized(doc.id) == []
    assert "1/4 sections" in panel.lbl_doc_summary.text()
    assert "Neutraliser cette section" in panel.btn_neutralize_section.text()


def test_document_inspector_neutralization_action_follows_the_selected_section(qtbot):
    """L'action de neutralisation décrit la section sélectionnée, comme celle d'exclusion."""
    uid = uuid.uuid4().hex[:6]
    doc, _chunks = _make_inspectable_document(uid)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)

    panel.chapters_tree.setCurrentItem(_all_tree_items(panel)[1])
    qtbot.wait(10)
    panel.btn_neutralize_section.click()
    assert _stored_neutralized(doc.id) == ["heading:Partie 1"]
    assert "Réactiver cette section" in panel.btn_neutralize_section.text()

    panel.chapters_tree.setCurrentItem(_all_tree_items(panel)[0])
    qtbot.wait(10)
    assert "Neutraliser cette section" in panel.btn_neutralize_section.text()

    # Un fragment au libellé de page n'a pas de titre de section à neutraliser.
    panel.chapters_tree.setCurrentItem(_all_tree_items(panel)[3])
    qtbot.wait(10)
    assert not panel.btn_neutralize_section.isEnabled()
    assert "titre" in panel.btn_neutralize_section.toolTip().lower()


def _make_granularity_document(uid: str) -> tuple[DocumentModel, list[DocumentChunkModel]]:
    """Chapitre avec préambule propre et sous-section : la granularité `node:` y a un sens."""
    doc = DocumentModel.create(
        title=f"Cours Imbrique {uid}",
        content="# Chapitre\nPreambule de garde.\n\n## Detail\nLe detail du chapitre.",
        file_type="md",
    )
    chunks = [
        DocumentChunkModel.create(document=doc, chunk_index=0, heading_path="Chapitre", content="Preambule de garde.", content_hash=f"dn_{uid}_0"),
        DocumentChunkModel.create(document=doc, chunk_index=1, heading_path="Chapitre > Detail", content="Le detail du chapitre.", content_hash=f"dn_{uid}_1"),
        # Un chapitre voisin, sans lien avec la ligne visée : c'est lui que la granularité
        # `node:` ne doit pas embarquer.
        DocumentChunkModel.create(document=doc, chunk_index=2, heading_path="Annexe", content="Hors sujet.", content_hash=f"dn_{uid}_2"),
    ]
    return doc, chunks


def test_the_25_words_aid_is_only_announced_where_it_qualifies(qtbot):
    """L'infobulle ne doit pas qualifier de « contenu court » un parent bien rédigé.

    `container_candidates` propose la neutralisation de tout titre qui ouvre une
    sous-section, seuil des 25 mots compris ou non : c'est au service de trancher si le
    seuil qualifie ce titre, sinon l'infobulle annonce un contenu court à 200 mots.
    """
    uid = uuid.uuid4().hex[:6]
    doc, chunks = _make_granularity_document(uid)
    maigre = DocumentChunkModel.get_by_id(chunks[0])
    maigre.content = "Six mots ici."
    maigre.save()
    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)
    parent_row = next(item for item in _all_tree_items(panel) if item.data(0, _ROLE_HEADING) == "Chapitre")

    panel.chapters_tree.setCurrentItem(parent_row)
    qtbot.wait(10)
    assert "Contenu court (3 mots)" in panel.btn_neutralize_section.toolTip()

    maigre.content = " ".join(["mot"] * 200)
    maigre.save()
    panel.load_chunks()
    panel.chapters_tree.setCurrentItem(next(item for item in _all_tree_items(panel) if item.data(0, _ROLE_HEADING) == "Chapitre"))
    qtbot.wait(10)
    assert "Contenu court" not in panel.btn_neutralize_section.toolTip()


def test_neutralizing_a_node_leaves_its_subsections_in_coverage(qtbot):
    """Neutraliser le contenu propre d'un titre n'efface pas ses sous-sections de la couverture.

    Sans cette granularité, désigner le préambule d'un chapitre revenait à déclarer toute sa
    lignée conteneur : la couverture disparaissait pour des sections qui, elles, ont du contenu
    propre. C'est le besoin utilisateur qui a fait naître la valeur `node:`.
    """
    uid = uuid.uuid4().hex[:6]
    doc, chunks = _make_granularity_document(uid)
    _cover_chunk_with_card(doc, chunks[1], uid)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)
    parent_row = next(item for item in _all_tree_items(panel) if item.data(0, _ROLE_HEADING) == "Chapitre")
    panel.chapters_tree.setCurrentItem(parent_row)
    qtbot.wait(10)

    panel.toggle_section_neutralization(scope=RegionScope.NODE)

    assert _stored_neutralized(doc.id) == ["node:Chapitre"]
    # Le préambule seul devient conteneur ; la sous-section, qui a son contenu, reste une unité.
    parent_chunk = DocumentChunkModel.get_by_id(chunks[0].id)
    child_chunk = DocumentChunkModel.get_by_id(chunks[1].id)
    assert (parent_chunk.is_structural_container, parent_chunk.container_origin) == (True, "declared")
    assert (child_chunk.is_structural_container, child_chunk.container_origin) == (False, None)
    annex = DocumentChunkModel.get(DocumentChunkModel.document == doc.id, DocumentChunkModel.heading_path == "Annexe")
    assert (annex.is_structural_container, annex.container_origin) == (False, None)
    # Le chapitre seul est neutralisé ; la sous-section couverte et l'annexe restent au dénominateur.
    assert "1/2 sections" in panel.lbl_doc_summary.text()

    # La granularité de lignée reste disponible, et elle emporte bien les descendants.
    panel.toggle_section_neutralization(scope=RegionScope.HEADING)
    # L'ordre de rendu est canonique : `node:` avant `heading:`, quelle que soit la chronology.
    assert _stored_neutralized(doc.id) == ["node:Chapitre", "heading:Chapitre"]
    child_chunk = DocumentChunkModel.get_by_id(chunks[1].id)
    assert child_chunk.is_structural_container is True
    assert "0/1 sections" in panel.lbl_doc_summary.text()


def test_excluding_a_node_leaves_its_subsections_in_scope(qtbot):
    """Écarter le contenu propre d'un titre ne sort pas ses sous-sections du périmètre."""
    uid = uuid.uuid4().hex[:6]
    doc, _chunks = _make_granularity_document(uid)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)
    parent_row = next(item for item in _all_tree_items(panel) if item.data(0, _ROLE_HEADING) == "Chapitre")
    panel.chapters_tree.setCurrentItem(parent_row)
    qtbot.wait(10)

    panel.toggle_section_exclusion(scope=RegionScope.NODE)

    assert _stored_exclusions(doc.id) == ["node:Chapitre"]
    assert DocumentRepository.is_region_excluded(DocumentModel.get_by_id(doc.id), heading_path="Chapitre") is True
    assert DocumentRepository.is_region_excluded(DocumentModel.get_by_id(doc.id), heading_path="Chapitre > Detail") is False

    # L'exclusion de lignée, elle, couvre la lignée entière.
    panel.toggle_section_exclusion(scope=RegionScope.HEADING)
    assert DocumentRepository.is_region_excluded(DocumentModel.get_by_id(doc.id), heading_path="Chapitre > Detail") is True


def test_inspector_context_menu_offers_both_granularities(qtbot):
    """Le menu contextuel propose la lignée et le nœud seul, sur un titre qui a des enfants."""
    uid = uuid.uuid4().hex[:6]
    doc, _chunks = _make_granularity_document(uid)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)
    parent_row = next(item for item in _all_tree_items(panel) if item.data(0, _ROLE_HEADING) == "Chapitre")
    labels = [action.text() for action in panel.chapter_context_menu(parent_row).actions()]

    assert "Neutraliser" in labels
    assert "Neutraliser le contenu seul de ce titre" in labels

    # Une feuille ne propose pas la granularité : elle dirait exactement la même chose.
    child_row = next(item for item in _all_tree_items(panel) if item.data(0, _ROLE_HEADING) == "Chapitre > Detail")
    leaf_labels = [action.text() for action in panel.chapter_context_menu(child_row).actions()]
    assert "Neutraliser le contenu seul de ce titre" not in leaf_labels


def test_the_neutralization_label_never_promises_more_than_the_action_writes(qtbot):
    """Une ligne héritée d'une déclaration de parent s'affiche neutralisée, et se réactive elle-même.

    Le bouton disait « Réactiver » parce que la ligne était couverte par la déclaration de son
    parent, mais l'action écrivait une clé exacte qui n'existait pas : rien n'était retiré, et
    un toast annonçait pourtant une réactivation. Le libellé et l'écriture doivent lire la même
    granularité.
    """
    uid = uuid.uuid4().hex[:6]
    doc, chunks = _make_granularity_document(uid)
    _cover_chunk_with_card(doc, chunks[1], uid)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)
    parent_row = next(item for item in _all_tree_items(panel) if item.data(0, _ROLE_HEADING) == "Chapitre")
    child_row = next(item for item in _all_tree_items(panel) if item.data(0, _ROLE_HEADING) == "Chapitre > Detail")

    # Le parent est déclaré : l'enfant est couvert par héritage, sans le déclarer lui-même.
    panel.chapters_tree.setCurrentItem(parent_row)
    qtbot.wait(10)
    panel.toggle_section_neutralization(scope=RegionScope.HEADING)
    panel.chapters_tree.setCurrentItem(child_row)
    qtbot.wait(10)
    assert panel.btn_neutralize_section.text().startswith("Neutraliser aussi")

    panel.toggle_section_neutralization(scope=RegionScope.HEADING)

    assert _stored_neutralized(doc.id) == ["heading:Chapitre", "heading:Chapitre > Detail"]
    panel.chapters_tree.setCurrentItem(child_row)
    qtbot.wait(10)
    assert panel.btn_neutralize_section.text().startswith("Réactiver")


def test_reactivating_a_lineage_keeps_an_independently_declared_descendant(qtbot):
    """Réactiver la lignée d'un titre ne déneutralise pas une sous-section déclarée par ailleurs.

    La déclaration d'un parent et celle de son enfant sont deux choix distincts ; retirer le
    premier ne peut pas effacer le second. Sans quoi la sous-section réapparaît dans le
    dénominateur de couverture alors que la règle persistée dit toujours le contraire.
    """
    uid = uuid.uuid4().hex[:6]
    doc, chunks = _make_granularity_document(uid)
    _cover_chunk_with_card(doc, chunks[1], uid)

    panel = DocumentInspectorPanel(doc)
    qtbot.addWidget(panel)
    parent_row = next(item for item in _all_tree_items(panel) if item.data(0, _ROLE_HEADING) == "Chapitre")
    child_row = next(item for item in _all_tree_items(panel) if item.data(0, _ROLE_HEADING) == "Chapitre > Detail")

    panel.chapters_tree.setCurrentItem(parent_row)
    qtbot.wait(10)
    panel.toggle_section_neutralization(scope=RegionScope.HEADING)
    panel.chapters_tree.setCurrentItem(child_row)
    qtbot.wait(10)
    panel.toggle_section_neutralization(scope=RegionScope.HEADING)

    # Le parent est réactivé, sa sous-section reste neutralisée par sa propre déclaration.
    panel.chapters_tree.setCurrentItem(parent_row)
    qtbot.wait(10)
    panel.toggle_section_neutralization(scope=RegionScope.HEADING)

    child_chunk = DocumentChunkModel.get(DocumentChunkModel.document == doc.id, DocumentChunkModel.heading_path == "Chapitre > Detail")
    assert (child_chunk.is_structural_container, child_chunk.container_origin) == (True, "declared")
    assert DocumentRepository.is_region_neutralized(DocumentModel.get_by_id(doc.id), heading_path="Chapitre > Detail") is True
    # La sous-section neutralisée sort du dénominateur : il n'y reste que le chapitre.
    assert "0/1 sections" in panel.lbl_doc_summary.text()
