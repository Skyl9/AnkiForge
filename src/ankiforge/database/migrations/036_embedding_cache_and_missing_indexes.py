import datetime
import logging

import peewee as pw
from peewee_migrate import Migrator

logger = logging.getLogger(__name__)


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 036 : création de la table embedding_cache et rattrapage des index manquants."""
    if fake:
        return

    # 1. Rétablissement des index manquants sur les tables déjà créées
    try:
        if database.table_exists("token_usage"):
            database.execute_sql("CREATE INDEX IF NOT EXISTS idx_token_usage_context ON token_usage (pipeline_id, persona_id, ab_run_id);")
    except Exception as e:
        logger.debug("Remarque création index idx_token_usage_context : %s", e)

    try:
        if database.table_exists("consultant_messages"):
            database.execute_sql("CREATE INDEX IF NOT EXISTS idx_consultant_msg_session_created ON consultant_messages (session_id, created_at);")
    except Exception as e:
        logger.debug("Remarque création index idx_consultant_msg_session_created : %s", e)

    try:
        if database.table_exists("consultant_sessions"):
            database.execute_sql("CREATE INDEX IF NOT EXISTS idx_consultant_session_updated ON consultant_sessions (updated_at DESC);")
    except Exception as e:
        logger.debug("Remarque création index idx_consultant_session_updated : %s", e)

    try:
        if database.table_exists("cardmodel"):
            database.execute_sql("CREATE INDEX IF NOT EXISTS idx_card_note_template ON cardmodel (note_id, template_index);")
            database.execute_sql("CREATE INDEX IF NOT EXISTS idx_card_suspended ON cardmodel (is_suspended);")
    except Exception as e:
        logger.debug("Remarque création index cardmodel : %s", e)

    try:
        if database.table_exists("note_chunk_links"):
            database.execute_sql("CREATE UNIQUE INDEX IF NOT EXISTS note_chunk_links_note_chunk ON note_chunk_links (note_id, chunk_id);")
    except Exception as e:
        logger.debug("Remarque création index note_chunk_links : %s", e)

    # 2. Création de la table embedding_cache avec son index unique
    if not database.table_exists("embedding_cache"):

        @migrator.create_model
        class EmbeddingCacheModel(pw.Model):
            id = pw.AutoField()
            text_hash = pw.CharField(max_length=255, index=True)
            model_id = pw.CharField(max_length=255, default="text-embedding-3-small", index=True)
            dimensions = pw.IntegerField(default=1536)
            embedding_json = pw.TextField(default="[]")
            created_at = pw.DateTimeField(default=datetime.datetime.now)

            class Meta:
                table_name = "embedding_cache"
                indexes = ((("text_hash", "model_id"), True),)


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 036 : suppression des index et de la table embedding_cache."""
    if fake:
        return
    try:
        database.execute_sql("DROP INDEX IF EXISTS idx_token_usage_context;")
        database.execute_sql("DROP INDEX IF EXISTS idx_consultant_msg_session_created;")
        database.execute_sql("DROP INDEX IF EXISTS idx_consultant_session_updated;")
        database.execute_sql("DROP INDEX IF EXISTS idx_card_note_template;")
        database.execute_sql("DROP INDEX IF EXISTS idx_card_suspended;")
    except Exception as e:
        logger.debug("Remarque rollback index 036 : %s", e)

    if database.table_exists("embedding_cache"):
        migrator.remove_model("embedding_cache")
