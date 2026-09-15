import html
import json
import logging
import re
from typing import Any

import peewee as pw
from peewee_migrate import Migrator

logger = logging.getLogger(__name__)

HTML_TAG_RE = re.compile(r"<[^>]+>")


def _clean_text(raw: str) -> str:
    """Supprime les balises HTML et décode les entités pour l'indexation FTS."""
    if not raw:
        return ""
    stripped = HTML_TAG_RE.sub(" ", raw)
    unescaped = html.unescape(stripped)
    return " ".join(unescaped.split())


def _extract_fields_text(content_str: str) -> str:
    """Extrait le texte brut de tous les champs d'un JSON de version de note."""
    if not content_str:
        return ""
    try:
        data = json.loads(content_str)
        if isinstance(data, dict):
            parts = [_clean_text(str(v)) for v in data.values() if v is not None]
            return " ".join(p for p in parts if p)
        if isinstance(data, list):
            parts = [_clean_text(str(item)) for item in data if item is not None]
            return " ".join(p for p in parts if p)
    except Exception:
        pass
    return _clean_text(content_str)


def _extract_tags_text(raw_tags: Any) -> str:
    """Convertit les tags (string ou JSON array) en liste de mots séparés par des espaces."""
    if not raw_tags:
        return ""
    if isinstance(raw_tags, str):
        raw_tags = raw_tags.strip()
        if raw_tags.startswith("["):
            try:
                parsed = json.loads(raw_tags)
                if isinstance(parsed, list):
                    return " ".join(str(t).strip() for t in parsed if t)
            except Exception:
                pass
        return " ".join(raw_tags.split())
    if isinstance(raw_tags, list | set | tuple):
        return " ".join(str(t).strip() for t in raw_tags if t)
    return str(raw_tags).strip()


def migrate(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Migration 030 : Création de la table FTS5 note_fts et des index de performance."""
    if fake:
        return

    # 1. Création de la table virtuelle FTS5 note_fts avec le tokenizer unicode61
    try:
        database.execute_sql("""
            CREATE VIRTUAL TABLE IF NOT EXISTS note_fts USING fts5(
                note_id UNINDEXED,
                deck_id UNINDEXED,
                fields_text,
                tags,
                tokenize = 'unicode61 remove_diacritics 2'
            );
        """)
        logger.info("Table virtuelle FTS5 'note_fts' créée avec succès.")
    except Exception as e:
        logger.warning("Impossible d'activer FTS5 (SQLite sans module FTS5 ?) : %s", e)

    # 2. Création des index B-Tree de performance
    indexes = [
        ("idx_note_chunk_link_chunk", "CREATE INDEX IF NOT EXISTS idx_note_chunk_link_chunk ON note_chunk_links (chunk_id);"),
        ("idx_card_deck_suspended", "CREATE INDEX IF NOT EXISTS idx_card_deck_suspended ON cardmodel (deck_id, is_suspended);"),
        ("idx_card_flags", "CREATE INDEX IF NOT EXISTS idx_card_flags ON cardmodel (flags);"),
        ("idx_audit_note_rule", "CREATE INDEX IF NOT EXISTS idx_audit_note_rule ON audit_records (note_id, rule_broken);"),
    ]
    for _idx_name, sql in indexes:
        try:
            database.execute_sql(sql)
        except Exception as e:
            logger.debug("Remarque sur la création d'index : %s", e)

    # 3. Backfill initial de note_fts à partir des versions actives des notes existantes
    try:
        # Vérifier si note_fts et notemodel existent
        cursor = database.execute_sql("SELECT name FROM sqlite_master WHERE type='table' AND name='note_fts';")
        if not cursor.fetchone():
            return

        if not (database.table_exists("notemodel") and database.table_exists("noteversionmodel")):
            return

        # Requête pour récupérer les notes avec leur version active et leur premier deck_id
        sql = """
            SELECT n.id, n.tags, nv.content, c.deck_id
            FROM notemodel n
            JOIN noteversionmodel nv ON nv.note_id = n.id AND nv.is_active = 1
            LEFT JOIN cardmodel c ON c.note_id = n.id AND c.template_index = 0
        """
        rows = database.execute_sql(sql).fetchall()
        if rows:
            insert_records = []
            for r in rows:
                n_id = r[0]
                tags_raw = r[1]
                content_raw = r[2]
                deck_id = r[3] or 0

                fields_text = _extract_fields_text(content_raw)
                tags_text = _extract_tags_text(tags_raw)

                insert_records.append((n_id, deck_id, fields_text, tags_text))

            # Supprimer les éventuelles entrées préexistantes
            database.execute_sql("DELETE FROM note_fts;")
            # Insertion par batch
            for rec in insert_records:
                database.execute_sql(
                    "INSERT INTO note_fts (note_id, deck_id, fields_text, tags) VALUES (?, ?, ?, ?);",
                    rec,
                )
            logger.info("FTS5 initialisé avec %d notes indexées.", len(insert_records))
    except Exception as e:
        logger.warning("Erreur lors du peuplement initial de note_fts : %s", e)


def rollback(migrator: Migrator, database: pw.Database, *, fake: bool = False) -> None:
    """Rollback 030 : Suppression de note_fts et des index de performance."""
    if fake:
        return

    indexes = [
        "idx_note_chunk_link_chunk",
        "idx_card_deck_suspended",
        "idx_card_flags",
        "idx_audit_note_rule",
    ]
    for idx_name in indexes:
        try:
            database.execute_sql(f"DROP INDEX IF EXISTS {idx_name};")
        except Exception:
            pass

    try:
        database.execute_sql("DROP TABLE IF EXISTS note_fts;")
    except Exception:
        pass
