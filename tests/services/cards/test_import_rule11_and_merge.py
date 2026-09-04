import json
import sqlite3
import zipfile
from pathlib import Path

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.cards.import_manager import ImportManager


def _build_apkg(tmp_path: Path, filename: str, guid: str, front: str, back: str, deck_name: str = "Default") -> Path:
    db_file = tmp_path / f"{filename}.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE col (id integer, models text, decks text)")
    models_str = '{"1": {"name": "Basic", "flds": [{"name": "Front"}, {"name": "Back"}]}}'
    decks_str = json.dumps({"1": {"id": 1, "name": deck_name}})
    conn.execute("INSERT INTO col VALUES (1, ?, ?)", (models_str, decks_str))
    conn.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, tags text, flds text)")
    conn.execute(f"INSERT INTO notes VALUES (1, '{guid}', 1, 'tag1', '{front}\x1f{back}')")
    conn.execute("CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer)")
    conn.execute("INSERT INTO cards VALUES (1, 1, 1, 0)")
    conn.commit()
    conn.close()

    apkg_path = tmp_path / f"{filename}.apkg"
    with zipfile.ZipFile(apkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", "{}")
    return apkg_path


def test_silent_update_when_no_manual_edits(tmp_path: Path) -> None:
    """Règle 11 : Si la note locale n'a jamais été éditée manuellement, la mise à jour est silencieuse."""
    nt = NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]')
    note = NoteModel.create(guid="g_auto_sync", note_type=nt)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Front": "Capitale France", "Back": "Lyon"}),
        source="import",  # Non manuel !
        is_active=True,
    )

    apkg = _build_apkg(tmp_path, "pkg_auto", "g_auto_sync", "Capitale France", "Paris")
    manager = ImportManager()
    analysis = manager.analyze_archive(apkg)

    assert len(analysis.conflicts) == 0
    assert len(analysis.silent_updates) == 1
    assert analysis.silent_updates[0]["reason"] == "incoming_newer"

    summary = manager.commit_import(analysis)
    assert summary["updated"] == 1

    latest_v = NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.desc()).first()
    assert latest_v.source == "import"
    data = json.loads(latest_v.content)
    assert data["Back"] == "Paris"


def test_strict_conflict_when_manual_edit_and_divergent(tmp_path: Path) -> None:
    """Règle 11 : Conflit strict déclenché uniquement si source='manual' et que le contenu diffère."""
    nt = NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]')
    note = NoteModel.create(guid="g_manual_conflict", note_type=nt)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Front": "Soleil", "Back": "Etoile jaune locale"}),
        source="manual",  # Modifié manuellement dans l'application !
        is_active=True,
    )

    apkg = _build_apkg(tmp_path, "pkg_conflict", "g_manual_conflict", "Soleil", "Naine jaune entrante")
    manager = ImportManager()
    analysis = manager.analyze_archive(apkg)

    assert len(analysis.conflicts) == 1
    conflict = analysis.conflicts[0]
    assert conflict.guid == "g_manual_conflict"
    assert conflict.local_content["Back"] == "Etoile jaune locale"
    assert conflict.incoming_content["Back"] == "Naine jaune entrante"
    assert conflict.field_diffs["Back"]["is_different"] is True


def test_commit_with_arbitrated_resolutions(tmp_path: Path) -> None:
    """Vérifie l'application des résolutions d'arbitrage (local, incoming, merged)."""
    nt = NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]')
    note = NoteModel.create(guid="g_arb", note_type=nt)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Front": "Atome", "Back": "Noyau et electrons locaux"}),
        source="manual",
        is_active=True,
    )

    apkg = _build_apkg(tmp_path, "pkg_arb", "g_arb", "Atome entrant", "Noyau et nuage electronique")
    manager = ImportManager()
    analysis = manager.analyze_archive(apkg)
    assert len(analysis.conflicts) == 1

    # Résolution arbitrée via Smart Merge : choix 'merged'
    resolutions = {
        "g_arb": {
            "choice": "merged",
            "content": {"Front": "Atome", "Back": "Noyau et nuage electronique (arbitré)"},
            "deck": "Sciences::Physique",
            "tags": ["fusion"],
        }
    }

    summary = manager.commit_import(analysis, conflict_resolutions=resolutions)
    assert summary["merged"] == 1

    latest_v = NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.desc()).first()
    assert latest_v.source == "merge"
    data = json.loads(latest_v.content)
    assert data["Back"] == "Noyau et nuage electronique (arbitré)"


def test_silent_deck_move_without_conflict(tmp_path: Path) -> None:
    """Règle 11 : Le déplacement d'un paquet sans modification du texte est silencieux."""
    nt = NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]')
    d_initial = DeckModel.create(name="AncienPaquet")
    note = NoteModel.create(guid="g_deck_move", note_type=nt)
    CardModel.create(note=note, deck=d_initial, template_index=0)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Front": "Question Fixe", "Back": "Reponse Fixe"}),
        source="manual",
        is_active=True,
    )

    # Même contenu, mais dans NouveauPaquet
    apkg = _build_apkg(tmp_path, "pkg_deck_move", "g_deck_move", "Question Fixe", "Reponse Fixe", deck_name="NouveauPaquet")
    manager = ImportManager()
    analysis = manager.analyze_archive(apkg)

    # Zéro conflit de contenu levé
    assert len(analysis.conflicts) == 0
    assert len(analysis.silent_updates) == 1

    manager.commit_import(analysis)

    card = CardModel.get(CardModel.note == note)
    assert card.deck.name == "NouveauPaquet"


def test_target_deck_override_redirects_all_notes(tmp_path: Path) -> None:
    """Vérifie que target_deck_id force toutes les cartes importées vers le paquet sélectionné."""
    target_deck = DeckModel.create(name="DestinationForcee")

    apkg = _build_apkg(tmp_path, "pkg_target", "g_target_1", "Test Target", "Reponse", deck_name="PaquetArchive")
    manager = ImportManager()
    analysis = manager.analyze_archive(apkg)

    manager.commit_import(analysis, target_deck_id=target_deck.id)

    note = NoteModel.get(NoteModel.guid == "g_target_1")
    card = CardModel.get(CardModel.note == note)
    assert card.deck == target_deck
