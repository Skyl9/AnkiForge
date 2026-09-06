import json
from unittest.mock import patch

import pytest

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.services.cards.export_manager import ExportManager


def test_generate_stable_id():
    manager = ExportManager()
    id1 = manager.generate_stable_id("Mon Paquet")
    id2 = manager.generate_stable_id("Mon Paquet")
    id3 = manager.generate_stable_id("Autre Paquet")

    assert id1 == id2, "Le hachage doit être déterministe."
    assert id1 != id3
    assert isinstance(id1, int)


@pytest.mark.integration
@patch("genanki.Package.write_to_file")
@patch("ankiforge.services.cards.export_manager.get_media_dir")
def test_export_deck(mock_get_dir, mock_write, tmp_path):
    """Vérifie l'export global en créant de vraies fausses données dans la DB RAM."""
    mock_get_dir.return_value = tmp_path
    manager = ExportManager()

    # 1. On peuple la base en mémoire (automatiquement fraîche grâce au conftest.py)
    parent_deck = DeckModel.create(name="Langues")
    sub_deck = DeckModel.create(name="Langues::Anglais", parent_deck=parent_deck)

    nt = NoteTypeModel.create(
        name="Basique",
        fields_schema='["Recto", "Verso"]',
        templates='[{"name": "Carte 1", "qfmt": "{{Recto}}", "afmt": "{{Verso}}"}]',
        css_style=".card { color: red; }",
    )

    note = NoteModel.create(guid="12345", note_type=nt, tags='["Test"]')
    NoteVersionModel.create(note=note, content=json.dumps({"Recto": "Hello", "Verso": "Bonjour <img src='test.png'>"}), is_active=True)
    CardModel.create(note=note, deck=sub_deck)

    # On simule la présence d'une image
    if not (tmp_path / "media").exists():
        (tmp_path / "media").mkdir()
    (tmp_path / "media" / "test.png").write_text("fake img")

    # 2. Exécution de l'exportation
    export_path = tmp_path / "export.apkg"
    manager.export_deck(parent_deck.id, export_path)

    # 3. Vérifications
    assert mock_write.called, "genanki n'a pas été appelé pour écrire le fichier."

    # On récupère le Package genanki passé en argument du mock pour vérifier son contenu
    package_args = mock_write.call_args
    # On sait que l'ExportManager passe l'export_path en argument
    assert str(export_path) in package_args[0]


@pytest.mark.integration
def test_export_package_real_file_and_cloze_auto_healing(tmp_path):
    """Vérifie la génération réelle d'un .apkg sans mock, avec auto-guérison de fields_schema='[]' et Cloze."""
    import sqlite3
    import zipfile

    deck = DeckModel.create(name="Médecine")
    nt = NoteTypeModel.create(
        name="Texte à trous spécial",
        fields_schema="[]",
        templates="[]",
        css_style=".cloze { font-weight: bold; }",
    )

    note = NoteModel.create(guid="cloze_guid_999", note_type=nt, tags='["medecine"]')
    content = {
        "Field_1": "Le muscle {{c1::biceps brachial}} s'insère sur la {{c2::tubérosité radiale}}.",
        "Field_2": "Remarque anatomique importante",
    }
    NoteVersionModel.create(note=note, content=json.dumps(content), is_active=True)
    CardModel.create(note=note, deck=deck, flags=3)

    manager = ExportManager()
    output_apkg = tmp_path / "test_medecine.apkg"

    count = manager.export_package(
        output_path=output_apkg,
        deck_id=deck.id,
        status_filter="all",
        include_media=False,
    )

    assert count == 1
    assert output_apkg.exists()
    assert output_apkg.stat().st_size > 0

    # Vérification du contenu du fichier .apkg (archive zip valide)
    with zipfile.ZipFile(output_apkg, "r") as zf:
        namelist = zf.namelist()
        assert "collection.anki2" in namelist

        # Extraction et inspection directe de la base Anki générée
        extracted_db = tmp_path / "collection.anki2"
        zf.extract("collection.anki2", tmp_path)

        conn = sqlite3.connect(extracted_db)
        cursor = conn.cursor()

        cursor.execute("SELECT count(*) FROM notes")
        notes_in_db = cursor.fetchone()[0]
        assert notes_in_db == 1

        cursor.execute("SELECT count(*) FROM cards")
        cards_in_db = cursor.fetchone()[0]
        # Le texte cloze contient c1 et c2 -> genanki doit avoir généré exactement 2 cartes
        assert cards_in_db == 2

        # Vérification du flag préservé
        cursor.execute("SELECT flags FROM cards")
        flags = [r[0] for r in cursor.fetchall()]
        assert 3 in flags

        conn.close()

    # Vérification de l'auto-guérison de la BDD
    refreshed_nt = NoteTypeModel.get_by_id(nt.id)
    assert refreshed_nt.fields_schema != "[]"
    parsed_fields = json.loads(refreshed_nt.fields_schema)
    assert "Field_1" in parsed_fields
    assert "Field_2" in parsed_fields
