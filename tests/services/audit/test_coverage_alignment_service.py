"""
Tests unitaires pour CoverageAlignmentService et la résolution bidirectionnelle des médias.
"""

import json
import uuid

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    MediaModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
)
from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService
from ankiforge.utils.paths import get_media_dir, resolve_media_path
from ankiforge.utils.tags import build_document_tags, clean_source_slug, parse_note_tags

pytestmark = pytest.mark.integration


def _make_note_with_tags(nt: NoteTypeModel, tags: list[str]) -> NoteModel:
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt, tags=json.dumps(tags))
    note.add_version({"Front": "Q", "Back": "R"}, source="manual")
    return note


def test_align_document_matching_and_coverage():
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Réseaux {uid}",
        content="Les protocoles réseau TCP et IP assurent l'acheminement des paquets.",
        file_type="md",
    )

    chunk1 = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Architecture > Modèle OSI et protocoles",
        content="Le protocole TCP garantit la fiabilité du transfert de paquets sur le réseau.",
        content_hash=f"hash1_{uid}",
    )
    chunk2 = DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path="Cryptographie > Chiffrement asymétrique",
        content="RSA utilise une paire de clés publique et privée pour chiffrer.",
        content_hash=f"hash2_{uid}",
    )

    deck = DeckModel.create(name=f"Deck Réseau {uid}")
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(
        name=f"Model {uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]',
        css_style="",
    )

    # Note 1 : traçabilité -> chunk 1 via section:<slug>
    tags1 = build_document_tags(doc_id=doc.id, section_name=chunk1.heading_path)
    note1 = _make_note_with_tags(nt, tags1)
    CardModel.create(note=note1, deck=deck, template_index=0)

    # Note 2 : traçabilité -> chunk 2 via section:<slug>
    tags2 = build_document_tags(doc_id=doc.id, section_name=chunk2.heading_path)
    note2 = _make_note_with_tags(nt, tags2)
    CardModel.create(note=note2, deck=deck, template_index=0)

    # Note 3 : aucun tag de traçabilité (contenu similaire, ne doit PAS être liée)
    note3 = _make_note_with_tags(nt, ["manuel"])
    CardModel.create(note=note3, deck=deck, template_index=0)

    # Exécution de l'alignement
    stats = CoverageAlignmentService.align_document(doc.id)
    assert stats["matched_notes"] == 2
    assert stats["covered_chunks"] == 2
    assert stats["total_chunks"] == 2
    assert stats["coverage_pct"] == 100.0

    # Vérification des liaisons en BDD
    links1 = list(NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == note1))
    assert len(links1) == 1
    assert links1[0].chunk_id == chunk1.id

    links2 = list(NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == note2))
    assert len(links2) == 1
    assert links2[0].chunk_id == chunk2.id

    links3 = list(NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == note3))
    assert len(links3) == 0


def test_align_document_ignores_lexical_overlap_without_tags():
    """Une forte similarité lexicale sans tags de traçabilité ne doit générer aucun lien."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Médical {uid}",
        content="L'hypertension artérielle est une élévation anormale de la pression sanguine.",
        file_type="md",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Cardiologie > Hypertension",
        content="L'hypertension artérielle est une élévation anormale de la pression sanguine.",
        content_hash=f"hash_{uid}",
    )

    deck = DeckModel.create(name=f"Deck Médical {uid}")
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Model {uid}")

    note = _make_note_with_tags(nt, ["révision"])
    CardModel.create(note=note, deck=deck, template_index=0)

    stats = CoverageAlignmentService.align_document(doc.id, min_overlap=2)
    assert stats["matched_notes"] == 0
    assert stats["covered_chunks"] == 0
    assert stats["coverage_pct"] == 0.0
    assert NoteChunkLinkModel.select().count() == 0


def test_align_document_does_not_create_fake_chunks():
    """La synchronisation ne doit plus créer de chunks factices pour couvrir une page non découpée."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Paginé {uid}",
        content="Contenu du document.",
        file_type="pdf",
        total_pages=5,
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        content="Page une",
        page_number=1,
        content_hash=f"hash_{uid}",
    )

    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Model {uid}")
    tags = build_document_tags(doc_id=doc.id, page_number=3)
    note = _make_note_with_tags(nt, tags)

    stats = CoverageAlignmentService.align_document(doc.id)
    assert stats["matched_notes"] == 0
    # Aucun chunk factice "Page 3" ne doit exister
    assert DocumentChunkModel.select().where(DocumentChunkModel.document == doc).count() == 1
    assert not NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == note).exists()


