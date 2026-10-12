"""Banc oracle `.apkg` adossé au moteur Anki officiel (ADR 0022).

Vérifie que les paquets produits par :class:`ExportManager` s'ouvrent **sans corruption**
dans le backend Anki officiel et restituent **fidèlement le contenu** : comptes notes/cartes,
types de note (champs, gabarits, CSS), hiérarchie des paquets, `guid` stables, médias
identiques (MD5), drapeaux 1-7 et suspension, balisage KaTeX ; et que l'import
**n'altère pas** une carte existante non modifiée.

L'oracle `anki` est une dépendance de **développement** uniquement. Les tests qui en
dépendent appellent ``pytest.importorskip("anki")`` : en son absence ils sont ignorés
proprement. Le fichier est marqué ``slow`` (exclu de la porte rapide).
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
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.cards.export_manager import ExportManager
from ankiforge.services.cards.import_manager import ImportManager

pytestmark = [pytest.mark.integration, pytest.mark.slow]

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "anki_oracle"
WITNESS_APKG = FIXTURES_DIR / "witness.apkg"
WITNESS_MEDIA_NAME = "witness.png"
WITNESS_MEDIA_BYTES = b"\x89PNG\r\n\x1a\n" + b"ankiforge-oracle-witness\n"
WITNESS_MEDIA_MD5 = hashlib.md5(WITNESS_MEDIA_BYTES).hexdigest()

# Fabrique d'une collection Forge exportable.
MEDIA_NAME = "oracle_img.png"
MEDIA_BYTES = b"\x89PNG\r\n\x1a\n" + b"ankiforge-forge-media\n"

BASIC_FIELDS = ["Recto", "Verso"]
BASIC_TEMPLATES = [{"name": "Carte 1", "qfmt": "{{Recto}}", "afmt": "{{FrontSide}}<hr id=answer>{{Verso}}"}]
BASIC_CSS = ".card { color: #123456; }"
CLOZE_FIELDS = ["Texte"]
CLOZE_TEMPLATES = [{"name": "Cloze", "qfmt": "{{cloze:Texte}}", "afmt": "{{cloze:Texte}}"}]
CLOZE_CSS = ".cloze { font-weight: bold; }"

GUID_BASIC = "forge-oracle-basic"
GUID_CLOZE = "forge-oracle-cloze"
GUID_KATEX = "forge-oracle-katex"


# ---------------------------------------------------------------------------
# Oracle : ouverture headless de la lib `anki`
# ---------------------------------------------------------------------------


def _open_imported_collection(apkg_path: Path, workdir: Path) -> Any:
    """Importe le paquet dans une collection neuve via le contrat officiel d'import.

    ``with_scheduling`` est activé : c'est la seule voie par laquelle le moteur Anki
    matérialise les drapeaux 1-7 et la suspension portés par les cartes du paquet.
    """
    pytest.importorskip("anki")
    from anki.collection import Collection, ImportAnkiPackageOptions, ImportAnkiPackageRequest

    workdir.mkdir(parents=True, exist_ok=True)
    col = Collection(str(workdir / "collection.anki2"))
    col.import_anki_package(
        ImportAnkiPackageRequest(
            package_path=str(apkg_path),
            options=ImportAnkiPackageOptions(with_scheduling=True),
        )
    )
    return col


def _open_package_collection(apkg_path: Path, workdir: Path) -> Any:
    """Ouvre directement la collection embarquée dans le paquet (voie d'ouverture Anki)."""
    pytest.importorskip("anki")
    from anki.collection import Collection

    workdir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apkg_path) as archive:
        archive.extract("collection.anki2", workdir)
    return Collection(str(workdir / "collection.anki2"))


def _models_by_name(col: Any) -> dict[str, dict[str, Any]]:
    models = col.models.all()
    if isinstance(models, dict):
        models = list(models.values())
    return {model["name"]: model for model in models}


