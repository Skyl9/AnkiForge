"""
Tests unitaires pour CoverageAlignmentService et la résolution bidirectionnelle des médias.
"""

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


def test_clean_text_and_extract_keywords():
    raw_html = "<p>Qu'est-ce que la <b>cyber sécurité</b> en réseau ? &nbsp; \\( \\alpha \\)</p>"
    cleaned = CoverageAlignmentService.clean_text_for_matching(raw_html)
    assert "<p>" not in cleaned
    assert "<b>" not in cleaned
    assert "&nbsp;" not in cleaned
    assert "cyber" in cleaned
    assert "sécurité" in cleaned

    kws = CoverageAlignmentService.extract_keywords(raw_html, min_len=4)
    assert "cyber" in kws
    assert "sécurité" in kws
    # Les stopwords comme "dans", "avec" ne doivent pas y être
    assert "dans" not in kws


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

    # Note 1 : correspond à chunk 1
    note1 = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt)
    note1.add_version({"Front": "Quel est le rôle du protocole TCP ?", "Back": "Fiabilité du transfert de paquets."}, source="manual")
    CardModel.create(note=note1, deck=deck, template_index=0)

    # Note 2 : correspond à chunk 2
    note2 = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt)
    note2.add_version({"Front": "Comment fonctionne RSA ?", "Back": "Chiffrement asymétrique avec paire de clés publique et privée."}, source="manual")
    CardModel.create(note=note2, deck=deck, template_index=0)

    # Note 3 : hors sujet (médecine)
    note3 = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt)
    note3.add_version({"Front": "Qu'est ce que l'hypertension artérielle ?", "Back": "Élévation anormale de la pression sanguine."}, source="manual")
    CardModel.create(note=note3, deck=deck, template_index=0)

    # Exécution de l'alignement
    stats = CoverageAlignmentService.align_document(doc.id, min_overlap=2)
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
    note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt)
    note.add_version({"Front": "Principe de l'algorithme de Dijkstra ?", "Back": "Calcul du plus court chemin sur un graphe pondéré positif."}, source="manual")

    matched_chunk = CoverageAlignmentService.find_matching_chunk_for_note(note.id, min_overlap=2)
    assert matched_chunk is not None
    assert matched_chunk.id == chunk.id


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
