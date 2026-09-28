"""
Tests unitaires pour la traçabilité par tags, la réconciliation déterministe
et le calcul coarse-grained de couverture documentaire (Pages & Sections).
Conforme aux Règles 2, 8, 19 et 20 de GEMINI.md.
"""

from __future__ import annotations

import json
import uuid

import pytest

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
from ankiforge.utils.tags import (
    build_document_tags,
    clean_source_slug,
    extract_tag_metadata,
    parse_note_tags,
    replace_provenance_tags,
)

pytestmark = pytest.mark.integration


def test_parse_note_tags() -> None:
    # 1. Format JSON
    assert parse_note_tags('["doc:12", "page:3"]') == ["doc:12", "page:3"]
    # 2. Format espace délimité (Anki standard)
    assert parse_note_tags("doc:12 page:3 general") == ["doc:12", "page:3", "general"]
    # 3. Format liste Python
    assert parse_note_tags(["tag1", " tag2 ", "tag1"]) == ["tag1", "tag2"]
    # 4. None ou chaîne vide
    assert parse_note_tags(None) == []
    assert parse_note_tags("") == []
    assert parse_note_tags("   ") == []


def test_clean_source_slug() -> None:
    assert clean_source_slug("Cours Anatomie Ch1.pdf") == "cours_anatomie_ch1"
    assert clean_source_slug("Biologie - Chapitre 3 (v2).md") == "biologie_chapitre_3_v2"
    assert clean_source_slug("Diapo_Presentation.pptx") == "diapo_presentation"
    assert clean_source_slug("   ") == "document"


def test_extract_tag_metadata() -> None:
    tags = ["ankiforge_generated", "doc:42", "source:neuroanatomie", "page:7", "section:cortex"]
    meta = extract_tag_metadata(tags)
    assert meta["doc_id"] == 42
    assert meta["source_slug"] == "neuroanatomie"
    assert meta["page_number"] == 7
    assert meta["section_slug"] == "cortex"

    # JSON input
    json_tags = json.dumps(["doc:99", "page:15"])
    meta_json = extract_tag_metadata(json_tags)
    assert meta_json["doc_id"] == 99
    assert meta_json["page_number"] == 15
    assert meta_json["source_slug"] is None


def test_build_document_tags() -> None:
    tags = build_document_tags(
        doc_id=10,
        doc_title="Cardiologie Clinique.pdf",
        page_number=4,
        section_name="Introduction",
        extra_tags=["examen_2026"],
    )
    assert "ankiforge_generated" in tags
    assert "doc:10" in tags
    assert "source:cardiologie_clinique" in tags
    assert "page:4" in tags
    assert "section:introduction" in tags
    assert "examen_2026" in tags


def test_replace_provenance_tags_rewrites_the_finest_section_and_chunk() -> None:
    """La réécriture de provenance remplace section:/chunk: sans toucher aux autres tags."""
    tags = json.dumps(build_document_tags(doc_id=10, doc_title="Cellulaire", page_number=4, section_name="Chapitre 2", chunk_id=11, extra_tags=["examen_2026"]))

    rewritten = replace_provenance_tags(tags, {"section": "chapitre_2_2_1_la_membrane", "chunk": 42})
    parsed = parse_note_tags(rewritten)

    assert "section:chapitre_2_2_1_la_membrane" in parsed
    assert "chunk:42" in parsed
    # L'ancien couple est complètement remplacé, jamais coexisté.
    assert "section:chapitre_2" not in parsed
    assert "chunk:11" not in parsed
    assert len([t for t in parsed if t.startswith("section:")]) == 1
    assert len([t for t in parsed if t.startswith("chunk:")]) == 1
    # Le reste de la traçabilité est préservé.
    assert "doc:10" in parsed
    assert "source:cellulaire" in parsed
    assert "page:4" in parsed
    assert "examen_2026" in parsed
    # Le format de sérialisation d'origine (JSON) est conservé.
    assert rewritten.startswith("[")


