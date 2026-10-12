#!/usr/bin/env python3
"""Génère la fixture témoin `.apkg` du banc oracle Anki (ADR 0022).

La fixture est versionnée sous `tests/fixtures/anki_oracle/witness.apkg` et ouverte par
l'oracle (`tests/integration/test_anki_export_oracle.py`) : elle garantit qu'un paquet
`.apkg` connu, hors-ligne et déterministe en contenu, s'ouvre sans corruption dans le
moteur Anki officiel, indépendamment de toute génération Forge.

Régénération :

    uv run python script/generate_anki_oracle_fixture.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import genanki

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "anki_oracle"
FIXTURE_PATH = FIXTURE_DIR / "witness.apkg"

# Contenu médiatique déterministe : l'oracle en vérifie le MD5 après import.
WITNESS_MEDIA_NAME = "witness.png"
WITNESS_MEDIA_BYTES = b"\x89PNG\r\n\x1a\n" + b"ankiforge-oracle-witness\n"

BASIC_MODEL_ID = 1000000001
CLOZE_MODEL_ID = 1000000002
DECK_ID = 1000000003


class WitnessCard(genanki.Card):
    """Carte genanki préservant le drapeau Anki (1-7) comme `AnkiForgeCard`.

    La duplication volontaire de ``write_to_db`` garantit l'**indépendance** de la
    fixture témoin vis-à-vis du code sous test (`AnkiForgeCard`) : l'oracle valide un
    paquet dont la fabrication ne dépend pas de l'export de la Forge.
    """

    def __init__(self, ord: int, suspend: bool = False, flags: int = 0) -> None:
        super().__init__(ord=ord, suspend=suspend)
        self.flags = flags

    def write_to_db(self, cursor: Any, timestamp: float, deck_id: int, note_id: int, id_gen: Any, due: int = 0) -> None:
        queue = -1 if self.suspend else 0
        cursor.execute(
            "INSERT INTO cards VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);",
            (
                next(id_gen),
                note_id,
                deck_id,
                self.ord,
                int(timestamp),
                -1,
                0,
                queue,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                int(getattr(self, "flags", 0) or 0),
                "",
            ),
        )


def _basic_model() -> genanki.Model:
    return genanki.Model(
        model_id=BASIC_MODEL_ID,
        name="OracleTémoin",
        fields=[{"name": "Recto"}, {"name": "Verso"}],
        templates=[
            {
                "name": "Carte 1",
                "qfmt": "{{Recto}}",
                "afmt": "{{FrontSide}}<hr id=answer>{{Verso}}",
            }
        ],
        css=".card { font-family: sans-serif; }",
    )


def _cloze_model() -> genanki.Model:
    return genanki.Model(
        model_id=CLOZE_MODEL_ID,
        name="OracleTémoinCloze",
        fields=[{"name": "Texte"}],
        templates=[
            {
                "name": "Cloze",
                "qfmt": "{{cloze:Texte}}",
                "afmt": "{{cloze:Texte}}",
            }
        ],
        css=".cloze { font-weight: bold; }",
        model_type=genanki.Model.CLOZE,
    )


def _force_cards(note: genanki.Note, flags: dict[int, int], suspended: set[int]) -> None:
    """Réécrit les cartes de la note avec drapeaux et suspension explicites (mêmes `ord`)."""
    note.cards = [WitnessCard(ord=card.ord, suspend=card.ord in suspended, flags=flags.get(card.ord, 0)) for card in note.cards]


def build_package() -> genanki.Package:
    """Construit le paquet témoin complet (drapeaux, suspension, média)."""
    basic = _basic_model()
    cloze = _cloze_model()

    deck = genanki.Deck(deck_id=DECK_ID, name="Témoin::Sous")

    basic_note = genanki.Note(
        model=basic,
        fields=['<img src="witness.png">Que teste l\'oracle ?', "L'ouverture sans corruption et la fidélité."],
        guid="oracle-witness-basic",
        tags=["oracle", "temoin"],
    )
    _force_cards(basic_note, flags={0: 2}, suspended=set())

    cloze_note = genanki.Note(
        model=cloze,
        fields=["Le {{c1::guid}} est {{c2::durable}}."],
        guid="oracle-witness-cloze",
        tags=["oracle"],
    )
    _force_cards(cloze_note, flags={}, suspended={0})

    katex_note = genanki.Note(
        model=basic,
        fields=["Equation \\(E=mc^2\\)", "Formule \\(\\int x\\,dx\\)"],
        guid="oracle-witness-katex",
        tags=["oracle", "katex"],
    )
    _force_cards(katex_note, flags={0: 4}, suspended=set())

    deck.add_note(basic_note)
    deck.add_note(cloze_note)
    deck.add_note(katex_note)

    package = genanki.Package([deck])
    package.media_files = [str(FIXTURE_DIR / WITNESS_MEDIA_NAME)]
    return package


def main() -> int:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    media_file = FIXTURE_DIR / WITNESS_MEDIA_NAME
    media_file.write_bytes(WITNESS_MEDIA_BYTES)
    try:
        build_package().write_to_file(str(FIXTURE_PATH))
    finally:
        # La fixture média n'est pas versionnée : seul le paquet l'embarque.
        media_file.unlink(missing_ok=True)

    print(f"Fixture oracle générée : {FIXTURE_PATH} ({FIXTURE_PATH.stat().st_size} octets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
