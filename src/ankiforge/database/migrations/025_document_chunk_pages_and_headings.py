import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 025 : Ajout des colonnes page_number et heading_path à document_chunks."""
    if not fake and database.table_exists("document_chunks"):
        chunk_cols = [col.name for col in database.get_columns("document_chunks")]
        if "page_number" not in chunk_cols:
            migrator.add_fields("document_chunks", page_number=pw.IntegerField(null=True))
        if "heading_path" not in chunk_cols:
            migrator.add_fields("document_chunks", heading_path=pw.CharField(max_length=255, null=True))


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 025 : Suppression des colonnes page_number et heading_path de document_chunks."""
    if not fake and database.table_exists("document_chunks"):
        chunk_cols = [col.name for col in database.get_columns("document_chunks")]
        to_remove = [c for c in ["page_number", "heading_path"] if c in chunk_cols]
        if to_remove:
            migrator.remove_fields("document_chunks", *to_remove)
