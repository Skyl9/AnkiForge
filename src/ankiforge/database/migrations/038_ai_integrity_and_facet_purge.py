"""
Migration 038 : FK manquantes sur le versionnage IA, neutralisation des CASCADE sur FK nullables,
purge de la colonne legacy `facet_id` et suppression d'un index dupliqué.

Aligne le DDL SQLite réel sur les modèles Peewee (source de vérité) après l'audit "Database & ORM"
(audits/raw/fk-missing-cascade-*.txt, schema-dump-*.txt) :

    * persona_versions.persona_id     -> REFERENCES personas(id) ON DELETE CASCADE (FK manquante)
    * persona_versions.llm_config_id  -> REFERENCES llm_configs(id) ON DELETE SET NULL (FK manquante)
    * consultant_sessions.persona_id  -> REFERENCES personas(id) ON DELETE SET NULL (FK manquante)
    * consultant_messages.session_id  -> REFERENCES consultant_sessions(id) ON DELETE CASCADE (FK manquante)
    * pipeline_steps.persona_id       -> nullable + ON DELETE SET NULL (CASCADE sur FK nullable = perte)
    * documentmodel.folder_id         -> ON DELETE SET NULL (CASCADE sur FK nullable = perte)
    * note_chunk_links.facet_id       -> colonne legacy orpheline purgée (feature "facettes" retirée du modèle)
    * token_usage.idx_token_usage_context -> index dupliqué supprimé (canonique tokenusagemodel_* de 037 conservé)

Technique : reconstruction sûre CREATE temp -> INSERT SELECT -> DROP -> RENAME, en préservant les
ids et les index nommés (pattern 037). Nettoyage préalable des lignes orphelines PRAGMA foreign_keys=OFF :
DELETE des versions/messages dont la cible a disparu, SET NULL des références à une personne/entité supprimée.
Idempotence : no-op sur base fraîche issue des modèles (DDL déjà conforme) ; PRAGMA foreign_keys=OFF
posé défensivement pour les appels directs (run_migrations le pose déjà).
"""

import logging

import peewee as pw
from peewee_migrate import Migrator

logger = logging.getLogger(__name__)

# FKs cibles (formats de DDL exacts émis par peewee / tables réécrites)
_FK_VERSION_PERSONA = '"persona_id" INTEGER NOT NULL REFERENCES "personas" ("id") ON DELETE CASCADE'
_FK_VERSION_LLM = '"llm_config_id" INTEGER REFERENCES "llm_configs" ("id") ON DELETE SET NULL'
_FK_SESSION_PERSONA = '"persona_id" INTEGER REFERENCES "personas" ("id") ON DELETE SET NULL'
_FK_MESSAGE_SESSION = '"session_id" INTEGER NOT NULL REFERENCES "consultant_sessions" ("id") ON DELETE CASCADE'
_FK_STEP_PERSONA_CLAUSE = 'FOREIGN KEY ("persona_id") REFERENCES "personas" ("id") ON DELETE SET NULL'
_FK_DOC_FOLDER_CLAUSE = 'FOREIGN KEY ("folder_id") REFERENCES "foldermodel" ("id") ON DELETE SET NULL'


def _existing_columns(database: pw.Database, table: str) -> set[str]:
    """Retourne l'ensemble des colonnes existantes d'une table SQLite."""
    try:
        rows = database.execute_sql(f"PRAGMA table_info({table});").fetchall()
        return {str(row[1]) for row in rows}
    except Exception as e:
        logger.debug("Impossible de lire les colonnes de %s : %s", table, e)
        return set()


def _table_sql(database: pw.Database, table: str) -> str:
    """Retourne le DDL brut d'une table depuis sqlite_master."""
    row = database.execute_sql("SELECT sql FROM sqlite_master WHERE type='table' AND name=?;", (table,)).fetchone()
    return str(row[0]) if row and row[0] else ""


def _index_sqls(database: pw.Database, table: str) -> list[str]:
    """Capture les DDL des index nommés d'une table (les auto-indexes ont sql NULL et sont ignorés)."""
    rows = database.execute_sql("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL;", (table,)).fetchall()
    return [str(row[0]) for row in rows if row[0]]