def test_stale_links_removed_when_tags_no_longer_match():
    """Un lien résiduel vers un document dont la note n'a plus de tags concordants est retiré."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours College {uid}", file_type="md")
    chunk = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Introduction",
        content="Contenu.",
        content_hash=f"hash_{uid}",
    )

    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Model {uid}")
    # La note portait un tag doc:<id> mais son tag a changé vers un autre document inexistant
    other_doc = DocumentModel.create(title=f"Autre Doc {uid}", file_type="md")
    note = _make_note_with_tags(nt, [f"doc:{other_doc.id}"])
    NoteChunkLinkModel.create(note=note, chunk=chunk)

    CoverageAlignmentService.sync_coverage_from_tags(doc_id=doc.id)

    remaining = NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == note)
    assert remaining.count() == 0


def test_find_matching_chunk_for_note():
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours Algorithmique {uid}", file_type="md")
    chunk = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Graphes > Plus court chemin Dijkstra",
        content="L'algorithme de Dijkstra trouve le plus court chemin avec des poids positifs.",
        content_hash=f"hash_dijkstra_{uid}",
    )

    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Type {uid}")
    tags = build_document_tags(doc_id=doc.id, section_name=chunk.heading_path)
    note = _make_note_with_tags(nt, tags)

    matched_chunk = CoverageAlignmentService.find_matching_chunk_for_note(note.id)
    assert matched_chunk is not None
    assert matched_chunk.id == chunk.id


def test_find_matching_chunk_for_note_without_tags_returns_none():
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours Sans Tag {uid}", file_type="md")
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Sans importance",
        content="Contenu.",
        content_hash=f"hash_{uid}",
    )

    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Type {uid}")
    note = _make_note_with_tags(nt, [])

    matched_chunk = CoverageAlignmentService.find_matching_chunk_for_note(note.id)
    assert matched_chunk is None


def test_resolve_finest_chunk_prefers_source_chunk_id():
    """source_chunk_id (provenance exacte) est prioritaire dans la résolution fine."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours Source {uid}", file_type="md")
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Chapitre 1 > Intro",
        content="Introduction générale.",
        content_hash=f"h1_{uid}",
    )
    c2 = DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path="Chapitre 1 > Définition",
        content="Définition précise d'un concept.",
        content_hash=f"h2_{uid}",
    )

    resolved = CoverageAlignmentService.resolve_finest_chunk_for_card(
        card_text="Définition précise d'un concept.",
        doc_id=doc.id,
        llm_section="Chapitre 1 > Intro",
        source_chunk_id=c2.id,
        page_number=None,
    )
    assert resolved is not None
    assert resolved.id == c2.id


