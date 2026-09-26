"""Tests pour le transfert élargi de contenu inter-profils (notes, cartes, modèles, médias)."""

import json
from pathlib import Path

import pytest
from peewee import SqliteDatabase

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    MediaModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionMediaModel,
    NoteVersionModel,
)
from ankiforge.services.profile_content_transfer import ProfileContentTransfer

pytestmark = pytest.mark.integration

CARD_MODELS = [
    DeckModel,
    NoteTypeModel,
    NoteModel,
    NoteVersionModel,
    CardModel,
    MediaModel,
    NoteVersionMediaModel,
]


@pytest.fixture
def transfer_setup(tmp_path: Path):
    profiles_dir = tmp_path / "profiles"

    # Source Profile
    source_dir = profiles_dir / "source"
    source_dir.mkdir(parents=True)
    source_media = source_dir / "media"
    source_media.mkdir()
    source_db = SqliteDatabase(str(source_dir / "ankiforge.db"))

    # Target Profile
    target_dir = profiles_dir / "target"
    target_dir.mkdir(parents=True)
    target_media = target_dir / "media"
    target_media.mkdir()
    target_db = SqliteDatabase(str(target_dir / "ankiforge.db"))

    # Init schemas in both
    for db in (source_db, target_db):
        with db.bind_ctx(CARD_MODELS, bind_refs=False, bind_backrefs=False):
            db.connect()
            db.create_tables(CARD_MODELS)
            db.close()

    return {
        "profiles_dir": profiles_dir,
        "source_db": source_db,
        "target_db": target_db,
        "source_media": source_media,
        "target_media": target_media,
    }


def test_list_decks_and_tags(transfer_setup):
    profiles_dir = transfer_setup["profiles_dir"]
    source_db = transfer_setup["source_db"]

    with source_db.bind_ctx(CARD_MODELS, bind_refs=False, bind_backrefs=False):
        source_db.connect()
        with source_db.atomic():
            DeckModel.create(name="Sciences::Physique")
            DeckModel.create(name="Langues::Anglais")
            nt = NoteTypeModel.create(name="Basic")
            NoteModel.create(note_type=nt, tags='["vocabulaire", "toefl"]')
            NoteModel.create(note_type=nt, tags="formule physique")
        source_db.close()

    decks = ProfileContentTransfer.list_decks("source", profiles_dir=profiles_dir)
    assert decks == ["Langues::Anglais", "Sciences::Physique"]

    tags = ProfileContentTransfer.list_tags("source", profiles_dir=profiles_dir)
    assert tags == ["formule", "physique", "toefl", "vocabulaire"]


def test_transfer_notes_preserves_guid_and_creates_hierarchy(transfer_setup):
    profiles_dir = transfer_setup["profiles_dir"]
    source_db = transfer_setup["source_db"]
    source_media = transfer_setup["source_media"]

    # Créer un faux média dans le dossier source
    sample_img = source_media / "img_test.png"
    sample_img.write_bytes(b"sample_png_bytes_12345")

    with source_db.bind_ctx(CARD_MODELS, bind_refs=False, bind_backrefs=False):
        source_db.connect()
        with source_db.atomic():
            deck = DeckModel.create(name="Sciences::Physique::Optique")
            nt = NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]')
            note = NoteModel.create(guid="unique-guid-12345", note_type=nt, tags='["optique"]')
            NoteVersionModel.create(
                note=note,
                version_number=1,
                content=json.dumps({"Front": "Qu'est-ce qu'une lentille ? <img src=\"img_test.png\">", "Back": "Un composant optique."}),
                is_active=True,
            )
            CardModel.create(note=note, deck=deck, template_index=0)
        source_db.close()

    preview = ProfileContentTransfer.get_transfer_preview("source", profiles_dir=profiles_dir)
    assert preview["notes_count"] == 1
    assert preview["cards_count"] == 1
    assert preview["note_types_count"] == 1
    assert preview["media_count"] == 1

    report = ProfileContentTransfer.transfer_content(
        source_profile="source",
        target_profile="target",
        profiles_dir=profiles_dir,
    )

    assert report.notes_imported == 1
    assert report.notes_updated == 0
    assert report.notes_skipped == 0
    assert report.media_transferred == 1
    assert report.decks_created == 3  # Sciences, Sciences::Physique, Sciences::Physique::Optique
    assert report.note_types_created == 1

    target_db = transfer_setup["target_db"]
    with target_db.bind_ctx(CARD_MODELS, bind_refs=False, bind_backrefs=False):
        target_db.connect()
        imported_note = NoteModel.get_or_none(NoteModel.guid == "unique-guid-12345")
        assert imported_note is not None
        assert imported_note.guid == "unique-guid-12345"
        assert imported_note.note_type.name == "Basic"

        # Vérifier cartes et deck
        cards = list(CardModel.select().where(CardModel.note == imported_note))
        assert len(cards) == 1
        assert cards[0].deck.name == "Sciences::Physique::Optique"
        target_db.close()

    # Vérifier copie physique du média
    target_media = transfer_setup["target_media"]
    assert (target_media / "img_test.png").exists()
    assert (target_media / "img_test.png").read_bytes() == b"sample_png_bytes_12345"


