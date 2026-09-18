"""
Migration 037 : intégrité référentielle (ON DELETE) et matérialisation des index canoniques du modèle.

Rétablit l'alignement modèle Peewee <-> DDL SQLite réel constaté par l'audit "Database & ORM"
(audits/raw/schema-dump-*.txt, fk-missing-cascade-*.txt, missing-indexes-*.txt) :

    * deckmodel.parent_deck_id    -> ON DELETE CASCADE  (un sous-deck et ses cartes suivent leur parent, sémantique native Anki)
    * notemodel.note_type_id      -> ON DELETE RESTRICT (un type de note utilisé ne se supprime jamais silencieusement)
    * token_usage.pipeline_id / persona_id
                                  -> véritables FK REFERENCES pipelines(id) / personas(id) ON DELETE SET NULL
    * index de modèle absents du DDL réel -> noms canoniques peewee, créés de façon idempotente
      (cardmodel_is_suspended, cardmodel_note_id_template_index,
       tokenusagemodel_pipeline_id_persona_id_ab_run_id, embeddingcachemodel_text_hash_model_id)

Technique : reconstruction sûre CREATE temp -> INSERT SELECT -> DROP -> RENAME, en préservant les
index nommés existants et les ids (FTS5 note_fts et clés étrangères restent cohérents). Exécutée avec
PRAGMA foreign_keys=OFF (posé par run_migrations, re-posé défensivement ici pour les appels directs).

Idempotence : si le DDL cible est déjà en place (base fraîche issue des modèles), la migration est un no-op.
"""

import logging

import peewee as pw
from peewee_migrate import Migrator

logger = logging.getLogger(__name__)

# Subtensions FK cibles (format exact du DDL émis par peewee create_tables / migrations antérieures)
_FK_PARENT_DECK = 'FOREIGN KEY ("parent_deck_id") REFERENCES "deckmodel" ("id")'
_FK_NOTE_TYPE = 'FOREIGN KEY ("note_type_id") REFERENCES "notetypemodel" ("id")'
_USAGE_COLS_LEGACY = '"pipeline_id" INTEGER, "persona_id" INTEGER,'
_USAGE_COLS_FK = '"pipeline_id" INTEGER REFERENCES "pipelines" ("id") ON DELETE SET NULL, "persona_id" INTEGER REFERENCES "personas" ("id") ON DELETE SET NULL,'


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


def _rebuild(database: pw.Database, table: str, transform) -> bool:
    """
    Reconstruit une table si son DDL diffère du ciblé (retourne True si réellement reconstruite).
    Préserve les ids et les index nommés. PRAGMA foreign_keys doit être OFF auparavant.
    """
    old_sql = _table_sql(database, table)
    if not old_sql:
        return False
    new_sql = transform(old_sql)
    if not new_sql or new_sql == old_sql:
        return False
    saved_indexes = _index_sqls(database, table)
    tmp = f"{table}__migration037"
    database.execute_sql(f'DROP TABLE IF EXISTS "{tmp}";')
    database.execute_sql(new_sql.replace(f'CREATE TABLE "{table}"', f'CREATE TABLE "{tmp}"', 1))
    database.execute_sql('INSERT INTO "{tmp}" SELECT * FROM "{table}";'.format(tmp=tmp, table=table))  # noqa: UP032  # nosec B608  # .format() pour une seule constante bandit (B608) ; identifiants internes figés, SQLite ne lie pas d'identifiants
    database.execute_sql(f'DROP TABLE "{table}";')
    database.execute_sql(f'ALTER TABLE "{tmp}" RENAME TO "{table}";')
    for index_sql in saved_indexes:
        database.execute_sql(index_sql)
    logger.info("Migration 037 : table '%s' reconstruite (intégrité référentielle alignée sur le modèle).", table)
    return True


def _deck_transform(sql: str) -> str:
    """Ajoute ON DELETE CASCADE au FK parent_deck de deckmodel."""
    if _FK_PARENT_DECK not in sql or "ON DELETE CASCADE" in sql:
        return sql
    return sql.replace(_FK_PARENT_DECK, _FK_PARENT_DECK + " ON DELETE CASCADE")


def _deck_rollback_transform(sql: str) -> str:
    """Retire ON DELETE CASCADE du FK parent_deck de deckmodel."""
    if _FK_PARENT_DECK not in sql:
        return sql
    return sql.replace(_FK_PARENT_DECK + " ON DELETE CASCADE", _FK_PARENT_DECK)


def _note_transform(sql: str) -> str:
    """Ajoute ON DELETE RESTRICT au FK note_type de notemodel."""
    if _FK_NOTE_TYPE not in sql or "ON DELETE RESTRICT" in sql:
        return sql
    return sql.replace(_FK_NOTE_TYPE, _FK_NOTE_TYPE + " ON DELETE RESTRICT")