def test_find_chunk_by_section_suffix_tolerant_leaf():
    """Le suffix-match tolère une section annoncée en titre feuille ou en breadcrumb complet."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours Suffix {uid}", file_type="md")
    c1 = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Chapitre 1 > La cellule > Noyau > Ribosomes",
        content="Les ribosomes synthétisent les protéines.",
        content_hash=f"hs_{uid}",
    )

    # Titre feuille seul
    assert CoverageAlignmentService._find_chunk_by_section_suffix(doc.id, "ribosomes").id == c1.id
    # Breadcrumb complet (sluggé)
    assert CoverageAlignmentService._find_chunk_by_section_suffix(doc.id, clean_source_slug("Chapitre 1 > La cellule > Noyau > Ribosomes")).id == c1.id
    # Niveau intermédiaire sans ambiguïté
    assert CoverageAlignmentService._find_chunk_by_section_suffix(doc.id, clean_source_slug("La cellule > Noyau > Ribosomes")).id == c1.id
    # Slug propre attendu
    assert CoverageAlignmentService._find_chunk_by_section_suffix(doc.id, clean_source_slug("Ribosomes")).id == c1.id
    # Inconnu -> None
    assert CoverageAlignmentService._find_chunk_by_section_suffix(doc.id, "inexistant") is None
    assert CoverageAlignmentService._find_chunk_by_section_suffix(doc.id, "") is None


def test_resolve_finest_chunk_page_and_lexical_overlap():
    """page_number puis overlap lexical résolvent la section fine par défaut."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours Resolve {uid}", file_type="md")
    c_page = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        page_number=4,
        content="Contenu de la page quatre.",
        content_hash=f"hp_{uid}",
    )
    c_deep = DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path="Recherche > Approfondissement > Comparaison",
        content="Mitochondrie chloroplastes et comparaison des deux organites.",
        content_hash=f"hd_{uid}",
    )

    # Résolution par numéro de page
    by_page = CoverageAlignmentService.resolve_finest_chunk_for_card(
        card_text="Contenu de la page quatre.",
        doc_id=doc.id,
        llm_section=None,
        source_chunk_id=None,
        page_number=4,
    )
    assert by_page is not None
    assert by_page.id == c_page.id

    # Résolution par overlap lexical fin (chunk profond)
    by_overlap = CoverageAlignmentService.resolve_finest_chunk_for_card(
        card_text="Mitochondrie et chloroplastes, comparaison des organites.",
        doc_id=doc.id,
    )
    assert by_overlap is not None
    assert by_overlap.id == c_deep.id

    # Aucune correspondance paramétrique ni lexicale -> None
    unmatched = CoverageAlignmentService.resolve_finest_chunk_for_card(
        card_text="Sujet totalement hors sujet sans liens de vocabulaire.",
        doc_id=doc.id,
        page_number=99,
    )
    assert unmatched is None

    # Document sans chunks -> None
    empty_doc = DocumentModel.create(title=f"Cours Vide {uid}", file_type="md")
    assert CoverageAlignmentService.resolve_finest_chunk_for_card("n'importe quoi", empty_doc.id) is None


def test_resolve_finest_chunk_deepest_on_tie():
    """À égalité lexicale, le fragment le plus profond (granularité fine) est retenu."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours Profondeur {uid}", file_type="md")
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Thème",
        content="Concepts clés communs partagés.",
        content_hash=f"ht1_{uid}",
    )
    c_deep = DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path="Thème > Sous-thème > Précision",
        content="Concepts clés communs partagés.",
        content_hash=f"ht2_{uid}",
    )

    resolved = CoverageAlignmentService.resolve_finest_chunk_for_card(
        card_text="Concepts clés communs partagés.",
        doc_id=doc.id,
    )
    assert resolved is not None
    assert resolved.id == c_deep.id


def test_align_document_publishes_coverage_synced_event():
    """Une modification de couverture émet un CoverageSyncedEvent pour notifier l'UI."""
    from ankiforge.utils.event_bus import CoverageSyncedEvent, event_bus

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours Event {uid}", file_type="md")
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Introduction",
        content="Contenu.",
        content_hash=f"hash_{uid}",
    )

    captured: list[CoverageSyncedEvent] = []

    def handler(event: CoverageSyncedEvent) -> None:
        captured.append(event)

    event_bus.subscribe(CoverageSyncedEvent, handler)
    try:
        CoverageAlignmentService.align_document(doc.id)
    finally:
        event_bus.unsubscribe(CoverageSyncedEvent, handler)

    assert len(captured) == 1
    assert captured[0].doc_id == doc.id
    assert captured[0].scope == "document"


