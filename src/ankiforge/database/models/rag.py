# ruff: noqa: E501
import datetime
import logging

from peewee import (
    BooleanField,
    CharField,
    DateTimeField,
    ForeignKeyField,
    IntegerField,
    TextField,
)

from ankiforge.database.base import BaseModel
from ankiforge.database.models.cards import MediaModel, NoteModel

logger = logging.getLogger(__name__)


class FolderModel(BaseModel):
    """Stocke les dossiers de la bibliothèque de documents."""

    name = CharField(unique=True)


class DocumentModel(BaseModel):
    """Stocke les cours après extraction par Marker et leur lien vers la BDD Vectorielle."""

    title = CharField(unique=True)
    content = TextField(default="")
    chroma_collection_name = CharField(null=True)  # Nom de la collection ChromaDB pour le RAG
    created_at = DateTimeField(default=datetime.datetime.now)
    folder = ForeignKeyField(FolderModel, backref="documents", null=True, on_delete="CASCADE")
    original_media = ForeignKeyField(MediaModel, backref="parsed_documents", null=True, on_delete="SET NULL")
    file_type = CharField(default="md")  # pdf, md, png, youtube, web
    source_url = CharField(null=True)


class DocumentChunkModel(BaseModel):
    """
    Un morceau de texte (paragraphe, sous-section ou page) issu d'un DocumentModel.
    Permet le suivi fin de la couverture de cours et l'indexation RAG.
    """

    document = ForeignKeyField(DocumentModel, backref="chunks", on_delete="CASCADE")
    chunk_index = IntegerField(default=0)
    content = TextField(default="")
    content_hash = CharField(index=True, default="")
    page_number = IntegerField(null=True)
    heading_path = CharField(null=True)
    is_profiled = BooleanField(default=False, null=True)

    class Meta:
        table_name = "document_chunks"
        indexes = ((("document", "chunk_index"), False),)


class NoteChunkLinkModel(BaseModel):
    """
    Liaison de traçabilité entre une Note Anki (NoteModel) et son fragment source (DocumentChunkModel).
    Permet le calcul de complétion de cours et l'audit anti-hallucination.
    """

    note = ForeignKeyField(NoteModel, backref="chunk_links", on_delete="CASCADE")
    chunk = ForeignKeyField(DocumentChunkModel, backref="note_links", on_delete="CASCADE")
    is_hallucinating = BooleanField(default=False)

    class Meta:
        table_name = "note_chunk_links"
        indexes = ((("note", "chunk"), True),)
