import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your migrations here."""
    migrator.add_fields(
        "documentmodel",
        original_media_id=pw.ForeignKeyField(model=migrator.orm["mediamodel"], backref="parsed_documents", field="id", null=True, on_delete="SET NULL"),
        file_type=pw.CharField(max_length=255, default="md"),
        source_url=pw.CharField(max_length=255, null=True),
    )


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your rollback migrations here."""
    migrator.remove_fields("documentmodel", "original_media_id", "file_type", "source_url")
