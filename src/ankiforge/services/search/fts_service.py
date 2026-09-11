"""Service de recherche plein-texte SQLite FTS5 pour AnkiForge.

Fournit l'indexation, la synchronisation, la recherche avec scoring BM25
et la génération de snippets pour les notes et tags.
"""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from peewee import Database

from ankiforge.database.base import db
from ankiforge.database.models.cards import CardModel, NoteModel, NoteVersionModel

logger = logging.getLogger(__name__)

HTML_TAG_RE = re.compile(r"<[^>]+>")
PUNCT_STRIP = " \t\r\n\"':;()[]{}*^~!?"


def clean_html(raw: str) -> str:
    """Supprime les balises HTML et décode les entités XML/HTML."""
    if not raw:
        return ""
    stripped = HTML_TAG_RE.sub(" ", raw)
    unescaped = html.unescape(stripped)
    return " ".join(unescaped.split())


def extract_fields_text(content_str: str) -> str:
    """Extrait le texte brut de tous les champs d'un JSON de version de note."""
    if not content_str:
        return ""
    try:
        data = json.loads(content_str)
        if isinstance(data, dict):
            parts = [clean_html(str(v)) for v in data.values() if v is not None]
            return " ".join(p for p in parts if p)
        if isinstance(data, list):
            parts = [clean_html(str(item)) for item in data if item is not None]
            return " ".join(p for p in parts if p)
    except Exception:
        pass
    return clean_html(content_str)


def extract_tags_text(raw_tags: Any) -> str:
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


def sanitize_fts5_query(query: str, as_prefix: bool = True) -> str:
    """Nettoie et formate une requête utilisateur pour FTS5.

    - Enrobe chaque token dans des guillemets doubles ("...") pour neutraliser
      les opérateurs FTS5 réservés (:, (, ), NOT, OR, AND).
    - Ajoute un préfixe wildcard (*) au dernier mot pour la recherche as-you-type.
    """
    raw_tokens = query.strip().split()
    clean_tokens: list[str] = []
    for t in raw_tokens:
        cleaned = t.strip(PUNCT_STRIP)
        if cleaned:
            clean_tokens.append(cleaned.replace('"', '""'))
    if not clean_tokens:
        return ""
    if as_prefix:
        prefix_token = f'"{clean_tokens[-1]}"*'
        standard_tokens = [f'"{token}"' for token in clean_tokens[:-1]]
        return " ".join(standard_tokens + [prefix_token])
    return " ".join(f'"{token}"' for token in clean_tokens)


def _get_target_db(database: Database | None = None) -> Database:
    """Retourne la base de données cible (privilégie la base liée au modèle NoteModel)."""
    if database is not None:
        return database
    if hasattr(NoteModel, "_meta") and getattr(NoteModel._meta, "database", None) is not None:
        return NoteModel._meta.database
    return db


@dataclass(frozen=True)
class FTSSearchResult:
    """Résultat d'une recherche plein-texte FTS5."""

    note_id: int
    deck_id: int
    rank: float
    snippet: str


