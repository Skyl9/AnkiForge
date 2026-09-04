import datetime
import logging
from typing import Any

from peewee import (
    BooleanField,
    CharField,
    DateTimeField,
    FloatField,
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
    file_type = CharField(default="md")  # pdf, md, png, youtube, web, album, epub, audio
    source_url = CharField(null=True)
    total_pages = IntegerField(default=1)


class DocumentPageModel(BaseModel):
    """Représente une page individuelle au sein d'un Document de type Album/Livre scanné."""

    document_id: Any
    media_id: Any

    document = ForeignKeyField(DocumentModel, backref="pages", on_delete="CASCADE")
    media = ForeignKeyField(MediaModel, backref="album_pages", on_delete="CASCADE")
    page_number = IntegerField(default=1)
    rotation = IntegerField(default=0)  # 0, 90, 180, 270 degrés
    crop_data = CharField(null=True)  # JSON [x, y, w, h] si recadrée
    ocr_text = TextField(default="")
    bounding_boxes = TextField(null=True)  # JSON list des figures détectées
    status = CharField(default="ready")  # pending, ocr_running, ready

    class Meta:
        table_name = "document_pages"
        indexes = ((("document", "page_number"), True),)


class DocumentChunkModel(BaseModel):
    """
    Un morceau de texte (paragraphe, sous-section ou page) issu d'un DocumentModel.
    Permet le suivi fin de la couverture de cours et l'indexation RAG.
    """

    document_id: Any
    media_id: Any

    document = ForeignKeyField(DocumentModel, backref="chunks", on_delete="CASCADE")
    chunk_index = IntegerField(default=0)
    content = TextField(default="")
    content_hash = CharField(index=True, default="")
    page_number = IntegerField(null=True)
    heading_path = CharField(null=True)
    is_profiled = BooleanField(default=False, null=True)
    start_time = FloatField(null=True)
    end_time = FloatField(null=True)
    media = ForeignKeyField(MediaModel, backref="chunks", null=True, on_delete="SET NULL")
    bounding_box = CharField(null=True)

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


class EmbeddingCacheModel(BaseModel):
    """
    Cache persistant d'embeddings vectoriels (dense vectors).
    Associe le hash SHA256 du texte et le model_id au vecteur sérialisé (JSON list de floats).
    Permet une ré-indexation RAG instantanée à coût 0 et calcul 0.
    """

    text_hash = CharField(max_length=64, index=True)
    model_id = CharField(max_length=128, default="text-embedding-3-small", index=True)
    dimensions = IntegerField(default=1536)
    embedding_json = TextField(default="[]")
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "embedding_cache"
        indexes = ((("text_hash", "model_id"), True),)
