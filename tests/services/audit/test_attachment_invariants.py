"""
Tests d'invariant du rattachement carte ➔ fragment.

Ces tests ne vérifient pas un cas d'écran mais la propriété qui, tant qu'elle a manqué,
a produit des cartes « hors couverture » sans que rien ne le signale : **une réingestion
d'un document ne doit jamais perdre le rattachement des cartes qui en sont issues.**

Invariant central : l'identité durable d'un bout de document est sa *section* (le fil
d'Ariane), jamais l'identifiant de base d'un fragment — réattribué à chaque découpage. Le
tag `chunk:` hérité est lu par tolérance mais plus jamais écrit, et sa présence ne doit
plus empêcher l'exploitation d'une `section:` résoluble.
"""

import json
import uuid

import pytest

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
)
from ankiforge.services.audit.coverage_alignment_service import (
    RESOLUTION_LEXICAL,
    RESOLUTION_PAGE,
    RESOLUTION_SECTION,
    CoverageAlignmentService,
)
from ankiforge.utils.tags import (
    build_document_tags,
    extract_tag_metadata,
    legacy_section_key,
    parse_note_tags,
    section_key,
)

pytestmark = pytest.mark.integration

ARCHIVE_HEADING = "Java Software File Suffixes and Names (Archive)"
ARCHIVE_SUBHEADING = "Suffixes de Fichiers Couramment Utilisés"


def _document(uid: str) -> DocumentModel:
    return DocumentModel.create(title=f"Cours Invariant {uid}", file_type="md")


def _add_chunks(doc: DocumentModel, uid: str) -> list[DocumentChunkModel]:
    """Reproduit la forme exacte du cas observé : transcription horodatée, document non paginé."""
    return [
        DocumentChunkModel.create(
            document=doc,
            chunk_index=0,
            heading_path=ARCHIVE_HEADING,
            content="Page d'archive.",
            content_hash=f"inv0_{uid}",
        ),
        DocumentChunkModel.create(
            document=doc,
            chunk_index=1,
            heading_path=f"{ARCHIVE_HEADING} > [00:00] Avertissement d'Archive",
            content="The information on this page is for Archive Purposes Only.",
            content_hash=f"inv1_{uid}",
        ),
        DocumentChunkModel.create(
            document=doc,
            chunk_index=2,
            heading_path=f"{ARCHIVE_HEADING} > [00:01] {ARCHIVE_SUBHEADING}",
            content="Java source utilise le suffixe .java, Java bytecode utilise le suffixe .class.",
            content_hash=f"inv2_{uid}",
        ),
    ]


def _note(doc: DocumentModel, tags: list[str], front: str = "Quels suffixes Java ?", back: str = "Java source .java et Java bytecode .class.") -> NoteModel:
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"NT Invariant {uuid.uuid4().hex[:6]}")
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt, tags=json.dumps(tags, ensure_ascii=False))
    note.add_version({"Front": front, "Back": back}, source="ai")
    return note


def _reingest(doc: DocumentModel, chunks: list[DocumentChunkModel]) -> list[DocumentChunkModel]:
    """Simule une réingestion : les fragments sont supprimés puis recréés, d'identifiants différents.

    C'est exactement ce que font `reindex_service`, `document_repository._regenerate_chunks`,
    `documents_view` et `copy_document_from_profile`. Un document de bourrage est créé au
    passage pour que SQLite n'attribue pas par coincidence les mêmes `rowid` qu'au découpage
    précédent — sans cela, le test passerait pour la mauvaise raison.
    """
    payloads = [(c.chunk_index, c.heading_path, c.content, c.content_hash) for c in chunks]
    padding = DocumentModel.create(title=f"Doc Bourrage {uuid.uuid4().hex[:6]}", file_type="md")
    for i in range(5):
        DocumentChunkModel.create(document=padding, chunk_index=i, content=f"remplissage {i}", content_hash=f"pad_{i}_{uuid.uuid4().hex[:6]}")

    for c in chunks:
        c.delete_instance(recursive=True)

    recreated = [
        DocumentChunkModel.create(
            document=doc,
            chunk_index=index,
            heading_path=heading,
            content=content,
            content_hash=content_hash,
        )
        for index, heading, content, content_hash in payloads
    ]
    padding.delete_instance(recursive=True)
    return recreated


# --- La clé de section est stable, la clé de fragment ne l'est pas -------------------------