def test_transfer_with_divergent_schema_clones_notetype(transfer_setup):
    profiles_dir = transfer_setup["profiles_dir"]
    source_db = transfer_setup["source_db"]
    target_db = transfer_setup["target_db"]

    # Target a déjà un type "Custom" avec schéma ["Question", "Reponse"]
    with target_db.bind_ctx(CARD_MODELS, bind_refs=False, bind_backrefs=False):
        target_db.connect()
        NoteTypeModel.create(name="Custom", fields_schema='["Question", "Reponse"]')
        target_db.close()

    # Source a un type "Custom" avec schéma divergent ["Front", "Back", "Remarque"]
    with source_db.bind_ctx(CARD_MODELS, bind_refs=False, bind_backrefs=False):
        source_db.connect()
        with source_db.atomic():
            deck = DeckModel.create(name="Default")
            nt_src = NoteTypeModel.create(name="Custom", fields_schema='["Front", "Back", "Remarque"]')
            note = NoteModel.create(guid="guid-divergent-999", note_type=nt_src)
            NoteVersionModel.create(note=note, content='{"Front":"Q","Back":"R","Remarque":"N"}', is_active=True)
            CardModel.create(note=note, deck=deck)
        source_db.close()

    report = ProfileContentTransfer.transfer_content(
        source_profile="source",
        target_profile="target",
        profiles_dir=profiles_dir,
    )

    assert report.notes_imported == 1
    assert report.note_types_created == 1

    with target_db.bind_ctx(CARD_MODELS, bind_refs=False, bind_backrefs=False):
        target_db.connect()
        imported_note = NoteModel.get(NoteModel.guid == "guid-divergent-999")
        assert imported_note.note_type.name == "Custom (Importé source)"
        # L'original est intact
        orig_nt = NoteTypeModel.get(NoteTypeModel.name == "Custom")
        assert json.loads(orig_nt.fields_schema) == ["Question", "Reponse"]
        target_db.close()


def test_transfer_collision_skip_vs_update(transfer_setup):
    profiles_dir = transfer_setup["profiles_dir"]
    source_db = transfer_setup["source_db"]
    target_db = transfer_setup["target_db"]

    with target_db.bind_ctx(CARD_MODELS, bind_refs=False, bind_backrefs=False):
        target_db.connect()
        nt = NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]')
        target_note = NoteModel.create(guid="collision-guid-001", note_type=nt)
        NoteVersionModel.create(note=target_note, version_number=1, content='{"Front":"Ancien"}', is_active=True)
        target_db.close()

    with source_db.bind_ctx(CARD_MODELS, bind_refs=False, bind_backrefs=False):
        source_db.connect()
        with source_db.atomic():
            nt_src = NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]')
            src_note = NoteModel.create(guid="collision-guid-001", note_type=nt_src)
            NoteVersionModel.create(note=src_note, version_number=1, content='{"Front":"Nouveau"}', is_active=True)
            deck = DeckModel.create(name="Default")
            CardModel.create(note=src_note, deck=deck)
        source_db.close()

    # 1. Transfert sans mise à jour -> doit être ignoré
    report_skip = ProfileContentTransfer.transfer_content(
        source_profile="source",
        target_profile="target",
        update_existing_notes=False,
        profiles_dir=profiles_dir,
    )
    assert report_skip.notes_imported == 0
    assert report_skip.notes_updated == 0
    assert report_skip.notes_skipped == 1

    # 2. Transfert avec mise à jour -> doit créer une nouvelle version
    report_update = ProfileContentTransfer.transfer_content(
        source_profile="source",
        target_profile="target",
        update_existing_notes=True,
        profiles_dir=profiles_dir,
    )
    assert report_update.notes_imported == 0
    assert report_update.notes_updated == 1
    assert report_update.notes_skipped == 0

    with target_db.bind_ctx(CARD_MODELS, bind_refs=False, bind_backrefs=False):
        target_db.connect()
        note = NoteModel.get(NoteModel.guid == "collision-guid-001")
        versions = list(NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.asc()))
        assert len(versions) == 2
        assert versions[0].is_active is False
        assert versions[1].is_active is True
        assert json.loads(versions[1].content)["Front"] == "Nouveau"
        target_db.close()


def test_transfer_media_deduplication(transfer_setup):
    profiles_dir = transfer_setup["profiles_dir"]
    source_db = transfer_setup["source_db"]
    source_media = transfer_setup["source_media"]
    target_db = transfer_setup["target_db"]
    target_media = transfer_setup["target_media"]

    content_bytes = b"shared_media_bytes_999"
    img_name = "diagram.png"
    (source_media / img_name).write_bytes(content_bytes)

    # Créer le même média déjà dans la cible
    (target_media / img_name).write_bytes(content_bytes)
    md5 = ProfileContentTransfer._calculate_md5(str(target_media / img_name))

    with target_db.bind_ctx(CARD_MODELS, bind_refs=False, bind_backrefs=False):
        target_db.connect()
        MediaModel.create(filename=img_name, original_name=img_name, checksum=md5, mime_type="image/png")
        target_db.close()

    # Créer la note dans la source qui utilise diagram.png
    with source_db.bind_ctx(CARD_MODELS, bind_refs=False, bind_backrefs=False):
        source_db.connect()
        with source_db.atomic():
            nt = NoteTypeModel.create(name="Basic")
            note = NoteModel.create(guid="media-guid-1", note_type=nt)
            NoteVersionModel.create(note=note, content='{"Front":"<img src=\\"diagram.png\\">"}', is_active=True)
            deck = DeckModel.create(name="Default")
            CardModel.create(note=note, deck=deck)
        source_db.close()

    report = ProfileContentTransfer.transfer_content(
        source_profile="source",
        target_profile="target",
        profiles_dir=profiles_dir,
    )

    assert report.notes_imported == 1
    # Déduplication : media_transferred doit être 0 car le checksum existe déjà
    assert report.media_transferred == 0