def test_replace_provenance_tags_is_partial_and_removable() -> None:
    """Chaque préfixe est traité indépendamment ; None retire le tag correspondant."""
    tags = json.dumps(build_document_tags(doc_id=10, section_name="Chapitre 2", chunk_id=11))

    only_section = parse_note_tags(replace_provenance_tags(tags, {"section": "noyau"}))
    assert "section:noyau" in only_section
    assert "chunk:11" in only_section

    only_chunk = parse_note_tags(replace_provenance_tags(tags, {"chunk": 12}))
    assert "chunk:12" in only_chunk
    assert "section:chapitre_2" in only_chunk

    without_section = parse_note_tags(replace_provenance_tags(tags, {"section": None}))
    assert not [t for t in without_section if t.startswith("section:")]
    assert "chunk:11" in without_section

    without_chunk = parse_note_tags(replace_provenance_tags(tags, {"chunk": None}))
    assert not [t for t in without_chunk if t.startswith("chunk:")]
    assert "section:chapitre_2" in without_chunk

    # Un préfixe inconnu est ignoré sans altérer les tags existants.
    assert parse_note_tags(replace_provenance_tags(tags, {"facet": "x"})) == parse_note_tags(tags)
    assert replace_provenance_tags(tags) == tags


def test_replace_provenance_tags_preserves_the_space_delimited_format() -> None:
    """Les tags sérialisés en espace (format Anki) ne basculent pas en JSON."""
    rewritten = replace_provenance_tags("ankiforge_generated doc:10 section:chapitre_2 chunk:11", {"section": "noyau", "chunk": 12})

    assert not rewritten.startswith("[")
    assert parse_note_tags(rewritten) == ["ankiforge_generated", "doc:10", "section:noyau", "chunk:12"]


def test_replace_provenance_tags_adds_missing_provenance() -> None:
    """Un tag absent est inséré, en fin de liste, sans dupliquer les autres."""
    rewritten = replace_provenance_tags(json.dumps(["manuel", "doc:10"]), {"section": "noyau", "chunk": 12})

    assert parse_note_tags(rewritten) == ["manuel", "doc:10", "section:noyau", "chunk:12"]


def test_replace_provenance_tags_handles_empty_input() -> None:
    assert parse_note_tags(replace_provenance_tags(None, {"section": "noyau"})) == ["section:noyau"]
    assert parse_note_tags(replace_provenance_tags("", {"section": "noyau"})) == ["section:noyau"]
    assert parse_note_tags(replace_provenance_tags("manuel")) == ["manuel"]


def test_sync_coverage_from_tags_paginated() -> None:
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Livre Anatomie {uid}",
        content="Anatomie complète",
        file_type="pdf",
        total_pages=5,
    )

    # Chunks préexistants pour les pages 1 et 2
    chunk_p1 = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        page_number=1,
        content="Page 1 content",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        page_number=2,
        content="Page 2 content",
    )

    deck = DeckModel.create(name=f"Deck Anat {uid}")
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(
        name=f"Model {uid}",
        fields_schema='["Front", "Back"]',
        templates="[]",
    )

    # Note avec tag page:1
    note1 = NoteModel.create(
        guid=uuid.uuid4().hex,
        note_type=nt,
        tags=json.dumps([f"doc:{doc.id}", "page:1"]),
    )
    CardModel.create(note=note1, deck=deck, template_index=0)

    # Note avec tag page:3 (chunk inexistant : ignore, aucun chunk factice créé)
    note2 = NoteModel.create(
        guid=uuid.uuid4().hex,
        note_type=nt,
        tags=json.dumps([f"doc:{doc.id}", "page:3"]),
    )
    CardModel.create(note=note2, deck=deck, template_index=0)

    # Synchronisation déterministe
    res = CoverageAlignmentService.sync_coverage_from_tags(doc_id=doc.id)
    assert res["matched_notes"] == 1
    assert res["newly_linked"] == 1

    # Aucun chunk factice pour la page 3 ne doit être créé
    assert DocumentChunkModel.select().where(DocumentChunkModel.document == doc).count() == 2

    # Vérification des liens NoteChunkLinkModel
    link1 = NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note1)
    assert link1 is not None
    assert link1.chunk_id == chunk_p1.id

    link2 = NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note2)
    assert link2 is None

    # Vérification du calcul coarse-grained
    doc_repo = DocumentRepository()
    stats = doc_repo.get_coverage_stats(doc.id)
    assert stats["unit_type"] == "pages"
    assert stats["total_units"] == 5
    assert stats["covered_units"] == 1  # Page 1 uniquement
    assert stats["coverage_pct"] == 20.0  # 1/5 = 20%
    assert 2 in stats["orphan_units"]
    assert 3 in stats["orphan_units"]
    assert 4 in stats["orphan_units"]
    assert 5 in stats["orphan_units"]