def test_section_key_is_stable_across_reingestion() -> None:
    """La clé de section ignore l'horodatage de transcription ; elle ne dépend d'aucun identifiant."""
    heading = f"{ARCHIVE_HEADING} > [00:01] {ARCHIVE_SUBHEADING}"

    assert section_key(heading) == "java_software_file_suffixes_and_names_archive_suffixes_de_fichiers_couramment_utilisés"
    # La forme historique garde l'horodatage : c'est elle que portent les notes antérieures.
    assert legacy_section_key(heading) == "java_software_file_suffixes_and_names_archive_0001_suffixes_de_fichiers_couramment_utilisés"
    # Et elle reste stable même si le texte change : seul le fil d'Ariane compte.
    assert section_key("Autre Cours > [07:42] Titre Different") == "autre_cours_titre_different"


def test_a_dangling_chunk_tag_does_not_prevent_the_section_from_resolving() -> None:
    """Le défaut observé : un `chunk:` périmé verrouillait une `section:` parfaitement résoluble."""
    uid = uuid.uuid4().hex[:6]
    doc = _document(uid)
    chunks = _add_chunks(doc, uid)

    # La note porte le tag d'une génération antérieure : `chunk:` (périmé) + `section:` (avec horodatage).
    legacy_tags = [
        "ankiforge_generated",
        f"doc:{doc.id}",
        f"source:section_key_{uid}",
        f"section:{legacy_section_key(chunks[2].heading_path)}",
        "chunk:999999",
    ]
    _note(doc, legacy_tags)

    target, resolution = CoverageAlignmentService.resolve_attachment(
        doc_id=doc.id,
        card_text="Java source utilise le suffixe .java.",
        llm_section=extract_tag_metadata(legacy_tags)["section_slug"],
        source_chunk_id=999999,
    )

    assert target is not None, "un chunk: périmé ne doit pas interdire d'exploiter la section"
    assert target.id == chunks[2].id
    assert resolution == RESOLUTION_SECTION

    # Et la réconciliation complète aboutit au même résultat, la note étant bien en base.
    assert CoverageAlignmentService.sync_coverage_from_tags(doc_id=doc.id)["newly_linked"] == 1


def test_reingestion_does_not_orphan_the_cards_and_the_note_repairs_itself() -> None:
    """Invariant de bout en bout : réingérer puis réconcilier doit rattacher, pas perdre."""
    uid = uuid.uuid4().hex[:6]
    doc = _document(uid)
    chunks = _add_chunks(doc, uid)
    note = _note(doc, build_document_tags(doc_id=doc.id, doc_title=doc.title, section_name=chunks[2].heading_path))

    first_pass = CoverageAlignmentService.sync_coverage_from_tags(doc_id=doc.id)
    before = NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note)
    assert first_pass["newly_linked"] == 1
    assert before is not None and before.chunk_id == chunks[2].id

    reingested = _reingest(doc, chunks)
    assert {c.id for c in reingested}.isdisjoint({c.id for c in chunks}), "la réingestion doit changer les identifiants de fragment"
    assert NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note) is None, "la suppression du fragment emporte son lien (CASCADE)"

    report = CoverageAlignmentService.sync_coverage_from_tags(doc_id=doc.id)

    assert report["unlinked_notes"] == 0
    assert report["newly_linked"] == 1
    assert report["resolution_breakdown"][RESOLUTION_SECTION] == 1

    link = NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note)
    assert link is not None and link.chunk_id == reingested[2].id
    assert link.resolution == RESOLUTION_SECTION


def test_reconciliation_canonicalises_the_legacy_provenance_it_crosses() -> None:
    """La réconciliation est auto-réparatrice : c'est ce qui évite une migration de données."""
    uid = uuid.uuid4().hex[:6]
    doc = _document(uid)
    chunks = _add_chunks(doc, uid)
    note = _note(
        doc,
        [
            "ankiforge_generated",
            f"doc:{doc.id}",
            f"section:{legacy_section_key(chunks[2].heading_path)}",
            "chunk:999999",
            "page:1",
        ],
    )

    report = CoverageAlignmentService.sync_coverage_from_tags(doc_id=doc.id)

    assert report["repaired_notes"] == 1
    tags = parse_note_tags(NoteModel.get_by_id(note.id).tags)
    assert f"section:{section_key(chunks[2].heading_path)}" in tags
    assert not [t for t in tags if t.startswith("chunk:")]
    # `page:1` était une presumption de portée, pas un fait : aucun fragment n'est paginé.
    assert not [t for t in tags if t.startswith("page:")]
    assert "ankiforge_generated" in tags


