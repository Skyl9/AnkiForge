"""
Unit tests for DocumentRepository.
"""

from __future__ import annotations

import json

import pytest

from ankiforge.database.models import DocumentModel, NoteModel, NoteTypeModel
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.services.markdown.structurer import MarkdownStructurer

pytestmark = pytest.mark.integration


def test_document_repository_crud() -> None:
    repo = DocumentRepository()

    # Folders
    folder = repo.create_folder("Computer Science")
    assert repo.get_folder_by_id(folder.id) is not None
    assert repo.get_folder_by_name("Computer Science") is not None
    assert len(repo.get_all_folders()) == 1

    # Documents
    doc = repo.create_document(
        title="Algorithms 101",
        content="Lecture on sorting algorithms...",
        file_type="pdf",
        folder=folder,
    )
    assert doc is not None
    assert repo.get_document_by_id(doc.id) is not None
    assert repo.get_document_by_title("Algorithms 101") is not None
    assert len(repo.get_all_documents(folder_id=folder.id)) == 1

    # Chunks
    chunks_data = [
        {"chunk_index": 1, "content": "Bubble sort...", "content_hash": "h1", "page_number": 1},
        {"chunk_index": 2, "content": "Quick sort...", "content_hash": "h2", "page_number": 2},
    ]
    created_chunks = repo.create_chunks(doc, chunks_data)
    assert len(created_chunks) == 2

    # Note-Chunk Link & Coverage stats
    nt = NoteTypeModel.create(name="Basic", fields_schema="[]")
    note = NoteModel.create(note_type=nt)
    link = repo.link_note_to_chunk(note, created_chunks[0])
    assert link is not None

    stats = repo.get_coverage_stats(doc.id)
    assert stats["total_chunks"] == 2
    assert stats["covered_chunks"] == 1
    assert stats["coverage_pct"] == 50.0

    # Delete Document
    deleted = repo.delete_document(doc.id)
    assert deleted is True
    assert repo.get_document_by_id(doc.id) is None
    assert len(repo.get_chunks_for_document(doc.id)) == 0


def test_ensure_folder_hierarchy_creates_parents_and_leaf() -> None:
    repo = DocumentRepository()
    leaf = repo.ensure_folder_hierarchy("Faculté::Semestre 1::Biologie")

    assert leaf is not None
    assert leaf.name == "Faculté::Semestre 1::Biologie"

    # Vérifie que les niveaux parents ont bien été créés en base
    assert repo.get_folder_by_name("Faculté") is not None
    assert repo.get_folder_by_name("Faculté::Semestre 1") is not None
    assert repo.get_folder_by_name("Faculté::Semestre 1::Biologie") is not None

    # Idempotence : un second appel retourne le même dossier sans doublon
    leaf2 = repo.ensure_folder_hierarchy("Faculté::Semestre 1::Biologie")
    assert leaf2.id == leaf.id


def test_heal_folder_hierarchies_creates_missing_parents() -> None:
    from ankiforge.database.models import FolderModel

    repo = DocumentRepository()
    # Création directe d'un dossier sans ses parents
    FolderModel.create(name="Sciences::Physique::Thermodynamique")

    assert repo.get_folder_by_name("Sciences") is None
    assert repo.get_folder_by_name("Sciences::Physique") is None

    healed_count = repo.heal_folder_hierarchies()
    assert healed_count == 2
    assert repo.get_folder_by_name("Sciences") is not None
    assert repo.get_folder_by_name("Sciences::Physique") is not None

    # Deuxième passage idempotent
    assert repo.heal_folder_hierarchies() == 0


def test_rename_folder_cascades_to_children() -> None:
    repo = DocumentRepository()
    repo.ensure_folder_hierarchy("Fac::L1::Maths")
    repo.ensure_folder_hierarchy("Fac::L1::Physique")
    root_fac = repo.get_folder_by_name("Fac")
    assert root_fac is not None

    renamed_root = repo.rename_folder(root_fac.id, "Université")
    assert renamed_root.name == "Université"

    assert repo.get_folder_by_name("Fac") is None
    assert repo.get_folder_by_name("Fac::L1") is None
    assert repo.get_folder_by_name("Fac::L1::Maths") is None

    assert repo.get_folder_by_name("Université") is not None
    assert repo.get_folder_by_name("Université::L1") is not None
    assert repo.get_folder_by_name("Université::L1::Maths") is not None
    assert repo.get_folder_by_name("Université::L1::Physique") is not None


