"""Test de la migration 046 : suppression des tables consultant_sessions et consultant_messages."""

import importlib

import pytest
from peewee_migrate import Migrator

from ankiforge.database.migration import run_migrations
from ankiforge.database.models import db

pytestmark = pytest.mark.integration


def test_migration_046_drops_consultant_tables(mock_db):
    """Vérifie que la migration 046 supprime proprement les tables de chat consultant."""
    run_migrations()

    mod_046 = importlib.import_module("ankiforge.database.migrations.046_drop_consultant_chat_tables")
    migrate_046 = mod_046.migrate

    # Recréer explicitement les tables pour tester leur suppression
    db.execute_sql("CREATE TABLE IF NOT EXISTS consultant_sessions (id INTEGER PRIMARY KEY, title TEXT);")
    db.execute_sql("CREATE TABLE IF NOT EXISTS consultant_messages (id INTEGER PRIMARY KEY, session_id INTEGER, role TEXT, content TEXT);")
    assert db.table_exists("consultant_sessions")
    assert db.table_exists("consultant_messages")

    migrator = Migrator(db)
    migrate_046(migrator, db)

    # Vérifier que les tables n'existent plus
    assert not db.table_exists("consultant_messages")
    assert not db.table_exists("consultant_sessions")
