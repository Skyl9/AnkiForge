import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
import zstandard as zstd

from ankiforge.database.models import (
    DeckModel,
    NoteModel,
)
from ankiforge.services.cards.import_manager import ImportManager


def test_import_legacy_apkg_collection_anki2(tmp_path: Path) -> None:
    """Vérifie l'importation d'une archive legacy Anki 2.0 (collection.anki2 avec JSON dans col)."""
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    models_json = {
        "1001": {
            "name": "CustomCardModel",
            "flds": [{"name": "Mot"}, {"name": "Sens"}, {"name": "Exemple"}],
            "tmpls": [{"name": "Recto->Verso", "qfmt": "{{Mot}}", "afmt": "{{FrontSide}}<hr>{{Sens}}<br>{{Exemple}}"}],
            "css": ".card { color: #333; }",
        }
    }
    decks_json = {
        "1": {"id": 1, "name": "Default"},
        "20": {"id": 20, "name": "Langues::Anglais::Vocabulaire"},
    }

    cursor.execute(
        "CREATE TABLE col (id integer, crt integer, mod integer, scm integer, ver integer, "
        "dcount integer, dsz integer, mtime_v integer, a integer, c integer, ctime integer, "
        "conf text, models text, decks text, dconf text, tags text)"
    )
    cursor.execute(
        "INSERT INTO col VALUES (1, 0, 0, 0, 11, 0, 0, 0, 0, 0, 0, '{}', ?, ?, '{}', '{}')",
        (json.dumps(models_json), json.dumps(decks_json)),
    )
    cursor.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, mod integer, usn integer, tags text, flds text, sfld text, csum integer, flags integer, data text)")
    cursor.execute("INSERT INTO notes VALUES (1, 'guid_leg_1', 1001, 0, 0, ' eng tag ', 'Apple\x1fPomme\x1fAn apple a day', 'Apple', 0, 0, '')")
    cursor.execute(
        "CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer, mod integer, "
        "usn integer, type integer, queue integer, due integer, ivl integer, factor integer, "
        "reps integer, lapses integer, left integer, odue integer, odid integer, flags integer, data text)"
    )
    cursor.execute("INSERT INTO cards VALUES (101, 1, 20, 0, 0, 0, 0, 0, 0, 5, 2500, 2, 0, 0, 0, 0, 0, '')")

    conn.commit()
    conn.close()

    apkg_path = tmp_path / "legacy_deck.apkg"
    with zipfile.ZipFile(apkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", "{}")

    manager = ImportManager()
    analysis = manager.analyze_archive(apkg_path)

    assert analysis.source_type == "apkg"
    assert len(analysis.new_notes) == 1
    assert analysis.new_notes[0]["deck_name"] == "Langues::Anglais::Vocabulaire"
    assert analysis.new_notes[0]["notetype_name"] == "CustomCardModel"
    assert analysis.new_notes[0]["field_names"] == ["Mot", "Sens", "Exemple"]
    assert analysis.new_notes[0]["content"] == {
        "Mot": "Apple",
        "Sens": "Pomme",
        "Exemple": "An apple a day",
    }

    summary = manager.commit_import(analysis)
    assert summary["created"] == 1

    note = NoteModel.get(NoteModel.guid == "guid_leg_1")
    assert note.note_type.name == "CustomCardModel"
    assert "Mot" in note.note_type.fields_schema
    assert note.note_type.css_style == ".card { color: #333; }"

    # Vérification de l'arborescence récursive du deck
    deep_deck = DeckModel.get(DeckModel.name == "Langues::Anglais::Vocabulaire")
    assert deep_deck.parent_deck is not None
    assert deep_deck.parent_deck.name == "Langues::Anglais"
    assert deep_deck.parent_deck.parent_deck is not None
    assert deep_deck.parent_deck.parent_deck.name == "Langues"


def test_import_modern_apkg_collection_anki21_uncompressed(tmp_path: Path) -> None:
    """Vérifie l'importation d'une base moderne Anki 2.1 uncompressed (collection.anki21 avec tables normalisées)."""
    db_file = tmp_path / "modern21.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    cursor.execute("CREATE TABLE col (id integer, crt integer, mod integer, scm integer, ver integer, dcount integer, dsz integer, mtime_v integer, a integer, c integer, ctime integer, conf text)")
    cursor.execute("INSERT INTO col VALUES (1, 0, 0, 0, 16, 0, 0, 0, 0, 0, 0, '{}')")

    cursor.execute("CREATE TABLE decks (id integer primary key, name text, mtime_secs integer, usn integer, common text)")
    cursor.execute("INSERT INTO decks VALUES (1, 'Default', 0, 0, '')")
    cursor.execute("INSERT INTO decks VALUES (50, 'Sciences\x1fBiologie', 0, 0, '')")

    cursor.execute("CREATE TABLE notetypes (id integer primary key, name text, mtime_secs integer, usn integer, config blob)")
    cursor.execute("INSERT INTO notetypes VALUES (2002, 'BioModel', 0, 0, X'1a00')")

    cursor.execute("CREATE TABLE fields (ntid integer, ord integer, name text, config blob, primary key(ntid, ord))")
    cursor.execute("INSERT INTO fields VALUES (2002, 0, 'Organisme', X'')")
    cursor.execute("INSERT INTO fields VALUES (2002, 1, 'Caracteristique', X'')")

    cursor.execute("CREATE TABLE templates (ntid integer, ord integer, name text, mtime_secs integer, usn integer, config blob, primary key(ntid, ord))")
    cursor.execute("INSERT INTO templates VALUES (2002, 0, 'Carte Organisme', 0, 0, X'')")

    cursor.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, mod integer, usn integer, tags text, flds text, sfld text, csum integer, flags integer, data text)")
    cursor.execute("INSERT INTO notes VALUES (10, 'guid_bio_1', 2002, 0, 0, 'bio cell', 'Mitochondrie\x1fCentrale energetique', 'Mitochondrie', 0, 0, '')")

    cursor.execute(
        "CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer, mod integer, "
        "usn integer, type integer, queue integer, due integer, ivl integer, factor integer, "
        "reps integer, lapses integer, left integer, odue integer, odid integer, flags integer, data text)"
    )
    cursor.execute("INSERT INTO cards VALUES (500, 10, 50, 0, 0, 0, 0, 0, 0, 10, 2500, 3, 0, 0, 0, 0, 0, '')")

    conn.commit()
    conn.close()

    apkg_path = tmp_path / "modern21.apkg"
    with zipfile.ZipFile(apkg_path, "w") as zf:
        zf.write(db_file, "collection.anki21")
        zf.writestr("media", "{}")

    manager = ImportManager()
    analysis = manager.analyze_archive(apkg_path)

    assert analysis.source_type == "apkg"
    assert len(analysis.new_notes) == 1
    note_info = analysis.new_notes[0]
    assert note_info["deck_name"] == "Sciences::Biologie"
    assert note_info["notetype_name"] == "BioModel"
    assert note_info["field_names"] == ["Organisme", "Caracteristique"]
    assert note_info["content"] == {"Organisme": "Mitochondrie", "Caracteristique": "Centrale energetique"}

    summary = manager.commit_import(analysis)
    assert summary["created"] == 1

    deck = DeckModel.get(DeckModel.name == "Sciences::Biologie")
    assert deck.parent_deck.name == "Sciences"