def _note_rollback_transform(sql: str) -> str:
    """Retire ON DELETE RESTRICT du FK note_type de notemodel."""
    if _FK_NOTE_TYPE not in sql:
        return sql
    return sql.replace(_FK_NOTE_TYPE + " ON DELETE RESTRICT", _FK_NOTE_TYPE)


def _token_transform(sql: str) -> str:
    """Transforme les colonnes pipeline_id/persona_id en véritables FKs ON DELETE SET NULL."""
    if 'REFERENCES "pipelines"' in sql or _USAGE_COLS_LEGACY not in sql:
        return sql
    return sql.replace(_USAGE_COLS_LEGACY, _USAGE_COLS_FK)


def _token_rollback_transform(sql: str) -> str:
    """Restaure des simples colonnes INTEGER sur token_usage."""
    if _USAGE_COLS_FK not in sql:
        return sql
    return sql.replace(_USAGE_COLS_FK, _USAGE_COLS_LEGACY)


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 037 : ON DELETE conforme aux modèles + index canoniques (idempotente)."""
    if fake:
        return
    try:
        database.execute_sql("PRAGMA foreign_keys = OFF;")
    except Exception as fk_err:
        logger.debug("Remarque PRAGMA foreign_keys = OFF (037) : %s", fk_err)

    try:
        # 1. Index canoniques du modèle manquants au DDL réel (idempotent, no-op en base fraîche)
        if database.table_exists("cardmodel"):
            database.execute_sql("CREATE INDEX IF NOT EXISTS cardmodel_is_suspended ON cardmodel (is_suspended);")
            database.execute_sql("CREATE INDEX IF NOT EXISTS cardmodel_note_id_template_index ON cardmodel (note_id, template_index);")
        if database.table_exists("token_usage"):
            database.execute_sql("CREATE INDEX IF NOT EXISTS tokenusagemodel_pipeline_id_persona_id_ab_run_id ON token_usage (pipeline_id, persona_id, ab_run_id);")
        if database.table_exists("embedding_cache"):
            database.execute_sql("CREATE UNIQUE INDEX IF NOT EXISTS embeddingcachemodel_text_hash_model_id ON embedding_cache (text_hash, model_id);")

        # 2. Réécritures DDL (no-op si DDL déjà conforme)
        if database.table_exists("deckmodel"):
            _rebuild(database, "deckmodel", _deck_transform)
        if database.table_exists("notemodel"):
            _rebuild(database, "notemodel", _note_transform)
        if database.table_exists("token_usage") and {"pipeline_id", "persona_id"} <= _existing_columns(database, "token_usage"):
            _rebuild(database, "token_usage", _token_transform)
    except Exception as e:
        logger.warning("Remarque sur la migration 037 (intégrité référentielle) : %s", e)
    finally:
        try:
            database.execute_sql("PRAGMA foreign_keys = ON;")
        except Exception as fk_err:
            logger.debug("Remarque PRAGMA foreign_keys = ON (037) : %s", fk_err)


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 037 : retrait des index canoniques et restauration du DDL d'avant migration."""
    if fake:
        return
    try:
        database.execute_sql("PRAGMA foreign_keys = OFF;")
    except Exception as fk_err:
        logger.debug("Remarque PRAGMA foreign_keys = OFF (rollback 037) : %s", fk_err)

    try:
        database.execute_sql("DROP INDEX IF EXISTS cardmodel_is_suspended;")
        database.execute_sql("DROP INDEX IF EXISTS cardmodel_note_id_template_index;")
        database.execute_sql("DROP INDEX IF EXISTS tokenusagemodel_pipeline_id_persona_id_ab_run_id;")
        database.execute_sql("DROP INDEX IF EXISTS embeddingcachemodel_text_hash_model_id;")

        if database.table_exists("deckmodel"):
            _rebuild(database, "deckmodel", _deck_rollback_transform)
        if database.table_exists("notemodel"):
            _rebuild(database, "notemodel", _note_rollback_transform)
        if database.table_exists("token_usage") and {"pipeline_id", "persona_id"} <= _existing_columns(database, "token_usage"):
            _rebuild(database, "token_usage", _token_rollback_transform)
    except Exception as e:
        logger.warning("Remarque sur le rollback de la migration 037 (intégrité référentielle) : %s", e)
    finally:
        try:
            database.execute_sql("PRAGMA foreign_keys = ON;")
        except Exception as fk_err:
            logger.debug("Remarque PRAGMA foreign_keys = ON (rollback 037) : %s", fk_err)
