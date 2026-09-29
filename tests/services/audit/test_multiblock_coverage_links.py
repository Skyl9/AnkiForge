"""
Tests de la résolution fine et du rattachement effectif des cartes issues d'une partie
multi-blocs du Batch Slice Composer.

Une partie agrège N fragments : la carte doit être rattachée au fragment qu'elle traite
réellement, et le lien de couverture (``NoteChunkLinkModel``) doit exister.
"""

import json
import logging
import uuid

import pytest

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
)
from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService
from ankiforge.services.batch.models import BatchSourceBlock
from ankiforge.services.batch.provenance import scope_provenance, stamp_scope_provenance
from ankiforge.utils.tags import build_document_tags

pytestmark = pytest.mark.integration


def _document_with_three_chunks(uid: str) -> tuple[DocumentModel, list[DocumentChunkModel]]:
    doc = DocumentModel.create(title=f"Cours Multi-Blocs {uid}", file_type="md")
    chunks = [
        DocumentChunkModel.create(
            document=doc,
            chunk_index=0,
            page_number=4,
            heading_path="Cellule > Membrane",
            content="La membrane plasmique délimite la cellule et régule ses échanges avec le milieu extérieur.",
            content_hash=f"mb0_{uid}",
        ),
        DocumentChunkModel.create(
            document=doc,
            chunk_index=1,
            page_number=5,
            heading_path="Cellule > Noyau",
            content="Le noyau abrite l'information génétique de la cellule sous forme d'ADN.",
            content_hash=f"mb1_{uid}",
        ),
        DocumentChunkModel.create(
            document=doc,
            chunk_index=2,
            page_number=9,
            heading_path="Cellule > Ribosomes",
            content="Les ribosomes synthétisent les protéines à partir de l'ARN messager.",
            content_hash=f"mb2_{uid}",
        ),
    ]
    return doc, chunks


def _block(chunk: DocumentChunkModel, ordinal: int) -> BatchSourceBlock:
    return BatchSourceBlock(
        kind="section",
        label=chunk.heading_path or f"Bloc {ordinal}",
        content=chunk.content or "",
        ordinal=ordinal,
        page_number=chunk.page_number,
        heading_path=chunk.heading_path,
        source_id=chunk.document_id,
        chunk_id=chunk.id,
    )


def test_multi_block_provenance_never_short_circuits_on_first_block_page() -> None:
    """La page du premier bloc ne doit pas produire de lien : c'est le recouvrement lexical qui tranche."""
    uid = uuid.uuid4().hex[:6]
    doc, chunks = _document_with_three_chunks(uid)
    card: dict[str, object] = {"Front": "Où se trouve l'information génétique ?", "Back": "Dans le noyau de la cellule."}
    stamp_scope_provenance([card], [_block(chunks[0], 0), _block(chunks[1], 1)])

    resolved = CoverageAlignmentService.resolve_finest_chunk_for_card(
        card_text=f"{card['Front']} {card['Back']}",
        doc_id=doc.id,
        llm_section=card.get("_source_heading_path"),
        source_chunk_id=card.get("_source_chunk_id"),
        page_number=card.get("_source_page_number"),
        source_blocks=scope_provenance([_block(chunks[0], 0), _block(chunks[1], 1)]),
    )

    assert resolved is not None
    assert resolved.id == chunks[1].id


def test_multi_block_provenance_refuses_a_chunk_outside_the_part() -> None:
    """Une carte dont le texte n'échoque aucun fragment de sa partie reste non rattachée.

    Rattacher à un fragment du document entier produirait un faux lien de couverture,
    plus trompeur que son absence : le lien doit rester dans la partie.
    """
    uid = uuid.uuid4().hex[:6]
    doc, chunks = _document_with_three_chunks(uid)
    parts = [_block(chunks[0], 0), _block(chunks[1], 1)]

    resolved = CoverageAlignmentService.resolve_finest_chunk_for_card(
        card_text="Que synthétisent les ribosomes ? Des protéines à partir de l'ARN messager.",
        doc_id=doc.id,
        source_blocks=scope_provenance(parts),
    )

    assert resolved is None