def test_import_modern_apkg_collection_anki21b_zstd_compressed(tmp_path: Path) -> None:
    """Vérifie l'importation d'une base Anki 2.1.50+ compressée en Zstandard (collection.anki21b)."""
    db_file = tmp_path / "modern21b_raw.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    cursor.execute("CREATE TABLE col (id integer, conf text)")
    cursor.execute("INSERT INTO col VALUES (1, '{}')")
    cursor.execute("CREATE TABLE decks (id integer primary key, name text)")
    cursor.execute("INSERT INTO decks VALUES (1, 'Default')")
    cursor.execute("INSERT INTO decks VALUES (99, 'Histoire\x1fFrance')")
    cursor.execute("CREATE TABLE notetypes (id integer primary key, name text, config blob)")
    cursor.execute("INSERT INTO notetypes VALUES (3003, 'HistoireModel', X'')")
    cursor.execute("CREATE TABLE fields (ntid integer, ord integer, name text, config blob)")
    cursor.execute("INSERT INTO fields VALUES (3003, 0, 'Evenement', X'')")
    cursor.execute("INSERT INTO fields VALUES (3003, 1, 'Date', X'')")
    cursor.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, tags text, flds text)")
    cursor.execute("INSERT INTO notes VALUES (20, 'guid_hist_1', 3003, 'rev', 'Prise de la Bastille\x1f14 Juillet 1789')")
    cursor.execute("CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer)")
    cursor.execute("INSERT INTO cards VALUES (600, 20, 99, 0)")

    conn.commit()
    conn.close()

    with open(db_file, "rb") as f:
        compressed_db = zstd.compress(f.read())

    apkg_path = tmp_path / "compressed_deck.apkg"
    with zipfile.ZipFile(apkg_path, "w") as zf:
        zf.writestr("collection.anki21b", compressed_db)
        zf.writestr("media", "{}")

    manager = ImportManager()
    analysis = manager.analyze_archive(apkg_path)

    assert len(analysis.new_notes) == 1
    assert analysis.new_notes[0]["deck_name"] == "Histoire::France"
    assert analysis.new_notes[0]["content"] == {"Evenement": "Prise de la Bastille", "Date": "14 Juillet 1789"}

    summary = manager.commit_import(analysis)
    assert summary["created"] == 1


