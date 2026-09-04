# ruff: noqa: E501
import datetime
import json
import logging
from typing import Any

from peewee import (
    BigIntegerField,
    BooleanField,
    CharField,
    DateTimeField,
    FloatField,
    ForeignKeyField,
    IntegerField,
    TextField,
)

from ankiforge.database.base import BaseModel, db, generate_guid

logger = logging.getLogger(__name__)


class DeckModel(BaseModel):
    """Représente un paquet Anki et sa hiérarchie (Subdecks)"""

    anki_id = BigIntegerField(unique=True, null=True)  # L'ID interne d'Anki (did)
    parent_deck = ForeignKeyField("self", null=True, backref="subdecks", on_delete="CASCADE")
    name = CharField(unique=True)  # Ex: "Science::Physique"
    description = TextField(null=True)
    created_at = DateTimeField(default=datetime.datetime.now)


class NoteTypeModel(BaseModel):
    """Représente le TYPE de note (Basic, Cloze...)"""

    anki_id = BigIntegerField(unique=True, null=True)  # L'ID interne d'Anki (mid)
    name = CharField(unique=True)
    description = TextField(null=True, default="")  # Directives d'usage sémantique et rôle pour l'IA
    fields_schema = TextField(default='["Front", "Back"]')  # JSON: Liste des noms des champs ["Front", "Back"]
    templates = TextField(default="[]")  # JSON: Les formats HTML des différentes cartes
    css_style = TextField(default="")  # Le CSS global du modèle


class NoteModel(BaseModel):
    """Le conteneur physique de la note. Il ne change jamais."""

    note_type_id: Any
    cards: Any
    versions: Any

    anki_id = BigIntegerField(unique=True, null=True)
    guid = CharField(unique=True, default=generate_guid)
    note_type = ForeignKeyField(NoteTypeModel, backref="notes")
    tags = TextField(null=True)
    status = CharField(default="new")
    last_synced_at = DateTimeField(null=True)
    anki_content_hash = CharField(null=True)

    @db.atomic()
    def add_version(self, new_content_dict: dict, source: str = "manual") -> "NoteVersionModel":
        """
        Crée une nouvelle version de la note (comme un git commit).
        Désactive l'ancienne version active.
        """
        current_active = NoteVersionModel.get_or_none(note=self, is_active=True)
        new_version_num = 1

        if current_active:
            new_version_num = current_active.version_number + 1
            current_active.is_active = False
            current_active.save()

        new_version = NoteVersionModel.create(
            note=self,
            version_number=new_version_num,
            content=json.dumps(new_content_dict, ensure_ascii=False),
            source=source,
            is_active=True,
        )
        return new_version

    @classmethod
    def purge_old_versions(cls, keep_last: int = 15) -> int:
        """
        Nettoie la base de données en ne conservant que les N dernières versions
        pour chaque note. Retourne le nombre de versions supprimées.
        """
        deleted_count = 0

        with db.atomic():
            for note in cls.select():
                versions = list(NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.desc()))

                if len(versions) > keep_last:
                    versions_to_delete = versions[keep_last:]
                    ids_to_delete = [v.id for v in versions_to_delete]
                    NoteVersionModel.delete().where(NoteVersionModel.id.in_(ids_to_delete)).execute()
                    deleted_count += len(ids_to_delete)

        return deleted_count


class NoteVersionModel(BaseModel):
    """L'historique des contenus de la note (système de version)."""

    note = ForeignKeyField(NoteModel, backref="versions", on_delete="CASCADE")
    version_number = IntegerField(default=1)
    content = TextField(default="{}")  # Le JSON contenant "Recto" et "Verso"
    created_at = DateTimeField(default=datetime.datetime.now)
    source = CharField(default="ai")  # Peut être 'ai', 'manual', ou 'import'
    is_active = BooleanField(default=True)  # Permet de savoir quelle version exporter

    class Meta:
        table_name = "noteversionmodel"
        indexes = (
            (("note", "is_active"), False),
            (("note", "version_number"), False),
        )


class MediaModel(BaseModel):
    """Représente un fichier média physique géré par ankiforge"""

    filename = CharField(unique=True)  # Nom unique généré (ex: sha256.png)
    original_name = CharField()  # Nom d'origine (ex: schema.png)
    checksum = CharField(unique=True)  # Hash SHA-256 pour la déduplication
    mime_type = CharField()  # Type MIME (image/png, audio/mp3)
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "mediamodel"


class NoteVersionMediaModel(BaseModel):
    """Table de liaison entre une version de note et ses médias associés"""

    note_version = ForeignKeyField(NoteVersionModel, backref="medias", on_delete="CASCADE")
    media = ForeignKeyField(MediaModel, backref="note_versions", on_delete="RESTRICT")

    class Meta:
        table_name = "noteversionmediamodel"


class CardModel(BaseModel):
    """La carte physique générée par la Note et rangée dans un Deck"""

    note_id: Any
    deck_id: Any

    anki_id = BigIntegerField(unique=True, null=True)  # L'ID interne d'Anki (cid)
    note = ForeignKeyField(NoteModel, backref="cards", on_delete="CASCADE")
    deck = ForeignKeyField(DeckModel, backref="cards", on_delete="CASCADE")
    template_index = IntegerField(default=0)  # Index du template (Recto=0, Verso=1)
    flags = IntegerField(default=0)  # Drapeau Anki (0=Aucun, 1..7=Couleurs Anki)

    # --- Statistiques FSRS synchronisées depuis Anki ---
    ivl = IntegerField(default=0)
    reps = IntegerField(default=0)
    lapses = IntegerField(default=0)
    stability = FloatField(default=0.0)
    difficulty = FloatField(default=0.0)
    retrievability = FloatField(default=0.0)

    class Meta:
        table_name = "cardmodel"
        indexes = (
            (("deck", "note"), False),
            (("note", "template_index"), False),
            (("flags",), False),
        )