def _rebuild(database: pw.Database, table: str, transform, *, insert_columns: list[str] | None = None, insert_values: list[str] | None = None) -> bool:
    """
    Reconstruit une table si son DDL diffère du ciblé (retourne True si réellement reconstruite).
    Préserve les ids et les index nommés. PRAGMA foreign_keys doit être OFF auparavant.
    `insert_columns`/`insert_values` permettent de projeter/synthesizer des colonnes quand la
    structure source diffère de la cible (ex: purge d'une colonne, réintroduction avec NULL).
    """
    old_sql = _table_sql(database, table)
    if not old_sql:
        return False
    new_sql = transform(old_sql)
    if not new_sql or new_sql == old_sql:
        return False
    saved_indexes = _index_sqls(database, table)
    tmp = f"{table}__migration038"
    database.execute_sql(f'DROP TABLE IF EXISTS "{tmp}";')
    database.execute_sql(new_sql.replace(f'CREATE TABLE "{table}"', f'CREATE TABLE "{tmp}"', 1))
    if insert_columns and insert_values:
        dst = ", ".join(f'"{col}"' for col in insert_columns)
        src = ", ".join(insert_values)
        database.execute_sql(f'INSERT INTO "{tmp}" ({dst}) SELECT {src} FROM "{table}";')  # nosec B608  # identifiants internes figés
    else:
        database.execute_sql('INSERT INTO "{tmp}" SELECT * FROM "{table}";'.format(tmp=tmp, table=table))  # noqa: UP032  # nosec B608  # identifiants internes figés
    database.execute_sql(f'DROP TABLE "{table}";')
    database.execute_sql(f'ALTER TABLE "{tmp}" RENAME TO "{table}";')
    for index_sql in saved_indexes:
        database.execute_sql(index_sql)
    logger.info("Migration 038 : table '%s' reconstruite (intégrité référentielle alignée sur le modèle).", table)
    return True


def _version_transform(sql: str) -> str:
    """Ajoute les FK persona_id/llm_config_id manquantes sur persona_versions."""
    if 'REFERENCES "personas"' not in sql:
        sql = sql.replace('"persona_id" INTEGER NOT NULL', _FK_VERSION_PERSONA, 1)
    if 'REFERENCES "llm_configs"' not in sql:
        sql = sql.replace('"llm_config_id" INTEGER', _FK_VERSION_LLM, 1)
    return sql


def _version_rollback_transform(sql: str) -> str:
    """Restitue les simples colonnes INTEGER sur persona_versions."""
    sql = sql.replace(_FK_VERSION_PERSONA, '"persona_id" INTEGER NOT NULL')
    sql = sql.replace(_FK_VERSION_LLM, '"llm_config_id" INTEGER')
    return sql


def _session_transform(sql: str) -> str:
    """Ajoute la FK persona_id manquante sur consultant_sessions."""
    if 'REFERENCES "personas"' in sql:
        return sql
    return sql.replace('"persona_id" INTEGER', _FK_SESSION_PERSONA, 1)


def _session_rollback_transform(sql: str) -> str:
    """Restitue une simple colonne INTEGER sur consultant_sessions."""
    sql = sql.replace(_FK_SESSION_PERSONA, '"persona_id" INTEGER')
    sql = sql.replace('"persona_id" INTEGER REFERENCES "personas" ("id")', '"persona_id" INTEGER')
    return sql


def _message_transform(sql: str) -> str:
    """Ajoute la FK session_id manquante sur consultant_messages."""
    if 'REFERENCES "consultant_sessions"' in sql:
        return sql
    return sql.replace('"session_id" INTEGER NOT NULL', _FK_MESSAGE_SESSION, 1)


def _message_rollback_transform(sql: str) -> str:
    """Restitue une simple colonne INTEGER sur consultant_messages."""
    sql = sql.replace(_FK_MESSAGE_SESSION, '"session_id" INTEGER NOT NULL')
    sql = sql.replace('"session_id" INTEGER NOT NULL REFERENCES "consultant_sessions" ("id")', '"session_id" INTEGER NOT NULL')
    return sql


def _step_transform(sql: str) -> str:
    """Neutralise le CASCADE sur la FK nullable persona_id de pipeline_steps (perte de données)."""
    if "ON DELETE SET NULL" in sql and '"persona_id" INTEGER NOT NULL' not in sql:
        return sql
    sql = sql.replace('"persona_id" INTEGER NOT NULL', '"persona_id" INTEGER', 1)
    sql = sql.replace('FOREIGN KEY ("persona_id") REFERENCES "personas" ("id") ON DELETE CASCADE', _FK_STEP_PERSONA_CLAUSE, 1)
    return sql


def _step_rollback_transform(sql: str) -> str:
    """Restitue le CASCADE et la non-nullabilité sur la FK persona_id de pipeline_steps."""
    sql = sql.replace(_FK_STEP_PERSONA_CLAUSE, 'FOREIGN KEY ("persona_id") REFERENCES "personas" ("id") ON DELETE CASCADE', 1)
    if '"persona_id" INTEGER' in sql and '"persona_id" INTEGER NOT NULL' not in sql:
        sql = sql.replace('"persona_id" INTEGER', '"persona_id" INTEGER NOT NULL', 1)
    return sql


