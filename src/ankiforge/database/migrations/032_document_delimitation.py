import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 032 : Ajout de start_page, end_page et excluded_headings à documentmodel."""
    if not fake and database.table_exists("documentmodel"):
        cols = [col.name for col in database.get_columns("documentmodel")]
        if "start_page" not in cols:
            migrator.add_fields("documentmodel", start_page=pw.IntegerField(null=True))
        if "end_page" not in cols:
            migrator.add_fields("documentmodel", end_page=pw.IntegerField(null=True))
        if "excluded_headings" not in cols:
            migrator.add_fields("documentmodel", excluded_headings=pw.TextField(null=True))


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 032 : Suppression de start_page, end_page et excluded_headings de documentmodel."""
    if not fake and database.table_exists("documentmodel"):
        cols = [col.name for col in database.get_columns("documentmodel")]
        to_remove = [c for c in ["start_page", "end_page", "excluded_headings"] if c in cols]
        if to_remove:
            migrator.remove_fields("documentmodel", *to_remove)
