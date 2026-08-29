# ruff: noqa: E501
import datetime
import logging

from peewee import (
    BooleanField,
    CharField,
    DateTimeField,
    ForeignKeyField,
    TextField,
)

from ankiforge.database.base import BaseModel
from ankiforge.database.models.cards import NoteModel, NoteVersionModel

logger = logging.getLogger(__name__)


class LinterRuleModel(BaseModel):
    """
    Définit une règle d'audit personnalisable par l'utilisateur.
    Ces règles seront injectées dynamiquement dans le prompt du Linter.
    """

    name = CharField(unique=True)  # Ex: "Principe d'Atomicité Minimale"
    category = CharField(default="cat-atomicite")
    category_label = CharField(default="Atomicité & Restructuration")
    description = TextField(null=True)
    is_active = BooleanField(default=True)
    color = CharField(default="#f87171")
    icon_name = CharField(default="squares-four")

    # L'instruction système stricte passée à l'IA
    prompt_injection = TextField()

    # Few-Shot Prompting (Exemples Avant/Après pour guider l'IA)
    example_bad = TextField(null=True)
    example_good = TextField(null=True)

    class Meta:
        table_name = "linter_rules"


class AuditRecordModel(BaseModel):
    """
    Stocke le résultat de l'audit IA pour une version SPÉCIFIQUE d'une note.
    Permet le 'Soft Analysis' (ne pas ré-auditer ce qui l'a déjà été).
    """

    note = ForeignKeyField(NoteModel, backref="audits", on_delete="CASCADE")
    note_version = ForeignKeyField(NoteVersionModel, backref="audit_record", on_delete="CASCADE")

    is_compliant = BooleanField(default=True)
    rule_broken = CharField(null=True)  # Nom de la règle brisée
    reason = TextField(null=True)  # Explication textuelle
    suggestion = TextField(null=True)  # JSON de la suggestion de l'IA

    analyzed_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "audit_records"
        indexes = ((("note", "note_version"), True),)


class IgnoredDuplicateModel(BaseModel):
    """Table pour mémoriser les conflits de doublons ignorés par l'utilisateur."""

    note_a = ForeignKeyField(NoteModel, on_delete="CASCADE")
    note_b = ForeignKeyField(NoteModel, on_delete="CASCADE")

    class Meta:
        table_name = "ignored_duplicates"
        indexes = ((("note_a", "note_b"), True),)
