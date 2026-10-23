import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
import zstandard as zstd

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    DocumentPageModel,
    FolderModel,
    MediaModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    PersonaFolderModel,
    PersonaModel,
    PipelineModel,
    PromptModel,
    SettingModel,
)
from ankiforge.services.cards import import_manager as import_manager_mod
from ankiforge.services.cards.import_manager import (
    MAX_APKG_DECOMPRESSED_BYTES,
    MAX_COLPKG_DECOMPRESSED_BYTES,
    ApkgSizeLimitError,
    ImportManager,
)

pytestmark = pytest.mark.integration


def _register_unicase(conn: sqlite3.Connection) -> None:
    conn.create_collation("unicase", lambda left, right: (left.casefold() > right.casefold()) - (left.casefold() < right.casefold()))


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
    _register_unicase(conn)
    cursor = conn.cursor()

    cursor.execute("CREATE TABLE col (id integer, crt integer, mod integer, scm integer, ver integer, dcount integer, dsz integer, mtime_v integer, a integer, c integer, ctime integer, conf text)")
    cursor.execute("INSERT INTO col VALUES (1, 0, 0, 0, 16, 0, 0, 0, 0, 0, 0, '{}')")

    cursor.execute("CREATE TABLE decks (id integer primary key, name text, mtime_secs integer, usn integer, common text)")
    cursor.execute("INSERT INTO decks VALUES (1, 'Default', 0, 0, '')")
    cursor.execute("INSERT INTO decks VALUES (50, 'Sciences\x1fBiologie', 0, 0, '')")

    cursor.execute("CREATE TABLE notetypes (id integer primary key, name text, mtime_secs integer, usn integer, config blob)")
    cursor.execute("INSERT INTO notetypes VALUES (2002, 'BioModel', 0, 0, X'1a00')")

    cursor.execute("CREATE TABLE fields (ntid integer, ord integer, name text COLLATE unicase, config blob, primary key(ntid, ord))")
    cursor.execute("INSERT INTO fields VALUES (2002, 0, 'Organisme', X'')")
    cursor.execute("INSERT INTO fields VALUES (2002, 1, 'Caracteristique', X'')")

    cursor.execute("CREATE TABLE templates (ntid integer, ord integer, name text COLLATE unicase, mtime_secs integer, usn integer, config blob, primary key(ntid, ord))")
    cursor.execute(
        "INSERT INTO templates VALUES (2002, 0, 'Carte Organisme', 0, 0, ?)",
        (json.dumps({"qfmt": "{{Organisme}}", "afmt": "{{FrontSide}}<hr>{{Caracteristique}}"}),),
    )

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
    _register_unicase(conn)
    cursor = conn.cursor()

    cursor.execute("CREATE TABLE col (id integer, conf text)")
    cursor.execute("INSERT INTO col VALUES (1, '{}')")
    cursor.execute("CREATE TABLE decks (id integer primary key, name text)")
    cursor.execute("INSERT INTO decks VALUES (1, 'Default')")
    cursor.execute("INSERT INTO decks VALUES (99, 'Histoire\x1fFrance')")
    cursor.execute("CREATE TABLE notetypes (id integer primary key, name text, config blob)")
    cursor.execute("INSERT INTO notetypes VALUES (3003, 'HistoireModel', X'')")
    cursor.execute("CREATE TABLE fields (ntid integer, ord integer, name text COLLATE unicase, config blob)")
    cursor.execute("INSERT INTO fields VALUES (3003, 0, 'Evenement', X'')")
    cursor.execute("INSERT INTO fields VALUES (3003, 1, 'Date', X'')")
    cursor.execute("CREATE TABLE templates (ntid integer, ord integer, name text COLLATE unicase, config blob)")
    cursor.execute(
        "INSERT INTO templates VALUES (3003, 0, 'Carte Histoire', ?)",
        (json.dumps({"qfmt": "{{Evenement}}", "afmt": "{{FrontSide}}<hr>{{Date}}"}),),
    )
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
    _register_unicase(conn_mod)
    conn_mod.execute("CREATE TABLE col (id integer)")
    conn_mod.execute("INSERT INTO col VALUES (1)")
    conn_mod.execute("CREATE TABLE decks (id integer primary key, name text)")
    conn_mod.execute("INSERT INTO decks VALUES (2, 'ModernDeck')")
    conn_mod.execute("CREATE TABLE notetypes (id integer primary key, name text, config blob)")
    conn_mod.execute("INSERT INTO notetypes VALUES (2, 'ModernModel', X'')")
    conn_mod.execute("CREATE TABLE fields (ntid integer, ord integer, name text COLLATE unicase, config blob)")
    conn_mod.execute("INSERT INTO fields VALUES (2, 0, 'Front', X'')")
    conn_mod.execute("INSERT INTO fields VALUES (2, 1, 'Back', X'')")
    conn_mod.execute("CREATE TABLE templates (ntid integer, ord integer, name text COLLATE unicase, config blob)")
    conn_mod.execute(
        "INSERT INTO templates VALUES (2, 0, 'Carte Moderne', ?)",
        (json.dumps({"qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}"}),),
    )
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