def test_sync_coverage_from_tags_global_publishes_all_event():
    """Un alignement global émet un CoverageSyncedEvent sans doc ciblé."""
    from ankiforge.utils.event_bus import CoverageSyncedEvent, event_bus

    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours Global Event {uid}", file_type="md")
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        content="Contenu.",
        content_hash=f"hash_global_{uid}",
    )

    captured: list[CoverageSyncedEvent] = []

    def handler(event: CoverageSyncedEvent) -> None:
        captured.append(event)

    event_bus.subscribe(CoverageSyncedEvent, handler)
    try:
        CoverageAlignmentService.sync_coverage_from_tags()
    finally:
        event_bus.unsubscribe(CoverageSyncedEvent, handler)

    assert len(captured) == 1
    assert captured[0].doc_id is None
    assert captured[0].scope == "all"


def test_resolve_media_path_bidirectional(tmp_path):
    media_dir = get_media_dir()
    media_dir.mkdir(parents=True, exist_ok=True)

    uid = uuid.uuid4().hex[:8]
    hashed_name = f"hashed_img_{uid}.jpg"
    orig_name = f"cours_schema_{uid}.jpg"

    # Créer le fichier physique sous son nom haché
    test_file = media_dir / hashed_name
    test_file.write_bytes(b"FAKE_IMAGE_DATA")

    # Créer l'enregistrement MediaModel
    MediaModel.create(
        filename=hashed_name,
        original_name=orig_name,
        checksum=f"chk_{uid}",
        mime_type="image/jpeg",
    )

    # 1. Résolution avec le nom haché -> direct
    p1 = resolve_media_path(hashed_name)
    assert p1.exists()
    assert p1.name == hashed_name

    # 2. Résolution avec le nom d'origine -> doit trouver le fichier haché grâce à MediaModel
    p2 = resolve_media_path(orig_name)
    assert p2.exists()
    assert p2.name == hashed_name


def test_find_chunk_by_section_suffix_ignores_toc_fragments():
    """Les entrées d'un sommaire (documents indexés en v4) ne captent jamais la liaison."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours Sommaire {uid}", file_type="md")
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        page_number=2,
        heading_path="Sommaire > 1 - Introduction",
        content="# Sommaire\n\n## 1 - Introduction .... 2\n\n## 2 - Statistiques .... 3\n\n## 3 - Probabilités .... 4",
        content_hash=f"toc_{uid}",
    )
    course = DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        page_number=15,
        heading_path="1 - Introduction",
        content="Une variable aléatoire est une fonction qui associe chaque issue à une valeur numérique. " * 6,
        content_hash=f"body_{uid}",
    )

    resolved = CoverageAlignmentService._find_chunk_by_section_suffix(doc.id, clean_source_slug("1 - Introduction"))

    assert resolved is not None
    assert resolved.id == course.id


def test_find_chunk_by_section_suffix_prefers_richest_fragment():
    """À granularité égale, la liaison va au fragment de cours, pas à l'annonce du sommaire."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours Collision {uid}", file_type="md")
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        page_number=2,
        heading_path="1 - Introduction",
        content="1 - Introduction",
        content_hash=f"thin_{uid}",
    )
    rich = DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        page_number=15,
        heading_path="1 - Introduction",
        content="Le cours détaillé sur les variables aléatoires et leur fonction de répartition. " * 5,
        content_hash=f"rich_{uid}",
    )

    resolved = CoverageAlignmentService._find_chunk_by_section_suffix(doc.id, clean_source_slug("1 - Introduction"))

    assert resolved is not None
    assert resolved.id == rich.id


