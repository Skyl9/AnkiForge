"""Tests d'intégration et unitaires pour le réalignement déterministe de couverture post-import .colpkg.

Conforme aux critères d'acceptation du ticket RAG - Réalignement Déterministe de Couverture Post-Import Colpkg
et à l'ADR 0009 / ADR 0036.
"""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

import pytest

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    NoteChunkLinkModel,
    NoteModel,
)
from ankiforge.services.audit.coverage_alignment_service import (
    RESOLUTION_LEXICAL,
    RESOLUTION_PAGE,
    RESOLUTION_SECTION,
    CoverageAlignmentService,
)
from ankiforge.services.cards.import_manager import ImportManager
from ankiforge.utils.tags import clean_source_slug, section_key


def _create_colpkg_file(
    file_path: Path,
    notes_data: list[dict[str, Any]],
    model_name: str = "Basic",
    deck_name: str = "Paquet Test",
) -> Path:
    """Génère une archive .colpkg minimale valide pour tester le flux de remplacement."""
    db_file = file_path.parent / f"{file_path.stem}_internal.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    models_json = {
        "101": {
            "name": model_name,
            "flds": [{"name": "Front"}, {"name": "Back"}],
            "tmpls": [{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}],
            "css": "",
        }
    }
    decks_json = {"1": {"id": 1, "name": deck_name}}
    cursor.execute("CREATE TABLE col (id integer, models text, decks text)")
    cursor.execute("INSERT INTO col VALUES (1, ?, ?)", (json.dumps(models_json), json.dumps(decks_json)))

    cursor.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, tags text, flds text)")
    cursor.execute("CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer, ivl integer, reps integer, lapses integer, flags integer, queue integer)")

    for i, n in enumerate(notes_data, start=1):
        nid = n.get("id", i)
        guid = n.get("guid", f"guid_{nid}")
        tags_str = " ".join(n.get("tags", []))
        front = n.get("front", f"Question {nid}")
        back = n.get("back", f"Reponse {nid}")
        flds = f"{front}\x1f{back}"
        cursor.execute("INSERT INTO notes VALUES (?, ?, 101, ?, ?)", (nid, guid, tags_str, flds))
        cursor.execute("INSERT INTO cards VALUES (?, ?, 1, 0, 0, 0, 0, 0, 0)", (nid, nid))

    conn.commit()
    conn.close()

    with zipfile.ZipFile(file_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", "{}")

    if db_file.exists():
        db_file.unlink()

    return file_path


def test_rag_reexport_coverage_alignment_service() -> None:
    """Vérifie que CoverageAlignmentService est accessible depuis ankiforge.services.rag.coverage_alignment_service."""
    from ankiforge.services.rag.coverage_alignment_service import (
        CoverageAlignmentService as RagCoverageAlignmentService,
    )

    assert RagCoverageAlignmentService is CoverageAlignmentService


def test_realign_profile_coverage_method_exists_and_returns_report() -> None:
    """Vérifie la présence et le contrat de la méthode CoverageAlignmentService.realign_profile_coverage()."""
    report = CoverageAlignmentService.realign_profile_coverage()
    assert isinstance(report, dict)
    assert "matched_notes" in report
    assert "resolution_breakdown" in report

    # Vérifie que la méthode peut également être invoquée sur une instance (ADR 0036 ligne 152)
    inst_report = CoverageAlignmentService().realign_profile_coverage()
    assert isinstance(inst_report, dict)
    assert "matched_notes" in inst_report


def test_colpkg_replacement_realigns_coverage_deterministically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie que l'import d'un .colpkg réaligne la couverture et restaure la traçabilité des cartes.

    Critères validés :
    1. Réalignement global déclenché en fin de _commit_colpkg_replacement.
    2. Cartes entrantes rattachées aux fragments correspondants.
    3. Palier de résolution renseigné (section, page, lexical).
    4. Cartes sans tag de provenance laissées hors couverture sans erreur.
    """
    monkeypatch.setattr(
        "ankiforge.services.cards.import_manager.backup_before_colpkg_import",
        lambda: tmp_path / "mock_backup.db",
    )

    # 1. Mise en place du document dans le Studio préservé
    doc = DocumentModel.create(
        title="Cours de Neurologie",
        content="Document complet sur le système nerveux.",
        file_type="md",
    )
    chunk1 = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        heading_path="Chapitre 1 > Neurotransmetteurs",
        page_number=1,
        content="L'acétylcholine et le glutamate sont des neurotransmetteurs majeurs excitateurs.",
    )
    chunk2 = DocumentChunkModel.create(
        document=doc,
        chunk_index=1,
        heading_path="Chapitre 2 > Synapses Chimiques",
        page_number=2,
        content="La fente synaptique accueille la libération vésiculaire des médiateurs chimiques.",
    )
    chunk3 = DocumentChunkModel.create(
        document=doc,
        chunk_index=2,
        heading_path="Chapitre 3 > Plasticité Synaptique",
        page_number=3,
        content="La potentialisation à long terme implique les récepteurs NMDA et AMPA membranaires.",
    )

    # 2. Préparation du .colpkg entrant avec différentes variantes de tags
    sec1_key = section_key("Chapitre 1 > Neurotransmetteurs")
    sec2_key = section_key("Chapitre 2 > Synapses Chimiques")
    doc_slug = clean_source_slug(doc.title)

    notes_incoming = [
        # Carte 1 : tag doc + section -> doit résoudre en RESOLUTION_SECTION sur chunk 1
        {
            "id": 1001,
            "guid": "guid_colpkg_sec",
            "front": "Quel est le rôle de l'acétylcholine ?",
            "back": "Neurotransmetteur excitateur majeur.",
            "tags": [f"doc:{doc.id}", f"section:{sec1_key}"],
        },
        # Carte 2 : tag doc + page -> doit résoudre en RESOLUTION_PAGE sur chunk 2
        {
            "id": 1002,
            "guid": "guid_colpkg_page",
            "front": "Que trouve-t-on dans la fente synaptique ?",
            "back": "Des médiateurs chimiques libérés par vésicules.",
            "tags": [f"doc:{doc.id}", "page:2"],
        },
        # Carte 3 : tag doc seul + texte distinctif -> doit résoudre en RESOLUTION_LEXICAL sur chunk 3
        {
            "id": 1003,
            "guid": "guid_colpkg_lexical",
            "front": "Quels récepteurs interviennent dans la potentialisation à long terme ?",
            "back": "Les récepteurs NMDA et AMPA membranaires.",
            "tags": [f"doc:{doc.id}"],
        },
        # Carte 4 : tag source_slug + section -> doit résoudre en RESOLUTION_SECTION sur chunk 2
        {
            "id": 1004,
            "guid": "guid_colpkg_source_slug",
            "front": "Comment fonctionne la synapse chimique ?",
            "back": "Libération vésiculaire dans la fente.",
            "tags": [f"source:{doc_slug}", f"section:{sec2_key}"],
        },
        # Carte 5 : carte générale sans aucun tag de provenance -> hors couverture sans erreur
        {
            "id": 1005,
            "guid": "guid_colpkg_no_prov",
            "front": "What is the capital of France?",
            "back": "Paris.",
            "tags": ["anglais", "géographie"],
        },
        # Carte 6 : carte avec doc:ID mais texte vide / sans match possible -> hors couverture sans erreur
        {
            "id": 1006,
            "guid": "guid_colpkg_doc_unmatched",
            "front": "???",
            "back": "---",
            "tags": [f"doc:{doc.id}"],
        },
        # Carte 7 : tag section seule (sans doc: ni source:), résoluble sur chunk 1
        {
            "id": 1007,
            "guid": "guid_colpkg_section_only",
            "front": "Action sur les récepteurs nicotiniques ?",
            "back": "Activation rapide par l'acétylcholine.",
            "tags": [f"section:{sec1_key}"],
        },
    ]

    colpkg_path = tmp_path / "test_coverage_realignment.colpkg"
    _create_colpkg_file(colpkg_path, notes_incoming)

    # 3. Exécution du remplacement de collection
    manager = ImportManager()
    analysis = manager.analyze_archive(colpkg_path)
    assert analysis.source_type == "colpkg"

    commit_res = manager.commit_import(analysis)
    assert commit_res["created"] == 7

    # 4. Vérification des liens de couverture rétablis
    note1 = NoteModel.get(NoteModel.guid == "guid_colpkg_sec")
    link1 = NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note1)
    assert link1 is not None, "Carte 1 (section) doit être rattachée à un chunk"
    assert link1.chunk_id == chunk1.id
    assert link1.resolution == RESOLUTION_SECTION

    note2 = NoteModel.get(NoteModel.guid == "guid_colpkg_page")
    link2 = NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note2)
    assert link2 is not None, "Carte 2 (page) doit être rattachée à un chunk"
    assert link2.chunk_id == chunk2.id
    assert link2.resolution == RESOLUTION_PAGE

    note3 = NoteModel.get(NoteModel.guid == "guid_colpkg_lexical")
    link3 = NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note3)
    assert link3 is not None, "Carte 3 (lexical) doit être rattachée à un chunk"
    assert link3.chunk_id == chunk3.id
    assert link3.resolution == RESOLUTION_LEXICAL

    note4 = NoteModel.get(NoteModel.guid == "guid_colpkg_source_slug")
    link4 = NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note4)
    assert link4 is not None, "Carte 4 (source slug + section) doit être rattachée"
    assert link4.chunk_id == chunk2.id
    assert link4.resolution == RESOLUTION_SECTION

    note5 = NoteModel.get(NoteModel.guid == "guid_colpkg_no_prov")
    link5 = NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note5)
    assert link5 is None, "Carte 5 sans tags de provenance doit rester hors couverture"

    note6 = NoteModel.get(NoteModel.guid == "guid_colpkg_doc_unmatched")
    link6 = NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note6)
    assert link6 is None, "Carte 6 sans correspondance doit rester hors couverture"

    note7 = NoteModel.get(NoteModel.guid == "guid_colpkg_section_only")
    link7 = NoteChunkLinkModel.get_or_none(NoteChunkLinkModel.note == note7)
    assert link7 is not None, "Carte 7 (section seule) doit être rattachée"
    assert link7.chunk_id == chunk1.id
    assert link7.resolution == RESOLUTION_SECTION