def test_sync_coverage_from_tags_continuous() -> None:
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(
        title=f"Polycopie Bio {uid}",
        content="# Intro\nTexte\n# Partie 1\nTexte",
        file_type="md",
    )

    c1 = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Intro",
        content="Introduction à la biologie",
    )
    DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path="Partie 1",
        content="Détail de la partie 1",
    )

    deck = DeckModel.create(name=f"Deck Bio {uid}")
    nt = NoteTypeModel.select().first() or NoteTypeModel.create(
        name=f"Model Bio {uid}",
        fields_schema='["Front", "Back"]',
        templates="[]",
    )

    # Note liée par source_slug et section:intro
    slug = clean_source_slug(doc.title)
    note = NoteModel.create(
        guid=uuid.uuid4().hex,
        note_type=nt,
        tags=f"source:{slug} section:intro",
    )
    CardModel.create(note=note, deck=deck, template_index=0)

    res = CoverageAlignmentService.sync_coverage_from_tags(doc_id=doc.id)
    assert res["matched_notes"] == 1

    link = NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note)
    assert link is not None
    assert link.chunk_id == c1.id

    # Vérification des stats
    stats = DocumentRepository().get_coverage_stats(doc.id)
    assert stats["unit_type"] == "sections"
    assert stats["total_units"] == 2
    assert stats["covered_units"] == 1
    assert stats["coverage_pct"] == 50.0


def test_build_and_parse_chunk_tag():
    """Le tag chunk:<id> est généré puis ré-extrai par extract_tag_metadata."""
    tags = build_document_tags(doc_id=7, section_name="Noyau > Ribosomes", chunk_id=123, extra_tags=["forge"])
    assert "chunk:123" in tags
    assert "section:noyau_ribosomes" in tags

    meta = extract_tag_metadata(tags)
    assert meta["chunk_id"] == 123
    assert meta["doc_id"] == 7
    assert meta["section_slug"] == "noyau_ribosomes"

    # chunk_id ignoré si invalide (négatif / non numérique)
    assert extract_tag_metadata(["chunk:-5"])["chunk_id"] is None
    assert extract_tag_metadata(["chunk:abc"])["chunk_id"] is None

    # chunk_id absent par défaut
    assert extract_tag_metadata([f"doc:{9}"])["chunk_id"] is None


def test_extract_tag_metadata_chunk_priority_order() -> None:
    """chunk_id est bien exposé à côté de page et section pour une résolution hiérarchique."""
    meta = extract_tag_metadata(["doc:5", "chunk:88", "page:3", "section:foo"])
    assert meta["chunk_id"] == 88
    assert meta["page_number"] == 3
    assert meta["section_slug"] == "foo"
    assert meta["doc_id"] == 5


def test_sync_coverage_from_tags_chunk_tag_takes_precedence() -> None:
    """Avec chunk:<id>, la synchro lie directement le fragment sans ambiguïté."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours Priorité {uid}", file_type="md")
    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Partie 1",
        content="Contenu partie 1",
    )
    c2 = DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path="Partie 1 > Sous-sujet",
        content="Contenu sous-sujet",
    )

    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Model {uid}")
    deck = DeckModel.create(name=f"Deck {uid}")
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt, tags=json.dumps([f"doc:{doc.id}", f"chunk:{c2.id}"]))
    CardModel.create(note=note, deck=deck, template_index=0)

    res = CoverageAlignmentService.sync_coverage_from_tags(doc_id=doc.id)
    assert res["matched_notes"] == 1

    link = NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note)
    assert link is not None
    assert link.chunk_id == c2.id


def test_sync_coverage_from_tags_defers_stale_document() -> None:
    """Un document stale (ancienne stratégie de structuration) n'est pas synchronisé."""
    uid = uuid.uuid4().hex[:6]
    doc = DocumentModel.create(title=f"Cours Stale {uid}", content="Contenu", file_type="md")
    doc.chunk_strategy_version = 0  # stratégie v1 (pré-033)
    doc.save()

    DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Partie 1",
        content="Contenu partie 1",
    )

    nt = NoteTypeModel.select().first() or NoteTypeModel.create(name=f"Model Stale {uid}")
    deck = DeckModel.create(name=f"Deck Stale {uid}")
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt, tags=json.dumps([f"doc:{doc.id}", "section:partie_1"]))
    CardModel.create(note=note, deck=deck, template_index=0)

    res = CoverageAlignmentService.sync_coverage_from_tags(doc_id=doc.id)

    # Le rapport est vide : la synchronisation est différée après re-indexation
    assert res["matched_notes"] == 0
    assert NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note) is None

    # Après re-indexation (marquage version courante), la synchro fonctionne
    doc.chunk_strategy_version = ChunkingService.CHUNKING_VERSION
    doc.save()
    res2 = CoverageAlignmentService.sync_coverage_from_tags(doc_id=doc.id)
    assert res2["matched_notes"] == 1
    assert NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note) is not None
