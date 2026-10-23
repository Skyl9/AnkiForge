"""Banc oracle `.colpkg` adossé au moteur Anki officiel (ADR 0022 et ADR 0036).

Le fichier ne fabrique aucune archive à la main : il instancie une collection
**authentique** via ``anki.collection.Collection``, y crée des notes sur des types
standards (Basic, Cloze) et un type personnalisé, une hiérarchie de paquets, des
drapeaux, une suspension et des médias factices, puis l'exporte avec
``export_collection_package(legacy=False)`` — donc en Zstandard ``collection.anki21b``
avec table unifiée et médias, exactement comme une sauvegarde Anki 2.1.50+ / v23 / v24.

L'archive obtenue est ingérée par :class:`ImportManager` (analyse puis remplacement
atomique) sur une base AnkiForge de test. Les assertions certifient la fidélité du
contenu (notes, cartes dérivées, gabarits HTML/CSS, hiérarchie, médias, drapeaux,
suspension) **et** l'isolation du Périmètre Studio (documents, fragments RAG, personas).

``anki`` est une dépendance de **développement** uniquement : le module est chargé via
``pytest.importorskip("anki")`` et le fichier est marqué ``slow`` (exclu de la porte
rapide). Aucun appel réseau : le backend Anki est un binaire local.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    MediaModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    PersonaModel,
)
from ankiforge.services.cards.import_manager import ImportManager

pytestmark = [pytest.mark.integration, pytest.mark.slow]

CUSTOM_NOTE_TYPE = "OracleCustom"
CUSTOM_FIELDS = ["Recto", "Verso"]
CUSTOM_QFORMAT = "{{Recto}}"
CUSTOM_AFORMAT = "{{FrontSide}}<hr id=answer>{{Verso}}"
CUSTOM_CSS = ".card { color: #123456; }"

PARENT_DECK = "OracleRacine"
CHILD_DECK = "OracleRacine::Sous"

IMAGE_NAME = "oracle_img.png"
IMAGE_BYTES = b"\x89PNG\r\n\x1a\n" + b"ankiforge-colpkg-oracle-image\n"
AUDIO_NAME = "oracle_audio.mp3"
AUDIO_BYTES = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"ankiforge-colpkg-oracle-audio\n"

BASIC_CONTENT = ('<img src="oracle_img.png">Que certifie l\'oracle ?', "L'ingestion sans corruption.")
CLOZE_CONTENT = "Le {{c1::cœur}} et le {{c2::poumon}}."
CUSTOM_CONTENT = ("\\(E=mc^2\\)", "[sound:oracle_audio.mp3]Formule célèbre.")


# ---------------------------------------------------------------------------
# Fabrique d'une collection Anki officielle exportée en `.colpkg`
# ---------------------------------------------------------------------------


def _build_official_colpkg(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    """Crée une collection officielle riche puis l'exporte en ``.colpkg`` moderne.

    Retourne le chemin de l'archive et les attendus (GUID, identifiants de cartes,
    identifiant du type personnalisé) lus depuis le moteur Anki lui-même.
    """
    pytest.importorskip("anki")
    from anki.collection import Collection
    from anki.decks import DeckId

    workdir = tmp_path / "official_anki"
    workdir.mkdir(parents=True, exist_ok=True)
    col = Collection(str(workdir / "collection.anki2"))
    try:
        custom_model = col.models.new(CUSTOM_NOTE_TYPE)
        for field_name in CUSTOM_FIELDS:
            col.models.add_field(custom_model, col.models.new_field(field_name))
        template = col.models.new_template("Carte 1")
        template["qfmt"] = CUSTOM_QFORMAT
        template["afmt"] = CUSTOM_AFORMAT
        col.models.add_template(custom_model, template)
        custom_model["css"] = CUSTOM_CSS
        col.models.add(custom_model)

        basic_model = col.models.by_name("Basic")
        cloze_model = col.models.by_name("Cloze")
        assert basic_model is not None and cloze_model is not None

        child_deck_id = DeckId(col.decks.add_normal_deck_with_name(CHILD_DECK).id)
        assert col.decks.by_name(PARENT_DECK) is not None

        imported_image = col.media.write_data(IMAGE_NAME, IMAGE_BYTES)
        imported_audio = col.media.write_data(AUDIO_NAME, AUDIO_BYTES)
        assert imported_image == IMAGE_NAME
        assert imported_audio == AUDIO_NAME

        def _add_note(model: Any, field_values: list[str], tags: list[str]) -> Any:
            note = col.new_note(model)
            for index, value in enumerate(field_values):
                note.fields[index] = value
            note.tags = tags
            col.add_note(note, child_deck_id)
            return note

        basic_note = _add_note(basic_model, list(BASIC_CONTENT), ["oracle", "basic"])
        # `Back Extra` reste vide : Anki rogne les champs finaux vides à l'écriture,
        # cas nominal d'une note Cloze réelle.
        cloze_note = _add_note(cloze_model, [CLOZE_CONTENT, ""], ["oracle", "cloze"])
        custom_note = _add_note(custom_model, list(CUSTOM_CONTENT), ["oracle", "custom"])

        basic_card = basic_note.cards()[0]
        basic_card.flags = 3
        col.update_card(basic_card)
        cloze_cards = sorted(cloze_note.cards(), key=lambda card: card.ord)
        col.sched.suspend_cards([cloze_cards[1].id])

        expected: dict[str, Any] = {
            "guids": {basic_note.guid, cloze_note.guid, custom_note.guid},
            "basic_guid": basic_note.guid,
            "cloze_guid": cloze_note.guid,
            "custom_guid": custom_note.guid,
            "custom_mid": custom_model["id"],
            "suspended_ords": {1},
        }

        colpkg_path = workdir / "official_collection.colpkg"
        col.export_collection_package(out_path=str(colpkg_path), include_media=True, legacy=False)
        _assert_modern_colpkg_format(colpkg_path)
        return colpkg_path, expected
    finally:
        col.close()


def _assert_modern_colpkg_format(colpkg_path: Path) -> None:
    """Certifie que l'archive est bien une collection moderne v23/v24 (Zstd, pas legacy).

    L'export officiel embarque aussi un ``collection.anki2`` de secours : sans cette
    assertion, une régression vers ``legacy=True`` resterait invisible et l'oracle ne
    couvrirait plus le chemin ``collection.anki21b`` réellement utilisé par Anki.
    """
    with zipfile.ZipFile(colpkg_path) as archive:
        names = set(archive.namelist())
        assert "collection.anki21b" in names, "L'archive doit contenir la base Zstandard collection.anki21b"
        assert "media" in names, "L'archive doit contenir la table des médias"
        assert archive.read("media").startswith(b"\x28\xb5\x2f\xfd"), "La table des médias doit être compressée en Zstandard"


def _prepare_media_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige le dossier média de la Forge vers un dossier temporaire vide."""
    media_dir = tmp_path / "forge_media"
    media_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("ankiforge.services.cards.import_manager.get_media_dir", lambda: media_dir)
    return media_dir


