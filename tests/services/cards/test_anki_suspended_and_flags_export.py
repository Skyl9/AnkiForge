"""
Tests complets pour la gestion des cartes suspendues et drapeaux Anki :
- Persistance Peewee CardModel (is_suspended)
- Migration 027
- Méthodes NoteRepository (suspend_card, suspend_note, is_note_suspended) et syntaxe is:suspended / -is:suspended
- Exportation .apkg avec SQLite queue == -1 et synchronisation des tags (flag::<color>, is::suspended)
- Importation .apkg avec extraction de queue == -1 ➔ is_suspended = True
- Modèle virtuel NoteVirtualTableModel (rôle IS_SUSPENDED_ROLE, BackgroundRole amber, suffixe ⏸️)
- EditionView bascule suspend (! / Ctrl+J) et filtrage statut (Actives / Suspendues)
"""

from __future__ import annotations

import importlib
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

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
from ankiforge.ui.models.delegates import IS_SUSPENDED_ROLE
from ankiforge.ui.models.note_table_model import NoteVirtualTableModel

mig_027 = importlib.import_module("ankiforge.database.migrations.027_card_suspended")


def test_card_model_suspended_persistence() -> None:
    """Vérifie que CardModel persiste correctement le champ is_suspended."""
    deck = DeckModel.create(name="Suspended::Deck")
    nt = NoteTypeModel.create(name="Suspended::Model", fields_schema='["Front", "Back"]', templates="[]")
    note = NoteModel.create(note_type=nt)

    card1 = CardModel.create(note=note, deck=deck, template_index=0, is_suspended=False)
    assert card1.is_suspended is False

    card2 = CardModel.create(note=note, deck=deck, template_index=1, is_suspended=True)
    assert card2.is_suspended is True

    # Relecture BDD
    reloaded = CardModel.get_by_id(card2.id)
    assert reloaded.is_suspended is True


def test_migration_027_idempotent() -> None:
    """Vérifie l'exécution sans erreur de la migration 027 sur cardmodel."""
    from peewee_migrate import Migrator

    migrator = Migrator(db)
    mig_027.migrate(migrator, db)
    cols = [col.name for col in db.get_columns("cardmodel")]
    assert "is_suspended" in cols


def test_note_repository_suspend_operations_and_search() -> None:
    """Teste suspend_card, suspend_note, is_note_suspended et la syntaxe is:suspended."""
    repo = NoteRepository()
    deck = DeckModel.create(name="Suspended::RepoDeck")
    nt = repo.create_note_type("RepoSuspModel", ["Front", "Back"], [{"name": "C1"}, {"name": "C2"}])

    note1 = repo.create_note(nt, deck, {"Front": "Question 1", "Back": "Reponse 1"}, tags=["science"])
    note2 = repo.create_note(nt, deck, {"Front": "Question 2", "Back": "Reponse 2"}, tags=["science"])

    # Initialement actives
    assert repo.is_note_suspended(note1.id) is False
    assert repo.is_note_suspended(note2.id) is False

    # Suspendre note 1
    assert repo.suspend_note(note1.id, suspend=True) is True
    assert repo.is_note_suspended(note1.id) is True

    # Vérifier que toutes les cartes de note 1 sont suspendues
    c1_cards = repo.get_cards_by_note(note1.id)
    assert all(c.is_suspended for c in c1_cards)

    # Réactiver une seule carte de note 1 -> la note n'est plus entièrement suspendue
    assert repo.suspend_card(c1_cards[0].id, suspend=False) is True
    assert repo.is_note_suspended(note1.id) is False

    # Réactiver toute la note 1
    assert repo.suspend_note(note1.id, suspend=False) is True
    assert repo.is_note_suspended(note1.id) is False

    # Suspendre note 2
    repo.suspend_note(note2.id, suspend=True)

    # Recherche par syntaxe is:suspended
    res_suspended = repo.search_notes("is:suspended")
    assert any(n.id == note2.id for n in res_suspended)
    assert not any(n.id == note1.id for n in res_suspended)

    # Recherche par syntaxe -is:suspended
    res_active = repo.search_notes("-is:suspended")
    assert any(n.id == note1.id for n in res_active)
    assert not any(n.id == note2.id for n in res_active)