def test_align_document_links_cards_to_course_chunk_not_to_toc():
    """Bout-en-bout : une carte taguée par section pointe vers le fragment de cours."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours E2E {uid}", file_type="md")
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        page_number=2,
        heading_path="1 - Introduction",
        content="# Sommaire\n\n## 1 - Introduction .... 2\n\n## 2 - Statistiques .... 3",
        content_hash=f"e2etoc_{uid}",
    )
    course = DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        page_number=15,
        heading_path="1 - Introduction",
        content="Le corps de cours de l'introduction aux données, détaillé et substantiel. " * 5,
        content_hash=f"e2ebody_{uid}",
    )
    deck = DeckModel.create(name=f"Deck E2E {uid}")
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(
        name=f"Model {uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]',
        css_style="",
    )
    note = _make_note_with_tags(nt, build_document_tags(doc_id=doc.id, section_name="1 - Introduction"))
    CardModel.create(note=note, deck=deck, template_index=0)

    stats = CoverageAlignmentService.align_document(doc.id)

    assert stats["matched_notes"] == 1
    links = list(NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == note))
    assert len(links) == 1
    assert links[0].chunk_id == course.id


# ---------------------------------------------------------------------------
# Affinement déterministe des liens vers les sous-sections (top-down narrowing)
# ---------------------------------------------------------------------------

_CHAPTER_BODY = (
    "Ce chapitre passe en revue l'ensemble des organites de la cellule eucaryote et précise, pour chacun d'eux, "
    "le rôle qu'il joue dans la survie et le fonctionnement de l'organisme, ainsi que les échanges de matière "
    "et d'énergie qu'il autorise avec l'environnement extérieur de la cellule."
)
_CONTAINER_BODY = "Ce chapitre présente les organites de la cellule."


def _make_refinable_document(uid: str, *, chapter_body: str = _CHAPTER_BODY) -> tuple[DocumentModel, dict[str, DocumentChunkModel]]:
    """Construit un arbre hiérarchique type H1 ➔ H2 ➔ (H3, H3, H3) à affiner."""
    doc = DocumentModel.create(title=f"Cours Cellulaire {uid}", file_type="md")
    chapter = "Biologie Cellulaire > 2 Les Structures Cellulaires"
    chunks = {
        "h1": DocumentChunkModel.create(
            document=doc,
            chunk_index=0,
            heading_path="Biologie Cellulaire",
            content="Le cours couvre la cellule et ses organites.",
            content_hash=f"rfd0_{uid}",
        ),
        "chapter": DocumentChunkModel.create(
            document=doc,
            chunk_index=1,
            heading_path=chapter,
            content=chapter_body,
            content_hash=f"rfd1_{uid}",
        ),
        "membrane": DocumentChunkModel.create(
            document=doc,
            chunk_index=2,
            heading_path=f"{chapter} > 2.1 La Membrane",
            content="La membrane plasmique délimite la cellule et contrôle les échanges de molécules.",
            content_hash=f"rfd2_{uid}",
        ),
        "noyau": DocumentChunkModel.create(
            document=doc,
            chunk_index=3,
            heading_path=f"{chapter} > 2.2 Le Noyau",
            content="Le noyau abrite l'information génétique de la cellule.",
            content_hash=f"rfd3_{uid}",
        ),
        "ribosomes": DocumentChunkModel.create(
            document=doc,
            chunk_index=4,
            heading_path=f"{chapter} > 2.3 Les Ribosomes",
            content="Les ribosomes synthétisent les protéines de la cellule.",
            content_hash=f"rfd4_{uid}",
        ),
    }
    return doc, chunks


def _make_card(
    uid: str,
    doc: DocumentModel,
    chunk: DocumentChunkModel,
    front: str,
    back: str,
    label: str,
) -> NoteModel:
    """Crée une carte taguée sur le fragment donné et la lui lie."""
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Model Affinement {uid}")
    deck = DeckModel.get_or_none(DeckModel.name == f"Deck Affinement {uid}") or DeckModel.create(name=f"Deck Affinement {uid}")
    tags = build_document_tags(doc_id=doc.id, doc_title=doc.title, section_name=chunk.heading_path, chunk_id=chunk.id)
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt, tags=json.dumps(tags))
    note.add_version({"Front": front, "Back": back}, source="manual")
    CardModel.create(note=note, deck=deck, template_index=0)
    NoteChunkLinkModel.create(note=note, chunk=chunk)
    return note


def _linked_chunk(note: NoteModel) -> DocumentChunkModel | None:
    link = NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note)
    return link.chunk if link else None


def test_refine_links_moves_a_chapter_card_to_its_sub_section():
    """Une carte de chapitre traitant une notion de sous-titre est rattachée à ce H3."""
    uid = uuid.uuid4().hex[:6]
    doc, chunks = _make_refinable_document(uid)
    overview = _make_card(uid, doc, chunks["chapter"], "Quelles sont les structures de la cellule ?", "La membrane, le noyau et les ribosomes.", "overview")
    membrane = _make_card(uid, doc, chunks["chapter"], "Quelle est la fonction de la membrane plasmique ?", "Elle délimite la cellule et contrôle les échanges.", "membrane")

    report = CoverageAlignmentService.refine_links_to_subsections(doc.id)

    assert report["reassigned"] == 1
    assert report["false_gaps_resolved"] == 1
    assert report["new_gaps"] == 0
    assert report["coverage_after"] > report["coverage_before"]

    assert _linked_chunk(membrane).id == chunks["membrane"].id
    assert _linked_chunk(overview).id == chunks["chapter"].id

    # Les tags de traçabilité suivent la nouvelle granularité.
    tags = parse_note_tags(NoteModel.get_by_id(membrane.id).tags)
    assert f"section:{clean_source_slug(chunks['membrane'].heading_path)}" in tags
    assert f"chunk:{chunks['membrane'].id}" in tags
    assert f"doc:{doc.id}" in tags
    assert "ankiforge_generated" in tags

    assert report["details"] == [
        {
            "note_id": membrane.id,
            "from_chunk_id": chunks["chapter"].id,
            "from_heading": chunks["chapter"].heading_path,
            "to_chunk_id": chunks["membrane"].id,
            "to_heading": chunks["membrane"].heading_path,
            "signal": "titre",
        }
    ]


def test_refine_links_keeps_a_card_citing_several_sub_sections_on_the_chapter():
    """Une carte qui cite plusieurs sous-sections reste une carte de chapitre."""
    uid = uuid.uuid4().hex[:6]
    doc, chunks = _make_refinable_document(uid, chapter_body=_CONTAINER_BODY)
    card = _make_card(uid, doc, chunks["chapter"], "Quels organites contient la cellule ?", "Elle contient un noyau et des ribosomes.", "multi")

    report = CoverageAlignmentService.refine_links_to_subsections(doc.id)

    assert report["reassigned"] == 0
    assert report["details"] == []
    assert _linked_chunk(card).id == chunks["chapter"].id


def test_refine_links_falls_back_on_lexical_overlap_when_the_title_is_absent():
    """Sans titre cité, le score lexical pondéré par l'idf désigne la sous-section la plus proche."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours Génétique {uid}", file_type="md")
    chapter = "Chapitre 3 : Génétique"
    parent = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path=chapter,
        content="Ce chapitre introduit la génétique et l'hérédité.",
        content_hash=f"lex0_{uid}",
    )
    transcription = DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path=f"{chapter} > 3.1 La Transcription",
        content="La transcription est la copie de l'ADN en ARN messager par l'ARN polymérase.",
        content_hash=f"lex1_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=2,
        heading_path=f"{chapter} > 3.2 La Mutation",
        content="Une mutation est une altération de la séquence d'ADN.",
        content_hash=f"lex2_{uid}",
    )
    card = _make_card(uid, doc, parent, "Comment l'ARN polymérase copie-t-elle l'ADN ?", "Elle synthétise un ARN messager à partir de la matrice d'ADN.", "lexical")

    report = CoverageAlignmentService.refine_links_to_subsections(doc.id)

    assert report["reassigned"] == 1
    assert report["details"][0]["signal"] == "lexique"
    assert report["details"][0]["to_chunk_id"] == transcription.id
    assert _linked_chunk(card).id == transcription.id