def test_a_second_reconciliation_is_a_no_op() -> None:
    """La réparation est idempotente : les tags sont déjà dans la forme canonique."""
    uid = uuid.uuid4().hex[:6]
    doc = _document(uid)
    chunks = _add_chunks(doc, uid)
    _note(doc, build_document_tags(doc_id=doc.id, doc_title=doc.title, section_name=chunks[2].heading_path))

    first = CoverageAlignmentService.sync_coverage_from_tags(doc_id=doc.id)
    second = CoverageAlignmentService.sync_coverage_from_tags(doc_id=doc.id)

    assert first["newly_linked"] == 1
    assert second["newly_linked"] == 0
    assert second["repaired_notes"] == 0


# --- Le palier gagnant est tracé ----------------------------------------------------------


def test_each_tier_records_how_the_fragment_was_designated() -> None:
    """Un rattachement permissif reste visible : un lien présumé se distingue d'un lien prouvé."""
    uid = uuid.uuid4().hex[:6]
    doc = _document(uid)
    target = _add_chunks(doc, uid)[2]

    exact, exact_tier = CoverageAlignmentService.resolve_attachment(doc_id=doc.id, source_chunk_id=target.id, llm_section="inexistant")
    section, section_tier = CoverageAlignmentService.resolve_attachment(doc_id=doc.id, llm_section=section_key(target.heading_path))
    lexical, lexical_tier = CoverageAlignmentService.resolve_attachment(doc_id=doc.id, card_text="suffixe .java pour le bytecode")

    assert (exact.id, exact_tier) == (target.id, "exact")
    assert (section.id, section_tier) == (target.id, RESOLUTION_SECTION)
    assert lexical is not None and lexical.id == target.id
    assert lexical_tier == RESOLUTION_LEXICAL


def test_a_page_tag_that_designs_no_fragment_falls_through_instead_of_blocking() -> None:
    """Un `page:` qui ne correspond à aucun fragment ne doit pas court-circuiter vers « non rattaché »."""
    uid = uuid.uuid4().hex[:6]
    doc = _document(uid)
    chunks = _add_chunks(doc, uid)
    page_chunk = DocumentChunkModel.create(
        document=doc,
        chunk_index=3,
        page_number=7,
        heading_path=f"{ARCHIVE_HEADING} > [00:03] Licences",
        content="Apache impose le fichier NOTICE.",
        content_hash=f"inv3_{uid}",
    )

    via_page, page_tier = CoverageAlignmentService.resolve_attachment(doc_id=doc.id, page_number=7)
    assert via_page is not None and via_page.id == page_chunk.id
    assert page_tier == RESOLUTION_PAGE

    # Page 1 (portée de lecture) alors que seul le fragment 7 est paginé : la section gagne.
    via_section, section_tier = CoverageAlignmentService.resolve_attachment(
        doc_id=doc.id,
        page_number=1,
        llm_section=section_key(chunks[2].heading_path),
    )
    assert via_section is not None and via_section.id == chunks[2].id
    assert section_tier == RESOLUTION_SECTION


def test_a_note_with_no_provenance_at_all_stays_unlinked() -> None:
    """Le permissif a une borne : ne rattacher à rien vaut mieux que rattacher n'importe quoi."""
    uid = uuid.uuid4().hex[:6]
    doc = _document(uid)
    _add_chunks(doc, uid)
    note = _note(doc, ["ankiforge_generated", f"doc:{doc.id}"], front="Question sans rapport", back="Réponse qui ne figure nulle part dans le document.")

    report = CoverageAlignmentService.sync_coverage_from_tags(doc_id=doc.id)

    assert report["unlinked_notes"] == 1
    assert NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note) is None


# --- L'identité de section est désignable par toutes ses formes ------------------------------


@pytest.mark.parametrize(
    "written_form",
    [
        pytest.param("canonical", id="canonique"),
        pytest.param("legacy", id="historique-avec-horodatage"),
        pytest.param("leaf", id="titre-feuille-seul"),
        pytest.param("suffix", id="sous-fil-dariane"),
    ],
)
def test_every_generation_of_the_section_tag_resolves(written_form: str) -> None:
    """Compatibilité dans les deux sens : les notes anciennes comme les nouvelles se rattachent."""
    uid = uuid.uuid4().hex[:6]
    doc = _document(uid)
    target = _add_chunks(doc, uid)[2]
    heading = target.heading_path or ""

    if written_form == "canonical":
        slug = section_key(heading)
    elif written_form == "legacy":
        slug = legacy_section_key(heading)
    elif written_form == "leaf":
        slug = section_key(ARCHIVE_SUBHEADING)
    else:
        slug = section_key(f"[00:01] {ARCHIVE_SUBHEADING}")

    resolved, tier = CoverageAlignmentService.resolve_attachment(doc_id=doc.id, llm_section=slug)

    assert resolved is not None and resolved.id == target.id, f"forme « {written_form} » non résolue"
    assert tier == RESOLUTION_SECTION