def _document_with_numbered_sections(title: str, sections: list[str]) -> int:
    """Crée un cours Markdown dont chaque section porte un fragment distinct."""
    repo = DocumentRepository()
    doc = repo.create_document(title=title, content="\n\n".join(f"# {name}\nContenu de {name}." for name in sections), file_type="md")
    repo.create_chunks(
        doc,
        [{"chunk_index": index, "heading_path": name, "content": f"Contenu de {name}.", "content_hash": f"h{index}"} for index, name in enumerate(sections)],
    )
    return doc.id


def _stored_exclusions(doc_id: int) -> list[str]:
    return DocumentRepository().get_excluded_headings(DocumentModel.get_by_id(doc_id))


def test_excluding_a_section_removes_it_from_the_gaps_and_the_coverage_ratio() -> None:
    """Exclure une section la sort des lacunes à combler et du dénominateur de couverture."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours exclusions 1", ["Préface", "Partie 1", "Corrigés"])

    before = repo.get_coverage_stats(doc_id)
    assert before["total_units"] == 3
    assert before["coverage_pct"] == 0.0
    assert before["orphan_units"] == ["Préface", "Partie 1", "Corrigés"]

    assert repo.set_section_excluded(doc_id, "Corrigés", True) is True

    after = repo.get_coverage_stats(doc_id)
    assert after["total_units"] == 2
    assert after["excluded_units"] == 1
    assert "Corrigés" not in after["orphan_units"]


def test_reincluding_a_section_puts_its_gap_back() -> None:
    """Ré-inclure une section réintègre sa lacune et rétablit le ratio de couverture."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours exclusions 2", ["Préface", "Partie 1"])
    repo.set_section_excluded(doc_id, "Préface", True)
    assert repo.get_coverage_stats(doc_id)["total_units"] == 1

    assert repo.set_section_excluded(doc_id, "Préface", False) is True

    restored = repo.get_coverage_stats(doc_id)
    assert restored["total_units"] == 2
    assert restored["excluded_units"] == 0
    assert "Préface" in restored["orphan_units"]


def test_excluding_a_section_preserves_the_persisted_page_holes() -> None:
    """Une exclusion de section ne doit pas effacer les trous de pages de la délimitation."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours exclusions 3", ["Partie 1", "Annexes"])
    doc = DocumentModel.get_by_id(doc_id)
    doc.excluded_headings = json.dumps(["page:2"], ensure_ascii=False)
    doc.save()

    repo.set_section_excluded(doc_id, "Annexes", True)
    assert _stored_exclusions(doc_id) == ["Annexes", "page:2"]

    repo.set_section_excluded(doc_id, "Annexes", False)
    assert _stored_exclusions(doc_id) == ["page:2"]


def test_reincluding_a_section_clears_the_broader_entries_that_still_cover_it() -> None:
    """Une entrée plus large laissée persistée ne doit pas figer le bouton sur « Ré-inclure »."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours exclusions 7", ["Annexe A", "Partie 1"])
    doc = DocumentModel.get_by_id(doc_id)
    doc.excluded_headings = json.dumps(["annexe"], ensure_ascii=False)
    doc.save()

    assert repo.set_section_excluded(doc_id, "Annexe A", False) is True

    assert repo.is_section_excluded(DocumentModel.get_by_id(doc_id), "Annexe A") is False
    assert _stored_exclusions(doc_id) == []


def test_excluding_a_section_stays_visible_to_the_delimitation_consumers() -> None:
    """L'exclusion doit rester effective là où le chemin de titre est nettoyé avant comparaison."""
    repo = DocumentRepository()
    raw_path = '<span id="p12">Partie **1**</span> > <a href="#x">Cas limites</a>'
    doc_id = _document_with_numbered_sections("Cours exclusions 8", [raw_path, "Annexes"])

    assert repo.set_section_excluded(doc_id, raw_path, True) is True

    doc = DocumentModel.get_by_id(doc_id)
    cleaned = MarkdownStructurer.clean_heading_title(raw_path)
    assert cleaned != raw_path
    assert repo.is_section_excluded(doc, cleaned) is True
    assert repo.is_section_excluded(doc, "Annexes") is False


