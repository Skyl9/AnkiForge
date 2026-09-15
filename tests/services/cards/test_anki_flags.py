"""
Tests complets pour la gestion des drapeaux Anki (flags 1 à 7) :
- Persistance Peewee CardModel
- Migration 026
- Méthodes NoteRepository et syntaxe de recherche flag:X
- Importation & Exportation .apkg avec préservation des drapeaux
- Modèle virtuel NoteVirtualTableModel et FlagItemDelegate
"""

from __future__ import annotations

import importlib
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QStyleOptionViewItem

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    db,
)
from ankiforge.repositories.note_repository import NoteRepository
from ankiforge.services.cards.export_manager import ExportManager
from ankiforge.services.cards.import_manager import ImportManager
from ankiforge.ui.models.delegates import FLAG_ROLE, FlagItemDelegate
from ankiforge.ui.models.note_table_model import NoteVirtualTableModel

mig_026 = importlib.import_module("ankiforge.database.migrations.026_card_flags")


def test_card_model_flags_persistence() -> None:
    """Vérifie que CardModel persiste correctement le champ flags (0..7)."""
    deck = DeckModel.create(name="Flags::Deck")
    nt = NoteTypeModel.create(name="Flags::Model", fields_schema='["Front", "Back"]', templates="[]")
    note = NoteModel.create(note_type=nt)

    card1 = CardModel.create(note=note, deck=deck, template_index=0, flags=0)
    assert card1.flags == 0

    card2 = CardModel.create(note=note, deck=deck, template_index=1, flags=1)  # Rouge
    assert card2.flags == 1

    card3 = CardModel.create(note=note, deck=deck, template_index=2, flags=7)  # Violet
    assert card3.flags == 7

    # Relecture BDD
    reloaded = CardModel.get_by_id(card2.id)
    assert reloaded.flags == 1


def test_migration_026_idempotent() -> None:
    """Vérifie l'exécution sans erreur de la migration 026 sur cardmodel."""
    from peewee_migrate import Migrator

    migrator = Migrator(db)
    # Exécution de migrate (doit être idempotent)
    mig_026.migrate(migrator, db)
    cols = [col.name for col in db.get_columns("cardmodel")]
    assert "flags" in cols


def test_note_repository_flag_operations_and_search() -> None:
    """Teste set_card_flag, set_note_flag, get_note_flag et la syntaxe de recherche flag:X."""
    repo = NoteRepository()
    deck = DeckModel.create(name="Flags::RepoDeck")
    nt = repo.create_note_type("RepoFlagsModel", ["Front", "Back"], [{"name": "C1"}])

    note1 = repo.create_note(nt, deck, {"Front": "Atomique", "Back": "Wozniak"}, tags=["physics"])
    note2 = repo.create_note(nt, deck, {"Front": "Interférence", "Back": "Difficile"}, tags=["physics"])
    note3 = repo.create_note(nt, deck, {"Front": "Cellule", "Back": "Biologie"}, tags=["bio"])

    # Par défaut, aucun drapeau
    assert repo.get_note_flag(note1.id) == 0
    assert repo.get_note_flag(note2.id) == 0
    assert repo.get_note_flag(note3.id) == 0

    # Assigner flag 1 (Rouge) à note1
    assert repo.set_note_flag(note1.id, 1) is True
    assert repo.get_note_flag(note1.id) == 1

    # Assigner flag 4 (Bleu) à note2
    assert repo.set_note_flag(note2.id, 4) is True
    assert repo.get_note_flag(note2.id) == 4

    # Assigner flag individuel sur carte de note3
    c3 = repo.get_cards_by_note(note3.id)[0]
    assert repo.set_card_flag(c3.id, 3) is True  # Vert
    assert repo.get_note_flag(note3.id) == 3

    # Recherche par syntaxe flag:1
    res_flag1 = repo.search_notes("flag:1")
    assert len(res_flag1) == 1
    assert res_flag1[0].id == note1.id

    # Recherche par nom de couleur en anglais ou français flag:red / flag:rouge
    res_red = repo.search_notes("flag:red")
    assert len(res_red) == 1
    assert res_red[0].id == note1.id

    res_rouge = repo.search_notes("flag:rouge")
    assert len(res_rouge) == 1
    assert res_rouge[0].id == note1.id

    # Recherche flag:blue (note2)
    res_blue = repo.search_notes("flag:blue")
    assert len(res_blue) == 1
    assert res_blue[0].id == note2.id

    # Recherche combinée : texte + flag
    res_combined = repo.search_notes("Atomique flag:1")
    assert len(res_combined) == 1
    assert res_combined[0].id == note1.id

    res_combined_mismatch = repo.search_notes("Cellule flag:1")
    assert len(res_combined_mismatch) == 0

    # Recherche -flag:0 (toutes les notes avec un drapeau actif)
    res_flagged = repo.search_notes("-flag:0")
    assert len(res_flagged) == 3

    # Retirer le drapeau de note1 (flag 0)
    assert repo.set_note_flag(note1.id, 0) is True
    assert repo.get_note_flag(note1.id) == 0

    res_flagged_after = repo.search_notes("-flag:0")
    assert len(res_flagged_after) == 2