def test_refine_links_keeps_a_literal_citation_despite_generic_parent_vocabulary():
    """Un mot d'usage commun partagé avec le conteneur n'annule pas une citation unique de sous-titre."""
    uid = uuid.uuid4().hex[:6]
    doc, chunks = _make_refinable_document(
        uid,
        chapter_body="Ce chapitre détaille les échanges de molécules entre la cellule et son environnement.",
    )
    card = _make_card(uid, doc, chunks["chapter"], "Fonction de la membrane ?", "Elle contrôle les échanges.", "generique")

    report = CoverageAlignmentService.refine_links_to_subsections(doc.id)

    assert report["reassigned"] == 1
    assert report["details"][0]["signal"] == "titre"
    assert _linked_chunk(card).id == chunks["membrane"].id


def test_significant_tokens_drops_section_numbering():
    """La numérotation des titres ne doit pas empêcher de reconnaître une sous-section citée."""
    assert "100" not in CoverageAlignmentService._significant_tokens("100 Le Noyau Cellulaire")
    assert CoverageAlignmentService._significant_tokens("100 Le Noyau Cellulaire") == {"noyau", "cellulaire"}


def test_refine_links_treats_duplicate_heading_paths_as_a_single_sub_section():
    """Deux fragments du même titre (page de PDF scindée) ne comptent pas pour deux sous-sections citées."""
    uid = uuid.uuid4().hex[:6]
    doc, chunks = _make_refinable_document(uid)
    duplicate = DocumentChunkModel.create(
        document=doc,
        chunk_index=5,
        heading_path=chunks["membrane"].heading_path,
        content="Suite de la membrane plasmique et de ses constituants.",
        content_hash=f"rfd5_{uid}",
    )
    card = _make_card(uid, doc, chunks["chapter"], "Quelle est la fonction de la membrane plasmique ?", "Elle délimite la cellule.", "dupl")
    # Une seconde carte de chapitre (dont le vocabulaire ne cite aucune sous-section) reste
    # sur le chapitre : le garde-fou de dernière carte ne fige que les conteneurs réellement enseignés.
    _make_card(uid, doc, chunks["chapter"], "Que couvre ce chapitre ?", "Les organites de la cellule.", "dupl_autre")

    report = CoverageAlignmentService.refine_links_to_subsections(doc.id)

    assert report["reassigned"] == 1
    assert report["details"][0]["signal"] == "titre"
    assert _linked_chunk(card).id in {chunks["membrane"].id, duplicate.id}


