import datetime

import peewee as pw
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 022 : Crée les tables consultant_sessions et consultant_messages pour la persistance des discussions."""

    @migrator.create_model
    class ConsultantSessionModel(pw.Model):
        id = pw.AutoField()
        title = pw.CharField(max_length=255, default="Nouvelle Session")
        persona_id = pw.IntegerField(null=True, index=True)
        created_at = pw.DateTimeField(default=datetime.datetime.now)
        updated_at = pw.DateTimeField(default=datetime.datetime.now)

        class Meta:
            table_name = "consultant_sessions"

    @migrator.create_model
    class ConsultantMessageModel(pw.Model):
        id = pw.AutoField()
        session_id = pw.IntegerField(index=True)
        role = pw.CharField(max_length=50)
        content = pw.TextField()
        thoughts = pw.TextField(null=True)
        tool_calls_json = pw.TextField(null=True)
        staged_diffs_json = pw.TextField(null=True)
        tokens_used = pw.IntegerField(default=0)
        created_at = pw.DateTimeField(default=datetime.datetime.now)

        class Meta:
            table_name = "consultant_messages"

    if not fake:
        try:
            database.execute_sql("CREATE INDEX IF NOT EXISTS idx_consultant_msg_session_created ON consultant_messages (session_id, created_at);")
            database.execute_sql("CREATE INDEX IF NOT EXISTS idx_consultant_session_updated ON consultant_sessions (updated_at DESC);")
        except Exception:
            pass  # nosec B110


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 022 : Supprime les tables consultant_messages et consultant_sessions."""
    migrator.remove_model("consultant_messages")
    migrator.remove_model("consultant_sessions")
