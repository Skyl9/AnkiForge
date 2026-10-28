"""Migration 046 : Dépose du chat Consultant IA et suppression des tables consultant_sessions et consultant_messages (ADR 0043)."""

import datetime
import logging

import peewee as pw
from peewee_migrate import Migrator

logger = logging.getLogger(__name__)


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 046 : Supprime les tables et index obsolètes de chat conversationnel in-app."""
    if fake:
        return

    try:
        database.execute_sql("DROP INDEX IF EXISTS idx_consultant_msg_session_created;")
        database.execute_sql("DROP INDEX IF EXISTS idx_consultant_session_updated;")
    except Exception as err:
        logger.debug("Suppression des index consultant ignorée : %s", err)

    if database.table_exists("consultant_messages"):
        try:
            migrator.remove_model("consultant_messages")
        except Exception:
            database.execute_sql("DROP TABLE IF EXISTS consultant_messages;")

    if database.table_exists("consultant_sessions"):
        try:
            migrator.remove_model("consultant_sessions")
        except Exception:
            database.execute_sql("DROP TABLE IF EXISTS consultant_sessions;")

    logger.info("Migration 046 : Tables consultant_sessions et consultant_messages supprimées avec succès.")


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 046 : Recrée les tables de discussion consultant."""
    if fake:
        return

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
