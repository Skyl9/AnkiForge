"""
Unit tests for DocumentRepository.
"""

from __future__ import annotations

import pytest

from ankiforge.database.models import NoteModel, NoteTypeModel
from ankiforge.repositories.document_repository import DocumentRepository

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