class FTSService:
    """Service gérant l'indexation et les requêtes FTS5 sur les notes."""

    @classmethod
    def is_available(cls, database: Database | None = None) -> bool:
        """Vérifie si la table virtuelle note_fts existe dans la base de données."""
        target_db = _get_target_db(database)
        try:
            cursor = target_db.execute_sql("SELECT name FROM sqlite_master WHERE type='table' AND name='note_fts';")
            return cursor.fetchone() is not None
        except Exception as e:
            logger.debug("Vérification disponibilité FTS5 échouée: %s", e)
            return False

    @classmethod
    def sync_note(cls, note_id: int, database: Database | None = None) -> bool:
        """Synchronise l'index FTS5 pour une note spécifique (idempotent)."""
        target_db = _get_target_db(database)
        if not cls.is_available(target_db):
            return False

        try:
            note = NoteModel.get_or_none(NoteModel.id == note_id)
            if not note:
                cls.delete_note(note_id, target_db)
                return True

            active_version = NoteVersionModel.get_or_none(NoteVersionModel.note == note, NoteVersionModel.is_active == True)  # noqa: E712
            card = CardModel.select(CardModel.deck).where(CardModel.note == note).first()
            deck_id = card.deck_id if card and card.deck_id else 0

            fields_text = extract_fields_text(active_version.content if active_version else "")
            tags_text = extract_tags_text(note.tags)

            with target_db.atomic():
                target_db.execute_sql("DELETE FROM note_fts WHERE note_id = ?;", (note_id,))
                target_db.execute_sql(
                    "INSERT INTO note_fts (note_id, deck_id, fields_text, tags) VALUES (?, ?, ?, ?);",
                    (note_id, deck_id, fields_text, tags_text),
                )
            return True
        except Exception as e:
            logger.error("Erreur lors de la synchronisation FTS5 de la note %s: %s", note_id, e)
            return False

    @classmethod
    def delete_note(cls, note_id: int, database: Database | None = None) -> bool:
        """Supprime une note de l'index FTS5."""
        target_db = _get_target_db(database)
        if not cls.is_available(target_db):
            return False

        try:
            with target_db.atomic():
                target_db.execute_sql("DELETE FROM note_fts WHERE note_id = ?;", (note_id,))
            return True
        except Exception as e:
            logger.error("Erreur lors de la suppression FTS5 de la note %s: %s", note_id, e)
            return False

    @classmethod
    def search(
        cls,
        query: str,
        deck_id: int | None = None,
        limit: int = 50,
        as_prefix: bool = True,
        database: Database | None = None,
    ) -> list[FTSSearchResult]:
        """Exécute une recherche FTS5 avec BM25 et extrait surligné.

        Retourne une liste de FTSSearchResult triée par pertinence BM25.
        """
        target_db = _get_target_db(database)
        if not cls.is_available(target_db):
            return []

        sanitized = sanitize_fts5_query(query, as_prefix=as_prefix)
        if not sanitized:
            return []

        try:
            if deck_id is not None:
                sql = """
                    SELECT note_id, deck_id, bm25(note_fts) as rank,
                           snippet(note_fts, -1, '<b>', '</b>', '...', 12) as snip
                    FROM note_fts
                    WHERE note_fts MATCH ? AND deck_id = ?
                    ORDER BY rank ASC
                    LIMIT ?;
                """
                cursor = target_db.execute_sql(sql, (sanitized, deck_id, limit))
            else:
                sql = """
                    SELECT note_id, deck_id, bm25(note_fts) as rank,
                           snippet(note_fts, -1, '<b>', '</b>', '...', 12) as snip
                    FROM note_fts
                    WHERE note_fts MATCH ?
                    ORDER BY rank ASC
                    LIMIT ?;
                """
                cursor = target_db.execute_sql(sql, (sanitized, limit))

            rows = cursor.fetchall()
            return [
                FTSSearchResult(
                    note_id=int(row[0]),
                    deck_id=int(row[1]) if row[1] is not None else 0,
                    rank=float(row[2]),
                    snippet=str(row[3] or ""),
                )
                for row in rows
            ]
        except Exception as e:
            logger.warning("Erreur lors de la recherche FTS5 pour '%s': %s", query, e)
            return []

    @classmethod
    def rebuild_fts(cls, database: Database | None = None) -> int:
        """Reconstruit entièrement l'index FTS5 à partir des notes existantes."""
        target_db = _get_target_db(database)
        if not cls.is_available(target_db):
            return 0

        try:
            sql_select = """
                SELECT n.id, n.tags, nv.content, c.deck_id
                FROM notemodel n
                JOIN noteversionmodel nv ON nv.note_id = n.id AND nv.is_active = 1
                LEFT JOIN cardmodel c ON c.note_id = n.id AND c.template_index = 0;
            """
            cursor = target_db.execute_sql(sql_select)
            rows = cursor.fetchall()

            insert_records: list[tuple[int, int, str, str]] = []
            for r in rows:
                n_id = int(r[0])
                tags_raw = r[1]
                content_raw = r[2]
                deck_id = int(r[3]) if r[3] is not None else 0

                fields_text = extract_fields_text(content_raw)
                tags_text = extract_tags_text(tags_raw)
                insert_records.append((n_id, deck_id, fields_text, tags_text))

            with target_db.atomic():
                target_db.execute_sql("DELETE FROM note_fts;")
                for rec in insert_records:
                    target_db.execute_sql(
                        "INSERT INTO note_fts (note_id, deck_id, fields_text, tags) VALUES (?, ?, ?, ?);",
                        rec,
                    )

            logger.info("FTS5 reconstruit avec succès : %d notes indexées.", len(insert_records))
            return len(insert_records)
        except Exception as e:
            logger.error("Erreur lors de la reconstruction FTS5 : %s", e)
            return 0