def test_export_manager_preserves_card_flags() -> None:
    """Vérifie que l'ExportManager sauvegarde fidèlement les drapeaux dans l'archive .apkg SQLite."""
    deck = DeckModel.create(name="Export::Deck")
    nt = NoteTypeModel.create(name="Export::Model", fields_schema='["Front", "Back"]', templates='[{"name":"Card 1","qfmt":"{{Front}}","afmt":"{{Back}}"}]')
    note = NoteModel.create(note_type=nt)
    note.add_version({"Front": "Capitale", "Back": "Paris"}, source="manual")

    # Carte avec drapeau 6 (Turquoise)
    CardModel.create(note=note, deck=deck, template_index=0, flags=6)

    export_mgr = ExportManager()
    with tempfile.NamedTemporaryFile(suffix=".apkg", delete=False) as tf:
        out_path = Path(tf.name)

    try:
        exported_count = export_mgr.export_package(
            output_path=out_path,
            deck_id=deck.id,
            status_filter="all",
            include_media=False,
        )
        assert exported_count == 1
        assert out_path.exists()

        # Inspection de la base SQLite interne de l'archive .apkg
        with zipfile.ZipFile(out_path, "r") as zf:
            zf.extract("collection.anki2", out_path.parent)

        anki_db_path = out_path.parent / "collection.anki2"
        conn = sqlite3.connect(str(anki_db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT ord, flags FROM cards")
        rows = cursor.fetchall()
        conn.close()
        anki_db_path.unlink(missing_ok=True)

        assert len(rows) == 1
        assert rows[0][0] == 0  # ord = 0
        assert rows[0][1] == 6  # flags = 6 (Turquoise)
    finally:
        out_path.unlink(missing_ok=True)


def test_import_manager_extracts_and_saves_flags() -> None:
    """Vérifie que l'ImportManager extrait et persiste les drapeaux depuis une archive Anki."""
    import_mgr = ImportManager()

    # Création d'une archive minimale de test avec flags = 5 (Rose)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_p = Path(tmpdir)
        anki_db = tmp_p / "collection.anki2"
        conn = sqlite3.connect(str(anki_db))
        c = conn.cursor()

        # Schema minimal Anki
        c.execute("""
            CREATE TABLE col (
                id integer primary key, crt integer, mod integer, scm integer, ver integer,
                dty integer, usn integer, ls integer, conf text, models text, decks text,
                dconf text, tags text
            );
        """)
        models_json = json.dumps(
            {
                "12345": {
                    "id": 12345,
                    "name": "TestModel",
                    "flds": [{"name": "Front"}, {"name": "Back"}],
                    "tmpls": [{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}],
                    "css": "",
                }
            }
        )
        decks_json = json.dumps({"1": {"id": 1, "name": "Default"}})
        c.execute("INSERT INTO col VALUES(1, 0, 0, 0, 11, 0, 0, 0, '', ?, ?, '', '')", (models_json, decks_json))

        c.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, mod integer, usn integer, tags text, flds text, sfld text, csum integer, flags integer, data text);")
        c.execute("INSERT INTO notes VALUES(1001, 'guid-flag-test', 12345, 0, -1, '', 'Question\x1fRéponse', 'Question', 0, 0, '')")

        c.execute("""
            CREATE TABLE cards (
                id integer primary key, nid integer, did integer, ord integer, mod integer,
                usn integer, type integer, queue integer, due integer, ivl integer, factor integer,
                reps integer, lapses integer, left integer, odue integer, odid integer,
                flags integer, data text
            );
        """)
        # Carte avec flags = 5 (Rose)
        c.execute("INSERT INTO cards VALUES(2001, 1001, 1, 0, 0, -1, 0, 0, 0, 10, 2500, 3, 0, 0, 0, 0, 5, '')")

        conn.commit()
        conn.close()

        # Emballage en zip .apkg
        apkg_path = tmp_p / "test_import_flags.apkg"
        with zipfile.ZipFile(apkg_path, "w") as zf:
            zf.write(anki_db, "collection.anki2")
            zf.writestr("media", "{}")

        analysis = import_mgr.analyze_archive(apkg_path)
        assert len(analysis.new_notes) == 1
        assert analysis.new_notes[0]["cards"][0]["flags"] == 5

        # Commit de l'import
        res = import_mgr.commit_import(analysis)
        assert res["created"] == 1

        # Vérification en BDD AnkiForge
        imported_note = NoteModel.get(NoteModel.guid == "guid-flag-test")
        cards = list(CardModel.select().where(CardModel.note == imported_note))
        assert len(cards) == 1
        assert cards[0].flags == 5


def test_note_virtual_table_model_and_flag_delegate() -> None:
    """Vérifie l'affichage et la mise à jour des drapeaux dans NoteVirtualTableModel et FlagItemDelegate."""
    deck = DeckModel.create(name="Table::Deck")
    nt = NoteTypeModel.create(name="Table::Model", fields_schema='["Front", "Back"]', templates="[]")
    note = NoteModel.create(note_type=nt)
    note.add_version({"Front": "Cellule", "Back": "Noyau"}, source="manual")
    CardModel.create(note=note, deck=deck, template_index=0, flags=2)  # Orange

    model = NoteVirtualTableModel(query=NoteModel.select())
    assert model.columnCount() == 7  # Checkbox, Flag, Recto, Autres, Modèle, Deck, Tags
    assert model.rowCount() >= 1

    row_idx = model.find_row_by_note_id(note.id)
    assert row_idx >= 0

    # Lecture via data()
    flag_idx = model.index(row_idx, 1)
    assert model.data(flag_idx, FLAG_ROLE) == 2
    assert "Orange" in str(model.data(flag_idx, Qt.ItemDataRole.ToolTipRole))

    # Mise à jour directe du drapeau
    model.update_note_flag(note.id, 7)  # Violet
    assert model.data(flag_idx, FLAG_ROLE) == 7
    assert "Violet" in str(model.data(flag_idx, Qt.ItemDataRole.ToolTipRole))

    # Test graphique sans crash du FlagItemDelegate
    delegate = FlagItemDelegate()
    img = QImage(64, 34, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(img)
    option = QStyleOptionViewItem()
    option.rect.setRect(0, 0, 32, 34)

    # Peinture avec drapeau
    delegate.paint(painter, option, flag_idx)

    # Peinture sans drapeau
    model.update_note_flag(note.id, 0)
    delegate.paint(painter, option, flag_idx)
    painter.end()