def test_import_database_priority_anki21b_over_anki2(tmp_path: Path) -> None:
    """Vérifie que collection.anki21b prévaut sur collection.anki2 lorsqu'ambiguïté dans le zip."""
    db_legacy = tmp_path / "legacy.db"
    conn_leg = sqlite3.connect(str(db_legacy))
    conn_leg.execute("CREATE TABLE col (id integer, models text, decks text)")
    conn_leg.execute('INSERT INTO col VALUES (1, \'{}\', \'{"1": {"id": 1, "name": "LegacyDeck"}}\')')
    conn_leg.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, tags text, flds text)")
    conn_leg.execute("INSERT INTO notes VALUES (1, 'guid_leg_only', 1, '', 'Legacy Question\x1fLegacy Answer')")
    conn_leg.execute("CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer)")
    conn_leg.execute("INSERT INTO cards VALUES (1, 1, 1, 0)")
    conn_leg.commit()
    conn_leg.close()

    db_modern = tmp_path / "modern.db"
    conn_mod = sqlite3.connect(str(db_modern))
    conn_mod.execute("CREATE TABLE col (id integer)")
    conn_mod.execute("INSERT INTO col VALUES (1)")
    conn_mod.execute("CREATE TABLE decks (id integer primary key, name text)")
    conn_mod.execute("INSERT INTO decks VALUES (2, 'ModernDeck')")
    conn_mod.execute("CREATE TABLE notetypes (id integer primary key, name text, config blob)")
    conn_mod.execute("INSERT INTO notetypes VALUES (2, 'ModernModel', X'')")
    conn_mod.execute("CREATE TABLE fields (ntid integer, ord integer, name text, config blob)")
    conn_mod.execute("INSERT INTO fields VALUES (2, 0, 'Front', X'')")
    conn_mod.execute("INSERT INTO fields VALUES (2, 1, 'Back', X'')")
    conn_mod.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, tags text, flds text)")
    conn_mod.execute("INSERT INTO notes VALUES (2, 'guid_mod_real', 2, '', 'Modern Question\x1fModern Answer')")
    conn_mod.execute("CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer)")
    conn_mod.execute("INSERT INTO cards VALUES (2, 2, 2, 0)")
    conn_mod.commit()
    conn_mod.close()

    with open(db_modern, "rb") as f:
        comp_mod = zstd.compress(f.read())

    dual_apkg = tmp_path / "dual.apkg"
    with zipfile.ZipFile(dual_apkg, "w") as zf:
        zf.write(db_legacy, "collection.anki2")
        zf.writestr("collection.anki21b", comp_mod)
        zf.writestr("media", "{}")

    manager = ImportManager()
    analysis = manager.analyze_archive(dual_apkg)

    # Doit avoir choisi la base moderne anki21b
    assert len(analysis.new_notes) == 1
    assert analysis.new_notes[0]["guid"] == "guid_mod_real"
    assert analysis.new_notes[0]["deck_name"] == "ModernDeck"


def test_import_corrupted_archive_raises_value_error(tmp_path: Path) -> None:
    """Vérifie le rejet propre d'un fichier corrompu ou non-zip."""
    bad_file = tmp_path / "fake.apkg"
    bad_file.write_text("not a zip archive")

    manager = ImportManager()
    with pytest.raises(ValueError, match="n'est pas une archive ZIP/APKG valide"):
        manager.analyze_archive(bad_file)


def test_import_zip_without_collection_db_raises_file_not_found(tmp_path: Path) -> None:
    """Vérifie qu'un zip sans base collection.anki* lève FileNotFoundError."""
    empty_zip = tmp_path / "empty.apkg"
    with zipfile.ZipFile(empty_zip, "w") as zf:
        zf.writestr("dummy.txt", "hello")

    manager = ImportManager()
    with pytest.raises(FileNotFoundError, match="Aucune base SQLite Anki"):
        manager.analyze_archive(empty_zip)