def test_import_incomplete_model_fails_before_commit(tmp_path: Path) -> None:
    """Un modèle sans template HTML est rejeté au lieu d'être complété automatiquement."""
    db_file = tmp_path / "incomplete.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE col (id integer, models text, decks text)")
    conn.execute(
        "INSERT INTO col VALUES (1, ?, ?)",
        ('{"1": {"name": "Incomplete", "flds": [{"name": "Front"}, {"name": "Back"}]}}', '{"1": {"id": 1, "name": "Default"}}'),
    )
    conn.execute("CREATE TABLE notes (id integer, guid text, mid integer, tags text, flds text)")
    conn.execute("INSERT INTO notes VALUES (1, 'invalid_model', 1, '', 'Q\x1fA')")
    conn.commit()
    conn.close()

    apkg_path = tmp_path / "incomplete.apkg"
    with zipfile.ZipFile(apkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", "{}")

    with pytest.raises(ValueError, match="aucun template valide"):
        ImportManager().analyze_archive(apkg_path)


@pytest.mark.parametrize("size_limit", [None, 1000])
def test_import_configurable_decompressed_size_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, size_limit: int | None) -> None:
    """Le plafond anti zip-bomb est réglable : la même archive est acceptée ou rejetée selon la valeur."""
    from ankiforge.services.cards import import_manager as import_manager_mod

    db_file = tmp_path / "limit.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE col (id integer, models text, decks text)")
    models_json = '{"1": {"name": "Basic", "flds": [{"name": "Front"}, {"name": "Back"}], '
    models_json += '"tmpls": [{"name": "Q->A", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}"}]}}'
    decks_json = '{"1": {"id": 1, "name": "Default"}}'
    conn.execute("INSERT INTO col VALUES (1, ?, ?)", (models_json, decks_json))
    conn.execute("CREATE TABLE notes (id integer, guid text, mid integer, tags text, flds text)")
    conn.execute("INSERT INTO notes VALUES (1, 'limit_guid', 1, '', 'Q\x1fA')")
    conn.commit()
    conn.close()

    apkg_path = tmp_path / "big.apkg"
    with zipfile.ZipFile(apkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", "{}")
        zf.writestr("asset_padding.bin", b"\x00" * 2048)

    monkeypatch.setattr(import_manager_mod, "_resolve_apkg_size_limit", lambda: size_limit)

    if size_limit == 1000:
        with pytest.raises(ValueError, match="dépasse le plafond"):
            ImportManager().analyze_archive(apkg_path)
    else:
        analysis = ImportManager().analyze_archive(apkg_path)
        assert len(analysis.new_notes) == 1


def test_apkg_size_limit_default_and_disabled_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le défaut 1 Gio s'applique sans réglage enregistré ; une valeur <= 0 désactive le plafond."""
    from ankiforge.services.cards import import_manager as import_manager_mod

    monkeypatch.setattr(
        import_manager_mod.SettingsService,
        "get",
        lambda key, default=None, category=None: import_manager_mod.MAX_APKG_DECOMPRESSED_BYTES if key == "anki/max_import_bytes" else default,
    )
    assert import_manager_mod._resolve_apkg_size_limit() == import_manager_mod.MAX_APKG_DECOMPRESSED_BYTES

    monkeypatch.setattr(
        import_manager_mod.SettingsService,
        "get",
        lambda key, default=None, category=None: 0 if key == "anki/max_import_bytes" else default,
    )
    assert import_manager_mod._resolve_apkg_size_limit() is None


@pytest.mark.parametrize(("provenance", "expected_origin"), [("default", "plafond par défaut"), ("user", "réglage utilisateur")])
def test_apkg_size_limit_error_message_rich(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provenance: str, expected_origin: str) -> None:
    """Le message d'erreur de plafond expose la taille, le plafond appliqué, la provenance et le raccourci vers les réglages."""
    from ankiforge.services.cards import import_manager as import_manager_mod
    from ankiforge.services.cards.import_manager import ApkgSizeLimitError

    db_file = tmp_path / "limit_msg.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE col (id integer, models text, decks text)")
    models_json = '{"1": {"name": "Basic", "flds": [{"name": "Front"}, {"name": "Back"}], '
    models_json += '"tmpls": [{"name": "Q->A", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}"}]}}'
    decks_json = '{"1": {"id": 1, "name": "Default"}}'
    conn.execute("INSERT INTO col VALUES (1, ?, ?)", (models_json, decks_json))
    conn.execute("CREATE TABLE notes (id integer, guid text, mid integer, tags text, flds text)")
    conn.execute("INSERT INTO notes VALUES (1, 'limit_msg_guid', 1, '', 'Q\x1fA')")
    conn.commit()
    conn.close()

    apkg_path = tmp_path / "big_msg.apkg"
    with zipfile.ZipFile(apkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", "{}")
        zf.writestr("asset_padding.bin", b"\x00" * 2048)

    monkeypatch.setattr(import_manager_mod, "_resolve_apkg_size_limit", lambda: 1000)
    monkeypatch.setattr(import_manager_mod, "_size_limit_provenance", lambda: provenance)

    with pytest.raises(ApkgSizeLimitError) as exc_info:
        ImportManager().analyze_archive(apkg_path)

    message = str(exc_info.value)
    assert message.startswith("Archive rejetée")
    assert "dépasse le plafond appliqué de 1000 octets" in message
    assert "Provenance du plafond :" in message and expected_origin in message
    assert "Paramètres" in message
    assert "Gio" in message
    assert exc_info.value.total_size > 1000
    assert exc_info.value.limit == 1000
    assert exc_info.value.provenance == provenance


def test_import_apkg_updates_existing_notetype_css_and_templates(tmp_path: Path) -> None:
    """Vérifie que l'import d'un paquet met à jour le CSS et les templates d'un modèle déjà utilisé par des notes."""
    nt = NoteTypeModel.create(
        name="SyncModel",
        anki_id=2001,
        fields_schema='["Front", "Back"]',
        templates=json.dumps([{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
        css_style=".card { color: black; }",
    )
    NoteModel.create(guid="guid_sync_1", note_type=nt)

    db_file = tmp_path / "sync_model.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    models_json = {
        "2001": {
            "name": "SyncModel",
            "flds": [{"name": "Front"}, {"name": "Back"}],
            "tmpls": [{"name": "Card 1 Modern", "qfmt": "<div class='modern'>{{Front}}</div>", "afmt": "{{FrontSide}}<hr>{{Back}}"}],
            "css": ".card { color: #0284c7; font-family: monospace; }",
        }
    }
    decks_json = {"1": {"id": 1, "name": "Default"}}
    cursor.execute("CREATE TABLE col (id integer, models text, decks text)")
    cursor.execute("INSERT INTO col VALUES (1, ?, ?)", (json.dumps(models_json), json.dumps(decks_json)))
    cursor.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, tags text, flds text)")
    cursor.execute("INSERT INTO notes VALUES (1, 'guid_sync_1', 2001, '', 'FrontVal\x1fBackVal')")
    cursor.execute("CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer, ivl integer, reps integer, lapses integer)")
    cursor.execute("INSERT INTO cards VALUES (10, 1, 1, 0, 0, 0, 0)")
    conn.commit()
    conn.close()

    apkg_path = tmp_path / "sync_model.apkg"
    with zipfile.ZipFile(apkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", "{}")

    manager = ImportManager()
    analysis = manager.analyze_archive(apkg_path)
    manager.commit_import(analysis)

    refreshed_nt = NoteTypeModel.get(NoteTypeModel.id == nt.id)
    assert refreshed_nt.css_style == ".card { color: #0284c7; font-family: monospace; }"
    parsed_tmpls = json.loads(refreshed_nt.templates)
    assert parsed_tmpls[0]["name"] == "Card 1 Modern"
    assert "<div class='modern'>" in parsed_tmpls[0]["qfmt"]


def test_import_apkg_reassigns_note_type(tmp_path: Path) -> None:
    """Vérifie qu'une note locale réaffectée à un autre modèle dans Anki met bien à jour note_type."""
    nt_old = NoteTypeModel.create(name="ModelOld", anki_id=3001, fields_schema='["Front", "Back"]', templates="[]", css_style="")
    nt_new = NoteTypeModel.create(name="ModelNew", anki_id=3002, fields_schema='["Front", "Back"]', templates="[]", css_style="")
    NoteModel.create(guid="guid_reassign_1", note_type=nt_old)

    db_file = tmp_path / "reassign.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    models_json = {
        "3002": {
            "name": "ModelNew",
            "flds": [{"name": "Front"}, {"name": "Back"}],
            "tmpls": [{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}],
            "css": "",
        }
    }
    decks_json = {"1": {"id": 1, "name": "Default"}}
    cursor.execute("CREATE TABLE col (id integer, models text, decks text)")
    cursor.execute("INSERT INTO col VALUES (1, ?, ?)", (json.dumps(models_json), json.dumps(decks_json)))
    cursor.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, tags text, flds text)")
    cursor.execute("INSERT INTO notes VALUES (1, 'guid_reassign_1', 3002, '', 'Front\x1fBack')")
    cursor.execute("CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer, ivl integer, reps integer, lapses integer)")
    cursor.execute("INSERT INTO cards VALUES (10, 1, 1, 0, 0, 0, 0)")
    conn.commit()
    conn.close()

    apkg_path = tmp_path / "reassign.apkg"
    with zipfile.ZipFile(apkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", "{}")

    manager = ImportManager()
    analysis = manager.analyze_archive(apkg_path)
    manager.commit_import(analysis)

    refreshed_note = NoteModel.get(NoteModel.guid == "guid_reassign_1")
    assert refreshed_note.note_type.id == nt_new.id
    assert refreshed_note.note_type.name == "ModelNew"


def test_import_colpkg_prunes_empty_orphan_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie que l'import d'une collection (.colpkg) supprime les modèles locaux vierges absents de la collection entrante."""
    monkeypatch.setattr("ankiforge.services.cards.import_manager.backup_before_colpkg_import", lambda: tmp_path / "backup.db")

    NoteTypeModel.create(name="ModelOrphan", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    NoteTypeModel.create(name="ModelKept", anki_id=4001, fields_schema='["Front", "Back"]', templates="[]", css_style="")

    db_file = tmp_path / "collection_prune.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    models_json = {
        "4001": {
            "name": "ModelKept",
            "flds": [{"name": "Front"}, {"name": "Back"}],
            "tmpls": [{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}],
            "css": "",
        }
    }
    decks_json = {"1": {"id": 1, "name": "Default"}}
    cursor.execute("CREATE TABLE col (id integer, models text, decks text)")
    cursor.execute("INSERT INTO col VALUES (1, ?, ?)", (json.dumps(models_json), json.dumps(decks_json)))
    cursor.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, tags text, flds text)")
    cursor.execute("CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer, ivl integer, reps integer, lapses integer)")
    conn.commit()
    conn.close()

    colpkg_path = tmp_path / "collection.colpkg"
    with zipfile.ZipFile(colpkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", "{}")

    manager = ImportManager()
    analysis = manager.analyze_archive(colpkg_path)
    assert analysis.source_type == "colpkg"
    manager.commit_import(analysis)

    assert NoteTypeModel.get_or_none(NoteTypeModel.name == "ModelOrphan") is None
    assert NoteTypeModel.get_or_none(NoteTypeModel.name == "ModelKept") is not None


def test_colpkg_size_limit_default_and_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le plafond par défaut pour .colpkg est 5 Gio ; un réglage utilisateur ou désactivation prime."""
    assert MAX_COLPKG_DECOMPRESSED_BYTES == 5 * 1024 * 1024 * 1024
    assert MAX_APKG_DECOMPRESSED_BYTES == 1 * 1024 * 1024 * 1024

    # 1. Sans réglage enregistré : colpkg = 5 Gio, apkg = 1 Gio
    monkeypatch.setattr(import_manager_mod.SettingsService, "get", lambda key, default=None, category=None: default)
    assert import_manager_mod._resolve_apkg_size_limit(is_colpkg=True) == MAX_COLPKG_DECOMPRESSED_BYTES
    assert import_manager_mod._resolve_apkg_size_limit(is_colpkg=False) == MAX_APKG_DECOMPRESSED_BYTES

    # 2. Réglage utilisateur enregistré (ex: 2 Gio) s'applique aux deux
    custom_bytes = 2 * 1024 * 1024 * 1024
    monkeypatch.setattr(
        import_manager_mod.SettingsService,
        "get",
        lambda key, default=None, category=None: custom_bytes if key == "anki/max_import_bytes" else default,
    )
    assert import_manager_mod._resolve_apkg_size_limit(is_colpkg=True) == custom_bytes
    assert import_manager_mod._resolve_apkg_size_limit(is_colpkg=False) == custom_bytes

    # 3. Réglage désactivé (<= 0)
    monkeypatch.setattr(
        import_manager_mod.SettingsService,
        "get",
        lambda key, default=None, category=None: 0 if key == "anki/max_import_bytes" else default,
    )
    assert import_manager_mod._resolve_apkg_size_limit(is_colpkg=True) is None
    assert import_manager_mod._resolve_apkg_size_limit(is_colpkg=False) is None

    # 4. Message d'erreur personnalisé à 5 Gio
    err_colpkg = ApkgSizeLimitError(6 * 1024**3, MAX_COLPKG_DECOMPRESSED_BYTES, provenance="default")
    assert "plafond par défaut (5 Gio)" in str(err_colpkg)


def test_colpkg_replacement_routes_and_aborts_if_backup_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """commit_import route vers le remplacement colpkg et avorte sans écriture si la sauvegarde échoue."""
    nt = NoteTypeModel.create(name="ModelSafety", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    NoteModel.create(guid="guid_safety", note_type=nt, status="active")

    db_file = tmp_path / "colpkg_abort.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    models_json = {
        "1": {
            "name": "Basic",
            "flds": [{"name": "Front"}, {"name": "Back"}],
            "tmpls": [{"name": "C1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}],
            "css": "",
        }
    }
    decks_json = {"1": {"id": 1, "name": "Default"}}
    cursor.execute("CREATE TABLE col (id integer, models text, decks text)")
    cursor.execute("INSERT INTO col VALUES (1, ?, ?)", (json.dumps(models_json), json.dumps(decks_json)))
    cursor.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, tags text, flds text)")
    cursor.execute("CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer, ivl integer, reps integer, lapses integer)")
    conn.commit()
    conn.close()

    colpkg_path = tmp_path / "safety.colpkg"
    with zipfile.ZipFile(colpkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", "{}")

    manager = ImportManager()
    analysis = manager.analyze_archive(colpkg_path)
    assert analysis.source_type == "colpkg"

    # Simuler l'échec de la sauvegarde pré-importation
    def _fail_backup(profile_name: str | None = None) -> Path:
        raise RuntimeError("Instantané pré-colpkg impossible (disque plein).")

    monkeypatch.setattr("ankiforge.services.cards.import_manager.backup_before_colpkg_import", _fail_backup)

    with pytest.raises(RuntimeError, match="Instantané pré-colpkg impossible"):
        manager.commit_import(analysis)

    # Sanctuarisation : aucune note locale n'a été purgée
    assert NoteModel.get_or_none(NoteModel.guid == "guid_safety") is not None
    assert NoteTypeModel.get_or_none(NoteTypeModel.name == "ModelSafety") is not None


def test_colpkg_replacement_eliminates_zombie_cards_and_updates_notetypes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le remplacement .colpkg purge les cartes zombies et met à jour les schémas de modèles sans corruption."""
    monkeypatch.setattr("ankiforge.services.cards.import_manager.backup_before_colpkg_import", lambda: tmp_path / "mock_backup.db")

    # 1. État initial de la base locale : cartes et modèles obsolètes (zombies)
    deck_old = DeckModel.create(name="Ancien Paquet")
    nt_old = NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    nt_zombie = NoteTypeModel.create(name="ModeleZombie", fields_schema='["Q", "A"]', templates="[]", css_style="")

    note_old = NoteModel.create(guid="guid_zombie_1", note_type=nt_old, status="active")
    CardModel.create(note=note_old, deck=deck_old, template_index=0)
    NoteVersionModel.create(note=note_old, version_number=1, content='{"Front": "F_old", "Back": "B_old"}', is_active=True)

    note_zombie = NoteModel.create(guid="guid_zombie_2", note_type=nt_zombie, status="active")
    CardModel.create(note=note_zombie, deck=deck_old, template_index=0)
    NoteVersionModel.create(note=note_zombie, version_number=1, content='{"Q": "Q_old", "A": "A_old"}', is_active=True)

    # 2. Collection entrante .colpkg :
    #    - Nouveau modèle "Basic" enrichi d'un troisième champ ["Front", "Back", "Remarque"]
    #    - Nouveau modèle "Specialiste" ["Concept", "Definition"]
    #    - Nouveau deck "Nouveau::SousPaquet"
    #    - Notes entrantes guid_fresh_1 et guid_fresh_2 (les zombies 1 et 2 n'y figurent pas)
    db_file = tmp_path / "colpkg_fresh.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    models_json = {
        "101": {
            "name": "Basic",
            "flds": [{"name": "Front"}, {"name": "Back"}, {"name": "Remarque"}],
            "tmpls": [{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}<br>{{Remarque}}"}],
            "css": ".card { font-size: 20px; }",
        },
        "102": {
            "name": "Specialiste",
            "flds": [{"name": "Concept"}, {"name": "Definition"}],
            "tmpls": [{"name": "Card 1", "qfmt": "{{Concept}}", "afmt": "{{Definition}}"}],
            "css": "",
        },
    }
    decks_json = {"10": {"id": 10, "name": "Nouveau::SousPaquet"}}
    cursor.execute("CREATE TABLE col (id integer, models text, decks text)")
    cursor.execute("INSERT INTO col VALUES (1, ?, ?)", (json.dumps(models_json), json.dumps(decks_json)))

    cursor.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, tags text, flds text)")
    cursor.execute("INSERT INTO notes VALUES (1, 'guid_fresh_1', 101, 'tagA tagB', 'F_fresh\x1fB_fresh\x1fNote importante')")
    cursor.execute("INSERT INTO notes VALUES (2, 'guid_fresh_2', 102, 'tagC', 'Anatomie\x1fScience du corps')")

    cursor.execute("CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer, ivl integer, reps integer, lapses integer, flags integer, queue integer)")
    cursor.execute("INSERT INTO cards VALUES (101, 1, 10, 0, 14, 5, 1, 2, 0)")
    cursor.execute("INSERT INTO cards VALUES (102, 2, 10, 0, 30, 8, 0, 4, -1)")
    conn.commit()
    conn.close()

    colpkg_path = tmp_path / "fresh_collection.colpkg"
    with zipfile.ZipFile(colpkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", "{}")

    manager = ImportManager()
    analysis = manager.analyze_archive(colpkg_path)
    assert analysis.source_type == "colpkg"
    assert len(analysis.new_notes) == 2

    res = manager.commit_import(analysis)
    assert res["created"] == 2

    # 3. Validation de l'élimination des zombies
    assert NoteModel.get_or_none(NoteModel.guid == "guid_zombie_1") is None
    assert NoteModel.get_or_none(NoteModel.guid == "guid_zombie_2") is None
    assert NoteTypeModel.get_or_none(NoteTypeModel.name == "ModeleZombie") is None
    assert DeckModel.get_or_none(DeckModel.name == "Ancien Paquet") is None

    # 4. Validation des nouvelles cartes et des types de note conformes
    n1 = NoteModel.get(NoteModel.guid == "guid_fresh_1")
    assert n1.note_type.name == "Basic"
    assert json.loads(n1.note_type.fields_schema) == ["Front", "Back", "Remarque"]
    assert n1.note_type.css_style == ".card { font-size: 20px; }"
    assert n1.tags == '["tagA", "tagB"]'

    v1 = NoteVersionModel.get(note=n1)
    assert json.loads(v1.content) == {"Front": "F_fresh", "Back": "B_fresh", "Remarque": "Note importante"}

    c1 = CardModel.get(note=n1)
    assert c1.deck.name == "Nouveau::SousPaquet"
    assert c1.ivl == 14
    assert c1.reps == 5
    assert c1.lapses == 1
    assert c1.flags == 2
    assert c1.is_suspended is False

    n2 = NoteModel.get(NoteModel.guid == "guid_fresh_2")
    c2 = CardModel.get(note=n2)
    assert c2.is_suspended is True
    assert c2.flags == 4


def test_colpkg_replacement_sanctuarizes_studio_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le remplacement .colpkg préserve intégralement et fidèlement 100% du Périmètre Studio."""
    monkeypatch.setattr("ankiforge.services.cards.import_manager.backup_before_colpkg_import", lambda: tmp_path / "mock_backup.db")

    # 1. Enregistrement des entités du Périmètre Studio
    folder = FolderModel.create(name="Dossier Neuroanatomie")
    doc = DocumentModel.create(title="Manuel de Neurosciences", folder=folder, page_count=120)
    page_media = MediaModel.create(checksum="page_media_123", filename="page1.png", original_name="page1.png", mime_type="image/png")
    page = DocumentPageModel.create(document=doc, media=page_media, page_number=42, ocr_text="Le cortex cérébral...")
    chunk = DocumentChunkModel.create(document=doc, chunk_index=1, content="Fragment détaillé sur les synapses.")

    p_folder = PersonaFolderModel.create(name="Dossier Personas")
    persona = PersonaModel.create(
        name="Expert Neuro",
        folder=p_folder,
        system_prompt="Tu es un enseignant-chercheur. Règles Wozniak strictes.",
        description="Enseignant-chercheur",
    )
    prompt = PromptModel.create(
        name="Prompt Fiches Anatomie",
        content="Formule des cartes sur {{topic}}",
    )
    pipeline = PipelineModel.create(
        name="Pipeline Découpage Neuro",
        description="DAG de synthèse",
        steps_config="[]",
    )
    SettingModel.create(key="theme/current", value="nordic_frost", category="ui")

    # 2. Données Anki antérieures vouées au remplacement
    old_deck = DeckModel.create(name="Vieux Deck")
    old_nt = NoteTypeModel.create(name="Vieux Type", fields_schema='["Front", "Back"]')
    old_note = NoteModel.create(guid="guid_to_be_replaced", note_type=old_nt)
    CardModel.create(note=old_note, deck=old_deck, template_index=0)

    # 3. Création et exécution d'un .colpkg entrant
    db_file = tmp_path / "colpkg_studio_safe.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    models_json = {
        "201": {
            "name": "Nouveau Modele",
            "flds": [{"name": "A"}, {"name": "B"}],
            "tmpls": [{"name": "C1", "qfmt": "{{A}}", "afmt": "{{B}}"}],
            "css": "",
        }
    }
    decks_json = {"1": {"id": 1, "name": "Deck Entrant"}}
    cursor.execute("CREATE TABLE col (id integer, models text, decks text)")
    cursor.execute("INSERT INTO col VALUES (1, ?, ?)", (json.dumps(models_json), json.dumps(decks_json)))
    cursor.execute("CREATE TABLE notes (id integer primary key, guid text, mid integer, tags text, flds text)")
    cursor.execute("INSERT INTO notes VALUES (1, 'guid_fresh_unique', 201, '', 'AA\x1fBB')")
    cursor.execute("CREATE TABLE cards (id integer primary key, nid integer, did integer, ord integer, ivl integer, reps integer, lapses integer)")
    cursor.execute("INSERT INTO cards VALUES (1, 1, 1, 0, 0, 0, 0)")
    conn.commit()
    conn.close()

    colpkg_path = tmp_path / "studio_sanctuary.colpkg"
    with zipfile.ZipFile(colpkg_path, "w") as zf:
        zf.write(db_file, "collection.anki2")
        zf.writestr("media", "{}")

    manager = ImportManager()
    analysis = manager.analyze_archive(colpkg_path)
    res = manager.commit_import(analysis)
    assert res["created"] == 1

    # 4. Vérification de la sanctuarisation absolue du Studio
    assert DocumentModel.get_by_id(doc.id).title == "Manuel de Neurosciences"
    assert FolderModel.get_by_id(folder.id).name == "Dossier Neuroanatomie"
    assert DocumentPageModel.get_by_id(page.id).page_number == 42
    assert DocumentChunkModel.get_by_id(chunk.id).content == "Fragment détaillé sur les synapses."
    assert PersonaFolderModel.get_by_id(p_folder.id).name == "Dossier Personas"
    assert PersonaModel.get_by_id(persona.id).name == "Expert Neuro"
    assert PromptModel.get_by_id(prompt.id).name == "Prompt Fiches Anatomie"
    assert PipelineModel.get_by_id(pipeline.id).name == "Pipeline Découpage Neuro"
    assert SettingModel.get(SettingModel.key == "theme/current").value == "nordic_frost"

    # Vérification que le périmètre Anki a bien été remplacé
    assert NoteModel.get_or_none(NoteModel.guid == "guid_to_be_replaced") is None
    assert DeckModel.get_or_none(DeckModel.name == "Vieux Deck") is None
    assert NoteTypeModel.get_or_none(NoteTypeModel.name == "Vieux Type") is None
    assert NoteModel.get_or_none(NoteModel.guid == "guid_fresh_unique") is not None
