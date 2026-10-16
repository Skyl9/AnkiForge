"""Migration 006 : bascule de l'index FAISS vers une collection ChromaDB sur documentmodel."""

import peewee as pw


def migrate(migrator, database, fake=False, **kwargs):
    """Ajoute chroma_collection_name et retire faiss_index_path de documentmodel."""
    migrator.add_fields("documentmodel", chroma_collection_name=pw.CharField(null=True, max_length=255))
    migrator.remove_fields("documentmodel", "faiss_index_path")


def rollback(migrator, database, fake=False, **kwargs):
    """Restaure faiss_index_path et retire chroma_collection_name de documentmodel."""
    migrator.add_fields("documentmodel", faiss_index_path=pw.CharField(null=True, max_length=255))
    migrator.remove_fields("documentmodel", "chroma_collection_name")