def test_refine_links_is_idempotent_and_leaves_leaf_links_untouched():
    """Une seconde passe ne reassigne rien : les liens déjà fins ne bougent plus."""
    uid = uuid.uuid4().hex[:6]
    doc, chunks = _make_refinable_document(uid, chapter_body=_CONTAINER_BODY)
    _make_card(uid, doc, chunks["membrane"], "Délimitation de la membrane ?", "Elle délimite la cellule.", "leaf")
    _make_card(uid, doc, chunks["chapter"], "Fonction de la membrane ?", "Elle contrôle les échanges.", "chapter")

    first = CoverageAlignmentService.refine_links_to_subsections(doc.id)
    second = CoverageAlignmentService.refine_links_to_subsections(doc.id)

    assert first["reassigned"] == 1
    assert second["reassigned"] == 0
    assert second["false_gaps_resolved"] == 0
    assert second["details"] == []


def test_refine_links_preserves_a_substantive_chapter_that_would_be_left_bare():
    """Une carte n'est pas retirée d'un chapitre porteur de contenu et de sa dernière carte."""
    uid = uuid.uuid4().hex[:6]
    doc, chunks = _make_refinable_document(uid)
    assert len(chunks["chapter"].content.split()) >= CoverageAlignmentService.MIN_PARENT_CONTENT_WORDS
    card = _make_card(uid, doc, chunks["chapter"], "Fonction de la membrane ?", "Elle contrôle les échanges.", "sole")

    report = CoverageAlignmentService.refine_links_to_subsections(doc.id)

    assert report["reassigned"] == 0
    assert report["kept_on_parent"] == 1
    assert _linked_chunk(card).id == chunks["chapter"].id