def test_multi_block_provenance_disambiguates_several_chunks_on_one_page() -> None:
    """Une page peut abriter plusieurs fragments : une route par page ne doit pas désigner le premier au hasard."""
    uid = uuid.uuid4().hex[:6]
    doc, _chunks = _document_with_three_chunks(uid)
    membrane = DocumentChunkModel.create(
        document=doc,
        chunk_index=3,
        page_number=4,
        heading_path="Cellule > Paroi",
        content="La paroi végétale est une structure rigide qui soutient la cellule.",
        content_hash=f"mb3_{uid}",
    )
    parts = [
        BatchSourceBlock(kind="section", label="page 4", content="x", ordinal=0, page_number=4, source_id=doc.id),
        BatchSourceBlock(kind="section", label="page 4 bis", content="y", ordinal=1, page_number=4, source_id=doc.id),
    ]

    resolved = CoverageAlignmentService.resolve_finest_chunk_for_card(
        card_text="La paroi végétale est une structure rigide qui soutient la cellule.",
        doc_id=doc.id,
        source_blocks=scope_provenance(parts),
    )

    assert resolved is not None
    assert resolved.id == membrane.id


def test_multi_block_card_gets_an_effective_coverage_link() -> None:
    """Critère d'acceptation : le lien créé pointe sur un fragment qui porte réellement le texte de la carte."""
    uid = uuid.uuid4().hex[:6]
    doc, chunks = _document_with_three_chunks(uid)
    nt = NoteTypeModel.create(name=f"NT Multi {uid}", fields_schema='["Front", "Back"]', templates="[]")
    parts = [_block(chunks[0], 0), _block(chunks[1], 1)]
    card: dict[str, object] = {"Front": "Quel organite contient l'ADN ?", "Back": "Le noyau, siège de l'information génétique."}
    stamp_scope_provenance([card], parts)

    resolved = CoverageAlignmentService.resolve_finest_chunk_for_card(
        card_text="Quel organite contient l'ADN ? Le noyau, siège de l'information génétique.",
        doc_id=doc.id,
        source_blocks=scope_provenance(parts),
    )
    assert resolved is not None
    note = NoteModel.create(
        guid=uuid.uuid4().hex,
        note_type=nt,
        tags=json.dumps(
            build_document_tags(
                doc_id=doc.id,
                doc_title=doc.title,
                page_number=resolved.page_number,
                section_name=resolved.heading_path,
                chunk_id=resolved.id,
            )
        ),
    )

    report = CoverageAlignmentService.sync_coverage_from_tags(doc_id=doc.id)

    assert report["matched_notes"] == 1
    assert report["newly_linked"] == 1
    assert report["unlinked_notes"] == 0
    link = NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note)
    assert link is not None
    assert link.chunk_id == resolved.id
    assert "information génétique" in (link.chunk.content or "")


def test_sync_reports_unlinked_notes_instead_of_dropping_them_silently(caplog: pytest.LogCaptureFixture) -> None:
    """Aucune note non rattachée n'est ignorée en silence : elle est comptée et journalisée."""
    uid = uuid.uuid4().hex[:6]
    doc, _chunks = _document_with_three_chunks(uid)
    nt = NoteTypeModel.create(name=f"NT Orpheline {uid}", fields_schema='["Front", "Back"]', templates="[]")
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt, tags=json.dumps(build_document_tags(doc_id=doc.id, doc_title=doc.title)))

    with caplog.at_level(logging.WARNING, logger="ankiforge.services.audit.coverage_alignment_service"):
        report = CoverageAlignmentService.sync_coverage_from_tags(doc_id=doc.id)

    assert report["unlinked_notes"] == 1
    assert NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == note).count() == 0
    assert any("non rattaché" in record.getMessage() for record in caplog.records)


def test_stale_document_raises_an_alert_instead_of_a_silent_zero(caplog: pytest.LogCaptureFixture) -> None:
    """Un document stale remonte une alerte explicite plutôt qu'un rapport vide muet."""
    uid = uuid.uuid4().hex[:6]
    doc, chunks = _document_with_three_chunks(uid)
    doc.chunk_strategy_version = 0
    doc.save()
    nt = NoteTypeModel.create(name=f"NT Stale {uid}", fields_schema='["Front", "Back"]', templates="[]")
    note = NoteModel.create(
        guid=uuid.uuid4().hex,
        note_type=nt,
        tags=json.dumps(build_document_tags(doc_id=doc.id, doc_title=doc.title, chunk_id=chunks[0].id)),
    )

    with caplog.at_level(logging.WARNING, logger="ankiforge.services.audit.coverage_alignment_service"):
        report = CoverageAlignmentService.sync_coverage_from_tags(doc_id=doc.id)

    assert report["stale_documents"] == [doc.id]
    assert report["newly_linked"] == 0
    assert NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == note).count() == 0
    assert any("stale" in record.getMessage().lower() for record in caplog.records)