def _doc_transform(sql: str) -> str:
    """Neutralise le CASCADE sur la FK nullable folder_id de documentmodel (perte de données)."""
    sql = sql.replace('FOREIGN KEY ("folder_id") REFERENCES "foldermodel" ("id") ON DELETE CASCADE', _FK_DOC_FOLDER_CLAUSE, 1)
    sql = sql.replace('"folder_id" INTEGER REFERENCES "foldermodel" ("id") ON DELETE CASCADE', '"folder_id" INTEGER REFERENCES "foldermodel" ("id") ON DELETE SET NULL', 1)
    return sql


def _doc_rollback_transform(sql: str) -> str:
    """Restitue le CASCADE sur la FK folder_id de documentmodel."""
    sql = sql.replace(_FK_DOC_FOLDER_CLAUSE, 'FOREIGN KEY ("folder_id") REFERENCES "foldermodel" ("id") ON DELETE CASCADE', 1)
    sql = sql.replace('"folder_id" INTEGER REFERENCES "foldermodel" ("id") ON DELETE SET NULL', '"folder_id" INTEGER REFERENCES "foldermodel" ("id") ON DELETE CASCADE', 1)
    return sql


def _note_chunk_links_transform(sql: str) -> str:
    """Purge la colonne legacy facet_id (et sa FK) de note_chunk_links."""
    if '"facet_id"' not in sql:
        return sql
    sql = sql.replace(', "facet_id" INTEGER, "is_hallucinating"', ', "is_hallucinating"', 1)
    sql = sql.replace(', FOREIGN KEY ("facet_id") REFERENCES "cognitive_facets" ("id") ON DELETE SET NULL', "", 1)
    sql = sql.replace(', "facet_id" INTEGER', "", 1)
    return sql


def _note_chunk_links_rollback_transform(sql: str) -> str:
    """Réintroduit (best-effort) la colonne facet_id et sa FK sur une table purgée."""
    if '"facet_id"' in sql:
        return sql
    if '"is_hallucinating" INTEGER NOT NULL' in sql:
        sql = sql.replace('"is_hallucinating" INTEGER NOT NULL', '"facet_id" INTEGER, "is_hallucinating" INTEGER NOT NULL', 1)
    sql = sql.replace(
        ', FOREIGN KEY ("chunk_id") REFERENCES "document_chunks" ("id") ON DELETE CASCADE',
        ', FOREIGN KEY ("chunk_id") REFERENCES "document_chunks" ("id") ON DELETE CASCADE, FOREIGN KEY ("facet_id") REFERENCES "cognitive_facets" ("id") ON DELETE SET NULL',
        1,
    )
    return sql


def _cleanup_orphans(database: pw.Database) -> None:
    """Supprime/rélie les lignes devenues orphelines par manque de FK (à exécuter FK OFF)."""
    try:
        if database.table_exists("persona_versions") and database.table_exists("personas"):
            database.execute_sql("DELETE FROM persona_versions WHERE persona_id NOT IN (SELECT id FROM personas);")
        if database.table_exists("persona_versions") and database.table_exists("llm_configs"):
            database.execute_sql("UPDATE persona_versions SET llm_config_id = NULL WHERE llm_config_id IS NOT NULL AND llm_config_id NOT IN (SELECT id FROM llm_configs);")
        if database.table_exists("consultant_sessions") and database.table_exists("personas"):
            database.execute_sql("UPDATE consultant_sessions SET persona_id = NULL WHERE persona_id IS NOT NULL AND persona_id NOT IN (SELECT id FROM personas);")
        if database.table_exists("consultant_messages") and database.table_exists("consultant_sessions"):
            database.execute_sql("DELETE FROM consultant_messages WHERE session_id NOT IN (SELECT id FROM consultant_sessions);")
    except Exception as e:
        logger.warning("Remarque sur le nettoyage des orphelins (038) : %s", e)


def _relink_nullable_steps(database: pw.Database) -> None:
    """Règle à NULL les pipeline_steps dont la persona a disparu (colonne désormais nullable)."""
    try:
        if database.table_exists("pipeline_steps") and database.table_exists("personas"):
            database.execute_sql("UPDATE pipeline_steps SET persona_id = NULL WHERE persona_id IS NOT NULL AND persona_id NOT IN (SELECT id FROM personas);")
    except Exception as e:
        logger.warning("Remarque sur la reliaison des pipeline_steps (038) : %s", e)


