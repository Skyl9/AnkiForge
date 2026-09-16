"""
Tests unitaires pour CoverageAlignmentService et la résolution bidirectionnelle des médias.
"""

import json
import uuid

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
from ankiforge.utils.tags import build_document_tags


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
