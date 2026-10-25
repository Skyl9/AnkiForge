"""Tests pour la migration 048_add_note_sort_field et le calcul de sort_field."""

from __future__ import annotations

import importlib
import json
import sqlite3
from pathlib import Path

import peewee as pw
import pytest

from ankiforge.utils.anki_renderer import compute_sort_field, strip_html_for_sort

mig_048 = importlib.import_module("ankiforge.database.migrations.048_add_note_sort_field")


@pytest.mark.unit
def test_strip_html_for_sort() -> None:
    assert strip_html_for_sort(None) == ""
    assert strip_html_for_sort("") == ""
    assert strip_html_for_sort("Simple texte") == "Simple texte"
    assert strip_html_for_sort("<b>Gras</b> et <i>Italique</i>") == "Gras et Italique"
    assert strip_html_for_sort("&nbsp;Café &amp; Thé&nbsp;") == "Café & Thé"
    assert strip_html_for_sort('<img src="test.jpg"> Image') == "test.jpg Image"
    assert strip_html_for_sort("[sound:audio.mp3] Audio") == "audio.mp3 Audio"
    assert strip_html_for_sort("<div>Multi<br>ligne \n et   espaces</div>") == "Multi ligne et espaces"


@pytest.mark.unit
def test_compute_sort_field() -> None:
    # 1. Dictionnaire standard (premier champ non-vide)
    data = {"Front": "<b>Mitochondrie</b>", "Back": "Centrale énergétique"}
    assert compute_sort_field(data) == "Mitochondrie"

    # 2. Premier champ vide -> repli sur le second champ non-vide
    data_empty_front = {"Front": "  ", "Back": "Définition importante"}
    assert compute_sort_field(data_empty_front) == "Définition importante"

    # 3. Tous les champs vides
    data_all_empty = {"Front": "", "Back": "  "}
    assert compute_sort_field(data_all_empty) == ""

    # 4. Clés internes ignorées (_orphaned_fields)
    data_orphaned = {"_orphaned_fields": "Ignoré", "Front": "Question réelle"}
    assert compute_sort_field(data_orphaned) == "Question réelle"

    # 5. Chaîne JSON
    json_str = json.dumps({"Recto": "Paris", "Verso": "France"})
    assert compute_sort_field(json_str) == "Paris"

    # 6. Liste ordonnée
    fields_list = ["", "Deuxième élément", "Troisième"]
    assert compute_sort_field(fields_list) == "Deuxième élément"

    # 7. Troncature à 512 caractères
    long_text = {"Front": "A" * 600}
    assert len(compute_sort_field(long_text)) == 512


@pytest.mark.integration
def test_migration_048_add_note_sort_field_and_backfill(tmp_path: Path) -> None:
    """Vérifie que la migration 048 ajoute la colonne sort_field, effectue le backfill et supporte le rollback."""
    db_file = tmp_path / "test_mig_048.db"
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()

    # Création manuelle d'un schéma simplifié avant migration 048
    cur.execute("""
        CREATE TABLE notemodel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT UNIQUE,
            tags TEXT,
            status TEXT DEFAULT 'new'
        )
    """)
    cur.execute("""
        CREATE TABLE noteversionmodel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id INTEGER,
            version_number INTEGER,
            content TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)

    # Insertion de notes et versions
    cur.execute("INSERT INTO notemodel (id, guid, status) VALUES (1, 'guid-1', 'new')")
    cur.execute("INSERT INTO notemodel (id, guid, status) VALUES (2, 'guid-2', 'new')")
    cur.execute("INSERT INTO notemodel (id, guid, status) VALUES (3, 'guid-3', 'new')")

    # Version active pour note 1
    c1 = json.dumps({"Front": "<b>Concept 1</b>", "Back": "Explication 1"})
    cur.execute("INSERT INTO noteversionmodel (note_id, version_number, content, is_active) VALUES (1, 1, ?, 1)", (c1,))

    # Version inactive v1 et active v2 pour note 2
    c2_old = json.dumps({"Front": "Ancien titre", "Back": "Ancien"})
    c2_act = json.dumps({"Front": "<i>Nouveau Titre</i>", "Back": "Nouveau"})
    cur.execute("INSERT INTO noteversionmodel (note_id, version_number, content, is_active) VALUES (2, 1, ?, 0)", (c2_old,))
    cur.execute("INSERT INTO noteversionmodel (note_id, version_number, content, is_active) VALUES (2, 2, ?, 1)", (c2_act,))

    # Note 3 sans version
    conn.commit()
    conn.close()

    # Exécution de la migration 048
    test_db = pw.SqliteDatabase(str(db_file))
    from peewee_migrate import Migrator

    migrator = Migrator(test_db)
    mig_048.migrate(migrator, test_db)

    # Vérifications
    check_conn = sqlite3.connect(str(db_file))
    check_cur = check_conn.cursor()

    # Vérifier que la colonne sort_field existe
    check_cur.execute("PRAGMA table_info(notemodel)")
    columns = [row[1] for row in check_cur.fetchall()]
    assert "sort_field" in columns

    # Vérifier le backfill
    check_cur.execute("SELECT id, sort_field FROM notemodel ORDER BY id ASC")
    rows = check_cur.fetchall()
    assert rows[0] == (1, "Concept 1")
    assert rows[1] == (2, "Nouveau Titre")
    assert rows[2] == (3, "")

    check_conn.close()

    # Vérifier le rollback
    mig_048.rollback(migrator, test_db)
    post_conn = sqlite3.connect(str(db_file))
    post_cur = post_conn.cursor()
    post_cur.execute("PRAGMA table_info(notemodel)")
    post_columns = [row[1] for row in post_cur.fetchall()]
    assert "sort_field" not in post_columns
    post_conn.close()
