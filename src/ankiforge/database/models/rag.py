import datetime
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
from ankiforge.services.parsing.chunking_service import ChunkingService


class FolderModel(BaseModel):
    """Stocke les dossiers de la bibliothèque de documents."""

    name = CharField(unique=True)


class DocumentModel(BaseModel):
    """Stocke les cours après extraction par Marker et leur lien vers la BDD Vectorielle."""

    title = CharField(unique=True)
    content = TextField(default="")
    chroma_collection_name = CharField(null=True)  # Nom de la collection ChromaDB pour le RAG
    created_at = DateTimeField(default=datetime.datetime.now)
    folder = ForeignKeyField(FolderModel, backref="documents", null=True, on_delete="SET NULL")
    original_media = ForeignKeyField(MediaModel, backref="parsed_documents", null=True, on_delete="SET NULL")
    file_type = CharField(default="md")  # pdf, md, png, youtube, web, album, epub, audio
    source_url = CharField(null=True)
    total_pages = IntegerField(default=1)
    start_page = IntegerField(null=True)
    end_page = IntegerField(null=True)
    #: Adresses de région **écartées** (ADR 0010), en JSON : la région sort du document, de son
    #: dénominateur de couverture et du rattachement des cartes. Entrées sans préfixe tolérées à la
    #: lecture, réécrites préfixées à l'écriture. L'écartement est une *règle* réévaluée à chaque
    #: réingestion, jamais un identifiant de fragment mémorisé — d'où la non-destruction de la matière.
    excluded_headings = TextField(null=True)
    #: Adresses de région **neutralisées** (ADR 0010) : elles ne sortent que du dénominateur de
    #: couverture, le document les conservant. Colonne distincte d'`excluded_headings` parce que les
    #: deux verbes ne se confondent pas — un seul drapeau ne pourrait pas les porter.
    neutralized_regions = TextField(null=True)
    chunk_strategy_version = IntegerField(default=ChunkingService.CHUNKING_VERSION)


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
    # Le booléen est non-nullable (default=False) : la couverture RAG dépend d'un état dichotomique clair.
    # L'audit "fk-missing-cascade" (audits/raw/) relevait null=True qui autorisait des états ambigus.
    is_profiled = BooleanField(default=False)
    start_time = FloatField(null=True)
    end_time = FloatField(null=True)
    media = ForeignKeyField(MediaModel, backref="chunks", null=True, on_delete="SET NULL")
    bounding_box = CharField(null=True)

    #: Fragment dont le contenu textuel est insuffisant (< 25 mots hors titres) pour
    #: justifier la création de flashcards, mais qui sert de nœud d'organisation pour
    #: des sous-sections substantielles. Neutre dans le calcul de couverture.
    is_structural_container = BooleanField(default=False)

    #: Cause de cette neutralisation : `derived` (déduite de la structure) ou `declared`
    #: (exigée par l'utilisateur via une adresse de région). `NULL` = unité de cours.
    #: Axe du drapeau, pas second drapeau : les deux verbes de l'ADR 0010 — écarter et
    #: neutraliser — ne partagent pas cet axe, ils ont chacun leur colonne au niveau document.
    container_origin = CharField(null=True)

    class Meta:
        table_name = "document_chunks"
        indexes = ((("document", "chunk_index"), False),)


class NoteChunkLinkModel(BaseModel):
    """
    Liaison de traçabilité entre une Note Anki (NoteModel) et son fragment source (DocumentChunkModel).
    Permet le calcul de complétion de cours et l'audit anti-hallucination.

    `chunk_id` est la désignation **précise** (instantanée), tandis que le tag `section:` est
    l'identité **durable** d'un bout de document, stable à travers les réingestions.
    `resolution` trace le palier qui a désigné le fragment : un rattachement permissif doit
    rester visible pour que l'utilisateur sache combien de ses liens sont prouvés et combien
    ne sont que présumés.
    """

    note_id: Any
    chunk_id: Any

    note = ForeignKeyField(NoteModel, backref="chunk_links", on_delete="CASCADE")
    chunk = ForeignKeyField(DocumentChunkModel, backref="note_links", on_delete="CASCADE")
    is_hallucinating = BooleanField(default=False)
    #: Palier de résolution ayant désigné le fragment : `exact`, `section`, `page`, `lexical`.
    #: NULL sur les liens écrits avant l'introduction de la traçabilité du palier.
    resolution = CharField(null=True, index=True)

    class Meta:
        table_name = "note_chunk_links"
        indexes = (
            (("note", "chunk"), True),
            (("chunk",), False),
        )


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