def create_required_indexes(database: pw.Database) -> None:
    """Index FKs conformes au schéma peewee (idempotents, no-op en base fraîche)."""
    try:
        if database.table_exists("persona_versions"):
            database.execute_sql("CREATE INDEX IF NOT EXISTS personaversionmodel_llm_config_id ON persona_versions (llm_config_id);")
        if database.table_exists("consultant_sessions"):
            database.execute_sql("CREATE INDEX IF NOT EXISTS consultantsessionmodel_persona_id ON consultant_sessions (persona_id);")
        if database.table_exists("consultant_messages"):
            database.execute_sql("CREATE INDEX IF NOT EXISTS consultantmessagemodel_session_id ON consultant_messages (session_id);")
    except Exception as e:
        logger.warning("Remarque sur les index 038 : %s", e)


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 038 : FK IA + CASCADE nullables neutralisés + purge facet_id (idempotente)."""
    if fake:
        return
    try:
        database.execute_sql("PRAGMA foreign_keys = OFF;")
    except Exception as fk_err:
        logger.debug("Remarque PRAGMA foreign_keys = OFF (038) : %s", fk_err)

    try:
        # 0. Nettoyage des orphelins historiques (invisible avec FK OFF, indispensable pour l'intégrité)
        _cleanup_orphans(database)

        # 1. Index dupliqué supprimé (le canonique tokenusagemodel_pipeline_id_persona_id_ab_run_id reste)
        database.execute_sql("DROP INDEX IF EXISTS idx_token_usage_context;")

        # 2. Réécritures DDL (no-op si DDL déjà conforme / base fraîche)
        if database.table_exists("persona_versions"):
            _rebuild(database, "persona_versions", _version_transform)
        if database.table_exists("consultant_sessions"):
            _rebuild(database, "consultant_sessions", _session_transform)
        if database.table_exists("consultant_messages"):
            _rebuild(database, "consultant_messages", _message_transform)
        if database.table_exists("pipeline_steps"):
            _rebuild(database, "pipeline_steps", _step_transform)
            _relink_nullable_steps(database)
        if database.table_exists("documentmodel") and "folder_id" in _existing_columns(database, "documentmodel"):
            _rebuild(database, "documentmodel", _doc_transform)

        # 3. Purge facet_id sur note_chunk_links : on retire d'abord ses index dédiés puis on réécrit
        if database.table_exists("note_chunk_links") and "facet_id" in _existing_columns(database, "note_chunk_links"):
            database.execute_sql("DROP INDEX IF EXISTS notechunklinkmodel_facet_id;")
            database.execute_sql("DROP INDEX IF EXISTS notechunklinkmodel_note_id_chunk_id_facet_id;")
            _rebuild(
                database,
                "note_chunk_links",
                _note_chunk_links_transform,
                insert_columns=["id", "note_id", "chunk_id", "is_hallucinating"],
                insert_values=["id", "note_id", "chunk_id", "is_hallucinating"],
            )

        # 4. Index complémentaires du schéma peewee (FK manquantes)
        create_required_indexes(database)
    except Exception as e:
        logger.warning("Remarque sur la migration 038 (intégrité référentielle IA) : %s", e)
    finally:
        try:
            database.execute_sql("PRAGMA foreign_keys = ON;")
        except Exception as fk_err:
            logger.debug("Remarque PRAGMA foreign_keys = ON (038) : %s", fk_err)


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 038 : restauration du DDL d'avant migration (best-effort pour la purge facet_id)."""
    if fake:
        return
    try:
        database.execute_sql("PRAGMA foreign_keys = OFF;")
    except Exception as fk_err:
        logger.debug("Remarque PRAGMA foreign_keys = OFF (rollback 038) : %s", fk_err)

    try:
        database.execute_sql("CREATE INDEX IF NOT EXISTS idx_token_usage_context ON token_usage (pipeline_id, persona_id, ab_run_id);")

        if database.table_exists("persona_versions"):
            _rebuild(database, "persona_versions", _version_rollback_transform)
        if database.table_exists("consultant_sessions"):
            _rebuild(database, "consultant_sessions", _session_rollback_transform)
        if database.table_exists("consultant_messages"):
            _rebuild(database, "consultant_messages", _message_rollback_transform)
        if database.table_exists("pipeline_steps"):
            _rebuild(database, "pipeline_steps", _step_rollback_transform)
        if database.table_exists("documentmodel") and "folder_id" in _existing_columns(database, "documentmodel"):
            _rebuild(database, "documentmodel", _doc_rollback_transform)
        if database.table_exists("note_chunk_links") and "facet_id" not in _existing_columns(database, "note_chunk_links"):
            _rebuild(
                database,
                "note_chunk_links",
                _note_chunk_links_rollback_transform,
                insert_columns=["id", "note_id", "chunk_id", "facet_id", "is_hallucinating"],
                insert_values=["id", "note_id", "chunk_id", "NULL", "is_hallucinating"],
            )
            database.execute_sql("CREATE INDEX IF NOT EXISTS notechunklinkmodel_facet_id ON note_chunk_links (facet_id);")
    except Exception as e:
        logger.warning("Remarque sur le rollback de la migration 038 (intégrité référentielle IA) : %s", e)
    finally:
        try:
            database.execute_sql("PRAGMA foreign_keys = ON;")
        except Exception as fk_err:
            logger.debug("Remarque PRAGMA foreign_keys = ON (rollback 038) : %s", fk_err)