def _seed_zombies_and_studio() -> dict[str, Any]:
    """Peuple un état local obsolète (Périmètre Anki) et un Périmètre Studio à préserver."""
    zombie_deck = DeckModel.create(name="Ancien Paquet")
    zombie_type = NoteTypeModel.create(name="ModeleZombie", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    zombie_note = NoteModel.create(guid="guid-colpkg-zombie", note_type=zombie_type, status="active")
    NoteVersionModel.create(
        note=zombie_note,
        version_number=1,
        content=json.dumps({"Front": "Fantôme", "Back": "À purger"}),
        source="manual",
        is_active=True,
    )
    CardModel.create(note=zombie_note, deck=zombie_deck, template_index=0)

    document = DocumentModel.create(title="Cours préservé", content="Matière du Studio", file_type="md")
    chunk = DocumentChunkModel.create(
        document=document,
        chunk_index=0,
        heading_path="Chapitre 1 > Préservation",
        page_number=1,
        content="Le Studio survit intégralement à un remplacement de collection.",
    )
    persona = PersonaModel.create(name="Persona préservée", system_prompt="Tu es un tuteur rigoureux.")

    return {
        "zombie_note_guid": zombie_note.guid,
        "zombie_type_name": zombie_type.name,
        "document_id": document.id,
        "chunk_id": chunk.id,
        "persona_id": persona.id,
    }


def _active_content(note: NoteModel) -> dict[str, str]:
    version = NoteVersionModel.get_or_none(NoteVersionModel.note == note, NoteVersionModel.is_active == True)  # noqa: E712
    assert version is not None, f"Note {note.guid} sans version active"
    parsed: dict[str, str] = json.loads(version.content)
    return parsed


# ---------------------------------------------------------------------------
# Oracle : analyse non destructive, remplacement atomique, fidélité du contenu
# ---------------------------------------------------------------------------


def test_official_colpkg_analysis_is_non_destructive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """L'analyse d'un `.colpkg` officiel n'écrit rien : la base locale reste intacte."""
    colpkg_path, expected = _build_official_colpkg(tmp_path)
    _prepare_media_dir(tmp_path, monkeypatch)
    seed = _seed_zombies_and_studio()

    analysis = ImportManager().analyze_archive(colpkg_path)
    try:
        assert analysis.source_type == "colpkg"
        assert {note["guid"] for note in analysis.new_notes} == expected["guids"]
        assert analysis.conflicts == []

        # Aucune écriture : les zombies et le Studio sont toujours là.
        assert NoteModel.get_or_none(NoteModel.guid == seed["zombie_note_guid"]) is not None
        assert DocumentModel.get_or_none(DocumentModel.id == seed["document_id"]) is not None
        assert PersonaModel.get_or_none(PersonaModel.id == seed["persona_id"]) is not None
    finally:
        analysis.cleanup()


def test_official_colpkg_replacement_purges_zombies_and_preserves_studio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le remplacement purge le Périmètre Anki obsolète et sanctuarise le Périmètre Studio."""
    colpkg_path, expected = _build_official_colpkg(tmp_path)
    _prepare_media_dir(tmp_path, monkeypatch)
    backup_calls: list[Path] = []
    backup_path = tmp_path / "ankiforge_backup_precolpkg_oracle.db"

    def _record_backup() -> Path:
        backup_calls.append(backup_path)
        return backup_path

    monkeypatch.setattr(
        "ankiforge.services.cards.import_manager.backup_before_colpkg_import",
        _record_backup,
    )
    seed = _seed_zombies_and_studio()

    manager = ImportManager()
    analysis = manager.analyze_archive(colpkg_path)
    result = manager.commit_import(analysis)

    assert backup_calls == [backup_path], "La sauvegarde de sécurité doit précéder toute écriture"
    assert result["created"] == 3
    assert result["updated"] == 0 and result["merged"] == 0
    assert result["media"] == 2

    # Purge du Périmètre Anki : plus aucune trace des cartes/notes/modèles zombies.
    assert NoteModel.get_or_none(NoteModel.guid == seed["zombie_note_guid"]) is None
    assert CardModel.select().count() == 4
    assert NoteModel.select().count() == 3
    assert NoteVersionModel.select().count() == 3
    assert NoteTypeModel.get_or_none(NoteTypeModel.name == seed["zombie_type_name"]) is None
    assert DeckModel.get_or_none(DeckModel.name == "Ancien Paquet") is None

    # Le Studio demeure strictement intact.
    assert DocumentModel.get_or_none(DocumentModel.id == seed["document_id"]) is not None
    assert DocumentChunkModel.get_or_none(DocumentChunkModel.id == seed["chunk_id"]) is not None
    assert PersonaModel.get_or_none(PersonaModel.id == seed["persona_id"]) is not None


def test_official_colpkg_content_fidelity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Notes, cartes dérivées, gabarits HTML/CSS, hiérarchie, médias et états SRS sont fidèles."""
    colpkg_path, expected = _build_official_colpkg(tmp_path)
    media_dir = _prepare_media_dir(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "ankiforge.services.cards.import_manager.backup_before_colpkg_import",
        lambda: tmp_path / "backup.db",
    )

    manager = ImportManager()
    analysis = manager.analyze_archive(colpkg_path)
    manager.commit_import(analysis)

    # GUID stables, sans doublon.
    notes = {note.guid: note for note in NoteModel.select()}
    assert set(notes) == expected["guids"]

    # Note Basic standard : contenu fidèle et carte unique.
    basic_note = notes[expected["basic_guid"]]
    basic_content = _active_content(basic_note)
    assert basic_content["Front"] == BASIC_CONTENT[0]
    assert basic_content["Back"] == BASIC_CONTENT[1]
    basic_cards = list(basic_note.cards)
    assert len(basic_cards) == 1
    assert basic_cards[0].flags == 3
    assert basic_cards[0].is_suspended is False
    assert basic_cards[0].deck.name == CHILD_DECK

    # Note Cloze standard : deux cartes dérivées de c1/c2, dont la seconde suspendue.
    cloze_note = notes[expected["cloze_guid"]]
    cloze_content = _active_content(cloze_note)
    assert cloze_content["Text"] == CLOZE_CONTENT
    assert cloze_content.get("Back Extra", "") == ""
    cloze_cards = {card.template_index: card for card in cloze_note.cards}
    assert set(cloze_cards) == {0, 1}
    assert cloze_cards[1].is_suspended is True
    assert cloze_cards[0].is_suspended is False
    assert cloze_note.tags is not None and "cloze" in json.loads(cloze_note.tags)

    # Type personnalisé : champs, gabarits HTML et CSS préservés à l'identique.
    custom_note = notes[expected["custom_guid"]]
    custom_type = custom_note.note_type
    assert custom_type is not None
    assert custom_type.name == CUSTOM_NOTE_TYPE
    assert custom_type.anki_id == expected["custom_mid"]
    assert json.loads(custom_type.fields_schema) == CUSTOM_FIELDS
    templates = json.loads(custom_type.templates)
    assert len(templates) == 1
    assert templates[0]["qfmt"] == CUSTOM_QFORMAT
    assert templates[0]["afmt"] == CUSTOM_AFORMAT
    assert custom_type.css_style.strip() == CUSTOM_CSS
    custom_content = _active_content(custom_note)
    assert custom_content["Recto"] == CUSTOM_CONTENT[0]
    assert custom_content["Verso"] == CUSTOM_CONTENT[1]

    # Types standards : champs, gabarits et CSS officiels restitués sans altération.
    basic_type = basic_note.note_type
    assert basic_type is not None and basic_type.name == "Basic"
    assert json.loads(basic_type.fields_schema) == ["Front", "Back"]
    assert "{{Front}}" in json.loads(basic_type.templates)[0]["qfmt"]
    assert "font-family: arial" in basic_type.css_style
    cloze_type = cloze_note.note_type
    assert cloze_type is not None and cloze_type.name == "Cloze"
    assert "{{cloze:Text}}" in json.loads(cloze_type.templates)[0]["qfmt"]

    # Hiérarchie des paquets : parent reconstitué, enfant rattaché.
    parent = DeckModel.get(DeckModel.name == PARENT_DECK)
    child = DeckModel.get(DeckModel.name == CHILD_DECK)
    assert child.parent_deck is not None and child.parent_deck.id == parent.id
    assert {deck.name for deck in parent.subdecks} >= {CHILD_DECK}

    # Médias : fichiers physiques identiques octet pour octet et dédupliqués en base.
    for filename, payload in ((IMAGE_NAME, IMAGE_BYTES), (AUDIO_NAME, AUDIO_BYTES)):
        imported = media_dir / filename
        assert imported.exists(), f"Média manquant : {filename}"
        assert imported.read_bytes() == payload
        checksum = hashlib.sha256(payload).hexdigest()
        assert MediaModel.get_or_none(MediaModel.checksum == checksum) is not None