def test_export_apkg_with_suspension_and_flags_tags() -> None:
    """Vérifie l'exportation .apkg avec SQLite queue == -1 et synchronisation des tags."""
    repo = NoteRepository()
    export_mgr = ExportManager()

    deck = DeckModel.create(name="Export::SuspendedDeck")
    nt = repo.create_note_type("ExportSuspModel", ["Front", "Back"], [{"name": "C1"}])
    note = repo.create_note(nt, deck, {"Front": "Anatomie", "Back": "Cortex"}, tags=["med"])

    # Assigner flag 3 (Vert) et suspendre la carte
    cards = repo.get_cards_by_note(note.id)
    c = cards[0]
    repo.set_card_flag(c.id, 3)
    repo.suspend_card(c.id, suspend=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "test_suspended_export.apkg"
        exported = export_mgr.export_package(
            output_path=out_path,
            deck_id=deck.id,
            status_filter="all",
            include_media=False,
            sync_flags_and_suspension_tags=True,
        )
        assert exported == 1
        assert out_path.exists()

        # Extraire et inspecter collection.anki2
        with zipfile.ZipFile(out_path, "r") as zf:
            zf.extract("collection.anki2", tmpdir)

        anki_db_path = Path(tmpdir) / "collection.anki2"
        conn = sqlite3.connect(str(anki_db_path))
        cur = conn.cursor()

        # Vérifier cards: queue == -1 (suspendu) et flags == 3 (Vert)
        cur.execute("SELECT queue, flags FROM cards")
        c_row = cur.fetchone()
        assert c_row is not None
        assert c_row[0] == -1  # queue = -1 (suspendu)
        assert c_row[1] == 3  # flags = 3

        # Vérifier notes tags: doit contenir flag::vert et is::suspended
        cur.execute("SELECT tags FROM notes")
        n_row = cur.fetchone()
        assert n_row is not None
        tags_str = n_row[0]
        assert "flag::vert" in tags_str
        assert "is::suspended" in tags_str
        assert "med" in tags_str

        conn.close()


def test_import_manager_extracts_and_saves_suspended() -> None:
    """Vérifie que ImportManager extrait queue == -1 pour marquer la carte is_suspended = True."""
    import_mgr = ImportManager()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_p = Path(tmpdir)
        anki_db = tmp_p / "collection.anki2"
        conn = sqlite3.connect(str(anki_db))
        c = conn.cursor()

        c.execute("""
            CREATE TABLE col (
                id integer primary key, crt integer, mod integer, scm integer, ver integer,
                dty integer, usn integer, ls integer, conf text, models text, decks text,
                dconf text, tags text
            );
        """)
        models_json = json.dumps(
            {
                "54321": {
                    "id": 54321,
                    "name": "SuspendedImportModel",
                    "flds": [{"name": "Front"}, {"name": "Back"}],
                    "tmpls": [{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}],
                    "css": "",
                }
            }
        )
        decks_json = json.dumps({"1": {"id": 1, "name": "Default"}})
        c.execute("INSERT INTO col VALUES(1, 0, 0, 0, 11, 0, 0, 0, '', ?, ?, '', '')", (models_json, decks_json))

        c.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, mod integer, usn integer, tags text, flds text, sfld text, csum integer, flags integer, data text);")
        c.execute("INSERT INTO notes VALUES(3001, 'guid-susp-test', 54321, 0, -1, '', 'Question\x1fRéponse', 'Question', 0, 0, '')")

        c.execute("""
            CREATE TABLE cards (
                id integer primary key, nid integer, did integer, ord integer, mod integer,
                usn integer, type integer, queue integer, due integer, ivl integer, factor integer,
                reps integer, lapses integer, left integer, odue integer, odid integer,
                flags integer, data text
            );
        """)
        # queue = -1 ➔ carte suspendue
        c.execute("INSERT INTO cards VALUES(4001, 3001, 1, 0, 0, -1, 0, -1, 0, 10, 2500, 3, 0, 0, 0, 0, 2, '')")

        conn.commit()
        conn.close()

        apkg_path = tmp_p / "test_import_suspended.apkg"
        with zipfile.ZipFile(apkg_path, "w") as zf:
            zf.write(anki_db, "collection.anki2")
            zf.writestr("media", "{}")

        analysis = import_mgr.analyze_archive(apkg_path)
        assert len(analysis.new_notes) == 1
        assert analysis.new_notes[0]["cards"][0]["is_suspended"] is True

        res = import_mgr.commit_import(analysis)
        assert res["created"] == 1

        imported_note = NoteModel.get(NoteModel.guid == "guid-susp-test")
        cards = list(CardModel.select().where(CardModel.note == imported_note))
        assert len(cards) == 1
        assert cards[0].is_suspended is True
        assert cards[0].flags == 2


