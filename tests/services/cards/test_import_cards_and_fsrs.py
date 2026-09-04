import sqlite3
import zipfile
from pathlib import Path

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
)
from ankiforge.services.cards.import_manager import ImportManager


def test_import_multi_cards_per_note(tmp_path: Path) -> None:
    """Vérifie qu'une note générant plusieurs cartes crée bien plusieurs CardModel (ord=0, ord=1)."""
    db_file = tmp_path / "multicard.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    cursor.execute("CREATE TABLE col (id integer, models text, decks text)")
    models_raw = '{"1": {"name": "Basic (and reversed)", "flds": [{"name": "Front"}, {"name": "Back"}]}}'
    decks_raw = '{"1": {"id": 1, "name": "Default"}}'
    cursor.execute("INSERT INTO col VALUES (1, ?, ?)", (models_raw, decks_raw))

    cursor.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, tags text, flds text)")
    cursor.execute("INSERT INTO notes VALUES (10, 'guid_multi_1', 1, '', 'Question\x1fReponse')")

    # 2 cartes pour la note 10 : ord=0 (Recto) et ord=1 (Verso)
    cursor.execute("CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer, ivl integer, reps integer, lapses integer)")
    cursor.execute("INSERT INTO cards VALUES (101, 10, 1, 0, 10, 3, 0)")
    cursor.execute("INSERT INTO cards VALUES (102, 10, 1, 1, 15, 4, 1)")

    conn.commit()
    conn.close()

    apkg_path = tmp_path / "multicard.apkg"
    with zipfile.ZipFile(apkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", "{}")

    manager = ImportManager()
    analysis = manager.analyze_archive(apkg_path)

    assert len(analysis.new_notes) == 1
    cards_declared = analysis.new_notes[0]["cards"]
    assert len(cards_declared) == 2
    assert cards_declared[0]["ord"] == 0
    assert cards_declared[1]["ord"] == 1

    summary = manager.commit_import(analysis)
    assert summary["created"] == 1

    note = NoteModel.get(NoteModel.guid == "guid_multi_1")
    cards = list(CardModel.select().where(CardModel.note == note).order_by(CardModel.template_index))
    assert len(cards) == 2

    # Carte 0
    assert cards[0].template_index == 0
    assert cards[0].ivl == 10
    assert cards[0].reps == 3
    assert cards[0].lapses == 0

    # Carte 1
    assert cards[1].template_index == 1
    assert cards[1].ivl == 15
    assert cards[1].reps == 4
    assert cards[1].lapses == 1


def test_import_cloze_cards_multi_decks(tmp_path: Path) -> None:
    """Vérifie que les cartes Cloze d'une note peuvent appartenir à des paquets distincts."""
    db_file = tmp_path / "cloze.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    cursor.execute("CREATE TABLE col (id integer, models text, decks text)")
    models_raw = '{"1": {"name": "Cloze", "flds": [{"name": "Text"}, {"name": "Extra"}]}}'
    decks_raw = '{"10": {"id": 10, "name": "Sciences"}, "20": {"id": 20, "name": "Histoire"}}'
    cursor.execute("INSERT INTO col VALUES (1, ?, ?)", (models_raw, decks_raw))

    cursor.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, tags text, flds text)")
    cursor.execute("INSERT INTO notes VALUES (20, 'guid_cloze_1', 1, '', 'En {{c1::1789}}, Lavoisier publie {{c2::Traite elementaire}}.\x1fNote')")

    cursor.execute("CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer, ivl integer, reps integer, lapses integer)")
    cursor.execute("INSERT INTO cards VALUES (201, 20, 10, 0, 5, 2, 0)")
    cursor.execute("INSERT INTO cards VALUES (202, 20, 20, 1, 8, 3, 0)")

    conn.commit()
    conn.close()

    apkg_path = tmp_path / "cloze.apkg"
    with zipfile.ZipFile(apkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", "{}")

    manager = ImportManager()
    analysis = manager.analyze_archive(apkg_path)

    summary = manager.commit_import(analysis)
    assert summary["created"] == 1

    note = NoteModel.get(NoteModel.guid == "guid_cloze_1")
    cards = list(CardModel.select().where(CardModel.note == note).order_by(CardModel.template_index))
    assert len(cards) == 2

    # Vérification des decks distincts
    deck_sciences = DeckModel.get(DeckModel.name == "Sciences")
    deck_histoire = DeckModel.get(DeckModel.name == "Histoire")

    assert cards[0].deck == deck_sciences
    assert cards[1].deck == deck_histoire


def test_silent_update_updates_existing_card_stats(tmp_path: Path) -> None:
    """Vérifie qu'un second import synchronise silencieusement les statistiques de révision des cartes."""
    db_file1 = tmp_path / "run1.db"
    conn = sqlite3.connect(str(db_file1))
    conn.execute("CREATE TABLE col (id integer, models text, decks text)")
    conn.execute('INSERT INTO col VALUES (1, \'{"1": {"name": "Basic", "flds": [{"name": "Front"}, {"name": "Back"}]}}\', \'{"1": {"id": 1, "name": "Default"}}\')')
    conn.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, tags text, flds text)")
    conn.execute("INSERT INTO notes VALUES (30, 'guid_srs_sync', 1, '', 'Q1\x1fR1')")
    conn.execute("CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer, ivl integer, reps integer, lapses integer)")
    conn.execute("INSERT INTO cards VALUES (301, 30, 1, 0, 1, 1, 0)")
    conn.commit()
    conn.close()

    apkg_v1 = tmp_path / "v1.apkg"
    with zipfile.ZipFile(apkg_v1, "w") as zf:
        zf.write(db_file1, "collection.anki2")
        zf.writestr("media", "{}")

    manager = ImportManager()
    analysis1 = manager.analyze_archive(apkg_v1)
    manager.commit_import(analysis1)

    # Vérification état initial
    note = NoteModel.get(NoteModel.guid == "guid_srs_sync")
    c1 = CardModel.get(CardModel.note == note, CardModel.template_index == 0)
    assert c1.ivl == 1
    assert c1.reps == 1

    # Deuxième import : mêmes cartes mais l'utilisateur a révisé dans Anki
    db_file2 = tmp_path / "run2.db"
    conn2 = sqlite3.connect(str(db_file2))
    conn2.execute("CREATE TABLE col (id integer, models text, decks text)")
    conn2.execute('INSERT INTO col VALUES (1, \'{"1": {"name": "Basic", "flds": [{"name": "Front"}, {"name": "Back"}]}}\', \'{"1": {"id": 1, "name": "Default"}}\')')
    conn2.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, tags text, flds text)")
    conn2.execute("INSERT INTO notes VALUES (30, 'guid_srs_sync', 1, '', 'Q1\x1fR1')")
    conn2.execute("CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer, ivl integer, reps integer, lapses integer)")
    conn2.execute("INSERT INTO cards VALUES (301, 30, 1, 0, 21, 6, 2)")
    conn2.commit()
    conn2.close()

    apkg_v2 = tmp_path / "v2.apkg"
    with zipfile.ZipFile(apkg_v2, "w") as zf:
        zf.write(db_file2, "collection.anki2")
        zf.writestr("media", "{}")

    analysis2 = manager.analyze_archive(apkg_v2)
    assert len(analysis2.conflicts) == 0
    assert len(analysis2.silent_updates) == 1

    summary2 = manager.commit_import(analysis2)
    assert summary2["updated"] == 1

    # Les stats de révision ont été mises à jour sans conflit
    c1 = CardModel.get_by_id(c1.id)
    assert c1.ivl == 21
    assert c1.reps == 6
    assert c1.lapses == 2
