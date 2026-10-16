"""Tests du rattachement des occlusions à leur source (ADR 0023).

La provenance d'une carte d'occlusion est **possédée par l'appelant** : une figure connaît son
fragment, donc le rattachement est résolu au palier ``exact`` et non déduit d'une section ou
d'une page. Ces tests verrouillent ce contrat, y compris le cas où le fragment n'appartient pas
au document — un mauvais rattachement silencieux est pire qu'une absence de rattachement.
"""

from __future__ import annotations

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
    RESOLUTION_EXACT,
    CoverageAlignmentService,
)
from ankiforge.utils.tags import parse_note_tags

pytestmark = pytest.mark.integration


def _make_note_type() -> NoteTypeModel:
    return NoteTypeModel.create(
        name=f"IOE {uuid.uuid4().hex[:6]}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]',
        css_style="",
    )


def _make_occlusion_note(nt: NoteTypeModel, tags: list[str] | None = None) -> NoteModel:
    """Une note d'occlusion telle que le service en crée : sans provenance."""
    note = NoteModel.create(
        guid=uuid.uuid4().hex,
        note_type=nt,
        tags=json.dumps(tags if tags is not None else ["image-occlusion"]),
    )
    note.add_version({"Front": "masque", "Back": "réponse"}, source="manual")
    return note


def test_attach_notes_writes_exact_link_and_canonical_provenance():
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Cours Anatomie {uid}",
        content="Le cœur est un organe musculaire.",
        file_type="pdf",
    )
    chunk = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Cardiologie > Le cœur",
        page_number=7,
        content="Le cœur est un organe musculaire creux.",
        content_hash=f"h_{uid}",
    )
    note = _make_occlusion_note(_make_note_type())

    attached = CoverageAlignmentService.attach_notes_to_source([note], doc_id=doc.id, source_chunk_id=chunk.id)

    assert attached == 1
    links = list(NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == note))
    assert len(links) == 1
    assert links[0].chunk_id == chunk.id
    assert links[0].resolution == RESOLUTION_EXACT

    tags = parse_note_tags(note.tags)
    assert f"doc:{doc.id}" in tags
    assert "page:7" in tags
    assert any(t.startswith("section:") for t in tags)
    assert "image-occlusion" in tags


def test_attach_notes_preserves_user_tags():
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Doc {uid}", content="Contenu.", file_type="md")
    chunk = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Partie A",
        content="Contenu de la partie A.",
        content_hash=f"h_{uid}",
    )
    note = _make_occlusion_note(_make_note_type(), tags=["image-occlusion", "urgent"])

    CoverageAlignmentService.attach_notes_to_source([note], doc_id=doc.id, source_chunk_id=chunk.id)

    tags = parse_note_tags(note.tags)
    assert "urgent" in tags
    assert "image-occlusion" in tags


def test_attach_notes_ignores_chunk_from_another_document():
    uid = uuid.uuid4().hex[:6]
    doc_a = DocumentModel.create(title=f"Doc A {uid}", content="A.", file_type="md")
    doc_b = DocumentModel.create(title=f"Doc B {uid}", content="B.", file_type="md")
    chunk_b = DocumentChunkModel.create(
        document=doc_b,
        chunk_index=0,
        heading_path="B",
        content="Contenu de B.",
        content_hash=f"hb_{uid}",
    )
    note = _make_occlusion_note(_make_note_type())

    attached = CoverageAlignmentService.attach_notes_to_source([note], doc_id=doc_a.id, source_chunk_id=chunk_b.id)

    assert attached == 0
    assert NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == note).count() == 0


def test_attach_notes_returns_zero_without_notes():
    doc = DocumentModel.create(title="Doc", content=".", file_type="md")
    chunk = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        content=".",
        content_hash="h_empty",
    )

    assert CoverageAlignmentService.attach_notes_to_source([], doc_id=doc.id, source_chunk_id=chunk.id) == 0