def test_note_virtual_table_model_suspended_rendering() -> None:
    """Vérifie le rendu et la mise à jour des cartes suspendues dans NoteVirtualTableModel."""
    deck = DeckModel.create(name="TableSusp::Deck")
    nt = NoteTypeModel.create(name="TableSusp::Model", fields_schema='["Front", "Back"]', templates='[{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]')
    note = NoteModel.create(note_type=nt)
    note.add_version({"Front": "Concept", "Back": "Définition"}, source="manual")

    card = CardModel.create(note=note, deck=deck, template_index=0, flags=0, is_suspended=True)

    # Test en mode cartes ('cards')
    model_cards = NoteVirtualTableModel(query=CardModel.select().where(CardModel.id == card.id), display_mode="cards")
    assert model_cards.rowCount() >= 1

    row_idx = 0
    # Role IS_SUSPENDED_ROLE
    assert model_cards.data(model_cards.index(row_idx, 0), IS_SUSPENDED_ROLE) is True

    # BackgroundRole: teinte ambrée
    bg_color = model_cards.data(model_cards.index(row_idx, 2), Qt.ItemDataRole.BackgroundRole)
    assert isinstance(bg_color, QColor)
    assert bg_color.red() == 234 and bg_color.green() == 179 and bg_color.blue() == 8

    # Colonne 4 (Gabarit): doit contenir le suffixe ⏸️
    tmpl_text = model_cards.data(model_cards.index(row_idx, 4), Qt.ItemDataRole.DisplayRole)
    assert "⏸️" in tmpl_text

    # Mise à jour directe
    model_cards.update_card_suspended(card.id, False)
    assert model_cards.data(model_cards.index(row_idx, 0), IS_SUSPENDED_ROLE) is False
    assert model_cards.data(model_cards.index(row_idx, 2), Qt.ItemDataRole.BackgroundRole) is None

    # Sauvegarde BDD pour que la requête du modèle notes voie l'état non suspendu
    card.is_suspended = False
    card.save()

    # Test en mode notes ('notes')
    model_notes = NoteVirtualTableModel(query=NoteModel.select().where(NoteModel.id == note.id), display_mode="notes")
    # Puisque la carte a été passée à False en BDD, la note n'est pas suspendue
    assert model_notes.data(model_notes.index(0, 0), IS_SUSPENDED_ROLE) is False

    # Met à jour la note à suspendue
    model_notes.update_note_suspended(note.id, True)
    assert model_notes.data(model_notes.index(0, 0), IS_SUSPENDED_ROLE) is True
    recto_text = model_notes.data(model_notes.index(0, 2), Qt.ItemDataRole.DisplayRole)
    assert "⏸️" in recto_text


def test_edition_view_suspend_toggle_and_filter(qtbot: Any) -> None:
    """Vérifie la bascule suspendue et le filtrage par statut dans EditionView."""
    from ankiforge.ui.views.edition_view.view import EditionView

    deck = DeckModel.create(name="ViewSusp::Deck")
    nt = NoteTypeModel.create(name="ViewSusp::Model", fields_schema='["Front", "Back"]', templates='[{"name": "C1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]')
    note_active = NoteModel.create(note_type=nt)
    note_active.add_version({"Front": "Active Card", "Back": "Visible"}, source="manual")
    c_act = CardModel.create(note=note_active, deck=deck, template_index=0, is_suspended=False)

    note_susp = NoteModel.create(note_type=nt)
    note_susp.add_version({"Front": "Suspended Card", "Back": "Hidden"}, source="manual")
    CardModel.create(note=note_susp, deck=deck, template_index=0, is_suspended=True)

    view = EditionView()
    qtbot.addWidget(view)
    view.refresh_data()

    # 1. Test du filtrage Statut : Actives uniquement
    view._on_status_filter_selected(False, "Statut : Actives ▾")
    loaded_nids = [r.note_id for r in view.note_table_model._loaded_rows]
    assert note_active.id in loaded_nids
    assert note_susp.id not in loaded_nids

    # 2. Test du filtrage Statut : Suspendues uniquement
    view._on_status_filter_selected(True, "Statut : Suspendues ⏸️ ▾")
    loaded_nids_susp = [r.note_id for r in view.note_table_model._loaded_rows]
    assert note_susp.id in loaded_nids_susp
    assert note_active.id not in loaded_nids_susp

    # 3. Test du basculement (_toggle_suspend_selected)
    view._on_status_filter_selected(None, "Statut : Tous ▾")
    # Basculer note_active via fallback_note_id
    view._toggle_suspend_selected(fallback_note_id=note_active.id)
    reloaded_c_act = CardModel.get_by_id(c_act.id)
    assert reloaded_c_act.is_suspended is True

    # Réactiver
    view._toggle_suspend_selected(fallback_note_id=note_active.id)
    reloaded_c_act2 = CardModel.get_by_id(c_act.id)
    assert reloaded_c_act2.is_suspended is False