def _notes_by_guid(col: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for note_id in col.find_notes(""):
        note = col.get_note(note_id)
        result[note.guid] = note
    return result


def _deck_names(col: Any) -> set[str]:
    return {deck["name"] for deck in col.decks.all()}


def _md5_of(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Fabrique d'une collection Forge exportable
# ---------------------------------------------------------------------------


def _prepare_media_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige le dossier média de la Forge vers un dossier temporaire peuplé."""
    media_dir = tmp_path / "forge_media"
    media_dir.mkdir(parents=True, exist_ok=True)
    (media_dir / MEDIA_NAME).write_bytes(MEDIA_BYTES)
    monkeypatch.setattr("ankiforge.services.cards.export_manager.get_media_dir", lambda: media_dir)
    monkeypatch.setattr("ankiforge.services.cards.import_manager.get_media_dir", lambda: media_dir)
    return media_dir


def _build_forge_collection() -> dict[str, Any]:
    """Peuple la base Forge d'un jeu déterministe couvrant tous les invariants."""
    deck_sub = DeckModel.create(name="OracleRacine::Sous")
    note_types = {
        "basic": NoteTypeModel.create(
            name="OracleBasic",
            fields_schema=json.dumps(BASIC_FIELDS),
            templates=json.dumps(BASIC_TEMPLATES),
            css_style=BASIC_CSS,
        ),
        "cloze": NoteTypeModel.create(
            name="OracleCloze",
            fields_schema=json.dumps(CLOZE_FIELDS),
            templates=json.dumps(CLOZE_TEMPLATES),
            css_style=CLOZE_CSS,
        ),
    }

    basic = NoteModel.create(guid=GUID_BASIC, note_type=note_types["basic"], tags=json.dumps(["oracle", "basic"]), status="new")
    NoteVersionModel.create(
        note=basic,
        content=json.dumps({"Recto": f'<img src="{MEDIA_NAME}">Que teste l\'oracle ?', "Verso": "L'ouverture sans corruption."}),
        source="manual",
        is_active=True,
    )
    CardModel.create(note=basic, deck=deck_sub, template_index=0, flags=3, is_suspended=False)

    cloze = NoteModel.create(guid=GUID_CLOZE, note_type=note_types["cloze"], tags=json.dumps(["oracle", "cloze"]), status="new")
    NoteVersionModel.create(
        note=cloze,
        content=json.dumps({"Texte": "Le {{c1::cœur}} et le {{c2::poumon}}."}),
        source="manual",
        is_active=True,
    )
    CardModel.create(note=cloze, deck=deck_sub, template_index=0, flags=0, is_suspended=True)
    CardModel.create(note=cloze, deck=deck_sub, template_index=1, flags=0, is_suspended=False)

    katex = NoteModel.create(guid=GUID_KATEX, note_type=note_types["basic"], tags=json.dumps(["oracle", "katex"]), status="new")
    NoteVersionModel.create(
        note=katex,
        content=json.dumps({"Recto": "\\(E=mc^2\\)", "Verso": "Formule \\(\\int x\\,dx\\) et \\[\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}\\]"}),
        source="manual",
        is_active=True,
    )
    CardModel.create(note=katex, deck=deck_sub, template_index=0, flags=5, is_suspended=False)

    return {"deck_sub": deck_sub, "basic": basic, "cloze": cloze, "katex": katex}


# ---------------------------------------------------------------------------
# Banc oracle : ouverture, intégrité, fidélité de contenu
# ---------------------------------------------------------------------------


def test_witness_fixture_is_versioned() -> None:
    """La fixture témoin versionnée doit exister pour que l'oracle soit reproductible."""
    assert WITNESS_APKG.exists(), f"Fixture oracle manquante : {WITNESS_APKG}. Régénérer via script/generate_anki_oracle_fixture.py"


def test_witness_fixture_opens_in_official_anki(tmp_path: Path) -> None:
    """La collection témoin versionnée s'ouvre sans corruption dans le moteur officiel."""
    col = _open_imported_collection(WITNESS_APKG, tmp_path / "oracle_witness")
    try:
        assert col.db.scalar("pragma integrity_check") == "ok"
        assert col.note_count() == 3
        assert col.card_count() == 4

        notes = _notes_by_guid(col)
        assert {"oracle-witness-basic", "oracle-witness-cloze", "oracle-witness-katex"} <= set(notes)

        assert notes["oracle-witness-basic"].cards()[0].flags == 2
        assert any(card.queue == -1 for card in notes["oracle-witness-cloze"].cards())
        assert notes["oracle-witness-katex"].cards()[0].flags == 4
        assert "\\(E=mc^2\\)" in notes["oracle-witness-katex"].fields[0]

        imported = Path(col.media.dir()) / WITNESS_MEDIA_NAME
        assert imported.exists()
        assert _md5_of(imported) == WITNESS_MEDIA_MD5
    finally:
        col.close()


def test_forge_apkg_opens_without_corruption(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un `.apkg` produit par la Forge s'ouvre et passe le contrôle d'intégrité sans réparation."""
    _prepare_media_dir(tmp_path, monkeypatch)
    _build_forge_collection()

    apkg = tmp_path / "forge.apkg"
    ExportManager().export_package(output_path=apkg, deck_id=None, include_media=True)
    assert apkg.exists()

    # Ouverture directe de la collection embarquée par le moteur officiel.
    col = _open_package_collection(apkg, tmp_path / "oracle_integrity")
    try:
        # Contrôle d'intégrité SQLite non réparateur.
        assert col.db.scalar("pragma integrity_check") == "ok"
        assert col.note_count() == 3
        assert col.card_count() == 4
    finally:
        col.close()


def test_forge_apkg_content_fidelity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Comptes, types de note, hiérarchie, guid, médias, drapeaux et KaTeX sont fidèles."""
    _prepare_media_dir(tmp_path, monkeypatch)
    _build_forge_collection()

    apkg = tmp_path / "forge_fidelity.apkg"
    ExportManager().export_package(output_path=apkg, deck_id=None, include_media=True)

    col = _open_imported_collection(apkg, tmp_path / "oracle_fidelity")
    try:
        # Comptes exacts : 3 notes ; le cloze c1/c2 dérive 2 cartes -> 4 cartes.
        assert col.note_count() == 3
        assert col.card_count() == 4

        # Types de note : champs, gabarits et CSS préservés.
        models = _models_by_name(col)
        assert "OracleBasic" in models and "OracleCloze" in models
        basic_model = models["OracleBasic"]
        assert [f["name"] for f in basic_model["flds"]] == BASIC_FIELDS
        assert [t["name"] for t in basic_model["tmpls"]] == ["Carte 1"]
        assert "{{Recto}}" in basic_model["tmpls"][0]["qfmt"]
        assert "{{FrontSide}}" in basic_model["tmpls"][0]["afmt"]
        assert "#123456" in basic_model["css"]
        assert models["OracleCloze"]["type"] == 1  # 1 = cloze

        # Hiérarchie des paquets (le parent est reconstitué par Anki).
        assert {"OracleRacine", "OracleRacine::Sous"} <= _deck_names(col)

        # `guid` stables et sans doublon.
        notes = _notes_by_guid(col)
        assert set(notes) == {GUID_BASIC, GUID_CLOZE, GUID_KATEX}
        assert len(notes) == col.note_count()

        # Média lié, identique octet pour octet (MD5).
        imported_media = Path(col.media.dir()) / MEDIA_NAME
        assert imported_media.exists()
        assert _md5_of(imported_media) == hashlib.md5(MEDIA_BYTES).hexdigest()

        # Drapeaux 1-7 et suspension reportés fidèlement.
        assert notes[GUID_BASIC].cards()[0].flags == 3
        assert notes[GUID_KATEX].cards()[0].flags == 5
        cloze_cards = {card.ord: card for card in notes[GUID_CLOZE].cards()}
        assert set(cloze_cards) == {0, 1}
        assert cloze_cards[0].queue == -1
        assert cloze_cards[1].queue != -1

        # KaTeX : balisage `\(...\)` (inline) et `\[...\]` (display) non corrompus.
        assert "\\(E=mc^2\\)" in notes[GUID_KATEX].fields[0]
        assert "\\(\\int x\\,dx\\)" in notes[GUID_KATEX].fields[1]
        assert "\\[\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}\\]" in notes[GUID_KATEX].fields[1]
    finally:
        col.close()


# ---------------------------------------------------------------------------
# Non-mutation : un import n'altère pas une carte existante non modifiée
# ---------------------------------------------------------------------------


def _snapshot_note(note_id: int) -> dict[str, Any]:
    note = NoteModel.get_by_id(note_id)
    active = NoteVersionModel.get_or_none(NoteVersionModel.note == note, is_active=True)
    cards = sorted(note.cards, key=lambda c: c.template_index)
    return {
        "guid": note.guid,
        "content": active.content if active else None,
        "versions": NoteVersionModel.select().where(NoteVersionModel.note == note).count(),
        "cards": [
            {
                "ord": card.template_index,
                "deck": card.deck.name if card.deck else None,
                "flags": card.flags,
                "suspended": card.is_suspended,
            }
            for card in cards
        ],
    }


@pytest.mark.parametrize(
    "options",
    [
        {"status_filter": "all", "sync": True, "media": True, "override_target": True, "resolutions": None},
        {"status_filter": "all", "sync": False, "media": False, "override_target": False, "resolutions": {}},
        {"status_filter": "new", "sync": True, "media": False, "override_target": False, "resolutions": None},
        {"status_filter": "new", "sync": False, "media": True, "override_target": True, "resolutions": {}},
    ],
)
def test_import_does_not_mutate_existing_card(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, options: dict[str, Any]) -> None:
    """Sous paramètres d'export et d'import variés, une carte existante reste intacte."""
    _prepare_media_dir(tmp_path, monkeypatch)
    _build_forge_collection()

    apkg = tmp_path / "forge_roundtrip.apkg"
    ExportManager().export_package(
        output_path=apkg,
        deck_id=None,
        status_filter=options["status_filter"],
        include_media=options["media"],
        sync_flags_and_suspension_tags=options["sync"],
    )

    # Note existante non modifiée (identique au paquet) + note totalement étrangère.
    existing_basic = NoteModel.get(NoteModel.guid == GUID_BASIC)
    existing_deck = DeckModel.create(name="Existant")
    unrelated_type = NoteTypeModel.create(
        name="ExistantType",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps(BASIC_TEMPLATES),
        css_style="",
    )
    unrelated = NoteModel.create(guid="unrelated-guid", note_type=unrelated_type, tags=json.dumps(["keep"]), status="new")
    NoteVersionModel.create(note=unrelated, content=json.dumps({"Front": "Intact", "Back": "Inchangé"}), source="manual", is_active=True)
    CardModel.create(note=unrelated, deck=existing_deck, template_index=0, flags=5, is_suspended=True)

    before_identical = _snapshot_note(existing_basic.id)
    before_unrelated = _snapshot_note(unrelated.id)

    manager = ImportManager()
    analysis = manager.analyze_archive(apkg)
    try:
        target_deck = DeckModel.get(DeckModel.name == "Existant") if options["override_target"] else None
        manager.commit_import(
            analysis,
            conflict_resolutions=options["resolutions"],
            target_deck_id=target_deck.id if target_deck else None,
        )
    finally:
        analysis.cleanup()

    # Une note identique à sa contrepartie du paquet n'est pas modifiée.
    assert _snapshot_note(existing_basic.id) == before_identical
    # Une note étrangère au paquet est totalement épargnée.
    assert _snapshot_note(unrelated.id) == before_unrelated