def test_coverage_stats_counts_the_sections_actually_removed_from_the_scope() -> None:
    """`excluded_units` compte les sections sorties du périmètre, pas les entrées brutes.

    Quatre entrées persistées ici, dont deux ne recoupent aucun fragment et une qui en
    recouvre trois : compter les entrées donnerait 4 au lieu de 3.
    """
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours exclusions 9", ["Partie 1", "Partie 1 > A", "Partie 1 > B", "Annexes"])
    doc = DocumentModel.get_by_id(doc_id)
    doc.excluded_headings = json.dumps(["partie 1", "page:2", "entrée orpheline", "autre annexe"], ensure_ascii=False)
    doc.save()

    stats = repo.get_coverage_stats(doc_id)
    assert stats["total_units"] == 1
    assert stats["excluded_units"] == 3


def test_exclusion_matching_ignores_case_and_follows_the_heading_path() -> None:
    """Le prédicat d'exclusion est insensible à la casse et suit le fil d'Ariane complet."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours exclusions 4", ["Remerciements", "Partie 1"])

    repo.set_section_excluded(doc_id, "Remerciements", True)
    doc = DocumentModel.get_by_id(doc_id)
    assert repo.is_section_excluded(doc, "REMERCIEMENTS") is True
    assert repo.is_section_excluded(doc, "Cours > Remerciements") is True
    assert repo.is_section_excluded(doc, "Partie 1") is False

    repo.set_section_excluded(doc_id, "Remerciements", False)
    assert repo.is_section_excluded(DocumentModel.get_by_id(doc_id), "Remerciements") is False
    assert repo.get_coverage_stats(doc_id)["excluded_units"] == 0


def test_set_section_excluded_rejects_blank_heading_and_unknown_document() -> None:
    """Une exclusion sans titre exploitable, ou sur un document absent, ne touche à rien."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours exclusions 5", ["Partie 1"])

    assert repo.set_section_excluded(doc_id, "   ", True) is False
    assert repo.set_section_excluded(-1, "Partie 1", True) is False

    assert _stored_exclusions(doc_id) == []


def test_set_section_excluded_rejects_a_generic_page_label() -> None:
    """Un libellé « Page N » auto-généré ne désigne pas une section : l'écrire exclurait la page entière."""
    repo = DocumentRepository()
    doc_id = _document_with_numbered_sections("Cours exclusions 6", ["Partie 1"])

    assert repo.is_excludable_heading("Partie 1") is True
    assert repo.is_excludable_heading("Page 12") is False
    assert repo.is_excludable_heading(None) is False

    assert repo.set_section_excluded(doc_id, "Page 12", True) is False
    assert _stored_exclusions(doc_id) == []


def test_ingestion_persists_the_structural_container_flag() -> None:
    """Le drapeau calculé au découpage doit atteindre la base, sur les deux chemins d'écriture.

    Sans cela, la colonne reste à zéro pour tout document nouvellement indexé : la
    couverture compterait comme unité à couvrir un titre qui n'est qu'un nœud
    d'organisation, et l'affinement lui logerait une carte pour solde un trou fictif.
    """
    repo = DocumentRepository()
    markdown = "\n\n".join(["# Cours", "## 2 Structures", "### 2.1 La Membrane", "### 2.2 Le Noyau"])

    doc = repo.save_imported_document(title="Cours drapeaux 1", content=markdown, file_type="md")
    stored = {chunk.heading_path: chunk.is_structural_container for chunk in repo.get_chunks_for_document(doc.id)}
    assert stored["Cours > 2 Structures"] is True
    assert stored["Cours > 2 Structures > 2.1 La Membrane"] is False

    chunks_data = [
        {"chunk_index": 0, "heading_path": "Thème > Section", "content": "Six mots ici.", "content_hash": "f1", "is_structural_container": True},
        {"chunk_index": 1, "heading_path": "Thème > Section > 2.1 La Membrane", "content": "La membrane délimite la cellule.", "content_hash": "f2", "is_structural_container": False},
    ]
    created = repo.create_chunks(DocumentModel.create(title="Cours drapeaux 2", file_type="md"), chunks_data)
    assert [chunk.is_structural_container for chunk in created] == [True, False]
