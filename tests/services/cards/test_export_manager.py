import pytest
import json
from unittest.mock import patch

from ankiforge.database.models import DeckModel, NoteTypeModel, NoteModel, CardModel, NoteVersionModel
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
