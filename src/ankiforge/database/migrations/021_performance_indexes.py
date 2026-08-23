import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 021 : Création d'index composites de haute performance pour éliminer les requêtes N+1 et accélérer les jointures."""
    if not fake:
        indexes = [
            ("idx_noteversion_note_active", "CREATE INDEX IF NOT EXISTS idx_noteversion_note_active ON noteversionmodel (note_id, is_active);"),
            ("idx_noteversion_note_ver", "CREATE INDEX IF NOT EXISTS idx_noteversion_note_ver ON noteversionmodel (note_id, version_number);"),
            ("idx_docchunk_doc_idx", "CREATE INDEX IF NOT EXISTS idx_docchunk_doc_idx ON document_chunks (document_id, chunk_index);"),
            ("idx_card_deck_note", "CREATE INDEX IF NOT EXISTS idx_card_deck_note ON cardmodel (deck_id, note_id);"),
            ("idx_auditrecord_compliant", "CREATE INDEX IF NOT EXISTS idx_auditrecord_compliant ON audit_records (is_compliant);"),
            ("idx_tokenusage_created", "CREATE INDEX IF NOT EXISTS idx_tokenusage_created ON token_usage (created_at);"),
        ]
        for _idx_name, sql in indexes:
            try:
                database.execute_sql(sql)
            except Exception:
                pass  # nosec B110


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 021 : Suppression des index composites de performance."""
    if not fake:
        indexes = [
            "idx_noteversion_note_active",
            "idx_noteversion_note_ver",
            "idx_docchunk_doc_idx",
            "idx_card_deck_note",
            "idx_auditrecord_compliant",
            "idx_tokenusage_created",
        ]
        for idx_name in indexes:
            try:
                database.execute_sql(f"DROP INDEX IF EXISTS {idx_name};")
            except Exception:
                pass  # nosec B110
