"""
Unit tests for DocumentRepository.
"""

from __future__ import annotations

from ankiforge.database.models import NoteModel, NoteTypeModel
from ankiforge.repositories.document_repository import DocumentRepository


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