def test_refine_links_reaches_the_h1_container_of_the_whole_course():
    """L'affinement descend depuis n'importe quel conteneur, H1 inclus."""
    uid = uuid.uuid4().hex[:6]
    doc, chunks = _make_refinable_document(uid, chapter_body=_CONTAINER_BODY)
    card = _make_card(uid, doc, chunks["h1"], "Où se trouve l'information génétique ?", "Dans le noyau de la cellule.", "h1")

    report = CoverageAlignmentService.refine_links_to_subsections(doc.id)

    assert report["reassigned"] == 1
    assert _linked_chunk(card).id == chunks["noyau"].id


def test_refine_links_ignores_toc_announcements_and_unrelated_documents():
    """Une entrée de sommaire n'est jamais une cible, et un autre document n'est pas touché."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours Sommaire {uid}", file_type="md")
    other = DocumentModel.create(title=f"Cours Autre {uid}", file_type="md")
    parent = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="2 Les Structures Cellulaires",
        content="Ce chapitre présente les organites.",
        content_hash=f"toc0_{uid}",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path="2 Les Structures Cellulaires > 2.1 La Membrane",
        content="# Sommaire\n\n## 2.1 La Membrane .... 12\n\n## 2.2 Le Noyau .... 14",
        content_hash=f"toc1_{uid}",
    )
    membrane = DocumentChunkModel.create(
        document=doc,
        chunk_index=2,
        heading_path="2 Les Structures Cellulaires > 2.2 La Membrane Plasmique",
        content="La membrane plasmique délimite la cellule.",
        content_hash=f"toc2_{uid}",
    )
    foreign = DocumentChunkModel.create(
        document=other,
        chunk_index=0,
        heading_path="2 Les Structures Cellulaires > 2.1 La Membrane",
        content="La membrane plasmique délimite la cellule.",
        content_hash=f"toc3_{uid}",
    )
    card = _make_card(uid, doc, parent, "Rôle de la membrane ?", "Elle délimite la cellule.", "toc")
    NoteChunkLinkModel.create(note=card, chunk=foreign)

    report = CoverageAlignmentService.refine_links_to_subsections(doc.id)

    assert report["reassigned"] == 1
    assert _linked_chunk(card).id == membrane.id
    assert NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == card, NoteChunkLinkModel.chunk == foreign) is not None


def test_refine_links_reports_an_empty_document_without_raising():
    """Un document inconnu ou sans lien ne produit aucun rapport illusoire."""
    uid = uuid.uuid4().hex[:6]
    empty = CoverageAlignmentService.refine_links_to_subsections(DocumentModel.create(title=f"Cours Vide {uid}", file_type="md").id)

    assert empty["reassigned"] == 0
    assert empty["false_gaps_resolved"] == 0
    assert empty["details"] == []

    missing = CoverageAlignmentService.refine_links_to_subsections(999999)
    assert missing["reassigned"] == 0
    assert missing["doc_id"] == 999999


def test_refine_links_publishes_coverage_synced_event():
    """L'affinement notifie l'UI pour rafraîchir couverture et sommaire."""
    from ankiforge.utils.event_bus import CoverageSyncedEvent, event_bus

    uid = uuid.uuid4().hex[:6]
    doc, chunks = _make_refinable_document(uid, chapter_body=_CONTAINER_BODY)
    _make_card(uid, doc, chunks["chapter"], "Fonction de la membrane ?", "Elle contrôle les échanges.", "event")

    captured: list[CoverageSyncedEvent] = []

    def handler(event: CoverageSyncedEvent) -> None:
        captured.append(event)

    event_bus.subscribe(CoverageSyncedEvent, handler)
    try:
        CoverageAlignmentService.refine_links_to_subsections(doc.id)
    finally:
        event_bus.unsubscribe(CoverageSyncedEvent, handler)

    assert len(captured) == 1
    assert captured[0].doc_id == doc.id
    assert captured[0].scope == "document"
