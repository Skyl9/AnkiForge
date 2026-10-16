"""Migration 010 : média d'origine, type de fichier et URL source sur documentmodel."""

import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Ajoute le média d'origine, le type de fichier et l'URL source à `documentmodel`."""
    migrator.add_fields(
        "documentmodel",
        original_media_id=pw.ForeignKeyField(model=migrator.orm["mediamodel"], backref="parsed_documents", field="id", null=True, on_delete="SET NULL"),
        file_type=pw.CharField(max_length=255, default="md"),
        source_url=pw.CharField(max_length=255, null=True),
    )


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Retire le média d'origine, le type de fichier et l'URL source de `documentmodel`."""
    migrator.remove_fields("documentmodel", "original_media_id", "file_type", "source_url")
